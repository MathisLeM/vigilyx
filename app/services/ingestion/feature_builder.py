"""
FEATURE BUILDER — Phase 2 ingestion
======================================
Aggregates raw_balance_transactions into daily_revenue_metrics.

This is the canonical implementation of the RAW -> FEATURE aggregation.
It replaces the identical function in simulation/seed_demo.py (which was
a Phase 1 bootstrap; seed_demo.py will call this module in Phase 2+).

Design:
- Idempotent upsert: safe to re-run for any date range.
- Row-by-row aggregation (no SQL GROUP BY) so the logic stays easy to audit
  and extend (e.g., add new metrics) without touching SQL.
- Returns a structured IngestionSummary so callers can report results.

Called by:
  - balance_ingester.py  (after raw insert, to recompute affected dates)
  - simulation/seed_demo.py  (seeding pipeline)
  - scheduler (nightly recompute)
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.daily_revenue import DailyRevenueMetrics
from app.models.raw_balance_transaction import RawBalanceTransaction
from data_contracts.stripe_schemas import (
    DISPUTE_CATEGORIES,
    REFUND_CATEGORIES,
    REVENUE_CATEGORIES,
)

logger = logging.getLogger(__name__)


@dataclass
class FeatureBuildResult:
    rows_written: int = 0
    rows_skipped: int = 0
    date_range: tuple[date, date] | None = None


def _get_date_bounds(
    db: Session,
    tenant_id: int,
    stripe_account_id: str,
    currency: str,
) -> tuple[date, date] | None:
    """Return (min_date, max_date) of raw transactions for this scope, or None."""
    from sqlalchemy import func

    bounds = (
        db.query(
            func.min(RawBalanceTransaction.created_at),
            func.max(RawBalanceTransaction.created_at),
        )
        .filter(
            RawBalanceTransaction.tenant_id == tenant_id,
            RawBalanceTransaction.stripe_account_id == stripe_account_id,
            RawBalanceTransaction.currency == currency,
        )
        .first()
    )
    if not bounds or not bounds[0]:
        return None
    return bounds[0].date(), bounds[1].date()


def _aggregate_one_day(
    db: Session,
    tenant_id: int,
    stripe_account_id: str,
    currency: str,
    day: date,
) -> None:
    """Upsert one daily_revenue_metrics row for the given day."""
    day_start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=timezone.utc)
    day_end   = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)

    rows = (
        db.query(RawBalanceTransaction)
        .filter(
            RawBalanceTransaction.tenant_id == tenant_id,
            RawBalanceTransaction.stripe_account_id == stripe_account_id,
            RawBalanceTransaction.currency == currency,
            RawBalanceTransaction.created_at >= day_start,
            RawBalanceTransaction.created_at <= day_end,
        )
        .all()
    )

    gross_revenue  = 0
    total_fees     = 0
    net_revenue    = 0
    charge_count   = 0
    refund_amount  = 0
    refund_count   = 0
    dispute_amount = 0
    dispute_count  = 0

    for row in rows:
        cat = row.reporting_category
        amt = row.amount_usd if row.amount_usd is not None else row.amount
        fee = row.fee_usd   if row.fee_usd   is not None else row.fee
        net = row.net_usd   if row.net_usd   is not None else row.net

        if cat in REVENUE_CATEGORIES:
            gross_revenue += amt
            total_fees    += fee
            net_revenue   += net
            charge_count  += 1
        elif cat in REFUND_CATEGORIES:
            refund_amount += abs(amt)
            refund_count  += 1
        elif cat in DISPUTE_CATEGORIES:
            dispute_amount += abs(amt)
            dispute_count  += 1

    avg_charge_value = (gross_revenue // charge_count) if charge_count > 0 else None
    fee_rate         = (total_fees / gross_revenue)    if gross_revenue > 0 else None
    refund_rate      = (refund_amount / gross_revenue) if gross_revenue > 0 else None
    net_balance_change = net_revenue - refund_amount - dispute_amount

    existing = (
        db.query(DailyRevenueMetrics)
        .filter(
            DailyRevenueMetrics.tenant_id == tenant_id,
            DailyRevenueMetrics.stripe_account_id == stripe_account_id,
            DailyRevenueMetrics.currency == currency,
            DailyRevenueMetrics.snapshot_date == day,
        )
        .first()
    )

    if existing:
        obj = existing
    else:
        obj = DailyRevenueMetrics(
            tenant_id=tenant_id,
            stripe_account_id=stripe_account_id,
            currency=currency,
            snapshot_date=day,
        )
        db.add(obj)

    # Original currency columns (same as USD in Phase 2 for USD accounts)
    obj.gross_revenue    = gross_revenue
    obj.total_fees       = total_fees
    obj.net_revenue      = net_revenue
    obj.charge_count     = charge_count
    obj.avg_charge_value = avg_charge_value
    obj.fee_rate         = fee_rate

    # USD columns
    obj.gross_revenue_usd    = gross_revenue
    obj.total_fees_usd       = total_fees
    obj.net_revenue_usd      = net_revenue
    obj.avg_charge_value_usd = avg_charge_value

    # Refunds
    obj.refund_amount     = refund_amount
    obj.refund_count      = refund_count
    obj.refund_rate       = refund_rate
    obj.refund_amount_usd = refund_amount

    # Disputes
    obj.dispute_amount     = dispute_amount
    obj.dispute_count      = dispute_count
    obj.dispute_amount_usd = dispute_amount

    # Composite
    obj.net_balance_change_usd = net_balance_change
    obj.computed_at            = datetime.now(timezone.utc)


def build_daily_features(
    db: Session,
    tenant_id: int,
    stripe_account_id: str,
    currency: str = "usd",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> FeatureBuildResult:
    """
    Aggregate raw_balance_transactions -> daily_revenue_metrics for a date range.

    If start_date / end_date are omitted, derives the range from the raw table.
    Idempotent: existing rows are updated in-place (recomputable by design).

    Returns a FeatureBuildResult with counts.
    """
    result = FeatureBuildResult()

    if not start_date or not end_date:
        bounds = _get_date_bounds(db, tenant_id, stripe_account_id, currency)
        if not bounds:
            logger.info(
                "feature_builder: no raw rows for tenant=%s account=%s currency=%s",
                tenant_id, stripe_account_id, currency,
            )
            return result
        start_date, end_date = bounds

    result.date_range = (start_date, end_date)
    current = start_date

    while current <= end_date:
        try:
            _aggregate_one_day(db, tenant_id, stripe_account_id, currency, current)
            db.flush()
            result.rows_written += 1
        except IntegrityError:
            db.rollback()
            result.rows_skipped += 1
            logger.warning(
                "feature_builder: IntegrityError on %s for tenant=%s — skipped",
                current, tenant_id,
            )
        current += timedelta(days=1)

    db.commit()
    logger.info(
        "feature_builder: %d rows written, %d skipped (%s to %s) for tenant=%s",
        result.rows_written,
        result.rows_skipped,
        start_date,
        end_date,
        tenant_id,
    )
    return result
