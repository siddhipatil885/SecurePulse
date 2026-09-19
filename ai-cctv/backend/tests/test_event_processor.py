"""Phase 4 event processor tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.domain.events import DetectionEvent
from app.domain.security import SecurityDecision
from app.models.camera import Camera
from app.models.security_event import SecurityEvent
from app.realtime.publisher import InMemoryEventPublisher
from app.integrations.security_engine import SecurityEngineError
from app.services.event_processor import (
    CameraDisabledError,
    CameraNotFoundError,
    EventProcessor,
    EventProcessingError,
    SecurityEngineUnavailableError,
)


def make_detection(**overrides: object) -> DetectionEvent:
    values: dict[str, object] = {
        "source": "frigate",
        "source_event_id": "frigate-123",
        "camera": "front_door",
        "object_type": "person",
        "confidence": 0.94,
        "timestamp": datetime(2026, 9, 19, 19, 30, 20, tzinfo=timezone.utc),
        "metadata": {"zones": ["entrance"]},
    }
    values.update(overrides)
    return DetectionEvent(**values)


def make_processor(
    camera: Camera | None = Camera(
        id=1, name="Front Door", frigate_camera_name="front_door", enabled=True
    ),
    existing: SecurityEvent | None = None,
    security_engine: AsyncMock | None = None,
    failure_mode: str = "STORE_UNCLASSIFIED",
    publisher: InMemoryEventPublisher | None = None,
) -> tuple[EventProcessor, AsyncMock, AsyncMock, AsyncMock]:
    session = AsyncMock()
    camera_repository = AsyncMock()
    camera_repository.get_by_frigate_name.return_value = camera
    event_repository = AsyncMock()
    event_repository.get_by_frigate_event_id.return_value = existing
    def persist(event: SecurityEvent) -> SecurityEvent:
        event.id = event.id or 1
        return event

    event_repository.create.side_effect = persist
    return (
        EventProcessor(
            session,
            camera_repository,
            event_repository,
            security_engine=security_engine,
            security_engine_failure_mode=failure_mode,
            publisher=publisher,
        ),
        session,
        camera_repository,
        event_repository,
    )


@pytest.mark.asyncio
async def test_processor_persists_unclassified_event() -> None:
    processor, session, _, event_repository = make_processor()

    result = await processor.process(make_detection())

    assert result.duplicate is False
    assert result.event.event_type == "DETECTION"
    assert result.event.severity == "UNCLASSIFIED"
    assert result.event.status == "UNCLASSIFIED"
    assert result.event.camera_id == 1
    assert result.event.zone == "entrance"
    event_repository.create.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_processor_returns_duplicate_without_creating_event() -> None:
    existing = SecurityEvent(id=42)
    processor, session, _, event_repository = make_processor(existing=existing)

    result = await processor.process(make_detection())

    assert result.duplicate is True
    assert result.event.id == 42
    event_repository.create.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_processor_rejects_unknown_camera() -> None:
    processor, _, _, _ = make_processor(camera=None)

    with pytest.raises(CameraNotFoundError):
        await processor.process(make_detection())


@pytest.mark.asyncio
async def test_processor_rejects_disabled_camera() -> None:
    camera = Camera(
        id=1, name="Front Door", frigate_camera_name="front_door", enabled=False
    )
    processor, _, _, _ = make_processor(camera=camera)

    with pytest.raises(CameraDisabledError):
        await processor.process(make_detection())


@pytest.mark.asyncio
async def test_processor_rejects_non_frigate_sources() -> None:
    processor, _, _, _ = make_processor()

    with pytest.raises(EventProcessingError):
        await processor.process(make_detection(source="unknown"))


@pytest.mark.asyncio
async def test_processor_applies_security_decision() -> None:
    security_engine = AsyncMock()
    security_engine.evaluate.return_value = SecurityDecision(
        event_type="LOITERING",
        score=82,
        severity="HIGH",
        reason="Person remained in restricted area",
    )
    processor, _, _, _ = make_processor(security_engine=security_engine)

    result = await processor.process(make_detection())

    assert result.event.event_type == "LOITERING"
    assert result.event.score == 82
    assert result.event.severity == "HIGH"
    assert result.event.status == "OPEN"
    security_engine.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_processor_stores_unclassified_when_engine_fails() -> None:
    security_engine = AsyncMock()
    security_engine.evaluate.side_effect = SecurityEngineError("timeout")
    processor, _, _, _ = make_processor(security_engine=security_engine)

    result = await processor.process(make_detection())

    assert result.event.status == "UNCLASSIFIED"
    assert result.event.score is None


@pytest.mark.asyncio
async def test_processor_can_reject_when_engine_fails() -> None:
    security_engine = AsyncMock()
    security_engine.evaluate.side_effect = SecurityEngineError("timeout")
    processor, session, _, event_repository = make_processor(
        security_engine=security_engine, failure_mode="REJECT"
    )

    with pytest.raises(SecurityEngineUnavailableError):
        await processor.process(make_detection())

    event_repository.create.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_processor_publishes_only_after_commit() -> None:
    publisher = InMemoryEventPublisher()
    queue = await publisher.subscribe()
    processor, session, _, _ = make_processor(publisher=publisher)

    await processor.process(make_detection())

    session.commit.assert_awaited_once()
    message = await queue.get()
    assert message["type"] == "security_event"
    assert message["data"]["id"] == 1  # type: ignore[index]