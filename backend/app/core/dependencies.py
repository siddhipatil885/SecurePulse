"""FastAPI dependency factories for application services."""

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db_session
from app.repositories.cameras import CameraRepository
from app.repositories.events import EventRepository
from app.realtime.publisher import InMemoryEventPublisher
from app.services.person_tracker import PersonTracker
from app.core.config import get_settings
from app.services.camera_service import CameraService
from app.services.event_service import EventService

_event_publisher = InMemoryEventPublisher()
_settings = get_settings()
_person_tracker = PersonTracker(
    lost_track_timeout_seconds=_settings.tracking_lost_track_timeout_seconds,
    minimum_detection_confidence=_settings.tracking_minimum_detection_confidence,
    default_frame_width=_settings.frame_width,
    default_frame_height=_settings.frame_height,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async for session in get_db_session():
        yield session


def get_camera_service(session: AsyncSession = Depends(get_session)) -> CameraService:
    return CameraService(CameraRepository(session))


def get_event_service(session: AsyncSession = Depends(get_session)) -> EventService:
    return EventService(EventRepository(session))


def get_event_publisher() -> InMemoryEventPublisher:
    return _event_publisher


def get_person_tracker() -> PersonTracker:
    """Return the process-local projection of Frigate's active person tracks."""
    return _person_tracker
