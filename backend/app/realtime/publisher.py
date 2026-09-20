"""In-process publish/subscribe for committed security events."""

import asyncio
import logging
from typing import Protocol

from app.models.security_event import SecurityEvent
from app.schemas.event import EventResponse

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish(self, event: SecurityEvent) -> None: ...


class InMemoryEventPublisher:
    """Small edge-friendly publisher suitable for a single backend process."""

    def __init__(self, queue_size: int = 100) -> None:
        self.queue_size = queue_size
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()

    async def subscribe(self) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: SecurityEvent) -> None:
        payload = {
            "type": "security_event",
            "data": EventResponse.model_validate(event).model_dump(
                mode="json", by_alias=True
            ),
        }
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Dropped real-time event for a slow subscriber")