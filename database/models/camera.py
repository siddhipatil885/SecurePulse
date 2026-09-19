"""
Camera model — represents a registered CCTV camera in SecurePulse.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


class Camera(Base):
    """A registered CCTV camera.

    Attributes:
        id: Primary key.
        name: Human-readable camera name (e.g., "Front Camera").
        frigate_camera_name: Camera identifier as configured in Frigate (e.g., "cam1").
        location: Optional description of physical location.
        enabled: Whether the camera is actively monitored.
        created_at: Row creation timestamp (UTC).
        updated_at: Row last-update timestamp (UTC).
        events: Related SecurityEvent records.
    """

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    frigate_camera_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ----- Relationships -----
    events: Mapped[list["SecurityEvent"]] = relationship(
        "SecurityEvent",
        back_populates="camera",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Camera(id={self.id}, name='{self.name}', frigate='{self.frigate_camera_name}')>"
