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
- **`model/`** — `dataset.py` aggregates the ledger into daily features and (lookback, horizon) windows, with the target framed as the *change* in cash position over the horizon rather than its absolute cumulative value (see below); `model.py` defines the `BiLSTMForecaster` (bidirectional LSTM → direct 14-day regression head); `train.py` fits it with a chronological train/val/test split (val used only to pick the best-epoch checkpoint and print a train-vs-val loss curve) and reports RMSE/MAE/R²; `confidence.py` scores each forecast window's reliability (history completeness, input volatility, the model's own recorded test error); `infer.py` loads a checkpoint, adds the last known actual cash position back onto the model's relative-change output, and always returns an absolute forecast **and** its confidence together, never bare numbers.
- **`agent/`** — `schema.py` defines the strict `ForecastOutput` contract (forecast, confidence, risk_flag, risk_reason, contributing_line_items); `risk.py` checks the forecast against a configurable shortfall threshold and attributes a triggered shortfall to specific recurring obligations or historically large outflows; `wrapper.py` assembles all of it and validates against the schema, retrying the build on failure rather than ever returning an unvalidated payload.
- **`api/`** — a FastAPI app exposing `POST /forecast` (validated input → full agent output as JSON) and `GET /health` (reports whether the checkpoint loaded).
- **`dashboard/`** — a thin Streamlit client that calls `/forecast` and renders the forecast line, a per-day confidence indicator, and a risk alert banner with contributing line items. No forecasting logic lives here.
- **`reports/`** — `generate_report.py` runs the checkpoint across a batch of as-of dates and writes a markdown exception report: recorded held-out accuracy, every low-confidence window with reasons, and every window the pipeline explicitly couldn't forecast.

## Measured model performance

From the most recently trained checkpoint (`model/checkpoints/bilstm_cashflow.pt`), evaluated on its chronological held-out test split (test metrics are recorded in the checkpoint at training time — see `model/train.py`), trained on 1,095 days of synthetic history:

| Split | RMSE | MAE | R² |
|---|---|---|---|
| Train | 29,210.03 | 23,139.58 | 0.5208 |
| **Test (held-out)** | **30,944.73** | **23,869.77** | **0.4540** |

Units are the change in cash position over the 14-day horizon, not the raw cumulative balance (see below for why). Test performance sits close to train performance — RMSE and MAE are nearly identical, and the R² gap is 0.07 — which is what "generalizing" actually looks like, as opposed to the model memorizing training windows.

**This was previously badly broken (test R² of -11.40, worse than predicting the mean) and required a real diagnosis, not a hyperparameter tweak:**

1. **Root cause: the original target was non-stationary.** `cash_position` is a cumulative running sum that only ever grows. Diagnosing the -11.40 run showed train targets falling in the 55K-443K range and test targets in 434K-575K — completely disjoint, purely because the chronological split put "later" (and therefore numerically larger) windows in test. The model was structurally incapable of extrapolating to values it never saw in train. Fix: `model/dataset.py` now targets the *change* in cash position over the horizon, relative to the last known value — a roughly stationary quantity — and `model/infer.py` adds that last known value back on so every consumer downstream (API, dashboard, risk checks) still sees an absolute forecast. This took R² from -11.40 to +0.08 on its own.
2. **Data volume vs. model capacity.** The original architecture (hidden_size=64, 2 layers) has 147,406 parameters against ~65 training windows from the default 90-day dataset — thousands of parameters per sample. Generated more synthetic history (1,095 days → 735 train / 130 val / 217 test windows) and shrank the model to hidden_size=16, 1 layer (4,350 parameters) to match.
3. **No validation split, no best-epoch selection.** Training only ever tracked a train/test split, so the final epoch's (often overfit) weights were always what got saved. `train.py` now carves a validation split out of training data, prints train-vs-val loss every 10 epochs, and — since the val curve reliably overfits well before epoch 150 in this setup — keeps the best-val-loss epoch's weights rather than the last epoch's. Added `weight_decay` (L2) as further regularization.
4. **Chronological split was already correct**, and scaling (fit on train only, applied to val/test, inverse-transformed before computing metrics) was already correct — verified, not just assumed, while diagnosing the above.

The confidence layer still reports low confidence on typical forecasts today, because it partly weighs the model's own recorded test RMSE against the target's scale — that's it doing its job honestly, not a leftover bug. Re-run `model/train.py` (defaults now reflect all of the above) and update the table if the data or architecture changes again.

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate synthetic transaction data (1095 days / ~3 years -- see "Measured
#    model performance" below for why the model needs this much history)
python data/generate_synthetic_transactions.py --num-days 1095

# 4. Train the model (saves a checkpoint to model/checkpoints/)
python model/train.py

# 5. Run inference from the command line
python model/infer.py

# 6. Run the risk-flagging agent layer from the command line
#    (threshold is on the same cumulative cash-position scale printed by
#    step 5 -- adjust to whatever's below your own forecast to see risk_flag
#    trigger)
python agent/wrapper.py --shortfall-threshold 6000000

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
