from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class EmailAlertConfig(Base):
    __tablename__ = "email_alert_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False)

    # Destination email (unencrypted — not a secret)
    alert_email = Column(String(255), nullable=False)

    # HIGH | MEDIUM_AND_HIGH | ALL
    alert_level = Column(String(20), nullable=False, default="HIGH")

    # Verification state
    is_verified = Column(Boolean, nullable=False, default=False)
    verification_token = Column(String(100), nullable=True, unique=True, index=True)
    token_expires_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
