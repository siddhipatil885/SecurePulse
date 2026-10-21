"""In-process publish/subscribe for committed security events."""

import asyncio
import logging
from typing import Protocol

from app.models.security_event import SecurityEvent
from app.schemas.event import EventResponse

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish(self, event: SecurityEvent) -> None: ...
    async def publish_tracks(
        self, camera_id: str, tracks: list[dict[str, object]], property_id: int | None = None
    ) -> None: ...


class InMemoryEventPublisher:
    """Small edge-friendly publisher suitable for a single backend process."""

    def __init__(self, queue_size: int = 100) -> None:
        self.queue_size = queue_size
        self._subscribers: dict[
            asyncio.Queue[dict[str, object]], frozenset[int] | None
        ] = {}
        self._camera_properties: dict[str, int] = {}

    async def subscribe(
        self, property_ids: frozenset[int] | None = None
    ) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers[queue] = property_ids
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        self._subscribers.pop(queue, None)

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
