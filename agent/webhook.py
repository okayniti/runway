"""
Webhook dispatch for risk alerts.

Fires a structured POST to a configured URL — a Slack Incoming Webhook —
whenever a forecast run (scheduled, see scheduler.py, or an on-demand
POST /forecast, see api/app.py) comes back with risk_flag=True. Delivery
failures are caught and logged, never raised — a broken or unreachable
webhook endpoint must not take down the scheduler or fail the forecast
request that triggered it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

try:
    from .schema import ForecastOutput
except ImportError:  # running as a top-level script rather than a package
    from schema import ForecastOutput

logger = logging.getLogger("runway.webhook")


def _first_shortfall_day(forecast: list[float], threshold: float, as_of_date: str) -> tuple[str, float]:
    """The first forecasted calendar date that falls below `threshold`, and
    the forecasted cash position on that day — mirrors agent.risk's
    "starting day N" logic but returns an actual date instead of an offset,
    since that's what an alert recipient needs, not a day-of-horizon index.
    Falls back to the horizon's minimum day if nothing is strictly below
    threshold (shouldn't happen when this is only called for risk_flag=True
    runs, but stays well-defined rather than raising if it ever is)."""
    as_of = datetime.fromisoformat(as_of_date).date()
    for i, value in enumerate(forecast):
        if value < threshold:
            return (as_of + timedelta(days=i + 1)).isoformat(), value
    worst_index = min(range(len(forecast)), key=lambda i: forecast[i]) if forecast else 0
    worst_value = forecast[worst_index] if forecast else 0.0
    return (as_of + timedelta(days=worst_index + 1)).isoformat(), worst_value


def build_alert_payload(
    tenant_id: str, as_of_date: str, output: ForecastOutput, shortfall_threshold: float
) -> dict:
    """Structured alert body — every field is drawn straight from the
    already-validated ForecastOutput (plus the threshold that flagged it),
    no re-derivation. This is the destination-agnostic data; see
    build_slack_message() for how it's presented in Slack specifically."""
    trigger_date, shortfall_amount = _first_shortfall_day(output.forecast, shortfall_threshold, as_of_date)
    return {
        "event": "shortfall_risk_detected",
        "tenant_id": tenant_id,
        "as_of_date": as_of_date,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "risk_reason": output.risk_reason,
        "shortfall_threshold": shortfall_threshold,
        "shortfall_trigger_date": trigger_date,
        "shortfall_amount": shortfall_amount,
        "confidence_score": output.confidence.score,
        "is_low_confidence": output.confidence.is_low_confidence,
        "forecast_minimum": min(output.forecast) if output.forecast else None,
        "contributing_line_items": [item.model_dump(mode="json") for item in output.contributing_line_items],
        "recommendations": [rec.model_dump(mode="json") for rec in output.recommendations],
    }


def build_slack_message(alert: dict) -> dict:
    """Format an alert payload (see build_alert_payload) as a Slack
    Incoming Webhook body: a plain-text `text` fallback (shown in
    notifications/previews) plus Block Kit `blocks` for the readable
    message in-channel — the shortfall amount, the date it triggers, and
    the top recommended action, exactly what item 1 of the polish pass
    asked for, nothing extra."""
    recommendations = alert.get("recommendations") or []
    top_action = recommendations[0]["description"] if recommendations else "No recommended action for this run."

    fallback_text = (
        f"Cash shortfall risk for {alert['tenant_id']}: projected "
        f"{alert['shortfall_amount']:,.2f} on {alert['shortfall_trigger_date']}"
    )

    return {
        "text": fallback_text,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Cash shortfall risk detected", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Tenant*\n{alert['tenant_id']}"},
                    {"type": "mrkdwn", "text": f"*Triggers on*\n{alert['shortfall_trigger_date']}"},
                    {"type": "mrkdwn", "text": f"*Projected cash position*\n{alert['shortfall_amount']:,.2f}"},
                    {"type": "mrkdwn", "text": f"*Threshold*\n{alert['shortfall_threshold']:,.2f}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Top recommended action*\n{top_action}"},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"as-of {alert['as_of_date']} · confidence "
                            f"{alert['confidence_score']:.2f} "
                            f"({'low' if alert['is_low_confidence'] else 'ok'})"
                        ),
                    }
                ],
            },
        ],
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


def dispatch_risk_alert(url: str, tenant_id: str, as_of_date: str, output: ForecastOutput, shortfall_threshold: float) -> bool:
    """Build the alert payload, format it for Slack, and dispatch it in one
    call — the single entry point both the scheduler and the on-demand
    /forecast route use so the two paths can never format the alert
    differently. Same never-raises contract as dispatch_webhook."""
    alert = build_alert_payload(tenant_id, as_of_date, output, shortfall_threshold)
    return dispatch_webhook(url, build_slack_message(alert))
