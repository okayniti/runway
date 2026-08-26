"""
Shortfall risk detection and root-cause line-item attribution.

check_shortfall_risk() flags a forecast window as at-risk when any
predicted day falls below a configurable cash-position threshold.
identify_contributing_line_items() then explains *why*, using only
information available in the historical transaction ledger:

- recurring fixed obligations (payroll, rent) are projected forward from
  their observed historical cadence; a projected occurrence that lands
  inside the forecast horizon is flagged as a driver
- the largest historical outflows in the trailing lookback window are
  flagged as drivers of the current negative trend the model is
  extrapolating, since the model has no visibility into specific
  not-yet-recorded future invoices

This is a heuristic, not a claim that these are literally the future
transactions that will occur — it operationalizes "upcoming line items"
using only data the forecaster actually has access to (the historical
ledger), rather than assuming a source of known future invoices that
doesn't exist in this pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from .schema import ContributingLineItem
except ImportError:  # running as a top-level script rather than a package
    from schema import ContributingLineItem

RECURRING_CATEGORIES = {"payroll", "rent"}


def check_shortfall_risk(
    forecast: np.ndarray, threshold: float
) -> tuple[bool, str | None, list[int]]:
    """Flag a forecast as at-risk if any predicted day falls below `threshold`.

    Returns (risk_flag, risk_reason, day_indices_below_threshold). Both the
    forecast and threshold are expected to be on the same cash-position
    scale produced by the model (see model/dataset.py for how that scale is
    defined).
    """
    forecast = np.asarray(forecast, dtype=float)
    below_mask = forecast < threshold
    if not below_mask.any():
        return False, None, []

    below_indices = [int(i) for i in np.where(below_mask)[0]]
    first_day = below_indices[0] + 1
    min_value = float(forecast[below_mask].min())
    horizon = len(forecast)

    reason = (
        f"Projected cash position falls below the {threshold:,.2f} threshold "
        f"starting day {first_day} of the {horizon}-day forecast, reaching a "
        f"low of {min_value:,.2f}."
    )
    return True, reason, below_indices


def _project_recurring_items(
    transactions: pd.DataFrame, as_of_date: pd.Timestamp, horizon: int
) -> list[ContributingLineItem]:
    """Project the next occurrence(s) of each recurring fixed obligation and
    flag any that fall within the forecast horizon."""
    items: list[ContributingLineItem] = []
    horizon_end = as_of_date + pd.Timedelta(days=horizon)

    for category in RECURRING_CATEGORIES:
        history = transactions[transactions["category"] == category].copy()
        if len(history) < 2:
            continue
        history["date"] = pd.to_datetime(history["date"])
        history = history.sort_values("date")

        intervals = history["date"].diff().dropna().dt.days
        if intervals.empty:
            continue
        cadence_days = int(round(intervals.median()))
        if cadence_days <= 0:
            continue

        last_date = history["date"].iloc[-1]
        avg_amount = float(history["amount"].tail(3).mean())

        next_date = last_date + pd.Timedelta(days=cadence_days)
        while next_date <= horizon_end:
            if next_date > as_of_date:
                items.append(
                    ContributingLineItem(
                        date=next_date.date(),
                        type="outflow",
                        category=category,
                        amount=round(avg_amount, 2),
                        note=f"projected recurring {category} (observed ~{cadence_days}-day cadence)",
                        basis="recurring_projection",
                    )
                )
            next_date += pd.Timedelta(days=cadence_days)

    return items


def _historical_outlier_items(
    transactions: pd.DataFrame, as_of_date: pd.Timestamp, lookback: int, top_n: int = 3
) -> list[ContributingLineItem]:
    """Flag the largest outflows in the trailing lookback window as drivers
    of the current negative trend."""
    window_start = as_of_date - pd.Timedelta(days=lookback)
    dated = transactions.copy()
    dated["date"] = pd.to_datetime(dated["date"])

    recent_outflows = dated[
        (dated["type"] == "outflow") & (dated["date"] > window_start) & (dated["date"] <= as_of_date)
    ]
    if recent_outflows.empty:
        return []

    top = recent_outflows.sort_values("amount", ascending=False).head(top_n)

    return [
        ContributingLineItem(
            date=row["date"].date(),
            type="outflow",
            category=str(row["category"]),
            amount=round(float(row["amount"]), 2),
            note=(str(row["note"]) if pd.notna(row.get("note")) else "") or "large recent outflow",
            basis="historical_outlier",
        )
        for _, row in top.iterrows()
    ]


def identify_contributing_line_items(
    transactions: pd.DataFrame,
    as_of_date: pd.Timestamp,
    horizon: int,
    lookback: int,
    max_items: int = 5,
) -> list[ContributingLineItem]:
    """Identify which line items are likely driving a forecasted shortfall.

    Combines projected recurring obligations landing inside the forecast
    horizon with the largest recent historical outflows, since the model
    itself only ever sees historical data — it has no ground truth about
    specific future invoices not yet in the ledger.
    """
    recurring = _project_recurring_items(transactions, as_of_date, horizon)
    outliers = _historical_outlier_items(transactions, as_of_date, lookback)

    combined = sorted(recurring + outliers, key=lambda item: item.amount, reverse=True)
    return combined[:max_items]
