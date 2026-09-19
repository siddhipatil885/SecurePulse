"""
Evidence model — file references (snapshots, clips) attached to security events.

IMPORTANT: Only file paths / URLs are stored. Binary image/video data is
NEVER stored inside PostgreSQL.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


class Evidence(Base):
    """A piece of evidence (snapshot, video clip, etc.) linked to an event.

    Attributes:
        id: Primary key.
        event_id: FK to the SecurityEvent this evidence belongs to.
        type: Evidence category (e.g., "snapshot", "clip", "thumbnail").
        file_path: Path or URL to the stored file. Never binary data.
        created_at: Row creation timestamp (UTC).
        event: Parent SecurityEvent relationship.
    """

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("security_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ----- Relationships -----
    event: Mapped["SecurityEvent"] = relationship(
        "SecurityEvent", back_populates="evidence_items"
    )

    def __repr__(self) -> str:
        return f"<Evidence(id={self.id}, type='{self.type}', event_id={self.event_id})>"
