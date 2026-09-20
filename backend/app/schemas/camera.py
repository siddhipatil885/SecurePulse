"""Camera API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    frigate_camera_name: str
    location: str | None
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None