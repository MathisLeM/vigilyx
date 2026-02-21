import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class DetectionMethod(str, enum.Enum):
    MAD = "MAD"
    ZSCORE = "ZSCORE"
    DUAL = "DUAL"   # Both MAD and Z-score fired — merged into one alert


class AlertSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnomalyAlert(Base):
    __tablename__ = "anomaly_alerts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "snapshot_date",
            "metric_name",
            "detection_method",
            name="uq_alert_dedup",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    metric_name = Column(String(50), nullable=False)
    metric_value = Column(Float, nullable=False)
    detection_method = Column(Enum(DetectionMethod), nullable=False)
    score = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    direction = Column(String(10), nullable=False)  # "spike" | "drop"
    pct_deviation = Column(Float, nullable=True)    # % away from rolling median baseline
    is_dual_confirmed = Column(Boolean, default=False, nullable=False)  # both MAD + Z-score fired
    hint = Column(String(500), nullable=False)
    severity = Column(Enum(AlertSeverity), nullable=False, default=AlertSeverity.MEDIUM)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", back_populates="anomaly_alerts")
