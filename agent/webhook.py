"""
Webhook dispatch for risk alerts.

Fires a structured POST to a configured URL whenever a scheduled forecast
run (see scheduler.py) comes back with risk_flag=True. Delivery failures
are caught and logged, never raised — a broken or unreachable webhook
endpoint must not take down the scheduler, and must never surface as a
failure to whatever triggered the forecast.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

try:
    from .schema import ForecastOutput
except ImportError:  # running as a top-level script rather than a package
    from schema import ForecastOutput

logger = logging.getLogger("runway.webhook")


def build_alert_payload(tenant_id: str, as_of_date: str, output: ForecastOutput) -> dict:
    """Structured alert body — every field is drawn straight from the
    already-validated ForecastOutput, no re-derivation."""
    return {
        "event": "shortfall_risk_detected",
        "tenant_id": tenant_id,
        "as_of_date": as_of_date,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "risk_reason": output.risk_reason,
        "confidence_score": output.confidence.score,
        "is_low_confidence": output.confidence.is_low_confidence,
        "forecast_minimum": min(output.forecast) if output.forecast else None,
        "contributing_line_items": [item.model_dump(mode="json") for item in output.contributing_line_items],
        "recommendations": [rec.model_dump(mode="json") for rec in output.recommendations],
    }


def dispatch_webhook(url: str, payload: dict, timeout: float = 10.0) -> bool:
    """POST payload to url. Returns True on a 2xx response, False on any
    failure — never raises, so a bad webhook target can't crash the caller."""
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("webhook dispatch to %s failed: %s", url, exc)
        return False
