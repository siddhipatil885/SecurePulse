"""Security event database access."""

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_event import SecurityEvent


class EventRepository:
    """Persist and query normalized security events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: SecurityEvent) -> SecurityEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: int) -> SecurityEvent | None:
        return await self.session.get(SecurityEvent, event_id)

    async def get_by_frigate_event_id(self, frigate_event_id: str) -> SecurityEvent | None:
        statement = select(SecurityEvent).where(
            SecurityEvent.frigate_event_id == frigate_event_id
        )
        return await self.session.scalar(statement)

    async def list(
        self,
        *,
        camera_id: int | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SecurityEvent]:
        statement: Select[tuple[SecurityEvent]] = select(SecurityEvent)
        if camera_id is not None:
            statement = statement.where(SecurityEvent.camera_id == camera_id)
        if event_type is not None:
            statement = statement.where(SecurityEvent.event_type == event_type)
        if severity is not None:
            statement = statement.where(SecurityEvent.severity == severity)
        if start_time is not None:
            statement = statement.where(SecurityEvent.timestamp >= start_time)
        if end_time is not None:
            statement = statement.where(SecurityEvent.timestamp <= end_time)
        statement = statement.order_by(SecurityEvent.timestamp.desc()).limit(limit).offset(offset)
        return list((await self.session.scalars(statement)).all())

    async def count(
        self,
        *,
        camera_id: int | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        statement = select(func.count(SecurityEvent.id))
        if camera_id is not None:
            statement = statement.where(SecurityEvent.camera_id == camera_id)
        if event_type is not None:
            statement = statement.where(SecurityEvent.event_type == event_type)
        if severity is not None:
            statement = statement.where(SecurityEvent.severity == severity)
        if start_time is not None:
            statement = statement.where(SecurityEvent.timestamp >= start_time)
        if end_time is not None:
            statement = statement.where(SecurityEvent.timestamp <= end_time)
        return int((await self.session.scalar(statement)) or 0)