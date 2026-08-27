"""
Synthetic transaction generator for cash-flow forecasting.

This module simulates daily cash inflows and outflows for a mid-size business
over a configurable date range (default 90 days). It is deliberately built to
be *messy* rather than a clean toy signal, because a forecasting model trained
on noiseless data will not generalize to real bank/ledger feeds.

Noise model
-----------
Inflows (receivables):
    Each day, a base receivable amount is scheduled from an invoice issued
    `payment_delay_days` earlier (a right-skewed delay, since businesses
    rarely pay exactly on terms — most pay a few days late, a few pay very
    late). On top of the delay:
      - Partial payments: a fraction of scheduled invoices are only paid
        `partial_payment_fraction` of their value on the "due" day, with the
        remainder trickling in over the following days (modeling customers
        who pay in installments or short-pay disputed amounts).
      - Amount noise: each payment amount is perturbed by multiplicative
        Gaussian noise to reflect rounding, discounts, and FX drift.
      - Occasional missed/failed payments: a small probability that a
        scheduled receivable simply does not land on its expected day and
        is deferred further (bounced payment, banking holiday, etc.).

Outflows (payables + recurring expenses):
    - Recurring fixed costs (payroll, rent, subscriptions) hit on fixed
      cadences (e.g., payroll biweekly, rent monthly) with only small
      amount noise, since these are contractually stable.
    - Variable payables (supplier invoices, ad-hoc vendor payments) are
      generated with their own random schedule and multiplicative noise,
      similar in spirit to receivables but without the partial-payment
      behavior (a business either pays a bill or doesn't).

Seasonality:
    - Weekly seasonality: transaction volume is suppressed on weekends
      (fewer invoices issued/settled, banking cutoffs) and elevated
      slightly on Mondays/Fridays.
    - Monthly seasonality: inflows and outflows both spike around
      month-end/month-start (typical B2B invoicing and payroll cycles),
      modeled as a smooth multiplicative bump keyed to day-of-month.

The generator is seeded for reproducibility but exposes the seed as a
parameter so multiple distinct synthetic businesses can be produced.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class SyntheticDataConfig:
    """Parameters controlling the synthetic transaction generator."""

    start_date: str = "2024-01-01"
    num_days: int = 90
    seed: int = 42

    # Receivables (inflows)
    base_daily_receivable_mean: float = 18_000.0
    receivable_amount_noise_std: float = 0.12  # multiplicative std dev
    payment_delay_shape: float = 2.0  # gamma shape -> right-skewed delay
    payment_delay_scale: float = 2.5  # gamma scale, in days
    partial_payment_prob: float = 0.15
    partial_payment_fraction_mean: float = 0.55
    missed_payment_prob: float = 0.04
    missed_payment_extra_delay_days: int = 10

    # Payables / recurring expenses (outflows)
    payroll_amount: float = 42_000.0
    payroll_cadence_days: int = 14
    rent_amount: float = 9_500.0
    base_daily_payable_mean: float = 9_000.0
    payable_amount_noise_std: float = 0.10

    # Seasonality
    weekend_volume_multiplier: float = 0.35
    monday_friday_volume_multiplier: float = 1.15
    month_edge_bump_multiplier: float = 1.4


def _weekly_seasonality_multiplier(dates: pd.DatetimeIndex, config: SyntheticDataConfig) -> np.ndarray:
    """Per-date volume multiplier: suppressed on weekends, elevated on Mon/Fri."""
    weekday = dates.weekday.to_numpy()  # Monday=0 ... Sunday=6
    multiplier = np.ones(len(dates))
    multiplier[weekday >= 5] = config.weekend_volume_multiplier
    multiplier[(weekday == 0) | (weekday == 4)] = config.monday_friday_volume_multiplier
    return multiplier


def _monthly_seasonality_multiplier(dates: pd.DatetimeIndex, config: SyntheticDataConfig) -> np.ndarray:
    """Per-date volume multiplier: smooth bump near month-start/month-end."""
    day_of_month = dates.day.to_numpy()
    days_in_month = dates.days_in_month.to_numpy()
    distance_to_edge = np.minimum(day_of_month - 1, days_in_month - day_of_month)
    proximity = np.clip(1.0 - distance_to_edge / 5.0, 0.0, 1.0)
    return 1.0 + proximity * (config.month_edge_bump_multiplier - 1.0)


def _generate_receivables(dates: pd.DatetimeIndex, config: SyntheticDataConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Simulate invoice-driven inflows with delay, partial payment, and miss noise."""
    weekly = _weekly_seasonality_multiplier(dates, config)
    monthly = _monthly_seasonality_multiplier(dates, config)

    records = []
    for invoice_idx, invoice_date in enumerate(dates):
        seasonal_mean = config.base_daily_receivable_mean * weekly[invoice_idx] * monthly[invoice_idx]
        if seasonal_mean <= 0:
            continue

        scheduled_amount = rng.lognormal(
            mean=np.log(seasonal_mean), sigma=config.receivable_amount_noise_std
        )

        delay_days = rng.gamma(shape=config.payment_delay_shape, scale=config.payment_delay_scale)
        if rng.random() < config.missed_payment_prob:
            delay_days += config.missed_payment_extra_delay_days
        payment_date = invoice_date + pd.Timedelta(days=round(delay_days))

        is_partial = rng.random() < config.partial_payment_prob
        if is_partial:
            first_fraction = np.clip(
                rng.normal(config.partial_payment_fraction_mean, 0.15), 0.1, 0.9
            )
            first_amount = scheduled_amount * first_fraction
            remainder_amount = scheduled_amount - first_amount
            remainder_delay = rng.gamma(shape=1.5, scale=3.0)
            remainder_date = payment_date + pd.Timedelta(days=round(remainder_delay))

            records.append(
                {
                    "date": payment_date,
                    "type": "inflow",
                    "category": "receivable",
                    "amount": round(first_amount, 2),
                    "invoice_date": invoice_date,
                    "note": "partial_payment_installment_1",
                }
            )
            records.append(
                {
                    "date": remainder_date,
                    "type": "inflow",
                    "category": "receivable",
                    "amount": round(remainder_amount, 2),
                    "invoice_date": invoice_date,
                    "note": "partial_payment_remainder",
                }
            )
        else:
            records.append(
                {
                    "date": payment_date,
                    "type": "inflow",
                    "category": "receivable",
                    "amount": round(scheduled_amount, 2),
                    "invoice_date": invoice_date,
                    "note": "full_payment",
                }
            )

    return pd.DataFrame.from_records(records)


def _generate_recurring_expenses(dates: pd.DatetimeIndex, config: SyntheticDataConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Simulate contractually fixed outflows: payroll (biweekly) and rent (monthly)."""
    records = []

    first_date = dates[0]
    payroll_dates = pd.date_range(
        start=first_date, end=dates[-1], freq=f"{config.payroll_cadence_days}D"
    )
    for pay_date in payroll_dates:
        amount = rng.normal(config.payroll_amount, config.payroll_amount * 0.02)
        records.append(
            {
                "date": pay_date,
                "type": "outflow",
                "category": "payroll",
                "amount": round(abs(amount), 2),
                "invoice_date": pd.NaT,
                "note": "recurring_payroll",
            }
        )

    month_starts = pd.date_range(start=first_date, end=dates[-1], freq="MS")
    for month_start in month_starts:
        rent_date = month_start + pd.Timedelta(days=min(4, (dates[-1] - month_start).days))
        amount = rng.normal(config.rent_amount, config.rent_amount * 0.01)
        records.append(
            {
                "date": rent_date,
                "type": "outflow",
                "category": "rent",
                "amount": round(abs(amount), 2),
                "invoice_date": pd.NaT,
                "note": "recurring_rent",
            }
        )

    return pd.DataFrame.from_records(records)


def _generate_payables(dates: pd.DatetimeIndex, config: SyntheticDataConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Simulate variable supplier/vendor payables with weekly/monthly seasonality."""
    weekly = _weekly_seasonality_multiplier(dates, config)
    monthly = _monthly_seasonality_multiplier(dates, config)

    records = []
    for idx, bill_date in enumerate(dates):
        seasonal_mean = config.base_daily_payable_mean * weekly[idx] * monthly[idx]
        if seasonal_mean <= 0:
            continue

        amount = rng.lognormal(mean=np.log(seasonal_mean), sigma=config.payable_amount_noise_std)
        settle_delay = rng.gamma(shape=1.2, scale=1.5)
        settle_date = bill_date + pd.Timedelta(days=round(settle_delay))

        records.append(
            {
                "date": settle_date,
                "type": "outflow",
                "category": "payable",
                "amount": round(amount, 2),
                "invoice_date": bill_date,
                "note": "vendor_payment",
            }
        )

    return pd.DataFrame.from_records(records)


def generate_synthetic_transactions(config: SyntheticDataConfig | None = None) -> pd.DataFrame:
    """
    Generate a synthetic daily transaction ledger for a mid-size business.

    Returns a DataFrame with one row per transaction (not pre-aggregated by
    day), columns: date, type (inflow/outflow), category, amount,
    invoice_date, note. Multiple transactions can share the same date.
    See the module docstring for the full noise/seasonality model.
    """
    config = config or SyntheticDataConfig()
    rng = np.random.default_rng(config.seed)

    dates = pd.date_range(start=config.start_date, periods=config.num_days, freq="D")

    receivables = _generate_receivables(dates, config, rng)
    recurring_expenses = _generate_recurring_expenses(dates, config, rng)
    payables = _generate_payables(dates, config, rng)

    transactions = pd.concat(
        [receivables, recurring_expenses, payables], ignore_index=True
    )
    transactions["date"] = pd.to_datetime(transactions["date"]).dt.normalize()
    transactions = transactions.sort_values("date").reset_index(drop=True)

    return transactions[["date", "type", "category", "amount", "invoice_date", "note"]]


def main() -> None:
    """CLI entry point: generate a synthetic ledger and write it to CSV."""
    parser = argparse.ArgumentParser(description="Generate synthetic cash-flow transactions.")
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--num-days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "synthetic_transactions.csv"),
        help="Output CSV path.",
    )
    args = parser.parse_args()

    config = SyntheticDataConfig(
        start_date=args.start_date, num_days=args.num_days, seed=args.seed
    )
    transactions = generate_synthetic_transactions(config)
    transactions.to_csv(args.output, index=False)
    print(f"Wrote {len(transactions)} transactions to {args.output}")


if __name__ == "__main__":
    main()
