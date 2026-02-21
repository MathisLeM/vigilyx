from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False)

    # Stripe — stored Fernet-encrypted
    stripe_api_key = Column(String(255), nullable=True)

    # Slack — webhook URL stored Fernet-encrypted
    # alert_level: "HIGH" | "MEDIUM_AND_HIGH" | "ALL"
    slack_webhook_url = Column(String(500), nullable=True)
    slack_alert_level = Column(String(20), nullable=True)

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = relationship("Tenant")
