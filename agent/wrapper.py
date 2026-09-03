"""
Agent layer: wraps the model's raw forecast + confidence into the strict
ForecastOutput schema, adds shortfall risk detection and contributing
line-item attribution, and enforces the schema with a bounded retry loop.

Forecast generation here is deterministic (no LLM sampling), so a schema
validation failure means the *pipeline* produced a malformed result — bad
input data, a NaN forecast, an edge case in the line-item attribution —
rather than "the model guessed wrong." build_forecast_output() re-runs the
full build on failure up to `max_retries` times before raising, so a
transient issue has a chance to clear before the caller sees a hard error.
Once retries are exhausted, it raises rather than returning an unvalidated
result — nothing downstream ever sees a payload that skipped the schema.

Persistence is opt-in: pass `store=` (an agent.store.ForecastStore) to log
the run and retroactively backfill actual outcomes for earlier runs whose
forecast horizon has now elapsed. Callers that don't pass a store (the
batch report tool, ad-hoc scripts) get identical behavior to before —
nothing about existing usage changes.

Usage:
    python agent/wrapper.py --shortfall-threshold 6000000
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.dataset import build_daily_features  # noqa: E402
from model.infer import CashFlowForecaster, ForecastResult  # noqa: E402

try:
    from .recommendations import generate_recommendations
    from .risk import check_shortfall_risk, identify_contributing_line_items
    from .schema import ConfidenceInfo, ForecastOutput
    from .store import DEFAULT_TENANT_ID, ForecastStore, summarize_transactions
except ImportError:  # running as a top-level script rather than a package
    from recommendations import generate_recommendations
    from risk import check_shortfall_risk, identify_contributing_line_items
    from schema import ConfidenceInfo, ForecastOutput
    from store import DEFAULT_TENANT_ID, ForecastStore, summarize_transactions


class ForecastValidationError(RuntimeError):
    """Raised when agent output still fails schema validation after all retries."""


def build_forecast_output(
    forecaster: CashFlowForecaster,
    transactions: pd.DataFrame,
    shortfall_threshold: float,
    max_retries: int = 3,
    store: ForecastStore | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> ForecastOutput:
    """Run inference, attach risk flagging + contributing line items, and
    validate the result against ForecastOutput — retrying on failure.

    `transactions` is a DataFrame already in memory (date, type, category,
    amount, ...) — callers reading from a CSV or an API request body both
    parse into this same shape first.

    If `store` is given, this run is logged (see agent.store.ForecastStore
    .log_run) and any earlier logged runs for `tenant_id` whose forecast
    horizon has now fully elapsed within this call's `transactions` get
    their actual outcome backfilled — this is how "here's a forecast"
    becomes "here's a forecast, and here's our track record."
    """
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result: ForecastResult = forecaster.predict_from_dataframe(transactions)

            transactions = transactions.copy()
            transactions["date"] = pd.to_datetime(transactions["date"])
            as_of_date = transactions["date"].max()

            risk_flag, risk_reason, _ = check_shortfall_risk(result.forecast, shortfall_threshold)

            contributing_line_items = []
            recommendations = []
            if risk_flag:
                contributing_line_items = identify_contributing_line_items(
                    transactions=transactions,
                    as_of_date=as_of_date,
                    horizon=forecaster.horizon,
                    lookback=forecaster.lookback,
                )
                recommendations = generate_recommendations(
                    forecast=[float(v) for v in result.forecast],
                    contributing_line_items=contributing_line_items,
                    transactions=transactions,
                    as_of_date=as_of_date,
                    lookback=forecaster.lookback,
                )

            candidate = ForecastOutput(
                forecast=[float(v) for v in result.forecast],
                confidence=ConfidenceInfo(
                    score=result.confidence.score,
                    is_low_confidence=result.confidence.is_low_confidence,
                    reasons=result.confidence.reasons,
                ),
                risk_flag=risk_flag,
                risk_reason=risk_reason,
                contributing_line_items=contributing_line_items,
                recommendations=recommendations,
            )

            if store is not None:
                store.log_run(
                    tenant_id=tenant_id,
                    as_of_date=as_of_date.date(),
                    horizon=forecaster.horizon,
                    input_snapshot=summarize_transactions(transactions),
                    output=candidate,
                )
                daily = build_daily_features(transactions)
                store.backfill_actuals(tenant_id=tenant_id, daily=daily)

            return candidate

        except (ValidationError, ValueError) as exc:
            last_error = exc
            continue

    raise ForecastValidationError(
        f"forecast output failed schema validation after {max_retries} attempts: {last_error}"
    ) from last_error


def main() -> None:
    """CLI entry point: run the full agent pipeline once against a CSV
    ledger and print the validated ForecastOutput as JSON."""
    import argparse
    import sys as _sys

    # Recommendation descriptions (agent/recommendations.py) legitimately
    # contain an em dash for readability. Found via a fresh-clone test on
    # Windows: with stdout redirected to a file, Python falls back to the
    # system codepage (cp1252) instead of UTF-8, which can't represent that
    # character -- the CLI's own JSON output came out with a single 0x97
    # byte in place of the dash, invalid UTF-8, unparseable by any
    # downstream `json.load()`. Forcing UTF-8 here fixes the actual output,
    # not just how it happens to look in one terminal.
    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run the agent layer's risk-flagging forecast wrapper.")
    parser.add_argument("--data-csv", default=str(PROJECT_ROOT / "data" / "synthetic_transactions.csv"))
    parser.add_argument(
        "--checkpoint", default=str(PROJECT_ROOT / "model" / "checkpoints" / "bilstm_cashflow.pt")
    )
    parser.add_argument("--shortfall-threshold", type=float, required=True)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    # Every other entry point into this pipeline degrades cleanly on bad
    # input: the API returns 422 (Pydantic rejects an empty transaction
    # list before this code ever runs), the frontend shows a specific
    # message, the scheduler logs and skips the tick. The CLI had no such
    # handling -- a missing file or a header-only/empty CSV surfaced as a
    # raw Python traceback instead of a one-line, actionable error.
    try:
        transactions = pd.read_csv(args.data_csv)
    except (FileNotFoundError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        print(f"Couldn't read '{args.data_csv}' as a transaction ledger CSV: {exc}", file=_sys.stderr)
        raise SystemExit(1) from None

    forecaster = CashFlowForecaster(args.checkpoint)
    try:
        output = build_forecast_output(
            forecaster=forecaster,
            transactions=transactions,
            shortfall_threshold=args.shortfall_threshold,
            max_retries=args.max_retries,
        )
    except ForecastValidationError as exc:
        print(f"Forecast pipeline failed: {exc}", file=_sys.stderr)
        raise SystemExit(1) from None

    print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
