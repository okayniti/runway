"""
Lightweight recurring forecast runner.

Wraps APScheduler's BackgroundScheduler to periodically re-run the full
agent pipeline against a fixed data source without a manual request, and
fires a webhook (see webhook.py) whenever a run comes back with
risk_flag=True. This is what makes the system "always-on monitoring"
rather than a tool someone has to remember to open.

Disabled by default — opt in via the RUNWAY_SCHEDULER_ENABLED env var
(see api/app.py's lifespan) — so existing manual /forecast usage is
completely unaffected by this module's existence.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

try:
    from .store import ForecastStore
    from .webhook import build_alert_payload, dispatch_webhook
    from .wrapper import build_forecast_output
except ImportError:  # running as a top-level script rather than a package
    from store import ForecastStore
    from webhook import build_alert_payload, dispatch_webhook
    from wrapper import build_forecast_output

logger = logging.getLogger("runway.scheduler")

JOB_ID = "runway_scheduled_forecast"


def run_scheduled_forecast(
    forecaster,
    data_csv: str | Path,
    shortfall_threshold: float,
    store: ForecastStore,
    tenant_id: str,
    webhook_url: str | None,
) -> None:
    """One scheduled tick: reload the data source, run the full agent
    pipeline (logging + backfill included, since `store` is passed
    through), and dispatch a webhook if risk_flag came back True."""
    try:
        transactions = pd.read_csv(data_csv)
        output = build_forecast_output(
            forecaster=forecaster,
            transactions=transactions,
            shortfall_threshold=shortfall_threshold,
            store=store,
            tenant_id=tenant_id,
        )
    except Exception:  # noqa: BLE001 - a bad tick must not kill the scheduler
        logger.exception("scheduled forecast run failed for tenant %s", tenant_id)
        return

    if output.risk_flag and webhook_url:
        as_of_date = pd.to_datetime(transactions["date"]).max().date().isoformat()
        payload = build_alert_payload(tenant_id, as_of_date, output)
        delivered = dispatch_webhook(webhook_url, payload)
        logger.info("webhook %s to %s for tenant %s", "delivered" if delivered else "FAILED", webhook_url, tenant_id)


def start_scheduler(
    forecaster,
    data_csv: str | Path,
    shortfall_threshold: float,
    store: ForecastStore,
    tenant_id: str,
    webhook_url: str | None,
    interval_seconds: int,
) -> BackgroundScheduler:
    """Start a background job that calls run_scheduled_forecast() once
    immediately and then every `interval_seconds`. Returns the scheduler
    so the caller can .shutdown() it (see api/app.py's lifespan)."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_scheduled_forecast,
        trigger="interval",
        seconds=interval_seconds,
        args=[forecaster, data_csv, shortfall_threshold, store, tenant_id, webhook_url],
        id=JOB_ID,
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "scheduler started: interval=%ss webhook=%s tenant=%s", interval_seconds, webhook_url, tenant_id
    )
    return scheduler
