from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User

router = APIRouter()

# ---------------------------------------------------------------------------
# Auth dependency — reused by all protected routers
# ---------------------------------------------------------------------------

_bearer = HTTPBearer()


class CurrentUser(BaseModel):
    user_id: int
    tenant_id: Optional[int]
    email: str
    is_admin: bool


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    """
    Decode and validate the Bearer JWT from the Authorization header.
    Raises HTTP 401 if the token is missing, expired, or invalid.
    """
    token = credentials.credentials
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


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: Optional[int]  # null for admin
    email: str
    is_admin: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenOut)
def login(
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
    return TokenOut(
        access_token=token,
        tenant_id=user.tenant_id,
        email=user.email,
        is_admin=user.is_admin,
    )
