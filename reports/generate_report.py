"""
Batch exception report generator for the cash-flow forecaster.

Runs the trained model across a batch of forecast windows — one per as-of
date, stepping backward day by day from the most recent day in the
ledger — and writes a markdown report combining:

1. Overall forecast accuracy on held-out data: the RMSE/MAE/R2 recorded in
   the model checkpoint at training time, against its own chronological
   test split. This is *not* recomputed against the batch here, because
   the batch is unlabeled — there's no future ground truth yet to score
   against. It's the model's known historical reliability, reported
   alongside what actually happened when it was run across the batch.
2. Every low-confidence window in the batch, with the specific reasons
   attached (see model/confidence.py).
3. Every window the pipeline explicitly could not forecast — most
   commonly an as-of date too early in the ledger to have `lookback` days
   of history behind it — captured and reported by date and reason rather
   than silently skipped.

Usage:
    python reports/generate_report.py --data-csv data/synthetic_transactions.csv --num-windows 30
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.dataset import TARGET_COLUMN, build_daily_features  # noqa: E402
from model.infer import CashFlowForecaster  # noqa: E402


@dataclass
class WindowReport:
    """One successfully forecast window's confidence outcome, for one as-of date."""

    as_of_date: pd.Timestamp
    confidence_score: float
    is_low_confidence: bool
    reasons: list[str]


@dataclass
class FailedWindow:
    """One as-of date the pipeline could not forecast, and why (as_of_date
    is None only when the offset itself falls before the start of the ledger)."""

    as_of_date: pd.Timestamp | None
    reason: str


def run_batch(
    forecaster: CashFlowForecaster, daily: pd.DataFrame, num_windows: int
) -> tuple[list[WindowReport], list[FailedWindow]]:
    """Run the forecaster once per as-of date, stepping backward one day at
    a time from the most recent date in `daily`, for up to `num_windows`
    windows (fewer if the ledger doesn't go back that far).
    """
    reports: list[WindowReport] = []
    failures: list[FailedWindow] = []

    total_days = len(daily)
    lookback = forecaster.lookback

    for offset in range(num_windows):
        window_end = total_days - offset
        if window_end <= 0:
            failures.append(
                FailedWindow(as_of_date=None, reason=f"offset {offset} is before the start of the ledger")
            )
            continue

        as_of_date = daily["date"].iloc[window_end - 1]
        window_start = window_end - lookback

        if window_start < 0:
            failures.append(
                FailedWindow(
                    as_of_date=as_of_date,
                    reason=(
                        f"only {window_end} day(s) of history available as of this date, "
                        f"need {lookback} for a full lookback window"
                    ),
                )
            )
            continue

        feature_window = daily[forecaster.feature_columns].to_numpy(dtype=np.float32)[window_start:window_end]
        baseline_cash_position = float(daily[TARGET_COLUMN].iloc[window_end - 1])

        try:
            result = forecaster.predict_window(
                feature_window, baseline_cash_position=baseline_cash_position, observed_days=lookback
            )
        except Exception as exc:  # noqa: BLE001 - report any pipeline failure, not just expected ones
            failures.append(FailedWindow(as_of_date=as_of_date, reason=str(exc)))
            continue

        reports.append(
            WindowReport(
                as_of_date=as_of_date,
                confidence_score=result.confidence.score,
                is_low_confidence=result.confidence.is_low_confidence,
                reasons=result.confidence.reasons,
            )
        )

    return reports, failures


def render_markdown(
    data_csv: Path,
    checkpoint_path: Path,
    test_metrics: dict,
    window_reports: list[WindowReport],
    failed_windows: list[FailedWindow],
) -> str:
    """Render the exception report as a markdown string: recorded held-out
    accuracy, a batch summary, every low-confidence window, and every
    window the pipeline could not forecast."""
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    num_windows = len(window_reports) + len(failed_windows)
    low_confidence = [w for w in window_reports if w.is_low_confidence]

    lines = [
        "# Cash-Flow Forecast Exception Report",
        "",
        f"Generated: {generated_at}",
        f"Data source: `{data_csv}`",
        f"Model checkpoint: `{checkpoint_path}`",
        "",
        "## Overall forecast accuracy (held-out test data)",
        "",
        "Recorded when the model was last trained, against its own chronological "
        "held-out test split — not recomputed against this batch, which has no "
        "ground truth to score against yet.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| RMSE | {test_metrics['rmse']:,.2f} |",
        f"| MAE | {test_metrics['mae']:,.2f} |",
        f"| R2 | {test_metrics['r2']:.4f} |",
        "",
        "## Batch summary",
        "",
        f"- Windows requested: {num_windows}",
        f"- Windows forecast successfully: {len(window_reports)}",
        f"- Low-confidence windows: {len(low_confidence)} / {len(window_reports)}",
        f"- Windows that could not be forecast: {len(failed_windows)}",
        "",
        "## Low-confidence windows",
        "",
    ]

    if low_confidence:
        for window in sorted(low_confidence, key=lambda w: w.as_of_date):
            reason_text = "; ".join(window.reasons) if window.reasons else "no specific reason recorded"
            lines.append(
                f"- **{window.as_of_date.date()}** — confidence {window.confidence_score:.2f}: {reason_text}"
            )
    else:
        lines.append("None — every forecast window in this batch met the confidence threshold.")
    lines.append("")

    lines.append("## Windows that could not be forecast reliably")
    lines.append("")
    if failed_windows:
        for failure in sorted(failed_windows, key=lambda w: (w.as_of_date is None, w.as_of_date)):
            label = failure.as_of_date.date() if failure.as_of_date is not None else "unknown date"
            lines.append(f"- **{label}** — {failure.reason}")
    else:
        lines.append("None.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """CLI entry point: run a batch of forecasts and write the markdown
    exception report to --output-dir. See module docstring for usage."""
    parser = argparse.ArgumentParser(
        description="Generate a batch exception report for the cash-flow forecaster."
    )
    parser.add_argument("--data-csv", default=str(PROJECT_ROOT / "data" / "synthetic_transactions.csv"))
    parser.add_argument(
        "--checkpoint", default=str(PROJECT_ROOT / "model" / "checkpoints" / "bilstm_cashflow.pt")
    )
    parser.add_argument(
        "--num-windows",
        type=int,
        default=30,
        help="How many as-of dates to batch-forecast, stepping back from the most recent day.",
    )
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "reports"))
    args = parser.parse_args()

    forecaster = CashFlowForecaster(args.checkpoint)
    transactions = pd.read_csv(args.data_csv)
    daily = build_daily_features(transactions)

    window_reports, failed_windows = run_batch(forecaster, daily, args.num_windows)

    report_markdown = render_markdown(
        data_csv=Path(args.data_csv),
        checkpoint_path=Path(args.checkpoint),
        test_metrics=forecaster.test_metrics,
        window_reports=window_reports,
        failed_windows=failed_windows,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"exception_report_{timestamp}.md"
    output_path.write_text(report_markdown, encoding="utf-8")

    print(f"Wrote report to {output_path}")


if __name__ == "__main__":
    main()
