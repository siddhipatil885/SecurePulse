"""Phase 9 mocked end-to-end detection pipeline test."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.domain.security import SecurityDecision
from app.integrations.frigate import FrigateEventParser
from app.models.camera import Camera
from app.realtime.publisher import InMemoryEventPublisher
from app.services.event_processor import EventProcessor


@pytest.mark.asyncio
async def test_frigate_detection_reaches_persistence_and_realtime() -> None:
    detection = FrigateEventParser().parse(
        {
            "type": "new",
            "after": {
                "id": "frigate-e2e-1",
                "camera": "front_door",
                "label": "person",
                "top_score": 0.94,
                "start_time": datetime(2026, 9, 19, tzinfo=timezone.utc).timestamp(),
            },
        }
    )
    session = AsyncMock()
    camera_repository = AsyncMock()
    camera_repository.get_by_frigate_name.return_value = Camera(
        id=1,
        name="Front Door",
        frigate_camera_name="front_door",
        enabled=True,
    )
    event_repository = AsyncMock()
    event_repository.get_by_frigate_event_id.return_value = None

    def persist(event):
        event.id = 101
        return event

    event_repository.create.side_effect = persist
    security_engine = AsyncMock()
    security_engine.evaluate.return_value = SecurityDecision(
        event_type="PERSON_DETECTED",
        score=15,
        severity="INFO",
        reason="Person detected",
    )
    publisher = InMemoryEventPublisher()
    queue = await publisher.subscribe()
    processor = EventProcessor(
        session,
        camera_repository,
        event_repository,
        security_engine=security_engine,
        publisher=publisher,
    )

    result = await processor.process(detection)
    message = await queue.get()

    assert result.event.id == 101
    assert result.event.severity == "INFO"
    assert result.event.score == 15
    assert message["type"] == "security_event"
    assert message["data"]["id"] == 101  # type: ignore[index]
    session.commit.assert_awaited_once()