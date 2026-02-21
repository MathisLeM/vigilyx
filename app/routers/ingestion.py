"""
INGESTION ROUTER — Phase 2/3
==============================
Exposes endpoints to trigger and inspect Stripe data ingestion.

Endpoints:
  POST /ingestion/{tenant_id}/run
      Trigger a full ingestion cycle for a tenant.
      Uses the Stripe API key stored in tenant_configs.
      Returns an IngestionResult summary.

  GET  /ingestion/{tenant_id}/status
      Returns when data was last ingested (latest raw_balance_transaction
      created_at) and the total raw row count for this tenant.

The ingestion runs synchronously in the request handler for now.
Phase 3+ can move long-running ingestions to a background task or
Celery worker while returning a job_id immediately.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.raw_balance_transaction import RawBalanceTransaction
from app.models.tenant import Tenant
from app.routers.auth import CurrentUser, assert_tenant_access, get_current_user
from app.services.ingestion.balance_ingester import (
    DEFAULT_ACCOUNT_ID,
    IngestionResult,
    run_ingestion,
)
from app.services.ingestion.stripe_client import StripeAuthError, StripeClientError

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────

class IngestionResponse(BaseModel):
    tenant_id: int
    stripe_account_id: str
    raw_inserted: int
    raw_skipped: int
    features_written: int
    features_skipped: int
    date_range: Optional[list[str]]
    duration_seconds: Optional[float]
    error: Optional[str]


class IngestionStatus(BaseModel):
    tenant_id: int
    stripe_account_id: str
    last_ingested_at: Optional[datetime]
    total_raw_rows: int
    has_stripe_key: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id, Tenant.is_active == True
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{tenant_id}/run", response_model=IngestionResponse)
def trigger_ingestion(
    tenant_id: int,
    stripe_account_id: str = Query(DEFAULT_ACCOUNT_ID),
    force_full: bool = Query(False, description="Ignore last-ingested timestamp and pull full lookback window"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Trigger a Stripe ingestion run for a tenant.

    - Requires a Stripe API key to be saved in tenant settings first.
    - By default performs an incremental pull (from last ingested timestamp).
    - Use force_full=true to pull the full INGESTION_LOOKBACK_DAYS window.
    """
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    try:
        result: IngestionResult = run_ingestion(
            db=db,
            tenant_id=tenant_id,
            stripe_account_id=stripe_account_id,
            force_full=force_full,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except StripeAuthError as exc:
        raise HTTPException(status_code=401, detail=f"Stripe auth failed: {exc}")
    except StripeClientError as exc:
        raise HTTPException(status_code=502, detail=f"Stripe API error: {exc}")
    except Exception as exc:
        logger.exception("Unexpected ingestion error for tenant %s: %s", tenant_id, exc)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")

    d = result.to_dict()
    return IngestionResponse(**d)


@router.get("/{tenant_id}/status", response_model=IngestionStatus)
def ingestion_status(
    tenant_id: int,
    stripe_account_id: str = Query(DEFAULT_ACCOUNT_ID),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Return the current ingestion status for a tenant:
    last ingested timestamp and total raw row count.
    """
    from sqlalchemy import func
    from app.models.tenant_config import TenantConfig

    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    agg = (
        db.query(
            func.max(RawBalanceTransaction.created_at).label("last_at"),
            func.count(RawBalanceTransaction.id).label("total"),
        )
        .filter(
            RawBalanceTransaction.tenant_id == tenant_id,
            RawBalanceTransaction.stripe_account_id == stripe_account_id,
        )
        .first()
    )

    cfg = (
        db.query(TenantConfig)
        .filter(TenantConfig.tenant_id == tenant_id)
        .first()
    )
    has_key = bool(cfg and cfg.stripe_api_key)

    return IngestionStatus(
        tenant_id=tenant_id,
        stripe_account_id=stripe_account_id,
        last_ingested_at=agg.last_at if agg else None,
        total_raw_rows=agg.total if agg else 0,
        has_stripe_key=has_key,
    )
