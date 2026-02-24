import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter()

# ---------------------------------------------------------------------------
# Auth dependency — reused by all protected routers
# ---------------------------------------------------------------------------


class CurrentUser(BaseModel):
    user_id: int
    tenant_id: Optional[int]
    email: str
    is_admin: bool


def get_current_user(request: Request) -> CurrentUser:
    """
    Decode and validate the JWT from the httpOnly access_token cookie.
    Raises HTTP 401 if the cookie is missing, expired, or invalid.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(
        user_id=int(payload["sub"]),
        tenant_id=payload.get("tenant_id"),
        email=payload["email"],
        is_admin=payload.get("is_admin", False),
    )


def assert_tenant_access(current_user: CurrentUser, tenant_id: int) -> None:
    """
    Raise HTTP 403 if a non-admin user tries to access another tenant's data.
    Admins (tenant_id=None) can access all tenants.
    """
    if current_user.is_admin:
        return
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you can only access your own tenant's data",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload["exp"] = expire
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.is_production,   # HTTPS-only in prod, HTTP allowed in dev
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserOut(BaseModel):
    tenant_id: Optional[int]
    email: str
    is_admin: bool


class SignupRequest(BaseModel):
    email: EmailStr
    password: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/signup", response_model=UserOut)
@limiter.limit("5/minute")
def signup(
    request: Request,
    response: Response,
    body: SignupRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Build a unique slug from the email local part
    local = re.sub(r"[^a-z0-9]", "", body.email.split("@")[0].lower())[:20] or "user"
    slug = f"{local}_{secrets.token_hex(3)}"

    tenant = Tenant(name=local, slug=slug)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        tenant_id=tenant.id,
        is_admin=False,
    )
    db.add(user)
    db.commit()

    # Seed demo data asynchronously — user gets token immediately
    from app.services.demo_seeder import seed_demo_for_tenant
    background_tasks.add_task(seed_demo_for_tenant, tenant.id)

    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": tenant.id,
        "email": user.email,
        "is_admin": False,
    })
    _set_auth_cookie(response, token)
    return UserOut(tenant_id=tenant.id, email=user.email, is_admin=False)


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "email": user.email,
        "is_admin": user.is_admin,
    })
    _set_auth_cookie(response, token)
    return UserOut(tenant_id=user.tenant_id, email=user.email, is_admin=user.is_admin)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("access_token", samesite="lax")


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser = Depends(get_current_user)):
    return UserOut(
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        is_admin=current_user.is_admin,
    )
