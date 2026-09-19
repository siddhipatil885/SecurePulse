"""Normalized detection domain objects independent of Frigate payloads."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DetectionEvent(BaseModel):
    """A validated observation emitted by an external detection system."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    camera: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include timezone information")
        return value.astimezone(timezone.utc)