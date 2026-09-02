"""
Confidence-calibration analysis.

Answers the question the confidence layer's existence is supposed to
justify: across every logged run whose actual outcome is now known (see
agent.store.ForecastStore.backfill_actuals), did low-confidence runs
actually turn out to have higher forecast error than high-confidence
runs? If not, the confidence score is decorative, not predictive — this
module reports that honestly either way. It does not attempt to make the
confidence layer look good; it computes what the logged data shows.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CalibrationBucket(BaseModel):
    """Aggregate error stats for one confidence bucket."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(pattern="^(low_confidence|high_confidence)$")
    num_runs: int = Field(ge=0)
    mean_confidence_score: float | None = None
    mean_error_rmse: float | None = None
    mean_error_mae: float | None = None


class CalibrationReport(BaseModel):
    """Whether logged confidence scores have actually tracked forecast
    error, computed from real logged runs — not asserted."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    total_runs_with_known_outcome: int = Field(ge=0)
    buckets: list[CalibrationBucket]
    is_well_calibrated: bool | None = Field(
        description="True if low-confidence runs had higher mean RMSE than high-confidence runs. "
        "Null if there isn't at least one run in each bucket yet to compare."
    )
    summary: str


def _bucket(label: str, rows: list[dict]) -> CalibrationBucket:
    if not rows:
        return CalibrationBucket(label=label, num_runs=0)
    n = len(rows)
    return CalibrationBucket(
        label=label,
        num_runs=n,
        mean_confidence_score=sum(r["confidence_score"] for r in rows) / n,
        mean_error_rmse=sum(r["error_rmse"] for r in rows) / n,
        mean_error_mae=sum(r["error_mae"] for r in rows) / n,
    )


def build_calibration_report(tenant_id: str, runs: list[dict]) -> CalibrationReport:
    """`runs` is a list of {"confidence_score", "is_low_confidence",
    "error_rmse", "error_mae"} dicts — one per logged run that already has
    a known actual outcome (agent.store.ForecastStore.get_runs_with_errors
    produces exactly this shape)."""
    low = [r for r in runs if r["is_low_confidence"]]
    high = [r for r in runs if not r["is_low_confidence"]]

    low_bucket = _bucket("low_confidence", low)
    high_bucket = _bucket("high_confidence", high)

    is_well_calibrated: bool | None = None
    if low_bucket.num_runs > 0 and high_bucket.num_runs > 0:
        is_well_calibrated = low_bucket.mean_error_rmse > high_bucket.mean_error_rmse

    if not runs:
        summary = "No logged runs have a known actual outcome yet — nothing to calibrate against."
    elif is_well_calibrated is None:
        only = "low" if low else "high"
        summary = (
            f"All {len(runs)} logged run(s) with a known outcome fall into a single "
            f"confidence bucket ({only}), so low-vs-high error can't be compared yet."
        )
    elif is_well_calibrated:
        summary = (
            f"Calibrated: low-confidence runs averaged {low_bucket.mean_error_rmse:,.2f} RMSE vs. "
            f"{high_bucket.mean_error_rmse:,.2f} for high-confidence runs — the confidence score "
            f"is tracking real forecast error on this data."
        )
    else:
        summary = (
            f"NOT calibrated: low-confidence runs averaged {low_bucket.mean_error_rmse:,.2f} RMSE vs. "
            f"{high_bucket.mean_error_rmse:,.2f} for high-confidence runs — confidence is not "
            f"predicting error direction correctly on this data."
        )

    return CalibrationReport(
        tenant_id=tenant_id,
        total_runs_with_known_outcome=len(runs),
        buckets=[low_bucket, high_bucket],
        is_well_calibrated=is_well_calibrated,
        summary=summary,
    )
