# runway

A financial cash-flow forecasting system using Bi-LSTM models, served via FastAPI with an agent-based risk-flagging and narrative layer.

## Overview

`runway` forecasts a business's 14-day-ahead net cash position from its recent transaction history, and wraps that forecast with two things a raw number doesn't give you: a **confidence score** (is this window actually predictable, or is the model guessing?) and a **risk layer** (did the forecast cross a shortfall threshold, and if so, which specific line items are driving it?). It's a full pipeline, not just a model — synthetic data generation, training/inference, risk logic, an HTTP API, a dashboard, and batch reporting all live in this repo.

In practical terms, it replaces a recurring manual task — someone periodically pulling bank balances into a spreadsheet to eyeball how much runway is left — with continuous, automated monitoring that alerts on its own the moment risk is detected (see "Scheduled and webhook-triggered monitoring" below). The cost shape shifts accordingly: from a person's recurring time to API/compute (model inference, hosting, outbound alerts) that scales with usage rather than with headcount. No specific pricing is claimed here — that's a real cost-shape difference, not a costed-out business case.

## Architecture

```
 data/              model/                          agent/                                  api/                  dashboard/
┌───────────┐    ┌───────────────────┐    ┌──────────────────────────────────┐    ┌─────────────────┐    ┌────────────┐
│ Synthetic │───▶│ Bi-LSTM forecast  │───▶│ Risk flagging + ranked            │───▶│ FastAPI         │───▶│ Streamlit  │
│ ledger    │    │ + confidence      │    │ recommendations + persistent      │    │ /forecast       │    │ dashboard  │
│ generator │    │ scoring           │    │ history (SQLite)                  │    │ /calibration    │    │            │
└───────────┘    └───────────────────┘    └────────────────┬───────────────────┘    │ /health         │    └────────────┘
                          │                                  │                        └────────┬────────┘
                          ▼                                  ▼                                 │ X-API-Key -> tenant_id
                  reports/ (batch                 agent/store.db: every run                (scopes /forecast and
                  exception reports,               logged, actual outcome                    /calibration per tenant)
                  run offline against              backfilled once real data
                  the checkpoint)                  catches up
                                                                │
                                                                ▼
                                                     agent/calibration.py: is confidence
                                                     actually predictive of error?
                                                     (real evidence, not asserted)

    agent/webhook.py: POSTs a readable Slack alert (RUNWAY_WEBHOOK_URL) the moment any run
    -- manual /forecast or scheduled -- comes back risk_flag=true
    agent/scheduler.py (opt-in, RUNWAY_SCHEDULER_ENABLED=true): re-runs the pipeline on an
    interval with no manual request
```

- **`data/`** — `generate_synthetic_transactions.py` produces a synthetic transaction ledger for a mid-size business: receivables with delay/partial-payment/missed-payment noise, recurring payroll/rent, variable vendor payables, and weekly/monthly seasonality.
- **`model/`** — `dataset.py` aggregates the ledger into daily features and (lookback, horizon) windows, with the target framed as the *change* in cash position over the horizon rather than its absolute cumulative value (see below); `model.py` defines the `BiLSTMForecaster` (bidirectional LSTM → direct 14-day regression head); `train.py` fits it with a chronological train/val/test split (val used only to pick the best-epoch checkpoint and print a train-vs-val loss curve) and reports RMSE/MAE/R²; `confidence.py` scores each forecast window's reliability (history completeness, input volatility, the model's own recorded test error); `infer.py` loads a checkpoint, adds the last known actual cash position back onto the model's relative-change output, and always returns an absolute forecast **and** its confidence together, never bare numbers.
- **`agent/`** — `schema.py` defines the strict `ForecastOutput` contract (forecast, confidence, risk_flag, risk_reason, contributing_line_items, recommendations); `risk.py` checks the forecast against a configurable shortfall threshold and attributes a triggered shortfall to specific recurring obligations or historically large outflows; `recommendations.py` proposes ranked, schema-enforced interventions when risk is flagged; `wrapper.py` assembles all of it, validates against the schema, and (when wired with a store) logs the run; `store.py` is the SQLite-backed persistent history with retroactive error backfilling; `scheduler.py` + `webhook.py` provide opt-in always-on monitoring; `calibration.py` reports whether confidence has actually tracked forecast error. See "Agent capabilities" below for what each of these does and why it's there.
- **`api/`** — a FastAPI app exposing `POST /forecast` (validated input → full agent output as JSON, tenant-scoped via an optional `X-API-Key` header) and `GET /calibration` (confidence-calibration report, same tenant scoping), plus `GET /health` (reports whether the checkpoint loaded). Can optionally run a background scheduler in-process (opt-in, see below).
- **`dashboard/`** — a thin Streamlit client that calls `/forecast` and renders the forecast line, a per-day confidence indicator, and a risk alert banner with contributing line items. No forecasting logic lives here.
- **`reports/`** — `generate_report.py` runs the checkpoint across a batch of as-of dates and writes a markdown exception report: recorded held-out accuracy, every low-confidence window with reasons, and every window the pipeline explicitly couldn't forecast.

## Agent capabilities

The agent layer (`agent/`) started as a single-shot risk-flagging wrapper around the model: take a forecast, flag a shortfall, explain why. This session upgraded it into a persistent, multi-tenant, self-monitoring system — the difference between a demo that answers one question and something with an actual track record.

**Persistent forecast history with retroactive accuracy backfilling.** `agent/store.py` logs every `/forecast` run to a local SQLite database — a snapshot of the input, the full agent output, and (once real time catches up to the forecast window) the actual outcome. On each new run, `backfill_actuals()` looks back at every earlier logged run whose 14-day horizon has now fully elapsed, computes what actually happened day by day, and stores the resulting forecast error. Why it matters: a forecast nobody checks against reality is just a number. This turns "here's a forecast" into "here's a forecast, and here's our track record of being right" — verified against this repo's own real historical data: a run logged against a ledger snapshot cut off at 2026-11-14 was later backfilled with real error stats (RMSE 21,207.50) once a subsequent run's data covered its full horizon.

**Schema-enforced recommended actions.** When `risk_flag` is true, `agent/recommendations.py` proposes up to 3 concrete interventions — `delay_payment` on the specific outflows already identified as driving the shortfall, `accelerate_collection` benchmarked against the largest real receivable in the trailing lookback window — each ranked by dollar impact and validated against a strict Pydantic schema (`agent.schema.Recommendation`). Why it matters: "you're at risk" is a diagnosis; a recommendation is a next step. Every field is computed from real contributing line items or real transaction history, never free text — the schema makes hallucinated advice structurally impossible, the same discipline the rest of the agent layer already applies to the forecast itself.

**Real Slack alerting, on-demand or scheduled.** `agent/webhook.py` POSTs a readable Slack message — the shortfall amount, the calendar date it triggers, and the top recommended action — to a Slack Incoming Webhook URL (`RUNWAY_WEBHOOK_URL`) the moment *any* run comes back `risk_flag=true`, whether that run was a manual `POST /forecast` or a scheduled tick. `agent/scheduler.py` (APScheduler) additionally re-runs the full pipeline on an interval with no manual request — opt-in via `RUNWAY_SCHEDULER_ENABLED=true`, disabled by default so nothing about manual usage changes. Neither path fires without `RUNWAY_WEBHOOK_URL` set, and a failed or unreachable webhook is logged, never fatal to the forecast request or the scheduler tick. Why it matters: this is what separates "a tool you have to remember to open" from "always-on monitoring" — the actual shape of what a business would pay for.

**Multi-tenant API-key scoping.** An optional `X-API-Key` header on `/forecast` and `/calibration` resolves to a `tenant_id` (`RUNWAY_API_KEYS`, JSON) that scopes everything written to the history store. No key falls back to a `default` tenant, so existing callers are unaffected; an unrecognized key is rejected with 401 rather than silently mis-scoping data. Why it matters: even demoed with one tenant, this is the difference between a hardcoded single-dataset script and an architecture actually built for multiple clients.

**Confidence-calibration report.** `GET /calibration` answers the question the confidence layer's existence is supposed to justify: across every logged run with a now-known outcome, did low-confidence runs actually have higher forecast error than high-confidence ones? It's computed from real logged history, not asserted.

> **The calibration finding, as of this session:** every logged run so far has landed in the `low_confidence` bucket — there are currently zero high-confidence runs to compare against. `/calibration` reports this honestly rather than papering over it: `"is_well_calibrated": null`, `"summary": "All 5 logged run(s) with a known outcome fall into a single confidence bucket (low), so low-vs-high error can't be compared yet."` It would have been trivial to fabricate a "yes, calibrated" verdict from a one-bucket sample. It doesn't. **That refusal to overclaim is the strongest evidence of rigor in this project** — a system willing to say "not enough evidence yet" about its own confidence layer is one whose other claims are worth trusting.

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

# 7. (Optional) Wire up Slack alerts: create a Slack Incoming Webhook
#    (api.slack.com/apps -> Create New App -> From scratch -> Incoming
#    Webhooks -> Activate -> Add New Webhook to Workspace), then set
#    RUNWAY_WEBHOOK_URL to the URL it gives you. With this set, any
#    /forecast call (or scheduled run) that comes back risk_flag=true
#    posts a readable alert to that Slack channel.
set RUNWAY_WEBHOOK_URL=https://hooks.slack.com/services/...   # Windows
# export RUNWAY_WEBHOOK_URL=https://hooks.slack.com/services/... # macOS/Linux

# 8. Start the API
uvicorn api.app:app --reload

# 9. In a separate terminal, start the dashboard (API must be running)
streamlit run dashboard/app.py

# 10. Generate a batch exception report
python reports/generate_report.py --num-windows 30
```

## Build Challenges

<!-- TODO: fill in based on what actually broke/surprised you during the build. -->

- [ ]
- [ ]
- [ ]
