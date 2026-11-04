"""Phase 3 Frigate adapter tests."""

from datetime import timezone
import json
from pathlib import Path

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
    assert detection.metadata["source_system"] == "frigate"
    assert detection.metadata["event_phase"] == "new"
    assert detection.metadata["occurred_at"] == detection.timestamp.isoformat()
    assert detection.metadata["ingested_at"]


def test_parser_accepts_end_event_when_frigate_omits_end_time() -> None:
    """Do not leave a live track open because an upstream end is incomplete."""
    detection = FrigateEventParser().parse(
        {
            "type": "end",
            "after": {
                "id": "abc123",
                "camera": "front_door",
                "label": "person",
                "top_score": 0.94,
                "start_time": 1790105420.0,
            },
        }
    )

    assert detection.metadata["lifecycle"] == "end"
    assert detection.timestamp.tzinfo == timezone.utc


def test_parser_revision_deduplicates_replays_but_preserves_real_updates() -> None:
    parser = FrigateEventParser()
    payload = {
        "type": "update",
        "after": {
            "id": "abc123",
            "camera": "front_door",
            "label": "person",
            "top_score": 0.94,
            "start_time": 1790105420.0,
            "frame_time": 1790105421.0,
        },
    }

    first = parser.parse(payload)
    replay = parser.parse(payload)
    payload["after"]["frame_time"] = 1790105422.0
    update = parser.parse(payload)

    assert first.metadata["revision"] == replay.metadata["revision"]
    assert first.metadata["revision"] != update.metadata["revision"]
    assert len(first.metadata["revision"]) == 64


def test_versioned_event_fixture_covers_frigate_lifecycle() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "frigate" / "v0.13" / "events.json"
    payloads = json.loads(fixture_path.read_text(encoding="utf-8"))
    detections = [FrigateEventParser().parse(payload) for payload in payloads]

    assert [item.metadata["lifecycle"] for item in detections] == ["new", "update", "end"]
    assert {item.source_event_id for item in detections} == {"sample-event-001"}
    assert detections[1].metadata["bounding_box"] == [402, 291, 953, 719]


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


@pytest.mark.parametrize("score", [True, -0.1, 1.1, float("nan"), float("inf")])
def test_parser_rejects_invalid_confidence(score: float) -> None:
    with pytest.raises(FrigatePayloadError):
        FrigateEventParser().parse(
            {"type": "new", "after": {"id": "e1", "camera": "cam", "label": "person", "top_score": score, "start_time": 1}}
        )


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


def test_client_configures_broker_credentials() -> None:
    client = FrigateClient(
        on_detection=lambda _: None,
        settings=Settings(mqtt_username="securepulse", mqtt_password="example-password"),
    )

    assert client.client._username == b"securepulse"


def test_mqtt_credentials_must_be_configured_as_a_pair() -> None:
    with pytest.raises(ValueError, match="configured together"):
        Settings(mqtt_username="securepulse")
