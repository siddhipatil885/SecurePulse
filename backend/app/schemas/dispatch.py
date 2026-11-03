from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class OfferCreate(BaseModel):
    incident_id: int = Field(gt=0)
    property_id: int = Field(gt=0)
    marshal_profile_id: int = Field(gt=0)
    expires_in_seconds: int = Field(default=60, ge=10, le=3600)
    idempotency_key: str = Field(min_length=8, max_length=128)


class OfferResponse(BaseModel):
    expected_version: int = Field(gt=0)


class OfferView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    security_event_id: int
    property_id: int
    marshal_profile_id: int
    status: Literal["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE", "DECLINED", "EXPIRED", "CANCELLED", "COMPLETED"]
    offered_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    closed_at: datetime | None
    version: int


class EligibleMarshal(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    service_area: str | None
    capacity: int


class AvailabilityUpdate(BaseModel):
    property_id: int = Field(gt=0)
    on_duty: bool
    available: bool
