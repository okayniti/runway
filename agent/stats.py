"""
Track-record statistics for the frontend's "Track Record" section.

Aggregates real numbers from the persistent history store (agent/store.py)
-- total forecasts run, shortfalls flagged, runs verified against actual
outcomes, and directional accuracy on those verified runs. Nothing here
is fabricated or hardcoded; if there's no history yet, the numbers are
honestly zero/null, not a placeholder standing in for one.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TrackRecordStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    total_forecasts_run: int = Field(ge=0)
    shortfalls_flagged: int = Field(ge=0)
    verified_against_actuals: int = Field(ge=0)
    directional_accuracy_pct: float | None = Field(
        default=None,
        description="Of verified runs, the percentage where the forecast's overall "
        "up/down direction over the horizon matched what actually happened. "
        "Null if there are no verified runs yet -- not zero, which would "
        "misleadingly read as 'always wrong'.",
    )


def _direction(values: list[float]) -> int:
    """+1 if the series ends higher than it starts, -1 if lower, 0 if flat."""
    if not values:
        return 0
    delta = values[-1] - values[0]
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def build_track_record_stats(
    tenant_id: str,
    total_forecasts_run: int,
    shortfalls_flagged: int,
    verified_rows: list[dict],
) -> TrackRecordStats:
    """`verified_rows` is a list of {"forecast": list[float], "actual": list[float]}
    dicts, one per logged run with a known actual outcome (see
    agent.store.ForecastStore.get_verified_forecast_actual_pairs).
    """
    if verified_rows:
        hits = sum(
            1 for row in verified_rows if _direction(row["forecast"]) == _direction(row["actual"])
        )
        directional_accuracy_pct = 100.0 * hits / len(verified_rows)
    else:
        directional_accuracy_pct = None

    return TrackRecordStats(
        tenant_id=tenant_id,
        total_forecasts_run=total_forecasts_run,
        shortfalls_flagged=shortfalls_flagged,
        verified_against_actuals=len(verified_rows),
        directional_accuracy_pct=directional_accuracy_pct,
    )
