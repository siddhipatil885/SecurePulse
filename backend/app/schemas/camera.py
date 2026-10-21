"""Camera API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    name: str
    frigate_camera_name: str
    location: str | None
    enabled: bool
    health_status: str | None = None
    health_observed_at: datetime | None = None
    created_at: datetime | None
    updated_at: datetime | None
