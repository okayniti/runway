"""
Pydantic schema for the agent layer's forecast output.

This is the contract between the model layer and everything downstream
(API responses, narrative generation, dashboards): every consumer gets a
forecast, a confidence readout, and — when a shortfall is detected — an
explicit reason plus the specific line items driving it, instead of having
to re-derive that from raw numbers. `model_config = ConfigDict(extra="forbid")`
on ForecastOutput means any field not defined here is a validation error,
not a silently-dropped typo.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContributingLineItem(BaseModel):
    """A historical or projected transaction identified as a driver of a
    forecasted cash shortfall."""

    model_config = ConfigDict(extra="forbid")

    date: date
    type: str = Field(pattern="^(inflow|outflow)$")
    category: str
    amount: float = Field(ge=0)
    note: str
    basis: str = Field(
        description=(
            "Why this item was flagged: 'recurring_projection' for a fixed "
            "obligation projected forward from its historical cadence, or "
            "'historical_outlier' for a large recent outflow driving the "
            "current negative trend."
        )
    )


class ConfidenceInfo(BaseModel):
    """Mirrors model.confidence.ConfidenceBreakdown as a validated schema."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    is_low_confidence: bool
    reasons: list[str] = Field(default_factory=list)


class ForecastOutput(BaseModel):
    """Strict schema for a single forecast window's agent-layer output."""

    model_config = ConfigDict(extra="forbid")

    forecast: list[float] = Field(min_length=1)
    confidence: ConfidenceInfo
    risk_flag: bool
    risk_reason: str | None = None
    contributing_line_items: list[ContributingLineItem] = Field(default_factory=list)

    @field_validator("risk_reason")
    @classmethod
    def _risk_reason_matches_flag(cls, value: str | None, info) -> str | None:
        """Enforce risk_reason is set if and only if risk_flag is True, so
        the two fields can never drift apart."""
        risk_flag = info.data.get("risk_flag")
        if risk_flag and not value:
            raise ValueError("risk_reason must be a non-empty string when risk_flag is True")
        if risk_flag is False and value:
            raise ValueError("risk_reason must be null when risk_flag is False")
        return value
