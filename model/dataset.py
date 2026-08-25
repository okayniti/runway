"""
Feature engineering and windowing for the Bi-LSTM cash-flow forecaster.

Turns a raw per-transaction ledger (as produced by
data/generate_synthetic_transactions.py) into a daily feature matrix, then
slices it into supervised (lookback, horizon) windows: given the past
`lookback` days of features, predict `cash_position` for the next `horizon`
days.

`cash_position` is defined here as the cumulative sum of daily net cash flow
(inflows minus outflows) starting from zero on the first day in range. The
synthetic ledger has no recorded starting bank balance, so this tracks the
*change* in cash position rather than an absolute balance — a real
deployment would offset it by the business's actual opening balance.
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
    (num_samples, horizon), where y[i] is `cash_position` for the `horizon`
    days immediately following the i-th input window.
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
    y = np.stack([target[i + lookback : i + lookback + horizon] for i in range(num_samples)])

    return X, y
