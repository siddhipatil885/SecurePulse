from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class PropertyAccess(BaseModel):
    id: int
    name: str
    role: Literal["owner", "reporter"]


class ReporterProfile(BaseModel):
    id: int
    email: str
    name: str
    properties: list[PropertyAccess]


class ReporterCamera(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str | None
    enabled: bool
    connection_status: Literal["unknown"] = "unknown"


class ReporterEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    camera_id: int
    event_type: str
    object_type: str
    confidence: float
    timestamp: datetime
    severity: str
    status: str
    reason: str | None
    zone: str | None


class ReporterEventPage(BaseModel):
    items: list[ReporterEvent]
    page: int
    page_size: int
    total: int


class ReporterSummary(BaseModel):
    camera_count: int
    event_count: int
    active_alert_count: int
    connected_camera_count: int | None = None
    active_incident_count: int | None = None
    security_status: Literal["unknown"] = "unknown"
