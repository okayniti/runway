"""
Inference entry point for the Bi-LSTM cash-flow forecaster.

Loads a trained checkpoint and produces, for each input window, both the
horizon-length cash-position forecast and a confidence score describing how
much that forecast should be trusted (see confidence.py). Callers should
always get a (forecast, confidence) pair back — never bare numbers — so
downstream consumers (API, agent layer) can't accidentally treat an
unreliable forecast as a solid one.

Usage:
    python model/infer.py --data-csv data/synthetic_transactions.csv
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch

try:
    from .confidence import ConfidenceBreakdown, score_window_confidence
    from .dataset import TARGET_COLUMN, build_daily_features
    from .model import BiLSTMForecaster
except ImportError:  # running as `python model/infer.py`, not `-m model.infer`
    from confidence import ConfidenceBreakdown, score_window_confidence
    from dataset import TARGET_COLUMN, build_daily_features
    from model import BiLSTMForecaster


@dataclass
class ForecastResult:
    """A forecast paired with its confidence — the only shape inference calls return."""

    forecast: np.ndarray  # shape (horizon,): predicted cash_position per day
    confidence: ConfidenceBreakdown


class CashFlowForecaster:
    """Wraps a trained checkpoint for inference with attached confidence scoring."""

    def __init__(self, checkpoint_path: str | Path, device: str | None = None):
        """Load a checkpoint (model weights, config, normalization stats,
        recorded test metrics) and rebuild the model ready for inference."""
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        config = checkpoint["config"]

        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model = BiLSTMForecaster(
            input_size=config["input_size"],
            horizon=config["horizon"],
            hidden_size=config["hidden_size"],
            num_layers=config["num_layers"],
            dropout=config["dropout"],
        ).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

        self.lookback = config["lookback"]
        self.horizon = config["horizon"]
        self.feature_columns = config["feature_columns"]

        self.x_mean = checkpoint["x_mean"]
        self.x_std = checkpoint["x_std"]
        self.y_mean = checkpoint["y_mean"]
        self.y_std = checkpoint["y_std"]
        self.test_metrics = checkpoint["test_metrics"]

        # Representative scale for turning the recorded test RMSE into a
        # relative error inside the confidence score.
        self.typical_scale = float(np.mean(np.abs(self.y_mean)))

    def predict_window(
        self,
        feature_window: np.ndarray,
        baseline_cash_position: float,
        observed_days: int | None = None,
    ) -> ForecastResult:
        """Forecast the next `horizon` days of absolute cash position from
        one (lookback, num_features) window.

        The model is trained to predict the *change* in cash position over
        the horizon, not the raw cumulative value (see model/dataset.py's
        module docstring for why). `baseline_cash_position` — the actual
        cash_position on this window's last day — is added back onto the
        model's output here, so every caller of this method always gets an
        absolute cash_position forecast, matching what the rest of the
        pipeline (risk checks, the API schema, the dashboard) expects.

        `observed_days` lets a caller flag that only part of the window is
        backed by real transaction data (e.g. a business with less history
        than `lookback`, zero-padded to fit) — defaults to the full lookback
        when not given.
        """
        expected_shape = (self.lookback, len(self.feature_columns))
        if feature_window.shape != expected_shape:
            raise ValueError(f"expected feature_window shape {expected_shape}, got {feature_window.shape}")
        observed_days = self.lookback if observed_days is None else observed_days

        normalized = (feature_window - self.x_mean[0]) / self.x_std[0]
        input_tensor = torch.from_numpy(normalized.astype(np.float32)).unsqueeze(0).to(self.device)

        with torch.no_grad():
            pred_norm = self.model(input_tensor).cpu().numpy()[0]
        forecast_delta = pred_norm * self.y_std[0] + self.y_mean[0]
        forecast = forecast_delta + baseline_cash_position

        net_flow_idx = self.feature_columns.index("net_flow")
        net_flow_window = feature_window[:, net_flow_idx]

        confidence = score_window_confidence(
            net_flow_window=net_flow_window,
            observed_days=observed_days,
            lookback=self.lookback,
            test_rmse=self.test_metrics["rmse"],
            typical_scale=self.typical_scale,
        )

        return ForecastResult(forecast=forecast, confidence=confidence)

    def predict_from_dataframe(self, transactions: pd.DataFrame) -> ForecastResult:
        """Build daily features from a raw transaction ledger already in
        memory and forecast from its most recent `lookback` days.

        If fewer than `lookback` days of history exist, the window is
        zero-padded on the left and `observed_days` is set accordingly, so
        the confidence score reflects the thin history rather than the
        model silently pretending it saw a full window.
        """
        daily = build_daily_features(transactions)
        baseline_cash_position = float(daily[TARGET_COLUMN].iloc[-1])

        if len(daily) < self.lookback:
            observed_days = len(daily)
            feature_window = np.zeros((self.lookback, len(self.feature_columns)), dtype=np.float32)
            recent = daily[self.feature_columns].to_numpy(dtype=np.float32)
            feature_window[-observed_days:] = recent
        else:
            observed_days = self.lookback
            feature_window = daily[self.feature_columns].to_numpy(dtype=np.float32)[-self.lookback :]

        return self.predict_window(
            feature_window, baseline_cash_position=baseline_cash_position, observed_days=observed_days
        )

    def predict_from_transactions(self, transactions_csv: str | Path) -> ForecastResult:
        """Convenience path: read a transaction ledger CSV from disk and
        forecast from it. See predict_from_dataframe for the in-memory
        equivalent (used by the API layer, which already has parsed
        transactions and shouldn't round-trip them through a file)."""
        return self.predict_from_dataframe(pd.read_csv(transactions_csv))


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description="Run inference with the trained cash-flow forecaster.")
    parser.add_argument("--data-csv", default=str(project_root / "data" / "synthetic_transactions.csv"))
    parser.add_argument(
        "--checkpoint", default=str(Path(__file__).resolve().parent / "checkpoints" / "bilstm_cashflow.pt")
    )
    args = parser.parse_args()

    forecaster = CashFlowForecaster(args.checkpoint)
    result = forecaster.predict_from_transactions(args.data_csv)

    print("14-day cash position forecast:")
    for day_idx, value in enumerate(result.forecast, start=1):
        print(f"  day {day_idx:2d}: {value:,.2f}")

    confidence = result.confidence
    print(f"\nconfidence: {confidence.score:.2f} ({'LOW' if confidence.is_low_confidence else 'OK'})")
    print(
        f"  history_completeness={confidence.history_completeness:.2f} "
        f"volatility_score={confidence.volatility_score:.2f} "
        f"model_error_score={confidence.model_error_score:.2f}"
    )
    for reason in confidence.reasons:
        print(f"  - {reason}")


if __name__ == "__main__":
    main()
