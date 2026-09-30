"""Operator alert state independent from detection and security-event records."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_camera_status", "camera_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False)
    security_event_id: Mapped[int] = mapped_column(
        ForeignKey("security_events.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera = relationship("Camera", back_populates="alerts")
    security_event = relationship("SecurityEvent")