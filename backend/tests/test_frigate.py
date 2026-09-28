"""Phase 3 Frigate adapter tests."""

from datetime import timezone

import pytest

from app.domain.events import DetectionEvent
from app.core.config import Settings
from app.integrations.frigate import FrigateClient, FrigateEventParser, FrigatePayloadError


def test_parser_normalizes_frigate_event() -> None:
    detection = FrigateEventParser().parse(
        {
            "type": "new",
            "before": {},
            "after": {
                "id": "abc123",
                "camera": "front_door",
                "label": "person",
                "top_score": 0.94,
                "start_time": 1790105420.0,
                "zones": ["entrance"],
                "has_snapshot": True,
            },
        }
    )

    assert isinstance(detection, DetectionEvent)
    assert detection.source_event_id == "abc123"
    assert detection.camera == "front_door"
    assert detection.confidence == 0.94
    assert detection.timestamp.tzinfo == timezone.utc
    assert detection.metadata["zones"] == ["entrance"]


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        {"type": "new", "after": {}},
        {"type": "stats", "after": {}},
        {"type": "new", "after": {"id": "abc", "camera": "cam1", "label": "person"}},
    ],
)
def test_parser_rejects_malformed_or_unsupported_events(payload: object) -> None:
    with pytest.raises(FrigatePayloadError):
        FrigateEventParser().parse(payload)  # type: ignore[arg-type]


def test_detection_event_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError):
        DetectionEvent(
            source="frigate",
            source_event_id="abc",
            camera="cam1",
            object_type="person",
            confidence=1.1,
            timestamp="2026-09-19T19:30:20Z",
        )


def test_client_starts_reconnectable_loop_without_blocking_for_broker() -> None:
    client = FrigateClient(
        on_detection=lambda _: None,
        settings=Settings(mqtt_host="broker", mqtt_port=1883),
    )
    client.client.connect_async = lambda host, port, keepalive: None  # type: ignore[method-assign]
    client.client.loop_start = lambda: None  # type: ignore[method-assign]

    assert client.start() is True
    assert client.connected is False


def test_client_connection_callbacks_control_live_state() -> None:
    client = FrigateClient(
        on_detection=lambda _: None,
        settings=Settings(),
    )

    client._on_connect(client.client, None, {}, 0)
    assert client.connected is True
    client._on_disconnect(client.client, None, 1)
    assert client.connected is False