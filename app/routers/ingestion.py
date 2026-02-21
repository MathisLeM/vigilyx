"""
INGESTION ROUTER — Phase 3
==============================
Exposes endpoints to trigger and inspect Stripe data ingestion.

Endpoints:
  POST /ingestion/{tenant_id}/run?connection_id={id}
      Trigger an ingestion cycle for a specific Stripe connection.
      Returns an IngestionResult summary.

  GET  /ingestion/{tenant_id}/status
      Returns ingestion status for each Stripe connection the tenant has:
      last ingested timestamp, total raw row count, and whether a key is set.

The ingestion runs synchronously in the request handler for now.
Phase 3+ can move long-running ingestions to a background task.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.raw_balance_transaction import RawBalanceTransaction
from app.models.stripe_connection import StripeConnection
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
    connection_id: int
    connection_name: str
    raw_inserted: int
    raw_skipped: int
    features_written: int
    features_skipped: int
    date_range: Optional[list[str]]
    duration_seconds: Optional[float]
    error: Optional[str]


class IngestionStatus(BaseModel):
    tenant_id: int
    connection_id: int
    connection_name: str
    stripe_account_id: Optional[str]
    last_ingested_at: Optional[datetime]
    total_raw_rows: int
    has_key: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id, Tenant.is_active == True
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _get_connection_or_404(conn_id: int, tenant_id: int, db: Session) -> StripeConnection:
    conn = db.query(StripeConnection).filter(
        StripeConnection.id == conn_id,
        StripeConnection.tenant_id == tenant_id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Stripe connection not found")
    return conn


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{tenant_id}/run", response_model=IngestionResponse)
def trigger_ingestion(
    tenant_id: int,
    connection_id: int = Query(..., description="ID of the StripeConnection to ingest from"),
    force_full: bool = Query(False, description="Ignore last-ingested timestamp and pull full lookback window"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Trigger a Stripe ingestion run for a specific connection belonging to this tenant.
    The connection must have an API key saved.
    """
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    connection = _get_connection_or_404(connection_id, tenant_id, db)

    try:
        result: IngestionResult = run_ingestion(
            db=db,
            tenant_id=tenant_id,
            connection=connection,
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

    return IngestionResponse(**result.to_dict())


@router.get("/{tenant_id}/status", response_model=list[IngestionStatus])
def ingestion_status(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Return ingestion status for each Stripe connection the tenant has.
    """
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    connections = (
        db.query(StripeConnection)
        .filter(StripeConnection.tenant_id == tenant_id)
        .order_by(StripeConnection.created_at)
        .all()
    )

    statuses = []
    for conn in connections:
        account_id = conn.stripe_account_id or DEFAULT_ACCOUNT_ID
        agg = (
            db.query(
                func.max(RawBalanceTransaction.created_at).label("last_at"),
                func.count(RawBalanceTransaction.id).label("total"),
            )
            .filter(
                RawBalanceTransaction.tenant_id == tenant_id,
                RawBalanceTransaction.stripe_account_id == account_id,
            )
            .first()
        )
        statuses.append(
            IngestionStatus(
                tenant_id=tenant_id,
                connection_id=conn.id,
                connection_name=conn.name,
                stripe_account_id=conn.stripe_account_id,
                last_ingested_at=agg.last_at if agg else None,
                total_raw_rows=agg.total if agg else 0,
                has_key=bool(conn.encrypted_api_key),
            )
        )

    return statuses
