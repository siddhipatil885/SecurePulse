"""Property-scoped incident, history, and evidence API schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IncidentHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    previous_status: str | None
    new_status: str
    actor_subject: str
    reason: str | None
    correlation_id: str
    occurred_at: datetime


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: int
    event_id: int
    type: str
    file_path: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="evidence_metadata",
        serialization_alias="metadata",
    )


class IncidentCommand(BaseModel):
    command: Literal["acknowledge", "resolve", "dismiss", "reopen"]
    reason: str = Field(min_length=1, max_length=1000)
    correlation_id: str = Field(min_length=1, max_length=255)
