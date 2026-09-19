"""Phase 7 real-time publisher tests."""

from datetime import datetime, timezone

import pytest

from app.models.security_event import SecurityEvent
from app.realtime.publisher import InMemoryEventPublisher


@pytest.mark.asyncio
async def test_publisher_broadcasts_serialized_security_event() -> None:
    publisher = InMemoryEventPublisher()
    first = await publisher.subscribe()
    second = await publisher.subscribe()
    event = SecurityEvent(
        id=42,
        camera_id=1,
        event_type="LOITERING",
        object_type="person",
        confidence=0.94,
        timestamp=datetime(2026, 9, 19, tzinfo=timezone.utc),
        severity="HIGH",
        status="OPEN",
        score=82,
        zone="entrance",
        frigate_event_id="frigate-42",
        reason="Person remained in restricted area",
        event_metadata={},
    )

    await publisher.publish(event)

    assert (await first.get())["data"]["event_type"] == "LOITERING"  # type: ignore[index]
    assert (await second.get())["data"]["score"] == 82  # type: ignore[index]


@pytest.mark.asyncio
async def test_unsubscribed_queue_stops_receiving_events() -> None:
    publisher = InMemoryEventPublisher()
    queue = await publisher.subscribe()
    await publisher.unsubscribe(queue)

    event = SecurityEvent(
        id=1,
        camera_id=1,
        event_type="DETECTION",
        object_type="person",
        confidence=0.8,
        timestamp=datetime(2026, 9, 19, tzinfo=timezone.utc),
        severity="INFO",
        status="OPEN",
        event_metadata={},
    )
    await publisher.publish(event)

    assert queue.empty()