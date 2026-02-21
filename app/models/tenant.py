from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(50), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    anomaly_alerts = relationship(
        "AnomalyAlert", back_populates="tenant", cascade="all, delete-orphan"
    )
    stripe_connections = relationship(
        "StripeConnection", back_populates="tenant", cascade="all, delete-orphan"
    )
