"""
Feature engineering and windowing for the Bi-LSTM cash-flow forecaster.

Turns a raw per-transaction ledger (as produced by
data/generate_synthetic_transactions.py) into a daily feature matrix, then
slices it into supervised (lookback, horizon) windows: given the past
`lookback` days of features, predict how `cash_position` will change over
the next `horizon` days.

`cash_position` (the daily column) is the cumulative sum of daily net cash
flow (inflows minus outflows) starting from zero on the first day in range.
The synthetic ledger has no recorded starting bank balance, so this tracks
the *change* in cash position rather than an absolute balance — a real
deployment would offset it by the business's actual opening balance.

Critically, `build_windows()` does NOT use that raw cumulative value as the
model's regression target. cash_position only ever grows in magnitude over
the life of the ledger, so a chronological train/test split (required for
a time series — see model/train.py) puts train and test targets in
completely disjoint numeric ranges: the model is trained to output values
in the train range and structurally cannot extrapolate to the much larger
values only seen in the test period. (Verified empirically while
diagnosing a -11.4 test R2: train targets fell in roughly 55K-443K, test
targets in 434K-575K — non-overlapping.) Instead, the target is the
*change* in cash_position over the horizon relative to the last lookback
day — i.e., "how much will cash move over the next `horizon` days from
here" — which is approximately stationary across time for a business
without long-term structural drift, so train and test target ranges
actually overlap and the model can generalize. Absolute cash_position is
reconstructed at inference time by adding this delta back onto the last
known real balance (see model.infer.CashFlowForecaster.predict_window).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "inflow_total",
    "outflow_total",
    "net_flow",
    "inflow_rolling_7d",
    "outflow_rolling_7d",
    "dow_sin",
    "dow_cos",
    "dom_sin",
    "dom_cos",
    "is_weekend",
]
TARGET_COLUMN = "cash_position"


def build_daily_features(transactions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a per-transaction ledger into one row per calendar day.

    Days with no transactions are filled with zero inflow/outflow rather
    than dropped, so the resulting series has no gaps for the model to
    silently skip over.
    """
    df = transactions.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    full_range = pd.date_range(df["date"].min(), df["date"].max(), freq="D")

    inflow = (
        df[df["type"] == "inflow"]
        .groupby("date")["amount"]
        .sum()
        .reindex(full_range, fill_value=0.0)
    )
    outflow = (
        df[df["type"] == "outflow"]
        .groupby("date")["amount"]
        .sum()
        .reindex(full_range, fill_value=0.0)
    )

    daily = pd.DataFrame(
        {
            "date": full_range,
            "inflow_total": inflow.to_numpy(),
            "outflow_total": outflow.to_numpy(),
        }
    )
    daily["net_flow"] = daily["inflow_total"] - daily["outflow_total"]
    daily["cash_position"] = daily["net_flow"].cumsum()

    daily["inflow_rolling_7d"] = daily["inflow_total"].rolling(7, min_periods=1).mean()
    daily["outflow_rolling_7d"] = daily["outflow_total"].rolling(7, min_periods=1).mean()

    dow = daily["date"].dt.dayofweek
    daily["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    daily["dow_cos"] = np.cos(2 * np.pi * dow / 7)

    dom = daily["date"].dt.day
    days_in_month = daily["date"].dt.days_in_month
    daily["dom_sin"] = np.sin(2 * np.pi * dom / days_in_month)
    daily["dom_cos"] = np.cos(2 * np.pi * dom / days_in_month)

    daily["is_weekend"] = (dow >= 5).astype(float)

    return daily.reset_index(drop=True)


def build_windows(
    daily: pd.DataFrame, lookback: int, horizon: int
) -> tuple[np.ndarray, np.ndarray]:
    """Slide a (lookback, horizon) window across the daily feature table.

    Returns X of shape (num_samples, lookback, num_features) and y of shape
    (num_samples, horizon), where y[i] is the *change* in `cash_position`
    for each of the `horizon` days immediately following the i-th input
    window, relative to `cash_position` on that window's last day (see the
    module docstring for why this — not the raw cumulative value — is the
    regression target).
    """
    features = daily[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    target = daily[TARGET_COLUMN].to_numpy(dtype=np.float32)

    num_days = len(daily)
    num_samples = num_days - lookback - horizon + 1
    if num_samples <= 0:
        raise ValueError(
            f"Not enough days ({num_days}) for lookback={lookback} + "
            f"horizon={horizon}. Generate more synthetic data or reduce "
            "lookback/horizon."
        )

    X = np.stack([features[i : i + lookback] for i in range(num_samples)])

    baseline = np.array([target[i + lookback - 1] for i in range(num_samples)], dtype=np.float32)
    y_absolute = np.stack(
        [target[i + lookback : i + lookback + horizon] for i in range(num_samples)]
    )
    y = y_absolute - baseline[:, None]

    return X, y
