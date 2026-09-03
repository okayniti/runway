# runway

A business usually finds out it's short on cash the day it happens — a bounced payment, a spreadsheet somebody finally opened. runway forecasts the next 14 days of net cash position from transaction history, flags the specific days it's projected to drop below a threshold, and says which line items are driving that, before any of it happens.

It's a full pipeline, not a single script: a Bi-LSTM model, an agent layer that turns a raw forecast into a risk verdict with evidence behind it, a FastAPI service, two frontends, and enough persistent history to check its own accuracy against what actually happened later.

In practical terms, it replaces a recurring manual task — someone periodically pulling bank balances into a spreadsheet to eyeball how much runway is left — with continuous, automated monitoring that alerts on its own the moment risk is detected. The cost shape shifts accordingly: from a person's recurring time to API/compute (model inference, hosting, outbound alerts) that scales with usage rather than headcount. No pricing is claimed here — that's a real cost-shape difference, not a costed-out business case.

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

- **`data/`** — `generate_synthetic_transactions.py` produces a synthetic ledger for a mid-size business: receivables with delay/partial-payment/missed-payment noise, recurring payroll/rent, variable vendor payables, weekly/monthly seasonality.
- **`model/`** — `dataset.py` aggregates the ledger into daily features and (lookback, horizon) windows, targeting the *change* in cash position rather than its absolute value (see "What we got wrong" below for why that distinction mattered). `model.py` defines the `BiLSTMForecaster`. `train.py` fits it with a chronological train/val/test split and reports RMSE/MAE/R². `confidence.py` scores each window's reliability. `infer.py` loads a checkpoint, adds the last known cash position back onto the model's relative-change output, and always returns a forecast paired with its confidence — never a bare number.
- **`agent/`** — `schema.py` defines the strict `ForecastOutput` contract; `risk.py` checks a forecast against a shortfall threshold and attributes it to specific recurring obligations or historical outliers; `recommendations.py` proposes ranked interventions when risk is flagged; `wrapper.py` assembles and validates all of it; `store.py` is the SQLite-backed history with retroactive error backfilling; `scheduler.py` + `webhook.py` run the always-on monitoring loop; `calibration.py` checks whether confidence has actually tracked error. Each gets its own section below.
- **`api/`** — FastAPI app exposing `POST /forecast`, `GET /calibration`, `GET /stats`, and `GET /health`. Tenant-scoped via an optional `X-API-Key` header. Can run a background scheduler in-process, opt-in.
- **`dashboard/`** — a thin Streamlit client against `/forecast`: the forecast line, a per-day confidence indicator, a risk banner with contributing line items. No forecasting logic lives here.
- **`frontend/`** — a Next.js demo site: a live forecast panel (upload a CSV or use the bundled sample), a track-record section and calibration spotlight backed by real `/stats` and `/calibration` data. Talks to the API through a same-origin `/api/backend/*` proxy (`frontend/next.config.ts`), so the backend needs no CORS setup and its real address never reaches client-side code. Same principle as the dashboard: a second client, no forecasting logic of its own.
- **`reports/`** — `generate_report.py` runs the checkpoint across a batch of as-of dates and writes a markdown exception report: held-out accuracy, every low-confidence window with reasons, every window the pipeline explicitly couldn't forecast.

## What the agent layer actually does

The model produces a number. Everything below turns that number into something a person can act on and check later.

**A forecast that also tells you when not to trust it.** Every window's forecast comes with a confidence score built from three signals, none of which require knowing the future: how much of the 30-day lookback window is real transaction data versus zero-padding for a thin history, how volatile the input's daily cash flow already is, and how large the model's own recorded held-out error is. They combine by taking the minimum of the three, not an average — one bad signal should pull confidence down, not get smoothed over by two healthy ones.

**Risk detection that names the cause, not just the symptom.** When a forecasted day drops below a shortfall threshold, `risk.py` traces it back to specific line items — a recurring payroll run landing inside the horizon, or the largest actual outflow in the recent ledger — then `recommendations.py` proposes up to three ranked interventions: delay a specific payment, accelerate a specific collection. Every number in a recommendation is arithmetic against real transaction history. Nothing is generated text, so there's nothing in that layer to hallucinate.

**Alerts that don't wait for someone to check.** An opt-in scheduler (`RUNWAY_SCHEDULER_ENABLED=true`) re-runs the pipeline on an interval with no manual request, and any run — scheduled or a plain `POST /forecast` — that comes back risk-flagged fires a Slack message with the shortfall amount, the calendar date it triggers, and the top recommended action. A failed or unreachable webhook is logged and never fatal to the request that triggered it: pointed at a nonexistent domain and, separately, a refused connection, and both times the forecast still returned in under half a second with the webhook failure logged, not swallowed and not surfaced as a 500.

**Scoped by tenant from the start, not bolted on.** An optional `X-API-Key` header resolves to a tenant ID that scopes everything written to the history store. Skip it and you get a default tenant — nothing about calling the API without a key changes. Get the key wrong and you get a 401, not data quietly landing in someone else's history.

**A track record that checks itself.** Every run gets logged — the input snapshot, the full output — and once real time catches up to a run's 14-day horizon, `backfill_actuals()` pulls the actual outcome from later ledger data and computes the error. Nobody has to go verify old forecasts by hand for the numbers on `/stats` to mean anything.

**Does confidence actually mean anything?** `GET /calibration` is the one place the system checks its own honesty: it buckets every logged run with a known outcome by confidence level and compares error between buckets. As of this write-up, every logged run lands in the same bucket — there's nothing to compare yet — and the endpoint says exactly that instead of fabricating a verdict from a one-bucket sample:

> `"is_well_calibrated": null`, `"summary": "All 5 logged run(s) with a known outcome fall into a single confidence bucket (low), so low-vs-high error can't be compared yet."`

It would have taken one line to fake a "yes, calibrated" verdict here. It doesn't, and that's the strongest evidence in this repo that the rest of its claims are worth checking rather than taking on faith.

## What we got wrong, and how we found it

Three real bugs, with the actual numbers, not a summary of "issues encountered."

**The model's test R² was -11.40 — worse than just predicting the mean.** `cash_position` is a cumulative running sum; it only ever grows. A chronological train/test split (correct for a time series — anything else leaks future data into training) put train targets in the 55K–443K range and test targets in 434K–575K, two ranges that barely overlap, purely because later data is numerically larger. The model had no way to extrapolate to values it had never seen in training. The fix wasn't a hyperparameter: `model/dataset.py` now targets the *change* in cash position over the horizon relative to the window's last known value — a quantity that doesn't drift the same way — and `model/infer.py` adds the last known value back on so every downstream consumer still sees an absolute number. That one change alone took R² from -11.40 to +0.08. Matching model capacity to the actual dataset size (147,406 parameters against ~65 training windows, cut down to 4,350 against 735) and adding a validation split so the best epoch gets saved instead of the last one brought it to 0.4540 on the held-out test set.

**Twenty concurrent requests to `/stats` failed about 30% of the time**, with `TypeError: 'NoneType' object is not subscriptable` on a plain `SELECT COUNT(*)` — not an edge case, a query that should never fail. FastAPI runs synchronous endpoints across a thread pool, and sqlite3's `check_same_thread=False` turns off its own safety check without adding back the locking that check existed to enforce. Nothing else was serializing access to the shared connection. Fixed with an `RLock` around every method in `agent/store.py` that touches it, then reproduced the original failure mode to confirm the fix rather than just checking the error was gone: 25 concurrent `POST /forecast` requests for the same tenant, zero failures, exactly 25 new rows in the store.

**Every forecast reported low confidence, regardless of the input.** Tracing the actual numbers: `model_error_score` was computed once from two checkpoint-level constants — test RMSE (30,944.73) divided by a "typical scale" (38,164.48) — so its value, 0.1892, never moved no matter what window came in. That alone sat below the 0.5 low-confidence threshold, and since the three confidence signals combine by taking the minimum, it silently dominated every score regardless of how good the input actually was. The "typical scale" turned out to be the mean of the target's own per-step *mean* values — a central-tendency measure standing in for what should have been a spread measure to compare an error against. Swapping in an actual spread measure (the target's own standard deviation) barely moved the number — 0.1517 instead of 0.1892 — which is what confirmed the baseline itself was the wrong concept, not just the wrong array. The real fix was using the model's own held-out test R² (0.4540) directly: it's RMSE already normalized against the target's variance, the statistically correct comparison, and it was sitting in the checkpoint the whole time, unused.

**The 0.5 confidence threshold was not lowered to make that last fix look better.** The current checkpoint's R² is 0.4540 — just under 0.5 — so every window from this exact model still reports low confidence, even a synthetic input built to be as clean as real cash-flow data gets: full history, near-zero volatility. That's an honest reflection of a model that explains 45% of held-out variance. It is not a leftover bug. Lowering the threshold to, say, 0.45 would have made a demo pass and would have meant nothing. A model trained past R² 0.5 clears the threshold with zero further code changes to this file. Until then, the score at least tracks real input quality now — a wildly volatile window and a calm one now score differently — instead of being one fixed number wearing a threshold.

The frontend build turned up its own bugs, caught the same way: by looking at what actually rendered, not by trusting a passing check.

- A real rigid-body physics engine (Matter.js) turned out to be the wrong tool for "tags fall and never overlap." Three tuning rounds in, fixing tags overlapping under solver pressure reliably reintroduced tags flipping onto their edge, and fixing that made the overlap worse than before. Replaced with a plain CSS flex-wrap for the settled layout — an unconditional overlap guarantee from the browser's own layout engine — plus a spring animation per tag for the fall. It can't overlap by construction instead of by tuning.
- A CSS radial mask meant only for a background grid was fading out real content sharing its container — `mask-image` clips an element's entire rendered output, not just its `background-image`. Caught by looking at a screenshot, not by any automated check.
- Removing `Math.random()` didn't fix a framer-motion hydration mismatch, because framer-motion itself serializes inline styles with different float precision on the server render versus the client mount. Rendered the component client-only instead of chasing the library's internals.
- Windows silently corrupts non-ASCII console output when it's redirected. A CLI tool's own JSON output came out as invalid UTF-8 when piped to a file, because Python falls back to the system codepage instead of UTF-8 when stdout isn't an interactive console. Found only by checking raw bytes during a fresh-clone test, not by looking at a terminal.

## Measured model performance

From the most recently trained checkpoint (`model/checkpoints/bilstm_cashflow.pt`), evaluated on its chronological held-out test split, trained on 1,095 days of synthetic history:

| Split | RMSE | MAE | R² |
|---|---|---|---|
| Train | 29,210.03 | 23,139.58 | 0.5208 |
| **Test (held-out)** | **30,944.73** | **23,869.77** | **0.4540** |

Units are the change in cash position over the 14-day horizon, not the raw cumulative balance — see "What we got wrong" above for why. Test performance sits close to train performance: RMSE and MAE are nearly identical, the R² gap is 0.07. That's what generalizing looks like, as distinct from a model that memorized its training windows and falls apart on anything new.

Re-run `model/train.py` and update this table if the data or architecture changes.

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate synthetic transaction data (1095 days / ~3 years -- see "Measured
#    model performance" above for why the model needs this much history)
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

# 10. In a separate terminal, start the Next.js frontend (API must be
#     running; the frontend proxies to it at http://127.0.0.1:8000 by
#     default -- set BACKEND_URL before `npm run dev` if the API is
#     running somewhere else)
cd frontend
npm install
npm run dev
# open http://localhost:3000 -- the live forecast panel there works
# against the bundled sample-ledger.csv with no upload needed

# 11. Generate a batch exception report
python reports/generate_report.py --num-windows 30
```
