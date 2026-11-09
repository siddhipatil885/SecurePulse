"""Additive operator contract; legacy camera and mobile incident APIs stay intact."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.dispatch import OfferView

CaseSource = Literal["camera", "reporter"]
CaseStatus = Literal["OPEN", "ACKNOWLEDGED", "UNCLASSIFIED", "RESOLVED", "DISMISSED", "CLOSED"]
CaseSeverity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


class CaseSummary(BaseModel):
    key: str
    source: CaseSource
    source_id: int
    property_id: int
    incident_type: str
    status: str
    source_status: str
    severity: str | None
    occurred_at: datetime
    description: str | None
    camera_id: int | None
    latest_assignment: OfferView | None = None


class CasePage(BaseModel):
    items: list[CaseSummary]
    total: int
    page: int
    page_size: int


class CaseLocation(BaseModel):
    address: str | None
    latitude: float | None = None
    longitude: float | None = None
    accuracy_metres: float | None = None


class CaseDetail(CaseSummary):
    location: CaseLocation
    confidence: float | None = None
    zone: str | None = None
    allowed_actions: list[str]
    dispatch_allowed: bool


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseCommand(CaseInput):
    command: Literal["acknowledge", "resolve", "dismiss", "reopen"]
    expected_status: CaseStatus
    reason: str = Field(min_length=1, max_length=1000)
    correlation_id: str = Field(min_length=8, max_length=128)

    @field_validator("reason", "correlation_id", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class CaseOffer(CaseInput):
    marshal_profile_id: int = Field(gt=0)
    expires_in_seconds: int = Field(default=60, ge=10, le=3600)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class CaseTimelineItem(BaseModel):
    key: str
    kind: Literal["incident_status", "assignment_status"]
    previous_status: str | None
    status: str
    actor_subject: str
    reason: str | None
    occurred_at: datetime
    assignment_id: int | None


class CaseTimelinePage(BaseModel):
    items: list[CaseTimelineItem]
    total: int
    page: int
    page_size: int


class CaseEvidence(BaseModel):
    id: int
    kind: str
    media_type: str | None
    original_filename: str | None
    byte_size: int | None
    occurred_at: datetime
    source: Literal["incident", "marshal"] = "incident"
    assignment_id: int | None = None


class CaseEvidencePage(BaseModel):
    items: list[CaseEvidence]
    total: int
    page: int
    page_size: int


class CaseAssignmentPage(BaseModel):
    items: list[OfferView]
    total: int
    page: int
    page_size: int


class AssignmentCancel(CaseInput):
    expected_version: int = Field(gt=0)


class OperatorMarshal(BaseModel):
    id: int
    name: str | None
    service_area: str | None
    capacity: int
