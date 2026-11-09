"""Durable ingestion, audit, notification, and response-operation models."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class SourceEventReceipt(Base):
    __tablename__ = "source_event_receipts"
    __table_args__ = (
        UniqueConstraint("source_system", "source_event_id", "event_phase", "revision", name="uq_source_event_receipts_identity"),
        Index("ix_source_event_receipts_property_received", "property_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"))
    security_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("security_events.id", ondelete="SET NULL")
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_phase: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[str] = mapped_column(String(64), default="0", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    security_event = relationship("SecurityEvent", back_populates="source_receipts")


class IncidentStatusHistory(Base):
    __tablename__ = "incident_status_history"
    __table_args__ = (Index("ix_incident_status_history_event_time", "security_event_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_event_id: Mapped[int] = mapped_column(ForeignKey("security_events.id", ondelete="CASCADE"), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    security_event = relationship("SecurityEvent", back_populates="status_history")


class AuditRecord(Base):
    __tablename__ = "audit_records"
    __table_args__ = (Index("ix_audit_records_property_time", "property_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (Index("ix_notification_outbox_status_available", "status", "available_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    security_event_id: Mapped[int | None] = mapped_column(ForeignKey("security_events.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    destination: Mapped[str | None] = mapped_column(String(255))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(128))

    attempts = relationship("NotificationAttempt", back_populates="outbox", cascade="all, delete-orphan")


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"
    __table_args__ = (UniqueConstraint("outbox_id", "attempt_number", name="uq_notification_attempts_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outbox_id: Mapped[int] = mapped_column(ForeignKey("notification_outbox.id", ondelete="CASCADE"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(String(1000))
    response_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    outbox = relationship("NotificationOutbox", back_populates="attempts")


class UserDeviceToken(Base):
    __tablename__ = "user_device_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_user_device_tokens_user_device"),
        Index("ix_user_device_tokens_active", "user_id", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    push_token: Mapped[str] = mapped_column(String(512), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_notification_preferences_user_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MarshalProfile(Base):
    __tablename__ = "marshal_profiles"
    __table_args__ = (Index("ix_marshal_profiles_property_active", "property_id", "active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    service_area: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), default='REQUIRED', server_default='REQUIRED', nullable=False)


class MarshalAvailability(Base):
    __tablename__ = "marshal_availability"

    marshal_profile_id: Mapped[int] = mapped_column(ForeignKey("marshal_profiles.id", ondelete="CASCADE"), primary_key=True)
    on_duty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    latitude: Mapped[float | None] = mapped_column()
    longitude: Mapped[float | None] = mapped_column()
    location_accuracy_m: Mapped[float | None] = mapped_column()
    location_heading: Mapped[float | None] = mapped_column()
    location_speed_mps: Mapped[float | None] = mapped_column()
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("ix_assignments_event_status", "security_event_id", "status"),
        Index("ix_assignments_reporter_incident_status", "reporter_incident_id", "status"),
        Index(
            "uq_assignments_one_active_offer",
            "security_event_id",
            unique=True,
            postgresql_where=text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW') AND team_key IS NULL"),
            sqlite_where=text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW') AND team_key IS NULL"),
        ),
        Index("uq_assignments_one_active_reporter", "reporter_incident_id", unique=True,
            postgresql_where=text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW') AND team_key IS NULL"),
            sqlite_where=text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW') AND team_key IS NULL")),
        Index('uq_assignment_pending_camera_marshal', 'security_event_id', 'marshal_profile_id', unique=True,
            postgresql_where=text("status = 'OFFERED'"), sqlite_where=text("status = 'OFFERED'")),
        Index('uq_assignment_pending_reporter_marshal', 'reporter_incident_id', 'marshal_profile_id', unique=True,
            postgresql_where=text("status = 'OFFERED'"), sqlite_where=text("status = 'OFFERED'")),
        CheckConstraint("(security_event_id IS NOT NULL AND reporter_incident_id IS NULL) OR "
                        "(security_event_id IS NULL AND reporter_incident_id IS NOT NULL)",
                        name="ck_assignments_one_incident_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)
    security_event_id: Mapped[int | None] = mapped_column(ForeignKey("security_events.id", ondelete="CASCADE"))
    reporter_incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("reporter_incidents.id", ondelete="CASCADE")
    )
    marshal_profile_id: Mapped[int] = mapped_column(ForeignKey("marshal_profiles.id"), nullable=False)
    team_key: Mapped[str | None] = mapped_column(String(64))
    team_role: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    events = relationship("AssignmentEvent", back_populates="assignment", cascade="all, delete-orphan")


class AssignmentEvent(Base):
    __tablename__ = "assignment_events"
    __table_args__ = (Index("ix_assignment_events_assignment_time", "assignment_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    assignment = relationship("Assignment", back_populates="events")


class MarshalLocationHistory(Base):
    __tablename__ = "marshal_location_history"
    __table_args__ = (
        Index("ix_marshal_location_history_assignment_recorded", "assignment_id", "recorded_at"),
        Index("ix_marshal_location_history_property_recorded", "property_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    marshal_profile_id: Mapped[int] = mapped_column(ForeignKey("marshal_profiles.id", ondelete="CASCADE"), nullable=False)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column()
    heading: Mapped[float | None] = mapped_column()
    speed_mps: Mapped[float | None] = mapped_column()
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarshalEvidence(Base):
    __tablename__ = "marshal_evidence"
    __table_args__ = (
        UniqueConstraint("assignment_id", "idempotency_key", name="uq_marshal_evidence_assignment_upload"),
        Index("ix_marshal_evidence_assignment_created", "assignment_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    uploader_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssignmentMessage(Base):
    __tablename__ = "assignment_messages"
    __table_args__ = (
        UniqueConstraint("sender_user_id", "client_message_id", name="uq_assignment_messages_sender_client_id"),
        Index("ix_assignment_messages_thread_created", "thread_key", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    thread_key: Mapped[str] = mapped_column(String(100), nullable=False)
    client_message_id: Mapped[str] = mapped_column(String(80), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
