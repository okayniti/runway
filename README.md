# runway

A financial cash-flow forecasting system using Bi-LSTM models, served via FastAPI with an agent-based risk-flagging and narrative layer.

## Overview

`runway` forecasts a business's 14-day-ahead net cash position from its recent transaction history, and wraps that forecast with two things a raw number doesn't give you: a **confidence score** (is this window actually predictable, or is the model guessing?) and a **risk layer** (did the forecast cross a shortfall threshold, and if so, which specific line items are driving it?). It's a full pipeline, not just a model — synthetic data generation, training/inference, risk logic, an HTTP API, a dashboard, and batch reporting all live in this repo.

## Architecture

```
 data/              model/                          agent/            api/          dashboard/
┌───────────┐    ┌───────────────────┐    ┌───────────────────┐    ┌─────────┐    ┌────────────┐
│ Synthetic │───▶│ Bi-LSTM forecast  │───▶│ Risk flagging +   │───▶│ FastAPI │───▶│ Streamlit  │
│ ledger    │    │ + confidence      │    │ narrative reasons │    │ /forecast│    │ dashboard  │
│ generator │    │ scoring           │    │                   │    │ /health │    │            │
└───────────┘    └───────────────────┘    └───────────────────┘    └─────────┘    └────────────┘
                          │
                          ▼
                  reports/ (batch exception reports, run offline against the checkpoint)
```

- **`data/`** — `generate_synthetic_transactions.py` produces a synthetic transaction ledger for a mid-size business: receivables with delay/partial-payment/missed-payment noise, recurring payroll/rent, variable vendor payables, and weekly/monthly seasonality.
- **`model/`** — `dataset.py` aggregates the ledger into daily features and (lookback, horizon) windows; `model.py` defines the `BiLSTMForecaster` (bidirectional LSTM → direct 14-day regression head); `train.py` fits it with a chronological train/test split and reports RMSE/MAE/R²; `confidence.py` scores each forecast window's reliability (history completeness, input volatility, the model's own recorded test error); `infer.py` loads a checkpoint and always returns a forecast **and** its confidence together, never bare numbers.
- **`agent/`** — `schema.py` defines the strict `ForecastOutput` contract (forecast, confidence, risk_flag, risk_reason, contributing_line_items); `risk.py` checks the forecast against a configurable shortfall threshold and attributes a triggered shortfall to specific recurring obligations or historically large outflows; `wrapper.py` assembles all of it and validates against the schema, retrying the build on failure rather than ever returning an unvalidated payload.
- **`api/`** — a FastAPI app exposing `POST /forecast` (validated input → full agent output as JSON) and `GET /health` (reports whether the checkpoint loaded).
- **`dashboard/`** — a thin Streamlit client that calls `/forecast` and renders the forecast line, a per-day confidence indicator, and a risk alert banner with contributing line items. No forecasting logic lives here.
- **`reports/`** — `generate_report.py` runs the checkpoint across a batch of as-of dates and writes a markdown exception report: recorded held-out accuracy, every low-confidence window with reasons, and every window the pipeline explicitly couldn't forecast.

## Measured model performance

From the most recently trained checkpoint (`model/checkpoints/bilstm_cashflow.pt`), evaluated on its chronological held-out test split (test metrics are recorded in the checkpoint at training time — see `model/train.py`):

| Metric | Value |
|---|---|
| RMSE | 148,532.83 |
| MAE | 137,054.73 |
| R² | -11.40 |

**This is not a good result, and that's worth stating plainly rather than burying it.** A negative R² means the model currently does worse than just predicting the mean of the test set. The pipeline itself — data generation, feature engineering, windowing, training loop, metric computation, checkpointing, confidence scoring, risk attribution, API, dashboard — all run correctly end-to-end and have been verified at each stage. What's under-scaled is the training data: the default synthetic run produces well under 100 usable (lookback + horizon) windows, split chronologically into a small train set and an even smaller test set, on a cumulative target (`cash_position`) with a strong trend that a Bi-LSTM this size can't yet extrapolate reliably from that little history. The confidence layer catches this correctly — it flags essentially every window as low-confidence, citing the model's own recorded test error as one of the reasons. More synthetic history, a longer training run, and/or reframing the target (e.g. daily net flow instead of cumulative position) are the likely next steps; re-run `model/train.py` and update the table above once that's done.

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate synthetic transaction data
python data/generate_synthetic_transactions.py --num-days 120

# 4. Train the model (saves a checkpoint to model/checkpoints/)
python model/train.py

# 5. Run inference from the command line
python model/infer.py

# 6. Run the risk-flagging agent layer from the command line
python agent/wrapper.py --shortfall-threshold 400000

# 7. Start the API
uvicorn api.app:app --reload

# 8. In a separate terminal, start the dashboard (API must be running)
streamlit run dashboard/app.py

# 9. Generate a batch exception report
python reports/generate_report.py --num-windows 30
```

## Build Challenges

<!-- TODO: fill in based on what actually broke/surprised you during the build. -->

- [ ]
- [ ]
- [ ]
