from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.routers.auth import CurrentUser, assert_tenant_access, get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_key(key: str) -> str:
    """sk_test_abcdefghijklmnop  →  sk_test_••••••••mnop"""
    if len(key) <= 8:
        return "••••••••"
    return key[:8] + "••••••••" + key[-4:]


def _get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _get_or_create_config(tenant_id: int, db: Session) -> TenantConfig:
    cfg = db.query(TenantConfig).filter(TenantConfig.tenant_id == tenant_id).first()
    if not cfg:
        cfg = TenantConfig(tenant_id=tenant_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConfigOut(BaseModel):
    tenant_id: int
    has_stripe_key: bool
    stripe_key_masked: Optional[str]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SaveKeyRequest(BaseModel):
    stripe_api_key: str


class TestResult(BaseModel):
    success: bool
    message: str
    account_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}", response_model=ConfigOut)
def get_config(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    cfg = _get_or_create_config(tenant_id, db)
    return ConfigOut(
        tenant_id=tenant_id,
        has_stripe_key=bool(cfg.stripe_api_key),
        stripe_key_masked=_mask_key(cfg.stripe_api_key) if cfg.stripe_api_key else None,
        updated_at=cfg.updated_at,
    )


@router.put("/{tenant_id}", response_model=ConfigOut)
def save_config(
    tenant_id: int,
    payload: SaveKeyRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    key = payload.stripe_api_key.strip()
    if not key.startswith(("sk_test_", "sk_live_")):
        raise HTTPException(
            status_code=422,
            detail="Invalid Stripe key — must start with sk_test_ or sk_live_",
        )
    cfg = _get_or_create_config(tenant_id, db)
    cfg.stripe_api_key = key
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)
    return ConfigOut(
        tenant_id=tenant_id,
        has_stripe_key=True,
        stripe_key_masked=_mask_key(key),
        updated_at=cfg.updated_at,
    )


@router.delete("/{tenant_id}/stripe-key", response_model=ConfigOut)
def delete_stripe_key(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    cfg = _get_or_create_config(tenant_id, db)
    cfg.stripe_api_key = None
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    return ConfigOut(
        tenant_id=tenant_id,
        has_stripe_key=False,
        stripe_key_masked=None,
        updated_at=cfg.updated_at,
    )


@router.post("/{tenant_id}/test-stripe", response_model=TestResult)
def test_stripe_connection(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    cfg = _get_or_create_config(tenant_id, db)
    if not cfg.stripe_api_key:
        raise HTTPException(status_code=400, detail="No Stripe API key configured")

    try:
        r = httpx.get(
            "https://api.stripe.com/v1/account",
            headers={"Authorization": f"Bearer {cfg.stripe_api_key}"},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            name = data.get("business_profile", {}).get("name") or data.get("email") or "—"
            return TestResult(success=True, message="Connection successful", account_name=name)
        elif r.status_code == 401:
            return TestResult(success=False, message="Invalid API key — authentication failed")
        else:
            return TestResult(success=False, message=f"Stripe returned status {r.status_code}")
    except httpx.TimeoutException:
        return TestResult(success=False, message="Request timed out — check your network")
    except Exception as e:
        return TestResult(success=False, message=f"Connection error: {str(e)}")
