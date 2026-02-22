"""
METRICS ROUTER
===============
Serves daily_revenue_metrics to the frontend.

Replaces the old /kpis/ router.
All monetary values are returned as DOLLARS (float) — cents divided by 100 —
so the frontend doesn't need to know about the internal cents representation.
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_revenue import DailyRevenueMetrics
from app.models.tenant import Tenant
from app.routers.auth import CurrentUser, assert_tenant_access, get_current_user

router = APIRouter()


# ── Response schema ───────────────────────────────────────────────────────────

class DailyMetricSnapshot(BaseModel):
    """
    One day of aggregated revenue metrics, returned to the frontend.
    All monetary values are in DOLLARS (float), not cents.
    """
    model_config = {"from_attributes": True}

    id: int
    tenant_id: int
    stripe_account_id: str
    currency: str
    snapshot_date: date

    # Revenue
    gross_revenue_usd: float
    net_revenue_usd: float
    charge_count: int
    avg_charge_value_usd: Optional[float]
    fee_rate: Optional[float]           # 0.0 – 1.0

    # Refunds
    refund_amount_usd: float
    refund_rate: Optional[float]        # 0.0 – 1.0

    # Disputes
    dispute_amount_usd: float

    # Composite
    net_balance_change_usd: Optional[float]

    computed_at: datetime

    @model_validator(mode="before")
    @classmethod
    def convert_cents_to_dollars(cls, data):
        """Convert integer cents fields to dollar floats before validation."""
        if hasattr(data, "__dict__"):
            # ORM object — convert cents columns
            obj = data
            return {
                "id": obj.id,
                "tenant_id": obj.tenant_id,
                "stripe_account_id": obj.stripe_account_id,
                "currency": obj.currency,
                "snapshot_date": obj.snapshot_date,
                "gross_revenue_usd": (obj.gross_revenue_usd or 0) / 100,
                "net_revenue_usd": (obj.net_revenue_usd or 0) / 100,
                "charge_count": obj.charge_count,
                "avg_charge_value_usd": (obj.avg_charge_value_usd / 100) if obj.avg_charge_value_usd else None,
                "fee_rate": obj.fee_rate,
                "refund_amount_usd": (obj.refund_amount_usd or 0) / 100,
                "refund_rate": obj.refund_rate,
                "dispute_amount_usd": (obj.dispute_amount_usd or 0) / 100,
                "net_balance_change_usd": (obj.net_balance_change_usd / 100) if obj.net_balance_change_usd is not None else None,
                "computed_at": obj.computed_at,
            }
        return data


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id, Tenant.is_active == True
    ).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{tenant_id}/snapshots", response_model=list[DailyMetricSnapshot])
def list_snapshots(
    tenant_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    currency: str = "usd",
    stripe_account_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Return daily revenue metrics for a tenant within a date range.
    Results are sorted ascending by date (oldest first).
    """
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    query = db.query(DailyRevenueMetrics).filter(
        DailyRevenueMetrics.tenant_id == tenant_id,
        DailyRevenueMetrics.currency == currency,
    )
    if stripe_account_id:
        query = query.filter(DailyRevenueMetrics.stripe_account_id == stripe_account_id)
    if start_date:
        query = query.filter(DailyRevenueMetrics.snapshot_date >= start_date)
    if end_date:
        query = query.filter(DailyRevenueMetrics.snapshot_date <= end_date)

    rows = query.order_by(DailyRevenueMetrics.snapshot_date.asc()).all()
    return [DailyMetricSnapshot.model_validate(r) for r in rows]


@router.get("/{tenant_id}/latest", response_model=Optional[DailyMetricSnapshot])
def latest_snapshot(
    tenant_id: int,
    currency: str = "usd",
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the most recent daily metric row for a tenant."""
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    row = (
        db.query(DailyRevenueMetrics)
        .filter(
            DailyRevenueMetrics.tenant_id == tenant_id,
            DailyRevenueMetrics.currency == currency,
        )
        .order_by(DailyRevenueMetrics.snapshot_date.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No metrics found")
    return DailyMetricSnapshot.model_validate(row)
