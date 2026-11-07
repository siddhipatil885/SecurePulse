"""In-process publish/subscribe for committed security events."""

import asyncio
import logging
from typing import Protocol, Callable, Awaitable

from app.models.security_event import SecurityEvent
from app.schemas.event import EventResponse

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish(self, event: SecurityEvent) -> None: ...
    async def publish_tracks(
        self, camera_id: str, tracks: list[dict[str, object]], property_id: int | None = None
    ) -> None: ...
    async def publish_case(self, property_id: int, key: str) -> None: ...
    async def publish_marshal_location(
        self, property_id: int, assignment_id: int, location: dict[str, object]
    ) -> None: ...


class InMemoryEventPublisher:
    """Small edge-friendly publisher suitable for a single backend process."""

    def __init__(self, queue_size: int = 100) -> None:
        self.queue_size = queue_size
        self._subscribers: dict[
            asyncio.Queue[dict[str, object]], frozenset[int] | None
        ] = {}
        self._camera_properties: dict[str, int] = {}
        self._location_access: dict[asyncio.Queue, Callable[[int, int], Awaitable[bool]]] = {}

    async def subscribe(
        self, property_ids: frozenset[int] | None = None,
        location_access: Callable[[int, int], Awaitable[bool]] | None = None,
    ) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers[queue] = property_ids
        if location_access is not None:
            self._location_access[queue] = location_access
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        self._subscribers.pop(queue, None)
        self._location_access.pop(queue, None)

    async def publish_case(self, property_id: int, key: str) -> None:
        payload = {"type": "case_updated", "property_id": property_id, "data": {"key": key}}
        for queue, property_ids in tuple(self._subscribers.items()):
            if property_ids is not None and property_id not in property_ids:
                continue
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Dropped case update for a slow subscriber")

    async def publish_marshal_location(
        self, property_id: int, assignment_id: int, location: dict[str, object]
    ) -> None:
        payload = {
            "type": "marshal_location",
            "property_id": property_id,
            "data": {"assignment_id": assignment_id, "location": location},
        }
        for queue, property_ids in tuple(self._subscribers.items()):
            if property_ids is not None and property_id not in property_ids:
                continue
            authorize = self._location_access.get(queue)
            try:
                allowed = authorize is not None and await authorize(property_id, assignment_id)
            except Exception:
                logger.warning('Unable to authorize marshal location subscriber')
                allowed = False
            if not allowed:
                continue
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Dropped marshal location update for a slow subscriber")

    async def publish(self, event: SecurityEvent) -> None:
        payload = {
            "type": "security_event",
            "event_id": f"security-event:{event.id}:{event.status}",
            "property_id": event.property_id,
            "kind": "incident.updated",
            "incident_id": event.id,
            "occurred_at": event.timestamp.isoformat(),
            "data": EventResponse.model_validate(event).model_dump(
                mode="json", by_alias=True
            ),
        }
        for queue, property_ids in tuple(self._subscribers.items()):
            if property_ids is not None and event.property_id not in property_ids:
                continue
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Dropped real-time event for a slow subscriber")

    async def publish_tracks(
        self, camera_id: str, tracks: list[dict[str, object]], property_id: int | None = None
    ) -> None:
        """Publish the current camera track set; observations are never alerts."""
        if property_id is not None:
            self._camera_properties[camera_id] = property_id
        else:
            property_id = self._camera_properties.get(camera_id)
        payload: dict[str, object] = {
            "type": "person_tracks",
            "data": {"camera_id": camera_id, "tracks": tracks},
        }
        if property_id is not None:
            payload["property_id"] = property_id
        for queue, property_ids in tuple(self._subscribers.items()):
            if property_ids is not None and (
                property_id is None or property_id not in property_ids
            ):
                continue
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Dropped real-time track update for a slow subscriber")
