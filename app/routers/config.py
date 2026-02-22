from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.stripe_connection import MAX_CONNECTIONS_PER_TENANT, StripeConnection
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.routers.auth import CurrentUser, assert_tenant_access, get_current_user
from app.services.crypto import decrypt_key, encrypt_key
from app.services.slack_notifier import VALID_LEVELS, send_test_message

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLACK_WEBHOOK_PREFIX = "https://hooks.slack.com/services/"


def _mask_key(key: str) -> str:
    """sk_test_abcdefghijklmnop  ->  sk_test_........mnop"""
    if len(key) <= 8:
        return "........"
    return key[:8] + "........" + key[-4:]


def _mask_webhook(url: str) -> str:
    """Mask the token segments of a Slack webhook URL."""
    if url.startswith(_SLACK_WEBHOOK_PREFIX):
        return _SLACK_WEBHOOK_PREFIX + "T.../B.../••••••••"
    return url[:30] + "••••••••" if len(url) > 30 else "••••••••"


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


def _get_connection_or_404(conn_id: int, tenant_id: int, db: Session) -> StripeConnection:
    conn = db.query(StripeConnection).filter(
        StripeConnection.id == conn_id,
        StripeConnection.tenant_id == tenant_id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Stripe connection not found")
    return conn


def _plaintext_webhook(cfg: TenantConfig) -> Optional[str]:
    """Return the decrypted Slack webhook URL, or None if not set."""
    if not cfg.slack_webhook_url:
        return None
    try:
        return decrypt_key(cfg.slack_webhook_url)
    except Exception:
        return None


def _decrypt_conn_key(conn: StripeConnection) -> Optional[str]:
    """Return the decrypted API key for a StripeConnection, or None."""
    if not conn.encrypted_api_key:
        return None
    try:
        return decrypt_key(conn.encrypted_api_key)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StripeConnectionOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    has_key: bool
    stripe_account_id: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class CreateConnectionRequest(BaseModel):
    name: str
    stripe_api_key: str


class UpdateConnectionRequest(BaseModel):
    name: Optional[str] = None
    stripe_api_key: Optional[str] = None


class TestResult(BaseModel):
    success: bool
    message: str
    account_name: Optional[str] = None
    stripe_account_id: Optional[str] = None


class SlackConfigOut(BaseModel):
    tenant_id: int
    has_slack_webhook: bool
    slack_webhook_masked: Optional[str]
    slack_alert_level: Optional[str]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SaveSlackRequest(BaseModel):
    webhook_url: str
    alert_level: str  # HIGH | MEDIUM_AND_HIGH | ALL


# ---------------------------------------------------------------------------
# Stripe connection endpoints
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/stripe-connections", response_model=list[StripeConnectionOut])
def list_stripe_connections(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    connections = (
        db.query(StripeConnection)
        .filter(StripeConnection.tenant_id == tenant_id)
        .order_by(StripeConnection.created_at)
        .all()
    )
    return [
        StripeConnectionOut(
            id=c.id,
            tenant_id=c.tenant_id,
            name=c.name,
            has_key=bool(c.encrypted_api_key),
            stripe_account_id=c.stripe_account_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in connections
    ]


@router.post("/{tenant_id}/stripe-connections", response_model=StripeConnectionOut, status_code=201)
def add_stripe_connection(
    tenant_id: int,
    payload: CreateConnectionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    count = db.query(StripeConnection).filter(StripeConnection.tenant_id == tenant_id).count()
    if count >= MAX_CONNECTIONS_PER_TENANT:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum of {MAX_CONNECTIONS_PER_TENANT} Stripe connections per tenant",
        )

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Connection name cannot be empty")

    key = payload.stripe_api_key.strip()
    if not key.startswith(("sk_test_", "sk_live_")):
        raise HTTPException(
            status_code=422,
            detail="Invalid Stripe key — must start with sk_test_ or sk_live_",
        )

    # Duplicate name check
    existing = db.query(StripeConnection).filter(
        StripeConnection.tenant_id == tenant_id,
        StripeConnection.name == name,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A connection named '{name}' already exists")

    conn = StripeConnection(
        tenant_id=tenant_id,
        name=name,
        encrypted_api_key=encrypt_key(key),
        created_at=datetime.now(timezone.utc),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)

    return StripeConnectionOut(
        id=conn.id,
        tenant_id=conn.tenant_id,
        name=conn.name,
        has_key=True,
        stripe_account_id=conn.stripe_account_id,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.put("/{tenant_id}/stripe-connections/{conn_id}", response_model=StripeConnectionOut)
def update_stripe_connection(
    tenant_id: int,
    conn_id: int,
    payload: UpdateConnectionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    conn = _get_connection_or_404(conn_id, tenant_id, db)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Connection name cannot be empty")
        # Duplicate name check (excluding self)
        dup = db.query(StripeConnection).filter(
            StripeConnection.tenant_id == tenant_id,
            StripeConnection.name == name,
            StripeConnection.id != conn_id,
        ).first()
        if dup:
            raise HTTPException(status_code=409, detail=f"A connection named '{name}' already exists")
        conn.name = name

    if payload.stripe_api_key is not None:
        key = payload.stripe_api_key.strip()
        if not key.startswith(("sk_test_", "sk_live_")):
            raise HTTPException(
                status_code=422,
                detail="Invalid Stripe key — must start with sk_test_ or sk_live_",
            )
        conn.encrypted_api_key = encrypt_key(key)
        # Reset discovered account id — re-test required
        conn.stripe_account_id = None

    conn.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conn)

    return StripeConnectionOut(
        id=conn.id,
        tenant_id=conn.tenant_id,
        name=conn.name,
        has_key=bool(conn.encrypted_api_key),
        stripe_account_id=conn.stripe_account_id,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.delete("/{tenant_id}/stripe-connections/{conn_id}", status_code=204)
def delete_stripe_connection(
    tenant_id: int,
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    conn = _get_connection_or_404(conn_id, tenant_id, db)
    db.delete(conn)
    db.commit()


@router.post("/{tenant_id}/stripe-connections/{conn_id}/test", response_model=TestResult)
def test_stripe_connection(
    tenant_id: int,
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    conn = _get_connection_or_404(conn_id, tenant_id, db)

    if not conn.encrypted_api_key:
        raise HTTPException(status_code=400, detail="No API key configured for this connection")

    plain = _decrypt_conn_key(conn)
    if not plain:
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt API key — check FERNET_KEY in .env",
        )

    try:
        r = httpx.get(
            "https://api.stripe.com/v1/account",
            headers={"Authorization": f"Bearer {plain}"},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            account_id = data.get("id")  # acct_...
            name = data.get("business_profile", {}).get("name") or data.get("email") or "—"
            # Persist discovered stripe_account_id
            conn.stripe_account_id = account_id
            conn.updated_at = datetime.now(timezone.utc)
            db.commit()
            return TestResult(
                success=True,
                message="Connection successful",
                account_name=name,
                stripe_account_id=account_id,
            )
        elif r.status_code == 401:
            return TestResult(success=False, message="Invalid API key — authentication failed")
        else:
            return TestResult(success=False, message=f"Stripe returned status {r.status_code}")
    except httpx.TimeoutException:
        return TestResult(success=False, message="Request timed out — check your network")
    except Exception as e:
        return TestResult(success=False, message=f"Connection error: {str(e)}")


# ---------------------------------------------------------------------------
# Slack endpoints
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/slack", response_model=SlackConfigOut)
def get_slack_config(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    cfg = _get_or_create_config(tenant_id, db)
    plain = _plaintext_webhook(cfg)
    return SlackConfigOut(
        tenant_id=tenant_id,
        has_slack_webhook=bool(cfg.slack_webhook_url),
        slack_webhook_masked=_mask_webhook(plain) if plain else None,
        slack_alert_level=cfg.slack_alert_level or "HIGH",
        updated_at=cfg.updated_at,
    )


@router.put("/{tenant_id}/slack", response_model=SlackConfigOut)
def save_slack_config(
    tenant_id: int,
    payload: SaveSlackRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    url = payload.webhook_url.strip()
    if not url.startswith("https://"):
        raise HTTPException(
            status_code=422,
            detail="Webhook URL must start with https://",
        )
    if payload.alert_level not in VALID_LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"alert_level must be one of: {', '.join(sorted(VALID_LEVELS))}",
        )

    cfg = _get_or_create_config(tenant_id, db)
    cfg.slack_webhook_url = encrypt_key(url)
    cfg.slack_alert_level = payload.alert_level
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cfg)

    return SlackConfigOut(
        tenant_id=tenant_id,
        has_slack_webhook=True,
        slack_webhook_masked=_mask_webhook(url),
        slack_alert_level=payload.alert_level,
        updated_at=cfg.updated_at,
    )


@router.delete("/{tenant_id}/slack", response_model=SlackConfigOut)
def delete_slack_config(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    cfg = _get_or_create_config(tenant_id, db)
    cfg.slack_webhook_url = None
    cfg.slack_alert_level = None
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    return SlackConfigOut(
        tenant_id=tenant_id,
        has_slack_webhook=False,
        slack_webhook_masked=None,
        slack_alert_level=None,
        updated_at=cfg.updated_at,
    )


@router.post("/{tenant_id}/test-slack", response_model=TestResult)
def test_slack_webhook(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    tenant = _get_tenant_or_404(tenant_id, db)
    cfg = _get_or_create_config(tenant_id, db)

    if not cfg.slack_webhook_url:
        raise HTTPException(status_code=400, detail="No Slack webhook configured")

    plain = _plaintext_webhook(cfg)
    if not plain:
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt Slack webhook URL — check FERNET_KEY in .env",
        )

    try:
        send_test_message(plain, tenant.name)
        return TestResult(success=True, message="Test message sent to Slack")
    except httpx.HTTPStatusError as e:
        return TestResult(success=False, message=f"Slack rejected the request (HTTP {e.response.status_code}) — check your webhook URL")
    except httpx.TimeoutException:
        return TestResult(success=False, message="Request timed out — check your network")
    except Exception as e:
        return TestResult(success=False, message=f"Error: {str(e)}")


# ---------------------------------------------------------------------------
# Email alert config schemas
# ---------------------------------------------------------------------------


class EmailConfigOut(BaseModel):
    tenant_id: int
    alert_email: str
    alert_level: str
    is_verified: bool
    verified_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SaveEmailRequest(BaseModel):
    alert_email: EmailStr
    alert_level: str   # HIGH | MEDIUM_AND_HIGH | ALL


class VerifyEmailResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Email alert config endpoints
# ---------------------------------------------------------------------------


def _get_email_config(tenant_id: int, db: Session) -> Optional[EmailAlertConfig]:
    return db.query(EmailAlertConfig).filter(EmailAlertConfig.tenant_id == tenant_id).first()


@router.get("/{tenant_id}/email", response_model=Optional[EmailConfigOut])
def get_email_config(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    cfg = _get_email_config(tenant_id, db)
    if not cfg:
        return None
    return EmailConfigOut(
        tenant_id=cfg.tenant_id,
        alert_email=cfg.alert_email,
        alert_level=cfg.alert_level,
        is_verified=cfg.is_verified,
        verified_at=cfg.verified_at,
        updated_at=cfg.updated_at,
    )


@router.put("/{tenant_id}/email", response_model=EmailConfigOut)
def save_email_config(
    tenant_id: int,
    payload: SaveEmailRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    tenant = _get_tenant_or_404(tenant_id, db)

    if payload.alert_level not in EMAIL_VALID_LEVELS:
        raise HTTPException(
            status_code=422,
            detail=f"alert_level must be one of: {', '.join(sorted(EMAIL_VALID_LEVELS))}",
        )

    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    expires = now + timedelta(hours=24)

    cfg = _get_email_config(tenant_id, db)
    email_changed = cfg is None or cfg.alert_email != str(payload.alert_email)

    if cfg is None:
        cfg = EmailAlertConfig(
            tenant_id=tenant_id,
            alert_email=str(payload.alert_email),
            alert_level=payload.alert_level,
            is_verified=False,
            verification_token=token,
            token_expires_at=expires,
            created_at=now,
            updated_at=now,
        )
        db.add(cfg)
    else:
        cfg.alert_email = str(payload.alert_email)
        cfg.alert_level = payload.alert_level
        cfg.updated_at = now
        if email_changed:
            # New email address — reset verification
            cfg.is_verified = False
            cfg.verified_at = None
            cfg.verification_token = token
            cfg.token_expires_at = expires

    db.commit()
    db.refresh(cfg)

    # Send verification email if address changed (or new)
    if email_changed:
        try:
            send_verification_email(cfg.alert_email, token, tenant.name)
        except Exception as exc:
            # Don't fail the save — user can resend manually
            pass

    return EmailConfigOut(
        tenant_id=cfg.tenant_id,
        alert_email=cfg.alert_email,
        alert_level=cfg.alert_level,
        is_verified=cfg.is_verified,
        verified_at=cfg.verified_at,
        updated_at=cfg.updated_at,
    )


@router.delete("/{tenant_id}/email", status_code=204)
def delete_email_config(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    cfg = _get_email_config(tenant_id, db)
    if cfg:
        db.delete(cfg)
        db.commit()


@router.post("/{tenant_id}/email/resend-verification", response_model=VerifyEmailResponse)
def resend_verification(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    tenant = _get_tenant_or_404(tenant_id, db)
    cfg = _get_email_config(tenant_id, db)
    if not cfg:
        raise HTTPException(status_code=404, detail="No email address configured")
    if cfg.is_verified:
        return VerifyEmailResponse(success=True, message="Email is already verified")

    now = datetime.now(timezone.utc)
    cfg.verification_token = secrets.token_urlsafe(32)
    cfg.token_expires_at = now + timedelta(hours=24)
    cfg.updated_at = now
    db.commit()

    try:
        send_verification_email(cfg.alert_email, cfg.verification_token, tenant.name)
        return VerifyEmailResponse(success=True, message=f"Verification email sent to {cfg.alert_email}")
    except Exception as exc:
        return VerifyEmailResponse(success=False, message=f"Failed to send email: {exc}")


# Public — no auth — token is the credential
@router.get("/email/verify", response_model=VerifyEmailResponse)
def verify_email_token(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    cfg = db.query(EmailAlertConfig).filter(
        EmailAlertConfig.verification_token == token,
    ).first()

    if not cfg:
        return VerifyEmailResponse(success=False, message="Invalid or already-used verification link")

    now = datetime.now(timezone.utc)
    if cfg.token_expires_at and cfg.token_expires_at.replace(tzinfo=timezone.utc) < now:
        return VerifyEmailResponse(success=False, message="Verification link has expired — please request a new one")

    cfg.is_verified = True
    cfg.verified_at = now
    cfg.verification_token = None
    cfg.token_expires_at = None
    cfg.updated_at = now
    db.commit()

    return VerifyEmailResponse(success=True, message=f"Email verified — alerts will be sent to {cfg.alert_email}")
