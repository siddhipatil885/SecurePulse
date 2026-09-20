"""FastAPI dependency factories for application services."""

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db_session
from app.repositories.cameras import CameraRepository
from app.repositories.events import EventRepository
from app.realtime.publisher import InMemoryEventPublisher
from app.services.camera_service import CameraService
from app.services.event_service import EventService

_event_publisher = InMemoryEventPublisher()


async def get_session() -> AsyncIterator[AsyncSession]:
    async for session in get_db_session():
        yield session


def get_camera_service(session: AsyncSession = Depends(get_session)) -> CameraService:
    return CameraService(CameraRepository(session))


def get_event_service(session: AsyncSession = Depends(get_session)) -> EventService:
    return EventService(EventRepository(session))


def get_event_publisher() -> InMemoryEventPublisher:
    return _event_publisher