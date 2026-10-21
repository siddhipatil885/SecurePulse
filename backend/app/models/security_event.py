"""Security event persistence model."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        UniqueConstraint("incident_key", name="uq_security_events_incident_key"),
        Index("ix_security_events_camera_id", "camera_id"),
        Index("ix_security_events_event_type", "event_type"),
        Index("ix_security_events_frigate_event_id", "frigate_event_id"),
        Index("ix_security_events_timestamp", "timestamp"),
        Index("ix_security_events_camera_timestamp", "camera_id", text("timestamp DESC")),
        Index("ix_security_events_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    zone: Mapped[str | None] = mapped_column(String(255))
    frigate_event_id: Mapped[str | None] = mapped_column(String(255))
    incident_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    camera = relationship("Camera", back_populates="security_events")
    property = relationship("Property", back_populates="security_events")
    evidence = relationship("Evidence", back_populates="security_event")
    alerts = relationship("Alert", back_populates="security_event")
    status_history = relationship(
        "IncidentStatusHistory", back_populates="security_event", cascade="all, delete-orphan"
    )
    source_receipts = relationship("SourceEventReceipt", back_populates="security_event")
