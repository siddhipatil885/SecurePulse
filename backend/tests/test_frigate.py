"""Phase 3 Frigate adapter tests."""

from datetime import timezone

import pytest

from app.domain.events import DetectionEvent
from app.integrations.frigate import FrigateEventParser, FrigatePayloadError


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