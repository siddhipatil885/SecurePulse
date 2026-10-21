"""Property API schemas."""

from pydantic import BaseModel, ConfigDict


class PropertyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    active: bool
