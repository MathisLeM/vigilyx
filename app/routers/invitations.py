"""
Invitation system — lets tenant users invite coworkers to join their company.

Flow
----
1. Authenticated user calls POST /{tenant_id}  → invitation row + token created.
2. Frontend builds the accept URL:
       https://<frontend>/invite/accept?token=<token>
   and displays it for the inviter to copy and share.
3. Invitee opens the URL, frontend calls GET /accept?token=<token>
   to validate (no auth required).
4. Invitee sets a password, frontend calls POST /accept
   → account created, JWT returned (auto-login).

Role field
----------
Currently always "member". Reserved for future RBAC — stored on the invitation
so that when roles are introduced the invite can carry the intended role.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.invitation import Invitation
from app.models.tenant import Tenant
from app.models.user import User
from app.routers.auth import (
    CurrentUser,
    _set_auth_cookie,
    assert_tenant_access,
    create_access_token,
    get_current_user,
    hash_password,
)

router = APIRouter()

_TOKEN_EXPIRY_DAYS = 7


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    email: str


class InvitationOut(BaseModel):
    """Returned only at creation time — includes the token so the inviter can share the link."""
    id: int
    tenant_id: int
    email: str
    role: str
    token: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]

    model_config = {"from_attributes": True}


class InvitationListOut(BaseModel):
    """Returned by the list endpoint — token is intentionally omitted."""
    id: int
    tenant_id: int
    email: str
    role: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AcceptTokenInfo(BaseModel):
    valid: bool
    email: str
    tenant_name: str
    expired: bool = False
    already_accepted: bool = False


class AcceptRequest(BaseModel):
    token: str
    password: str


class AcceptOut(BaseModel):
    tenant_id: int
    email: str
    is_admin: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_tenant_or_404(tenant_id: int, db: Session) -> Tenant:
    t = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_active == True).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return t


# ---------------------------------------------------------------------------
# Public endpoints — defined FIRST so "accept" is not swallowed by /{tenant_id}
# ---------------------------------------------------------------------------


@router.get("/accept", response_model=AcceptTokenInfo)
def validate_token(token: str, db: Session = Depends(get_db)):
    """Validate an invitation token. No authentication required."""
    inv = db.query(Invitation).filter(Invitation.token == token).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")

    tenant = db.query(Tenant).filter(Tenant.id == inv.tenant_id).first()
    tenant_name = tenant.name if tenant else "Unknown"

    if inv.is_accepted:
        return AcceptTokenInfo(
            valid=False, email=inv.email,
            tenant_name=tenant_name, already_accepted=True,
        )
    if inv.is_expired:
        return AcceptTokenInfo(
            valid=False, email=inv.email,
            tenant_name=tenant_name, expired=True,
        )
    return AcceptTokenInfo(valid=True, email=inv.email, tenant_name=tenant_name)


@router.post("/accept", response_model=AcceptOut, status_code=201)
def accept_invitation(payload: AcceptRequest, response: Response, db: Session = Depends(get_db)):
    """Complete registration from an invitation token. No authentication required."""
    inv = db.query(Invitation).filter(Invitation.token == payload.token).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.is_accepted:
        raise HTTPException(status_code=409, detail="This invitation has already been used")
    if inv.is_expired:
        raise HTTPException(status_code=410, detail="This invitation has expired")
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    # Guard against race condition — email registered between invite and accept
    if db.query(User).filter(User.email == inv.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(
        email=inv.email,
        hashed_password=hash_password(payload.password),
        tenant_id=inv.tenant_id,
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    inv.accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "email": user.email,
        "is_admin": user.is_admin,
    })
    _set_auth_cookie(response, token)
    return AcceptOut(tenant_id=user.tenant_id, email=user.email, is_admin=user.is_admin)


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------


@router.post("/{tenant_id}", response_model=InvitationOut, status_code=201)
def create_invitation(
    tenant_id: int,
    payload: InviteRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create an invitation for a new team member."""
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)

    email = payload.email.lower().strip()

    # Email already has an account
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists",
        )

    # A valid pending invitation already exists
    existing = (
        db.query(Invitation)
        .filter(
            Invitation.tenant_id == tenant_id,
            Invitation.email == email,
            Invitation.accepted_at == None,
        )
        .first()
    )
    if existing and not existing.is_expired:
        raise HTTPException(
            status_code=409,
            detail="A pending invitation already exists for this email",
        )

    now = datetime.now(timezone.utc)
    inv = Invitation(
        tenant_id=tenant_id,
        invited_by=current_user.user_id,
        email=email,
        token=secrets.token_urlsafe(32),
        role="member",
        created_at=now,
        expires_at=now + timedelta(days=_TOKEN_EXPIRY_DAYS),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{tenant_id}", response_model=list[InvitationListOut])
def list_invitations(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all pending (not yet accepted) invitations for a tenant."""
    assert_tenant_access(current_user, tenant_id)
    _get_tenant_or_404(tenant_id, db)
    return (
        db.query(Invitation)
        .filter(
            Invitation.tenant_id == tenant_id,
            Invitation.accepted_at == None,
        )
        .order_by(Invitation.created_at.desc())
        .all()
    )


@router.delete("/{tenant_id}/{invitation_id}", status_code=204)
def revoke_invitation(
    tenant_id: int,
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Revoke (delete) a pending invitation."""
    assert_tenant_access(current_user, tenant_id)
    inv = (
        db.query(Invitation)
        .filter(Invitation.id == invitation_id, Invitation.tenant_id == tenant_id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    db.delete(inv)
    db.commit()
