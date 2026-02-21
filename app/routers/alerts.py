from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alert import AlertSeverity, DetectionMethod
from app.models.tenant import Tenant
from app.routers.auth import CurrentUser, assert_tenant_access, get_current_user
from app.services.alert_service import (
    generate_combo_hint,
    get_alert_stats,
    get_alerts,
    resolve_alert,
    run_detection_pipeline,
)

router = APIRouter()

_SEVERITY_ORDER = {AlertSeverity.LOW: 0, AlertSeverity.MEDIUM: 1, AlertSeverity.HIGH: 2}


# ── Response models ───────────────────────────────────────────────────────────

class AlertOut(BaseModel):
    id: int
    tenant_id: int
    stripe_account_id: Optional[str]
    snapshot_date: date
    metric_name: str
    metric_value: float
    detection_method: DetectionMethod
    score: float
    threshold: float
    direction: str
    pct_deviation: Optional[float]
    is_dual_confirmed: bool
    hint: str
    severity: AlertSeverity
    is_resolved: bool
    resolved_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyAlertGroup(BaseModel):
    """All anomalies detected on a single day, with a combo analysis."""
    snapshot_date: date
    total_alerts: int
    dual_count: int
    highest_severity: AlertSeverity
    directions: list[str]           # unique directions present ("spike", "drop")
    metrics_affected: list[str]     # unique metric names affected
    combo_hint: str                 # rule-based combo analysis
    alerts: list[AlertOut]          # individual alerts, severity desc


class RunDetectionRequest(BaseModel):
    detection_days: int = 7
    stripe_account_id: Optional[str] = None


class RunDetectionResponse(BaseModel):
    created: int
    alerts: list[AlertOut]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _merge_legacy_dual_pairs(alerts: list[AlertOut]) -> list[AlertOut]:
    """
    Backwards-compat: merge old MAD+ZSCORE pair rows (stored before the DUAL
    migration) into a single DUAL alert row.
    New DUAL rows and non-dual singles are passed through unchanged.
    """
    result: list[AlertOut] = []
    pending: dict[tuple, AlertOut] = {}

    for a in alerts:
        if a.detection_method == DetectionMethod.DUAL or not a.is_dual_confirmed:
            result.append(a)
            continue

        key = (a.snapshot_date, a.metric_name)
        if key not in pending:
            pending[key] = a
        else:
            first = pending.pop(key)
            mad = first if first.detection_method == DetectionMethod.MAD else a
            zs  = a     if first.detection_method == DetectionMethod.MAD else first
            avg_score = round((mad.score + zs.score) / 2, 4)
            avg_pct   = (
                round((mad.pct_deviation + zs.pct_deviation) / 2, 1)
                if mad.pct_deviation is not None and zs.pct_deviation is not None
                else mad.pct_deviation
            )
            result.append(mad.model_copy(update={
                "detection_method": DetectionMethod.DUAL,
                "score": avg_score,
                "pct_deviation": avg_pct,
                "is_dual_confirmed": True,
            }))

    result.extend(pending.values())
    return result


def _to_alert_out(alerts) -> list[AlertOut]:
    return _merge_legacy_dual_pairs(
        [AlertOut.model_validate(a) for a in alerts]
    )


def _build_daily_groups(alerts: list[AlertOut]) -> list[DailyAlertGroup]:
    """Group a flat list of AlertOut by snapshot_date, newest first."""
    by_date: dict[date, list[AlertOut]] = defaultdict(list)
    for a in alerts:
        by_date[a.snapshot_date].append(a)

    groups: list[DailyAlertGroup] = []
    for snap_date in sorted(by_date.keys(), reverse=True):
        day_alerts = sorted(
            by_date[snap_date],
            key=lambda a: _SEVERITY_ORDER[a.severity],
            reverse=True,
        )
        highest = max(day_alerts, key=lambda a: _SEVERITY_ORDER[a.severity]).severity
        groups.append(DailyAlertGroup(
            snapshot_date=snap_date,
            total_alerts=len(day_alerts),
            dual_count=sum(1 for a in day_alerts if a.detection_method == DetectionMethod.DUAL),
            highest_severity=highest,
            directions=sorted({a.direction for a in day_alerts}),
            metrics_affected=sorted({a.metric_name for a in day_alerts}),
            combo_hint=generate_combo_hint(day_alerts),
            alerts=day_alerts,
        ))
    return groups


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{tenant_id}/daily", response_model=list[DailyAlertGroup])
def list_daily_groups(
    tenant_id: int,
    resolved: Optional[bool] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    stripe_account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Return alerts grouped by date, newest first.
    Each group includes a combo-analysis hint for the day's anomaly pattern.
    """
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    raw = get_alerts(
        db, tenant_id, resolved=resolved, start=start_date, end=end_date,
        stripe_account_id=stripe_account_id,
    )
    flat = _to_alert_out(raw)
    return _build_daily_groups(flat)


@router.get("/{tenant_id}/", response_model=list[AlertOut])
def list_alerts(
    tenant_id: int,
    resolved: Optional[bool] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    stripe_account_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    raw = get_alerts(
        db, tenant_id, resolved=resolved, start=start_date, end=end_date,
        stripe_account_id=stripe_account_id,
    )
    return _to_alert_out(raw)


@router.post("/{tenant_id}/run-detection", response_model=RunDetectionResponse)
def trigger_detection(
    tenant_id: int,
    payload: RunDetectionRequest = RunDetectionRequest(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    new_alerts = run_detection_pipeline(
        db, tenant_id,
        detection_days=payload.detection_days,
        stripe_account_id=payload.stripe_account_id,
    )
    merged = _to_alert_out(new_alerts)
    return RunDetectionResponse(created=len(merged), alerts=merged)


@router.patch("/{tenant_id}/{alert_id}/resolve", response_model=AlertOut)
def resolve(
    tenant_id: int,
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    alert = resolve_alert(db, alert_id, tenant_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertOut.model_validate(alert)


@router.get("/{tenant_id}/stats")
def alert_stats(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    return get_alert_stats(db, tenant_id)
