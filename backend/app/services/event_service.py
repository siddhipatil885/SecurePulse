"""Security event application service."""

from datetime import datetime

from app.core.exceptions import ApplicationError
from app.models.security_event import SecurityEvent
from app.repositories.events import EventRepository


class EventService:
    """Coordinate event reads, filtering, and pagination."""

    def __init__(self, repository: EventRepository) -> None:
        self.repository = repository

    async def get(self, event_id: int) -> SecurityEvent:
        event = await self.repository.get_by_id(event_id)
        if event is None:
            raise ApplicationError(
                "EVENT_NOT_FOUND", "The requested event does not exist.", 404
            )
        return event

    async def list(
        self,
        *,
        camera_id: int | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SecurityEvent], int]:
        if start_time and end_time and start_time > end_time:
            raise ApplicationError(
                "INVALID_TIME_RANGE", "start_time must be before end_time."
            )
        filters = {
            "camera_id": camera_id,
            "event_type": event_type,
            "severity": severity,
            "start_time": start_time,
            "end_time": end_time,
        }
        total = await self.repository.count(**filters)
        events = await self.repository.list(
            **filters, limit=page_size, offset=(page - 1) * page_size
        )
        return events, total