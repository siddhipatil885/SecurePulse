"""Security event API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    camera_id: int
    event_type: str
    object_type: str
    confidence: float
    timestamp: datetime
    severity: str
    status: str
    score: int | None
    zone: str | None
    frigate_event_id: str | None
    reason: str | None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="event_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime | None


class EventPage(BaseModel):
    items: list[EventResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)