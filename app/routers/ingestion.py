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
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_revenue import DailyRevenueMetrics
from app.models.raw_balance_transaction import RawBalanceTransaction
from app.models.stripe_connection import StripeConnection
from app.models.tenant import Tenant
from app.routers.auth import CurrentUser, assert_tenant_access, get_current_user
from app.services.detection.account_trainer import (
    MIN_DAYS_FOR_TRAINING,
    model_exists,
    read_model_meta,
    train_account_model,
)
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


class ModelStatus(BaseModel):
    connection_id: int
    connection_name: str
    stripe_account_id: Optional[str]
    days_available: int        # total daily_revenue_metrics rows for this account
    first_date: Optional[date]
    last_date: Optional[date]
    has_enough_data: bool      # days_available >= MIN_DAYS_FOR_TRAINING
    has_model: bool            # .pkl file exists on disk
    trained_at: Optional[datetime]
    model_type: str            # "custom" | "base"


class TrainResult(BaseModel):
    status: str                # "trained" | "not_enough_data"
    days_available: int
    first_date: Optional[date]
    last_date: Optional[date]
    trained_at: Optional[datetime]
    model_path: Optional[str]


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


@router.get("/{tenant_id}/model-status", response_model=list[ModelStatus])
def model_status(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Return AI model status for each Stripe connection.
    Includes data availability from daily_revenue_metrics and
    whether a trained account model exists on disk.
    """
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    connections = (
        db.query(StripeConnection)
        .filter(StripeConnection.tenant_id == tenant_id)
        .order_by(StripeConnection.created_at)
        .all()
    )

    result = []
    for conn in connections:
        if not conn.stripe_account_id:
            # Not yet tested — no data, no model
            result.append(ModelStatus(
                connection_id=conn.id,
                connection_name=conn.name,
                stripe_account_id=None,
                days_available=0,
                first_date=None,
                last_date=None,
                has_enough_data=False,
                has_model=False,
                trained_at=None,
                model_type="base",
            ))
            continue

        # Count daily feature rows for this account
        agg = (
            db.query(
                func.count(DailyRevenueMetrics.id).label("n_days"),
                func.min(DailyRevenueMetrics.snapshot_date).label("first_date"),
                func.max(DailyRevenueMetrics.snapshot_date).label("last_date"),
            )
            .filter(
                DailyRevenueMetrics.tenant_id == tenant_id,
                DailyRevenueMetrics.stripe_account_id == conn.stripe_account_id,
            )
            .first()
        )
        days_available = agg.n_days if agg else 0
        first_date = agg.first_date if agg else None
        last_date = agg.last_date if agg else None

        # Check disk for model + metadata
        has_model = model_exists(conn.stripe_account_id)
        meta = read_model_meta(conn.stripe_account_id) if has_model else None
        trained_at = None
        if meta and meta.get("trained_at"):
            try:
                trained_at = datetime.fromisoformat(meta["trained_at"])
            except Exception:
                pass

        result.append(ModelStatus(
            connection_id=conn.id,
            connection_name=conn.name,
            stripe_account_id=conn.stripe_account_id,
            days_available=days_available,
            first_date=first_date,
            last_date=last_date,
            has_enough_data=days_available >= MIN_DAYS_FOR_TRAINING,
            has_model=has_model,
            trained_at=trained_at,
            model_type="custom" if has_model else "base",
        ))

    return result


@router.post("/{tenant_id}/train", response_model=TrainResult)
def trigger_training(
    tenant_id: int,
    connection_id: int = Query(..., description="ID of the StripeConnection to train a model for"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Train (or retrain) a per-account Isolation Forest model for a specific
    Stripe connection. The connection must have been tested (stripe_account_id set).
    Requires at least 30 days of daily_revenue_metrics data.
    """
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    conn = _get_connection_or_404(connection_id, tenant_id, db)

    if not conn.stripe_account_id:
        raise HTTPException(
            status_code=422,
            detail="Connection has not been tested yet — stripe_account_id is unknown. "
                   "Use 'Test connection' in Settings first.",
        )

    # Data availability check (for the response — trainer also checks internally)
    agg = (
        db.query(
            func.count(DailyRevenueMetrics.id).label("n_days"),
            func.min(DailyRevenueMetrics.snapshot_date).label("first_date"),
            func.max(DailyRevenueMetrics.snapshot_date).label("last_date"),
        )
        .filter(
            DailyRevenueMetrics.tenant_id == tenant_id,
            DailyRevenueMetrics.stripe_account_id == conn.stripe_account_id,
        )
        .first()
    )
    days_available = agg.n_days if agg else 0
    first_date = agg.first_date if agg else None
    last_date = agg.last_date if agg else None

    try:
        meta = train_account_model(db, tenant_id, conn.stripe_account_id)
    except Exception as exc:
        logger.exception(
            "Training error for tenant=%s connection=%s: %s", tenant_id, conn.name, exc
        )
        raise HTTPException(status_code=500, detail=f"Training failed: {exc}")

    if meta is None:
        return TrainResult(
            status="not_enough_data",
            days_available=days_available,
            first_date=first_date,
            last_date=last_date,
            trained_at=None,
            model_path=None,
        )

    trained_at = None
    if meta.get("trained_at"):
        try:
            trained_at = datetime.fromisoformat(meta["trained_at"])
        except Exception:
            pass

    return TrainResult(
        status="trained",
        days_available=days_available,
        first_date=first_date,
        last_date=last_date,
        trained_at=trained_at,
        model_path=meta.get("model_path"),
    )
