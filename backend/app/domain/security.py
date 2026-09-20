"""Security-engine request and decision contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SecuritySeverity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


class SecurityContext(BaseModel):
    """Context sent to the security intelligence engine."""

    model_config = ConfigDict(extra="forbid")

    camera_id: int = Field(gt=0)
    object_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    zone: str | None = None


class SecurityDecision(BaseModel):
    """Validated classification returned by the security intelligence engine."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=100)
    score: int = Field(ge=0, le=100)
    severity: SecuritySeverity
    reason: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)