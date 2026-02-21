from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base

MAX_CONNECTIONS_PER_TENANT = 5


class StripeConnection(Base):
    __tablename__ = "stripe_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_stripe_conn_name"),
    )

    id                = Column(Integer, primary_key=True, index=True)
    tenant_id         = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name              = Column(String(100), nullable=False)         # user label, e.g. "Production"
    encrypted_api_key = Column(String(500), nullable=True)          # Fernet-encrypted; NULL = key not set
    stripe_account_id = Column(String(100), nullable=True)          # discovered on Test; NULL = not tested
    created_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", back_populates="stripe_connections")
