"""
Persistent history store for forecast runs.

Every /forecast call (when wired with a store — see agent/wrapper.py's
optional `store` parameter) is logged here: a snapshot of the input, the
full agent output, and — once enough real time has passed that a later
run's data covers this run's forecast horizon — the actual outcome and
forecast error, computed retroactively by backfill_actuals(). This is
what turns a stateless "here's a forecast" into "here's a forecast, and
here's our track record of being right."

Plain sqlite3 (stdlib), no ORM: the schema is small and stable enough
that an ORM would add indirection without buying anything here.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from .schema import ForecastOutput
except ImportError:  # running as a top-level script rather than a package
    from schema import ForecastOutput

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "store.db"
DEFAULT_TENANT_ID = "default"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    horizon INTEGER NOT NULL,
    horizon_end_date TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    forecast_json TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    is_low_confidence INTEGER NOT NULL,
    confidence_reasons_json TEXT NOT NULL,
    risk_flag INTEGER NOT NULL,
    risk_reason TEXT,
    contributing_line_items_json TEXT NOT NULL,
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    actual_cash_position_json TEXT,
    forecast_error_json TEXT,
    error_rmse REAL,
    error_mae REAL,
    error_computed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_tenant ON forecast_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_runs_horizon_end ON forecast_runs(tenant_id, horizon_end_date);
"""


@dataclass
class RunRecord:
    """One logged forecast run, as read back from the store."""

    id: int
    tenant_id: str
    run_at: str
    as_of_date: str
    horizon: int
    horizon_end_date: str
    input_snapshot: dict
    output: dict  # the ForecastOutput fields, as stored
    actual_cash_position: list[float] | None
    forecast_error: list[float] | None
    error_rmse: float | None
    error_mae: float | None
    error_computed_at: str | None


def summarize_transactions(transactions: pd.DataFrame) -> dict:
    """Build a compact input snapshot for the run log: enough to audit
    what the run actually saw, without duplicating the full ledger on
    every single run (which would bloat the store fast on a schedule)."""
    dated = transactions.copy()
    dated["date"] = pd.to_datetime(dated["date"])
    inflow_total = float(dated.loc[dated["type"] == "inflow", "amount"].sum())
    outflow_total = float(dated.loc[dated["type"] == "outflow", "amount"].sum())
    return {
        "num_transactions": int(len(dated)),
        "date_range_start": dated["date"].min().date().isoformat(),
        "date_range_end": dated["date"].max().date().isoformat(),
        "total_inflow": round(inflow_total, 2),
        "total_outflow": round(outflow_total, 2),
    }


class ForecastStore:
    """SQLite-backed log of forecast runs, scoped by tenant_id.

    One connection is shared across every request (FastAPI runs each sync
    endpoint in a threadpool worker, so multiple threads call into this
    class concurrently). sqlite3's own docs are explicit that
    check_same_thread=False requires the caller to serialize access to the
    connection itself -- it does not do that for you. `self._lock` (an
    RLock, since backfill_actuals calls into the same connection from
    within one already-locked call) guards every method that touches
    `self._conn`. Without it, concurrent requests intermittently raised
    `TypeError: 'NoneType' object is not subscriptable` on a plain
    `SELECT COUNT(*)` -- reproduced with 20 concurrent requests to /stats,
    ~30% failure rate, before this fix.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a database file may already exist
        on disk. SQLite's ADD COLUMN has no IF NOT EXISTS, so each is
        attempted and a "duplicate column" failure is treated as already-
        migrated rather than an error."""
        for statement in ("ALTER TABLE forecast_runs ADD COLUMN recommendations_json TEXT NOT NULL DEFAULT '[]'",):
            try:
                self._conn.execute(statement)
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

    def log_run(
        self,
        tenant_id: str,
        as_of_date: date,
        horizon: int,
        input_snapshot: dict,
        output: ForecastOutput,
    ) -> int:
        """Record one forecast run. Returns the new row's id."""
        horizon_end_date = as_of_date + timedelta(days=horizon)
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO forecast_runs (
                    tenant_id, run_at, as_of_date, horizon, horizon_end_date,
                    input_snapshot_json, forecast_json, confidence_score,
                    is_low_confidence, confidence_reasons_json, risk_flag,
                    risk_reason, contributing_line_items_json, recommendations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    datetime.now(timezone.utc).isoformat(),
                    as_of_date.isoformat(),
                    horizon,
                    horizon_end_date.isoformat(),
                    json.dumps(input_snapshot),
                    json.dumps(output.forecast),
                    output.confidence.score,
                    int(output.confidence.is_low_confidence),
                    json.dumps(output.confidence.reasons),
                    int(output.risk_flag),
                    output.risk_reason,
                    json.dumps([item.model_dump(mode="json") for item in output.contributing_line_items]),
                    json.dumps([rec.model_dump(mode="json") for rec in output.recommendations]),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def backfill_actuals(self, tenant_id: str, daily: pd.DataFrame) -> int:
        """For every logged run whose forecast horizon has now fully
        elapsed within `daily` (real transaction data, aggregated by
        model.dataset.build_daily_features), and which hasn't been
        backfilled yet, compute the actual cash_position for each
        forecasted day and the resulting forecast error. Returns the
        number of runs backfilled.
        """
        daily_by_date = {ts.date(): float(pos) for ts, pos in zip(daily["date"], daily["cash_position"])}
        if not daily_by_date:
            return 0
        latest_available_date = max(daily_by_date)

        with self._lock:
            rows = self._conn.execute(
                "SELECT id, as_of_date, horizon, forecast_json FROM forecast_runs "
                "WHERE tenant_id = ? AND actual_cash_position_json IS NULL",
                (tenant_id,),
            ).fetchall()

            backfilled = 0
            for run_id, as_of_str, horizon, forecast_json in rows:
                as_of = date.fromisoformat(as_of_str)
                horizon_dates = [as_of + timedelta(days=i) for i in range(1, horizon + 1)]
                if horizon_dates[-1] > latest_available_date:
                    continue  # this run's horizon hasn't fully elapsed yet
                if not all(d in daily_by_date for d in horizon_dates):
                    continue  # gap in daily data; skip rather than guess

                actual = [daily_by_date[d] for d in horizon_dates]
                forecast = json.loads(forecast_json)
                errors = [a - f for a, f in zip(actual, forecast)]
                rmse = float(np.sqrt(np.mean(np.square(errors))))
                mae = float(np.mean(np.abs(errors)))

                self._conn.execute(
                    "UPDATE forecast_runs SET actual_cash_position_json = ?, forecast_error_json = ?, "
                    "error_rmse = ?, error_mae = ?, error_computed_at = ? WHERE id = ?",
                    (
                        json.dumps(actual),
                        json.dumps(errors),
                        rmse,
                        mae,
                        datetime.now(timezone.utc).isoformat(),
                        run_id,
                    ),
                )
                backfilled += 1

            self._conn.commit()
            return backfilled

    def get_summary_counts(self, tenant_id: str) -> tuple[int, int]:
        """(total_runs, risk_flagged_runs) for this tenant -- the two
        simplest, most honest track-record numbers: how many forecasts
        have actually been run, and how many came back flagged."""
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM forecast_runs WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()[0]
            flagged = self._conn.execute(
                "SELECT COUNT(*) FROM forecast_runs WHERE tenant_id = ? AND risk_flag = 1", (tenant_id,)
            ).fetchone()[0]
        return int(total), int(flagged)

    def get_verified_forecast_actual_pairs(self, tenant_id: str) -> list[dict]:
        """Every run for this tenant with a known actual outcome, as
        {"forecast", "actual"} dicts (each a list[float]) -- the shape
        agent.stats needs to compute directional accuracy."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT forecast_json, actual_cash_position_json FROM forecast_runs "
                "WHERE tenant_id = ? AND actual_cash_position_json IS NOT NULL",
                (tenant_id,),
            ).fetchall()
        return [{"forecast": json.loads(f), "actual": json.loads(a)} for f, a in rows]

    def get_runs_with_errors(self, tenant_id: str) -> list[dict]:
        """Every run for this tenant with a known actual outcome, as
        {"confidence_score", "is_low_confidence", "error_rmse", "error_mae"}
        dicts — the shape agent.calibration needs."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT confidence_score, is_low_confidence, error_rmse, error_mae "
                "FROM forecast_runs WHERE tenant_id = ? AND error_rmse IS NOT NULL",
                (tenant_id,),
            ).fetchall()
        return [
            {
                "confidence_score": row[0],
                "is_low_confidence": bool(row[1]),
                "error_rmse": row[2],
                "error_mae": row[3],
            }
            for row in rows
        ]

    def list_runs(self, tenant_id: str, limit: int = 50) -> list[RunRecord]:
        """Most recent runs for this tenant, newest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, tenant_id, run_at, as_of_date, horizon, horizon_end_date, "
                "input_snapshot_json, forecast_json, confidence_score, is_low_confidence, "
                "confidence_reasons_json, risk_flag, risk_reason, contributing_line_items_json, "
                "recommendations_json, actual_cash_position_json, forecast_error_json, "
                "error_rmse, error_mae, error_computed_at "
                "FROM forecast_runs WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        records = []
        for row in rows:
            records.append(
                RunRecord(
                    id=row[0],
                    tenant_id=row[1],
                    run_at=row[2],
                    as_of_date=row[3],
                    horizon=row[4],
                    horizon_end_date=row[5],
                    input_snapshot=json.loads(row[6]),
                    output={
                        "forecast": json.loads(row[7]),
                        "confidence": {
                            "score": row[8],
                            "is_low_confidence": bool(row[9]),
                            "reasons": json.loads(row[10]),
                        },
                        "risk_flag": bool(row[11]),
                        "risk_reason": row[12],
                        "contributing_line_items": json.loads(row[13]),
                        "recommendations": json.loads(row[14]),
                    },
                    actual_cash_position=json.loads(row[15]) if row[15] else None,
                    forecast_error=json.loads(row[16]) if row[16] else None,
                    error_rmse=row[17],
                    error_mae=row[18],
                    error_computed_at=row[19],
                )
            )
        return records

    def close(self) -> None:
        self._conn.close()
