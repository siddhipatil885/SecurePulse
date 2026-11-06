from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.case import CaseDetail, CaseEvidence, CaseTimelineItem
from app.schemas.dispatch import OfferView


class NotificationReport(BaseModel):
    kind: str
    destination: str | None
    status: str
    attempts: int = Field(ge=0)
    last_attempt_at: datetime | None = None


class IncidentReport(BaseModel):
    generated_at: datetime
    incident: CaseDetail
    timeline: list[CaseTimelineItem]
    evidence: list[CaseEvidence]
    assignments: list[OfferView]
    notifications: list[NotificationReport]
    metrics: dict[str, Any]
    tracking: dict[str, Any]
