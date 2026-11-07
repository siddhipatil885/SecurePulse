from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class MarshalOnboarding(Base):
    __tablename__ = 'marshal_onboarding'
    marshal_profile_id: Mapped[int] = mapped_column(ForeignKey('marshal_profiles.id'), primary_key=True)
    encrypted_details: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    documents: Mapped[dict] = mapped_column(JSON, nullable=False)
    id_type: Mapped[str] = mapped_column(String(32), nullable=False)
    id_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    review_note: Mapped[str | None] = mapped_column(String(1000))
