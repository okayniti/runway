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

A background scheduler (agent/scheduler.py) can optionally re-run the
forecast on an interval and POST a webhook when risk flips true, without
anyone calling /forecast manually — disabled by default, opt in with:
    RUNWAY_SCHEDULER_ENABLED=true
    RUNWAY_SCHEDULE_INTERVAL_SECONDS=3600   (default)
    RUNWAY_WEBHOOK_URL=https://example.com/hook  (optional; no webhook fires without it)
    RUNWAY_SCHEDULE_DATA_CSV=data/synthetic_transactions.csv  (default)
    RUNWAY_SCHEDULE_SHORTFALL_THRESHOLD=0   (default)
    RUNWAY_SCHEDULE_TENANT_ID=default        (default)

/forecast is multi-tenant-shaped: an optional X-API-Key header resolves to
a tenant_id that scopes everything written to the history store (run logs,
backfilled actuals) for that request. No key -> the "default" tenant, so
every existing caller (the dashboard, curl examples above, anything from
before this feature existed) keeps working unmodified. A key that IS
provided but isn't recognized -> 401, so a typo'd key can't silently land
data in the wrong tenant. Configure real keys with:
    RUNWAY_API_KEYS='{"<key>": "<tenant_id>", ...}'   (JSON; default has one demo key)

Run with:
    uvicorn api.app:app --reload
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.calibration import CalibrationReport, build_calibration_report  # noqa: E402
from agent.schema import ForecastOutput  # noqa: E402
from agent.scheduler import start_scheduler  # noqa: E402
from agent.store import DEFAULT_TENANT_ID, ForecastStore  # noqa: E402
from agent.wrapper import ForecastValidationError, build_forecast_output  # noqa: E402
from model.infer import CashFlowForecaster  # noqa: E402

CHECKPOINT_PATH = PROJECT_ROOT / "model" / "checkpoints" / "bilstm_cashflow.pt"

# API key -> tenant_id. Override with RUNWAY_API_KEYS (JSON) for real
# deployments; the built-in default exists purely so the demo key used in
# examples/tests resolves to something without requiring env setup.
API_KEYS: dict[str, str] = json.loads(os.environ.get("RUNWAY_API_KEYS", '{"demo-key": "demo-tenant"}'))

_state: dict = {"forecaster": None, "load_error": None, "store": None, "scheduler": None}


def resolve_tenant(x_api_key: str | None = Header(default=None)) -> str:
    """No key -> DEFAULT_TENANT_ID, so every pre-existing caller keeps
    working unmodified. An unrecognized key -> 401, so a typo can't
    silently scope data to the wrong (nonexistent) tenant."""
    if x_api_key is None:
        return DEFAULT_TENANT_ID
    tenant_id = API_KEYS.get(x_api_key)
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    return tenant_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _state["forecaster"] = CashFlowForecaster(CHECKPOINT_PATH)
    except Exception as exc:  # noqa: BLE001 - surfaced via /health, not a crash
        _state["load_error"] = str(exc)
    _state["store"] = ForecastStore()

    if os.environ.get("RUNWAY_SCHEDULER_ENABLED", "").lower() in ("1", "true", "yes"):
        if _state["forecaster"] is not None:
            _state["scheduler"] = start_scheduler(
                forecaster=_state["forecaster"],
                data_csv=os.environ.get(
                    "RUNWAY_SCHEDULE_DATA_CSV", str(PROJECT_ROOT / "data" / "synthetic_transactions.csv")
                ),
                shortfall_threshold=float(os.environ.get("RUNWAY_SCHEDULE_SHORTFALL_THRESHOLD", "0")),
                store=_state["store"],
                tenant_id=os.environ.get("RUNWAY_SCHEDULE_TENANT_ID", DEFAULT_TENANT_ID),
                webhook_url=os.environ.get("RUNWAY_WEBHOOK_URL") or None,
                interval_seconds=int(os.environ.get("RUNWAY_SCHEDULE_INTERVAL_SECONDS", "3600")),
            )

    yield

    if _state["scheduler"] is not None:
        _state["scheduler"].shutdown(wait=False)


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


@app.get("/calibration", response_model=CalibrationReport)
def calibration(tenant_id: str = Depends(resolve_tenant)) -> CalibrationReport:
    """Across every logged run for this tenant with a now-known actual
    outcome, report whether low-confidence runs really did have higher
    forecast error than high-confidence runs — real evidence of whether
    the confidence layer means anything, computed from logged history,
    not asserted."""
    store: ForecastStore = _state["store"]
    runs = store.get_runs_with_errors(tenant_id)
    return build_calibration_report(tenant_id, runs)


@app.post("/forecast", response_model=ForecastOutput)
def forecast(request: ForecastRequest, tenant_id: str = Depends(resolve_tenant)) -> ForecastOutput:
    """Forecast the next 14 days of cash position from recent transaction
    history and return the full agent output: forecast, confidence,
    risk flag/reason, and contributing line items. Scoped by tenant_id,
    resolved from the optional X-API-Key header (see module docstring)."""
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
            tenant_id=tenant_id,
        )
    except ForecastValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
