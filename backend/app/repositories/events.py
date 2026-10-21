"""Security event database access."""

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.security_event import SecurityEvent
from app.models.operations import SourceEventReceipt


class EventRepository:
    """Persist and query normalized security events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, event: SecurityEvent) -> SecurityEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_receipt(self, receipt: SourceEventReceipt) -> SourceEventReceipt:
        self.session.add(receipt)
        await self.session.flush()
        return receipt

    async def get_receipt(
        self,
        *,
        source_system: str,
        source_event_id: str,
        event_phase: str,
        revision: str,
    ) -> SourceEventReceipt | None:
        statement = select(SourceEventReceipt).options(selectinload(SourceEventReceipt.security_event)).where(
            SourceEventReceipt.source_system == source_system,
            SourceEventReceipt.source_event_id == source_event_id,
            SourceEventReceipt.event_phase == event_phase,
            SourceEventReceipt.revision == revision,
        )
        return await self.session.scalar(statement)

    async def get_by_id(
        self, event_id: int, property_ids: frozenset[int] | None = None
    ) -> SecurityEvent | None:
        statement = select(SecurityEvent).where(SecurityEvent.id == event_id)
        if property_ids is not None:
            statement = statement.where(SecurityEvent.property_id.in_(property_ids))
        return await self.session.scalar(statement)

    async def get_by_frigate_event_id(self, frigate_event_id: str) -> SecurityEvent | None:
        statement = select(SecurityEvent).where(
            SecurityEvent.frigate_event_id == frigate_event_id
        )
        return await self.session.scalar(statement)

    async def get_recent_by_camera_object(
        self,
        camera_id: int,
        object_type: str,
        since: datetime,
    ) -> SecurityEvent | None:
        statement = (
            select(SecurityEvent)
            .where(
                SecurityEvent.camera_id == camera_id,
                SecurityEvent.object_type == object_type,
                SecurityEvent.timestamp >= since,
            )
            .order_by(SecurityEvent.timestamp.desc())
            .limit(1)
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
        property_ids: frozenset[int] | None = None,
    ) -> list[SecurityEvent]:
        statement: Select[tuple[SecurityEvent]] = select(SecurityEvent)
        if property_ids is not None:
            statement = statement.where(SecurityEvent.property_id.in_(property_ids))
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
        statement = statement.order_by(SecurityEvent.timestamp.desc(), SecurityEvent.id.desc()).limit(limit).offset(offset)
        return list((await self.session.scalars(statement)).all())

    async def count(
        self,
        *,
        camera_id: int | None = None,
        event_type: str | None = None,
        severity: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        property_ids: frozenset[int] | None = None,
    ) -> int:
        statement = select(func.count(SecurityEvent.id))
        if property_ids is not None:
            statement = statement.where(SecurityEvent.property_id.in_(property_ids))
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
