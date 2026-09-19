"""
SecurityEvent model — represents a detected security event in SecurePulse.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


class SecurityEvent(Base):
    """A security event detected by the surveillance pipeline.

    Examples: PERSON_DETECTED, VEHICLE_DETECTED, INTRUSION, LOITERING.

    Attributes:
        id: Primary key.
        camera_id: FK to the camera that captured this event.
        event_type: Category of the event (e.g., "PERSON_DETECTED").
        object_type: Detected object class (e.g., "person", "car").
        confidence: Detection confidence score, 0.0–1.0 inclusive. Nullable
            when the source does not provide a confidence value.
        timestamp: When the event occurred (timezone-aware).
        severity: Severity label (e.g., "INFO", "WARNING", "CRITICAL").
        status: Lifecycle status (e.g., "OPEN", "ACKNOWLEDGED", "RESOLVED").
        zone: Optional zone name where the event was detected.
        frigate_event_id: Frigate's own event identifier. Used for dedup.
        metadata_: Arbitrary JSONB payload for extensibility.
        created_at: Row creation timestamp (UTC).
        camera: Parent Camera relationship.
        evidence_items: Related Evidence records.
    """

    __tablename__ = "security_events"

    # ----- Table-level constraints & indexes -----
    __table_args__ = (
        # Confidence must be between 0 and 1 (inclusive) when provided.
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_security_events_confidence_range",
        ),
        # Composite index: "recent events for a specific camera"
        Index(
            "ix_security_events_camera_timestamp",
            "camera_id",
            "timestamp",
            postgresql_ops={"timestamp": "DESC"},
        ),
        # Partial unique index on frigate_event_id (only non-NULL values).
        # Prevents duplicate Frigate event insertion while allowing NULLs.
        Index(
            "ix_security_events_frigate_event_id",
            "frigate_event_id",
            unique=True,
            postgresql_where="frigate_event_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    zone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    frigate_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ----- Relationships -----
    camera: Mapped["Camera"] = relationship("Camera", back_populates="events")
    evidence_items: Mapped[list["Evidence"]] = relationship(
        "Evidence",
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<SecurityEvent(id={self.id}, type='{self.event_type}', "
            f"camera_id={self.camera_id}, severity='{self.severity}')>"
        )
