"""Persisted anonymous Frigate track sessions."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (Index("ix_tracks_camera_last_seen", "camera_id", "last_seen"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False)
    track_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    bounding_box: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    frame_width: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_height: Mapped[int] = mapped_column(Integer, nullable=False)
    face_visible: Mapped[bool | None] = mapped_column(nullable=True)

    camera = relationship("Camera", back_populates="tracks")