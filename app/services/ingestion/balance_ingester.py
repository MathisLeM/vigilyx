"""
BALANCE INGESTER — Phase 2 ingestion
=======================================
Orchestrates a full ingestion run for one tenant:

  1. Look up the tenant's Stripe API key from tenant_configs.
  2. Determine the date range to pull (last ingested timestamp or lookback window).
  3. Stream balance_transactions from Stripe via stripe_client.
  4. Upsert each validated transaction into raw_balance_transactions (idempotent).
  5. Recompute daily_revenue_metrics for the affected date range via feature_builder.

Returns an IngestionResult dataclass that the router serialises to JSON.

Error handling:
- StripeAuthError  -> propagated so the router returns HTTP 422 (bad key).
- StripeClientError -> propagated so the router returns HTTP 502 (Stripe down).
- Any other exception -> logged and re-raised.

Stripe account_id:
  For simple (non-Connect) Stripe accounts the balance_transactions API
  returns transactions for the account that owns the API key.
  We store "__default__" as the stripe_account_id in that case.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.raw_balance_transaction import RawBalanceTransaction
from app.models.tenant_config import TenantConfig
from app.services.crypto import decrypt_key
from app.services.ingestion.feature_builder import FeatureBuildResult, build_daily_features
from app.services.ingestion.stripe_client import (
    StripeAuthError,
    StripeClientError,
    stream_balance_transactions,
)
from data_contracts.stripe_schemas import StripeBalanceTransaction

logger = logging.getLogger(__name__)

# Sentinel used when no Connect account ID is available
DEFAULT_ACCOUNT_ID = "__default__"


@dataclass
class IngestionResult:
    tenant_id: int
    stripe_account_id: str
    raw_inserted: int = 0
    raw_skipped: int = 0
    features_written: int = 0
    features_skipped: int = 0
    ingestion_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ingestion_end: Optional[datetime] = None
    date_range: Optional[tuple[date, date]] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "stripe_account_id": self.stripe_account_id,
            "raw_inserted": self.raw_inserted,
            "raw_skipped": self.raw_skipped,
            "features_written": self.features_written,
            "features_skipped": self.features_skipped,
            "date_range": (
                [str(self.date_range[0]), str(self.date_range[1])]
                if self.date_range
                else None
            ),
            "duration_seconds": (
                round((self.ingestion_end - self.ingestion_start).total_seconds(), 1)
                if self.ingestion_end
                else None
            ),
            "error": self.error,
        }


def _get_api_key(db: Session, tenant_id: int) -> str:
    """
    Retrieve the Stripe API key for a tenant from tenant_configs.
    Raises ValueError if no key is configured.
    """
    cfg = (
        db.query(TenantConfig)
        .filter(TenantConfig.tenant_id == tenant_id)
        .first()
    )
    if not cfg or not cfg.stripe_api_key:
        raise ValueError(
            f"No Stripe API key configured for tenant {tenant_id}. "
            "Add one via the Settings page."
        )
    return decrypt_key(cfg.stripe_api_key)


def _last_ingested_at(
    db: Session,
    tenant_id: int,
    stripe_account_id: str,
) -> Optional[datetime]:
    """
    Return the most recent created_at timestamp in raw_balance_transactions
    for this tenant+account, or None if there are no rows yet.
    """
    from sqlalchemy import func

    result = (
        db.query(func.max(RawBalanceTransaction.created_at))
        .filter(
            RawBalanceTransaction.tenant_id == tenant_id,
            RawBalanceTransaction.stripe_account_id == stripe_account_id,
        )
        .scalar()
    )
    return result  # datetime or None


def _insert_raw(
    db: Session,
    tenant_id: int,
    stripe_account_id: str,
    txn: StripeBalanceTransaction,
    base_currency: str = "usd",
) -> bool:
    """
    Insert one validated StripeBalanceTransaction into raw_balance_transactions.
    Returns True if inserted, False if skipped (duplicate or non-base-currency).
    """
    # Phase 2: only handle base-currency rows; skip multi-currency (Phase 3+)
    if txn.currency != base_currency:
        return False

    usd_rate  = 1.0
    amount_usd = txn.amount
    fee_usd    = txn.fee
    net_usd    = txn.net

    row = RawBalanceTransaction(
        tenant_id=tenant_id,
        stripe_account_id=stripe_account_id,
        stripe_id=txn.id,
        stripe_object=txn.object,
        amount=txn.amount,
        fee=txn.fee,
        net=txn.net,
        currency=txn.currency,
        usd_exchange_rate=usd_rate,
        amount_usd=amount_usd,
        fee_usd=fee_usd,
        net_usd=net_usd,
        type=txn.type,
        reporting_category=txn.reporting_category,
        status=txn.status,
        source_id=txn.source,
        created_at=txn.created_datetime(),
        available_on=txn.available_on_datetime(),
        description=txn.description,
        fee_details_json=json.dumps([fd.model_dump() for fd in txn.fee_details]),
        metadata_json=json.dumps(txn.metadata),
        ingestion_source="api_poll",
    )
    db.add(row)
    try:
        db.flush()
        return True
    except IntegrityError:
        db.rollback()
        return False


def run_ingestion(
    db: Session,
    tenant_id: int,
    stripe_account_id: str = DEFAULT_ACCOUNT_ID,
    force_full: bool = False,
) -> IngestionResult:
    """
    Run a full ingestion cycle for one tenant.

    Args:
        db:                 SQLAlchemy session.
        tenant_id:          Tenant to ingest for.
        stripe_account_id:  Stripe Connect account ID, or DEFAULT_ACCOUNT_ID.
        force_full:         If True, ignore the last-ingested timestamp and
                            pull the full INGESTION_LOOKBACK_DAYS window.

    Returns:
        IngestionResult with counts and metadata.

    Raises:
        ValueError:         No Stripe API key configured.
        StripeAuthError:    Invalid API key.
        StripeClientError:  Unrecoverable Stripe API error.
    """
    result = IngestionResult(
        tenant_id=tenant_id,
        stripe_account_id=stripe_account_id,
    )

    # -- 1. Get API key ---------------------------------------------------
    api_key = _get_api_key(db, tenant_id)

    # -- 2. Determine date window -----------------------------------------
    if force_full:
        created_after = None  # stripe_client defaults to INGESTION_LOOKBACK_DAYS
    else:
        last_ts = _last_ingested_at(db, tenant_id, stripe_account_id)
        if last_ts:
            # Overlap by 1 hour to catch any transactions that might have
            # arrived slightly out-of-order on Stripe's side.
            created_after = last_ts - timedelta(hours=1)
        else:
            created_after = None

    created_before = datetime.now(timezone.utc)

    logger.info(
        "Ingestion start — tenant=%s account=%s from=%s",
        tenant_id,
        stripe_account_id,
        created_after.strftime("%Y-%m-%d %H:%M") if created_after else "lookback",
    )

    # -- 3. Stream + insert raw rows --------------------------------------
    affected_dates: set[date] = set()

    for txn in stream_balance_transactions(api_key, created_after, created_before):
        inserted = _insert_raw(db, tenant_id, stripe_account_id, txn, settings.BASE_CURRENCY)
        if inserted:
            result.raw_inserted += 1
            affected_dates.add(txn.created_datetime().date())
        else:
            result.raw_skipped += 1

    db.commit()

    logger.info(
        "Raw insert done — inserted=%d skipped=%d affected_dates=%d",
        result.raw_inserted,
        result.raw_skipped,
        len(affected_dates),
    )

    # -- 4. Recompute features for affected dates -------------------------
    if affected_dates:
        min_date = min(affected_dates)
        max_date = max(affected_dates)

        feature_result: FeatureBuildResult = build_daily_features(
            db=db,
            tenant_id=tenant_id,
            stripe_account_id=stripe_account_id,
            currency=settings.BASE_CURRENCY,
            start_date=min_date,
            end_date=max_date,
        )
        result.features_written = feature_result.rows_written
        result.features_skipped = feature_result.rows_skipped
        result.date_range = (min_date, max_date)
    elif result.raw_inserted == 0:
        # No new data — still report the range we queried
        logger.info("Ingestion: no new transactions found")

    result.ingestion_end = datetime.now(timezone.utc)
    logger.info("Ingestion complete: %s", result.to_dict())
    return result
