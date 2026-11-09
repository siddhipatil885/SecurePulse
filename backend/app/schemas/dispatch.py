from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OfferCreate(BaseModel):
    incident_id: int | None = Field(default=None, gt=0)
    reporter_incident_id: int | None = Field(default=None, gt=0)
    property_id: int = Field(gt=0)
    marshal_profile_id: int = Field(gt=0)
    expires_in_seconds: int = Field(default=300, ge=10, le=300)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_incident_source(self):
        if (self.incident_id is None) == (self.reporter_incident_id is None):
            raise ValueError("Provide exactly one incident source.")
        return self


class OfferResponse(BaseModel):
    expected_version: int = Field(gt=0)


class BroadcastOffer(OfferCreate):
    marshal_profile_id: int | None = None
    marshal_profile_ids: list[int] = Field(min_length=1, max_length=20)


class TeamOfferCreate(BaseModel):
    incident_id: int | None = Field(default=None, gt=0)
    reporter_incident_id: int | None = Field(default=None, gt=0)
    property_id: int = Field(gt=0)
    marshal_profile_ids: list[int] = Field(min_length=1, max_length=20)
    expires_in_seconds: int = Field(default=300, ge=10, le=300)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_incident_source(self):
        if (self.incident_id is None) == (self.reporter_incident_id is None):
            raise ValueError("Provide exactly one incident source.")
        return self


class AssignmentProgress(BaseModel):
    expected_version: int = Field(gt=0)
    status: Literal["EN_ROUTE", "ON_SCENE", "INVESTIGATING", "PENDING_REVIEW"]
    review_summary: str | None = Field(default=None, min_length=10, max_length=2000)

    @model_validator(mode="after")
    def require_review_summary(self):
        if self.status == "PENDING_REVIEW" and not (self.review_summary or "").strip():
            raise ValueError("Provide an investigation summary before supervisor review.")
        return self


class SupervisorReview(BaseModel):
    expected_version: int = Field(gt=0)
    approved: bool
    reason: str = Field(min_length=5, max_length=2000)

    @field_validator("reason")
    @classmethod
    def trim_review_reason(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Provide a useful review reason.")
        return value


class ResponderLocation(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    heading: float | None = None
    speed_mps: float | None = None
    updated_at: datetime
    distance_m: float | None = None
    eta_seconds: int | None = None
    eta_source: Literal["gps_speed", "urban_fallback"] | None = None

    @field_validator('updated_at')
    @classmethod
    def utc_timestamp(cls, value):
        """Expose UTC explicitly, restoring markers dropped by SQLite storage."""
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class OfferView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    security_event_id: int | None
    reporter_incident_id: int | None = None
    property_id: int
    marshal_profile_id: int
    team_key: str | None = None
    team_role: str | None = None
    status: Literal["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE", "INVESTIGATING", "PENDING_REVIEW", "DECLINED", "EXPIRED", "CANCELLED", "COMPLETED"]
    offered_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    closed_at: datetime | None
    version: int
    responder_location: ResponderLocation | None = None


class EligibleMarshal(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    service_area: str | None
    capacity: int
    name: str | None = None


class AvailabilityUpdate(BaseModel):
    property_id: int = Field(gt=0)
    on_duty: bool
    available: bool


class DispatchRequest(BaseModel):
    property_id: int = Field(gt=0)
    expires_in_seconds: int = Field(default=300, ge=10, le=300)
    correlation_id: str = Field(min_length=8, max_length=255)


class DispatchOutcome(BaseModel):
    status: Literal["OFFERED", "ESCALATED"]
    incident_id: int
    assignment: OfferView | None = None
    reason: str | None = None


class ReporterDispatchOutcome(BaseModel):
    status: Literal["OFFERED", "ESCALATED"]
    reporter_incident_id: int
    assignment: OfferView | None = None
    reason: str | None = None
