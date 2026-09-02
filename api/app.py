"""
FastAPI app exposing the cash-flow forecasting + risk-flagging agent layer
over HTTP.

POST /forecast takes recent transaction history as JSON (the same shape
produced by data/generate_synthetic_transactions.py) plus a shortfall
threshold, and returns the full agent output — forecast values, confidence,
risk flag/reason, and contributing line items — validated against
agent.schema.ForecastOutput.

GET /health reports whether the model checkpoint loaded successfully at
startup, so a broken/missing checkpoint fails fast and visibly instead of
surfacing as a 500 on someone's first real request.

Run with:
    uvicorn api.app:app --reload
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.schema import ForecastOutput  # noqa: E402
from agent.store import DEFAULT_TENANT_ID, ForecastStore  # noqa: E402
from agent.wrapper import ForecastValidationError, build_forecast_output  # noqa: E402
from model.infer import CashFlowForecaster  # noqa: E402

CHECKPOINT_PATH = PROJECT_ROOT / "model" / "checkpoints" / "bilstm_cashflow.pt"

_state: dict = {"forecaster": None, "load_error": None, "store": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _state["forecaster"] = CashFlowForecaster(CHECKPOINT_PATH)
    except Exception as exc:  # noqa: BLE001 - surfaced via /health, not a crash
        _state["load_error"] = str(exc)
    _state["store"] = ForecastStore()
    yield


app = FastAPI(
    title="runway",
    description="Cash-flow forecasting and risk-flagging API",
    lifespan=lifespan,
)


class TransactionRecord(BaseModel):
    """One row of transaction history, matching the synthetic ledger schema
    produced by data/generate_synthetic_transactions.py."""

    date: date
    type: str = Field(pattern="^(inflow|outflow)$")
    category: str = Field(min_length=1)
    amount: float = Field(ge=0)
    invoice_date: date | None = None
    note: str | None = None


class ForecastRequest(BaseModel):
    transactions: list[TransactionRecord] = Field(
        min_length=1, description="Recent transaction history, oldest first or any order."
    )
    shortfall_threshold: float = Field(
        description="Cash-position floor. Any forecasted day below this triggers risk_flag."
    )

    @field_validator("transactions")
    @classmethod
    def _must_include_both_transaction_types(
        cls, value: list[TransactionRecord]
    ) -> list[TransactionRecord]:
        """Reject a transaction list that's neither inflows nor outflows
        (e.g. every record failed a stricter check upstream and slipped
        through as some other type) rather than silently forecasting on it."""
        types = {t.type for t in value}
        if not types & {"inflow", "outflow"}:
            raise ValueError("transactions must include at least one inflow or outflow record")
        return value


@app.get("/health")
def health(response: Response) -> dict:
    """Liveness/readiness check. Returns 200/{"status": "ok"} once the model
    checkpoint has loaded, or 503 with a detail message if it failed or
    hasn't finished loading yet."""
    if _state["load_error"] is not None:
        response.status_code = 503
        return {"status": "unhealthy", "detail": f"model failed to load: {_state['load_error']}"}
    if _state["forecaster"] is None:
        response.status_code = 503
        return {"status": "unhealthy", "detail": "model not yet loaded"}
    return {"status": "ok"}


@app.post("/forecast", response_model=ForecastOutput)
def forecast(request: ForecastRequest) -> ForecastOutput:
    """Forecast the next 14 days of cash position from recent transaction
    history and return the full agent output: forecast, confidence,
    risk flag/reason, and contributing line items."""
    forecaster: CashFlowForecaster | None = _state["forecaster"]
    if forecaster is None:
        raise HTTPException(
            status_code=503,
            detail=f"model unavailable: {_state['load_error'] or 'not yet loaded'}",
        )

    transactions = pd.DataFrame.from_records([t.model_dump() for t in request.transactions])

    try:
        return build_forecast_output(
            forecaster=forecaster,
            transactions=transactions,
            shortfall_threshold=request.shortfall_threshold,
            store=_state["store"],
            tenant_id=DEFAULT_TENANT_ID,
        )
    except ForecastValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
