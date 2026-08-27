"""
Streamlit dashboard for the cash-flow forecasting API.

Uploads (or falls back to the bundled synthetic) transaction history,
calls POST /forecast on the running FastAPI service, and displays the
result: a 14-day forecast line, a per-day confidence indicator, and — when
risk_flag is true — an alert banner with the reasoning and the specific
line items driving the projected shortfall.

This is a thin client: all forecasting, risk detection, and confidence
scoring happen server-side (see api/app.py, agent/wrapper.py). The
dashboard only renders what the API returns.

Run with (API must already be running, e.g. `uvicorn api.app:app`):
    streamlit run dashboard/app.py
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "synthetic_transactions.csv"

_CONFIDENCE_COLORS = {"high": "#2e7d32", "medium": "#b8860b", "low": "#c62828"}

st.set_page_config(page_title="Cash Flow Forecast", layout="centered")


def _confidence_level(score: float) -> str:
    """Bucket a confidence score into a display level for color-coding."""
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _load_transactions(uploaded_file) -> pd.DataFrame:
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    if not DEFAULT_DATA_PATH.exists():
        raise FileNotFoundError(
            f"No file uploaded and no default dataset at {DEFAULT_DATA_PATH}. "
            "Upload a transactions CSV, or generate one with "
            "python data/generate_synthetic_transactions.py."
        )
    return pd.read_csv(DEFAULT_DATA_PATH)


def _transactions_to_records(transactions: pd.DataFrame) -> list[dict]:
    """Convert to JSON-safe records: NaN (from optional columns like
    invoice_date/note) must become None, since NaN isn't valid JSON."""
    records = transactions.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and pd.isna(value):
                record[key] = None
    return records


def _call_forecast_api(base_url: str, transactions: pd.DataFrame, shortfall_threshold: float) -> dict:
    payload = {
        "transactions": _transactions_to_records(transactions),
        "shortfall_threshold": shortfall_threshold,
    }
    response = requests.post(f"{base_url.rstrip('/')}/forecast", json=payload, timeout=30)
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"API returned {response.status_code}: {detail}")
    return response.json()


st.title("Cash Flow Forecast")

with st.sidebar:
    st.header("Settings")
    api_base_url = st.text_input("API base URL", value="http://localhost:8000")
    shortfall_threshold = st.number_input("Shortfall threshold", value=0.0, step=1000.0)
    uploaded_file = st.file_uploader("Transaction history (CSV)", type="csv")
    run_clicked = st.button("Run forecast", type="primary")

if not run_clicked:
    st.info("Configure settings in the sidebar and click **Run forecast**.")
    st.stop()

try:
    transactions = _load_transactions(uploaded_file)
    result = _call_forecast_api(api_base_url, transactions, shortfall_threshold)
except Exception as exc:
    st.error(f"Could not generate a forecast: {exc}")
    st.stop()

forecast = result["forecast"]
confidence = result["confidence"]
risk_flag = result["risk_flag"]
risk_reason = result.get("risk_reason")
contributing_line_items = result.get("contributing_line_items", [])

if risk_flag:
    st.error(f"**Shortfall risk detected.** {risk_reason}")
else:
    st.success("No shortfall risk detected for this forecast window.")

horizon = len(forecast)
level = _confidence_level(confidence["score"])
chart_df = pd.DataFrame(
    {
        "day": range(1, horizon + 1),
        "forecast": forecast,
        "confidence_level": [level] * horizon,
    }
)

st.subheader("14-day forecast")
line_chart = (
    alt.Chart(chart_df)
    .mark_line(point=True)
    .encode(
        x=alt.X("day:O", title="Day"),
        y=alt.Y("forecast:Q", title="Cash position"),
        tooltip=["day", "forecast"],
    )
)
st.altair_chart(line_chart, width="stretch")

st.subheader("Confidence")
st.caption(
    f"Overall confidence: {confidence['score']:.2f} ({level.upper()}) — one score "
    "covers the full forecast window; shown per day below for alignment with the chart."
)
confidence_strip = (
    alt.Chart(chart_df)
    .mark_rect(height=24)
    .encode(
        x=alt.X("day:O", title="Day"),
        color=alt.Color(
            "confidence_level:N",
            scale=alt.Scale(
                domain=list(_CONFIDENCE_COLORS.keys()), range=list(_CONFIDENCE_COLORS.values())
            ),
            legend=alt.Legend(title="Confidence"),
        ),
    )
    .properties(height=40)
)
st.altair_chart(confidence_strip, width="stretch")

if confidence.get("reasons"):
    for reason in confidence["reasons"]:
        st.caption(f"- {reason}")

if risk_flag and contributing_line_items:
    st.subheader("Contributing line items")
    st.dataframe(pd.DataFrame(contributing_line_items), width="stretch", hide_index=True)
