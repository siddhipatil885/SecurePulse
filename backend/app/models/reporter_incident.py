"""Reporter-created incidents and their private evidence."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ReporterIncident(Base):
    __tablename__ = "reporter_incidents"
    __table_args__ = (
        UniqueConstraint("reporter_user_id", "idempotency_key", name="uq_reporter_incident_idempotency"),
        Index("ix_reporter_incidents_property_created", "property_id", "created_at"),
        Index("ix_reporter_incidents_reporter_created", "reporter_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4000))
    address: Mapped[str | None] = mapped_column(String(1000))
    latitude: Mapped[float | None] = mapped_column()
    longitude: Mapped[float | None] = mapped_column()
    location_accuracy: Mapped[float | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    evidence = relationship("ReporterIncidentEvidence", back_populates="incident", cascade="all, delete-orphan")
    timeline = relationship("ReporterIncidentTimeline", back_populates="incident", cascade="all, delete-orphan")


class ReporterIncidentTimeline(Base):
    __tablename__ = "reporter_incident_timeline"
    __table_args__ = (Index("ix_reporter_incident_timeline_incident_time", "incident_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("reporter_incidents.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    incident = relationship("ReporterIncident", back_populates="timeline")


class ReporterIncidentEvidence(Base):
    __tablename__ = "reporter_incident_evidence"
    __table_args__ = (Index("ix_reporter_incident_evidence_incident", "incident_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("reporter_incidents.id", ondelete="CASCADE"), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    incident = relationship("ReporterIncident", back_populates="evidence")
