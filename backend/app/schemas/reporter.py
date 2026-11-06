from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ReporterProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ReporterPasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class PropertyAccess(BaseModel):
    id: int
    name: str
    role: Literal["owner", "reporter", "dispatcher", "marshal"]


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
    connection_status: Literal["unknown", "online", "offline", "disabled"] = "unknown"


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
    alert_id: int | None = None
    alert_status: str | None = None


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
    security_status: Literal["unknown", "attention_required", "camera_issue", "no_active_incidents"] = "unknown"


IncidentType = Literal[
    "THEFT", "BREAK_IN", "SUSPICIOUS_ACTIVITY", "ASSAULT", "PROPERTY_DAMAGE",
    "FIRE", "MEDICAL_EMERGENCY", "OTHER",
]


class ReporterIncidentCreate(BaseModel):
    property_id: int = Field(ge=1)
    incident_type: IncidentType
    description: str | None = Field(default=None, max_length=4000)
    address: str | None = Field(default=None, max_length=1000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy: float | None = Field(default=None, ge=0, le=100000)

    @field_validator("address", "description", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_location(self):
        if not self.address and (self.latitude is None or self.longitude is None):
            raise ValueError("Provide a location address or coordinates.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be provided together.")
        return self


class ReporterIncidentTimelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    actor_subject: str
    message: str
    occurred_at: datetime


class ReporterEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    media_type: str
    original_filename: str
    byte_size: int
    created_at: datetime


class ReporterIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    property_id: int
    incident_type: str
    description: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    location_accuracy: float | None
    status: str
    created_at: datetime
    updated_at: datetime
    evidence: list[ReporterEvidenceResponse] = Field(default_factory=list)
    timeline: list[ReporterIncidentTimelineResponse] = Field(default_factory=list)
    dispatch: "ReporterDispatchResponse | None" = None
    details_included: bool = True


class ReporterDispatchResponse(BaseModel):
    assignment_id: int
    status: str
    marshal_profile_id: int
    offered_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    closed_at: datetime | None
    version: int


class ReporterIncidentPage(BaseModel):
    items: list[ReporterIncidentResponse]
    page: int
    page_size: int
    total: int


class DeviceRegistration(BaseModel):
    device_id: str = Field(min_length=1, max_length=255)
    push_token: str = Field(min_length=1, max_length=512)
    provider: Literal["expo"] = "expo"


class NotificationPreferenceUpdate(BaseModel):
    category: Literal["SECURITY_ALERTS", "INCIDENT_UPDATES", "DISPATCH_UPDATES"]
    enabled: bool


class NotificationPreferenceResponse(NotificationPreferenceUpdate):
    updated_at: datetime


class AlertReviewRequest(BaseModel):
    decision: Literal["CONFIRMED", "FALSE_ALARM"]
