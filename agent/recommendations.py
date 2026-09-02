"""
Concrete, schema-enforced intervention recommendations.

Computed purely from the forecast, the already-identified
contributing_line_items (see risk.py), and the raw transaction history —
never freeform text generation. Two action types:

- delay_payment: proposes pushing back one of the outflow line items
  already identified as driving the shortfall (contributing_line_items),
  ranked by amount.
- accelerate_collection: proposes pulling forward collection on a
  receivable, benchmarked against the largest actual receivable in the
  trailing lookback window (a real historical data point). This system
  has no visibility into outstanding/unpaid AR beyond settled transaction
  history, so the recommendation is phrased as a benchmark against real
  historical receivable size, not a claim about a specific known future
  invoice.

The "projected effect" for each is a simple, transparent heuristic:
shifting a known dollar amount fully outside (or inside) the forecast
horizon raises or lowers every forecast day from the shift point onward
by that amount. This is stated in each recommendation's description as
what it is — an estimate — not presented as a second model run. The
Bi-LSTM itself has no mechanism to accept a hypothetical intervention as
input, and this module deliberately does not pretend otherwise by
re-running it.
"""

from __future__ import annotations

import pandas as pd

try:
    from .schema import ContributingLineItem, Recommendation
except ImportError:  # running as a top-level script rather than a package
    from schema import ContributingLineItem, Recommendation

DEFAULT_SHIFT_DAYS = 7


def _largest_recent_receivable(
    transactions: pd.DataFrame, as_of_date: pd.Timestamp, lookback: int
) -> dict | None:
    """Mirrors risk.py's _historical_outlier_items, but for inflows — the
    largest real receivable in the trailing lookback window, used as a
    concrete benchmark for an accelerate_collection recommendation."""
    window_start = as_of_date - pd.Timedelta(days=lookback)
    dated = transactions.copy()
    dated["date"] = pd.to_datetime(dated["date"])

    recent_inflows = dated[
        (dated["type"] == "inflow") & (dated["date"] > window_start) & (dated["date"] <= as_of_date)
    ]
    if recent_inflows.empty:
        return None

    top = recent_inflows.sort_values("amount", ascending=False).iloc[0]
    return {
        "date": top["date"].date(),
        "category": str(top["category"]),
        "amount": round(float(top["amount"]), 2),
    }


def generate_recommendations(
    forecast: list[float],
    contributing_line_items: list[ContributingLineItem],
    transactions: pd.DataFrame,
    as_of_date: pd.Timestamp,
    lookback: int,
    max_recommendations: int = 3,
) -> list[Recommendation]:
    """Propose up to `max_recommendations` interventions, ranked by
    projected dollar impact on the forecasted horizon minimum.

    Intended to be called only when risk_flag is True — an empty
    contributing_line_items list and no receivables in the lookback
    window will simply yield an empty recommendation list.
    """
    current_minimum = min(forecast) if forecast else 0.0
    candidates: list[Recommendation] = []

    for item in sorted(contributing_line_items, key=lambda i: i.amount, reverse=True):
        candidates.append(
            Recommendation(
                rank=1,  # reassigned after sorting/truncating below
                action="delay_payment",
                description=(
                    f"Delay the {item.category} payment of {item.amount:,.2f} "
                    f"(scheduled {item.date}, flagged via {item.basis}) by "
                    f"{DEFAULT_SHIFT_DAYS} days. If pushed fully outside the forecast "
                    f"horizon, the projected minimum rises from {current_minimum:,.2f} "
                    f"to {current_minimum + item.amount:,.2f}."
                ),
                reference_date=item.date,
                reference_category=item.category,
                reference_amount=item.amount,
                suggested_shift_days=DEFAULT_SHIFT_DAYS,
                projected_shortfall_relief=item.amount,
                projected_new_minimum=current_minimum + item.amount,
            )
        )

    receivable = _largest_recent_receivable(transactions, as_of_date, lookback)
    if receivable is not None:
        candidates.append(
            Recommendation(
                rank=1,
                action="accelerate_collection",
                description=(
                    f"Accelerate collection on receivables, benchmarked against the "
                    f"{receivable['amount']:,.2f} {receivable['category']} received on "
                    f"{receivable['date']} — the largest real receivable in the trailing "
                    f"{lookback}-day window. Collecting a similar amount "
                    f"{DEFAULT_SHIFT_DAYS} days earlier would raise the projected minimum "
                    f"from {current_minimum:,.2f} to {current_minimum + receivable['amount']:,.2f}. "
                    f"This is a benchmark against historical receivable size, not a claim "
                    f"about a specific known outstanding invoice."
                ),
                reference_date=receivable["date"],
                reference_category=receivable["category"],
                reference_amount=receivable["amount"],
                suggested_shift_days=-DEFAULT_SHIFT_DAYS,
                projected_shortfall_relief=receivable["amount"],
                projected_new_minimum=current_minimum + receivable["amount"],
            )
        )

    candidates.sort(key=lambda r: r.projected_shortfall_relief, reverse=True)
    top = candidates[:max_recommendations]
    return [rec.model_copy(update={"rank": i + 1}) for i, rec in enumerate(top)]
