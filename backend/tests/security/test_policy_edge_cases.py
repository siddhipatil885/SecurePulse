from datetime import datetime, time, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.security.adapters.frigate import FrigateDetectionAdapter, FrigateDetectionError
from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import (
    BoundingBox,
    DetectionEvent,
    EventState,
    OperatingWindow,
    Point,
    Zone,
)

T0 = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)  # Sunday


def make_zone(**overrides) -> Zone:
    values = {
        "id": "restricted",
        "name": "Restricted",
        "camera_id": "cam1",
        "polygon": [
            Point(x=400, y=200), Point(x=800, y=200),
            Point(x=800, y=600), Point(x=400, y=600),
        ],
    }
    values.update(overrides)
    return Zone(**values)


def make_detection(*, at=T0, bbox=None, confidence=0.9, width=1920, height=1080,
                   phase=EventState.START, object_id="object-1", source_event_id="event-1"):
    return {
        "source": "frigate", "source_event_id": source_event_id, "camera_id": "cam1",
        "object_id": object_id, "object_type": "person", "confidence": confidence,
        "timestamp": at, "bbox": bbox or BoundingBox(x1=500, y1=300, x2=700, y2=500),
        "frame_width": width, "frame_height": height, "event_state": phase,
    }


def zone_entries(engine, detection, at):
    return [candidate for candidate in engine.evaluate(detection, current_time=at)
            if candidate.event_type.value == "ZONE_ENTRY"]


def test_zone_hours_are_local_and_end_is_exclusive():
    zone = make_zone(
        timezone="UTC",
        restricted_hours=[OperatingWindow(weekdays=[6], start=time(9), end=time(11))],
    )
    engine = SecurityEngine(SecurityConfig(zones=[zone]))
    allowed_time = T0.replace(hour=8)
    restricted_time = T0.replace(hour=10)
    after_window = T0.replace(hour=11)

    assert zone.is_restricted_at(restricted_time)
    assert not zone.is_restricted_at(after_window)
    assert not zone_entries(engine, DetectionEvent(**make_detection(at=allowed_time)), allowed_time)
    assert zone_entries(engine, DetectionEvent(**make_detection(at=restricted_time)), restricted_time)


def test_zone_dwell_and_confidence_gate_are_applied():
    zone = make_zone(minimum_confidence=0.8, minimum_dwell_seconds=3)
    engine = SecurityEngine(SecurityConfig(zones=[zone], zone_entry_cooldown_seconds=0))
    low = DetectionEvent(**make_detection(confidence=0.7))
    assert zone_entries(engine, low, T0) == []
    assert zone_entries(engine, DetectionEvent(**make_detection(at=T0)), T0) == []
    assert zone_entries(engine, DetectionEvent(**make_detection(at=T0 + timedelta(seconds=2))),
                        T0 + timedelta(seconds=2)) == []
    result = zone_entries(engine, DetectionEvent(**make_detection(at=T0 + timedelta(seconds=3))),
                          T0 + timedelta(seconds=3))
    assert len(result) == 1
    assert result[0].metadata["dwell_seconds"] == 3


def test_frame_resolution_change_scales_configured_polygon():
    zone = make_zone(frame_width=1920, frame_height=1080)
    engine = SecurityEngine(SecurityConfig(zones=[zone]))
    from app.security.models import DetectionEvent

    detection = DetectionEvent(**make_detection(
        bbox=BoundingBox(x1=220, y1=120, x2=300, y2=200), width=960, height=540,
    ))
    assert zone_entries(engine, detection, T0)


def test_end_phase_clears_track_state_and_late_updates_are_ignored():
    zone = make_zone()
    engine = SecurityEngine(SecurityConfig(zones=[zone], zone_entry_cooldown_seconds=60))
    assert zone_entries(engine, DetectionEvent(**make_detection()), T0)
    ended = DetectionEvent(**make_detection(at=T0 + timedelta(seconds=1), phase=EventState.END))
    assert engine.evaluate(ended, current_time=ended.timestamp) == []
    late_update = DetectionEvent(**make_detection(at=T0 + timedelta(seconds=2), phase=EventState.UPDATE))
    assert engine.evaluate(late_update, current_time=late_update.timestamp) == []
    reentered = DetectionEvent(**make_detection(
        at=T0 + timedelta(seconds=2), object_id="object-2", source_event_id="event-2",
    ))
    assert zone_entries(engine, reentered, reentered.timestamp)


def test_out_of_order_end_does_not_close_newer_active_event():
    engine = SecurityEngine(SecurityConfig(zones=[make_zone()], zone_entry_cooldown_seconds=0))
    assert zone_entries(engine, DetectionEvent(**make_detection(at=T0)), T0)
    later = DetectionEvent(**make_detection(at=T0 + timedelta(seconds=5), phase=EventState.UPDATE))
    engine.evaluate(later, current_time=later.timestamp)
    old_end = DetectionEvent(**make_detection(at=T0 + timedelta(seconds=2), phase=EventState.END))
    assert engine.evaluate(old_end, current_time=old_end.timestamp) == []
    current = DetectionEvent(**make_detection(at=T0 + timedelta(seconds=6), phase=EventState.UPDATE))
    # The old END must not reset zone membership for the newer active event.
    assert zone_entries(engine, current, current.timestamp) == []


def test_out_of_order_outside_frame_does_not_reset_zone_entry_state():
    engine = SecurityEngine(SecurityConfig(zones=[make_zone()], zone_entry_cooldown_seconds=0))
    entered = DetectionEvent(**make_detection(at=T0))
    assert zone_entries(engine, entered, T0)
    late_outside = DetectionEvent(**make_detection(
        at=T0 - timedelta(seconds=1), bbox=BoundingBox(x1=100, y1=300, x2=300, y2=500),
    ))
    engine.evaluate(late_outside, current_time=late_outside.timestamp)
    still_inside = DetectionEvent(**make_detection(at=T0 + timedelta(seconds=1)))
    assert zone_entries(engine, still_inside, still_inside.timestamp) == []


def test_invalid_self_intersecting_zone_is_rejected():
    with pytest.raises(ValidationError):
        make_zone(polygon=[
            Point(x=0, y=0), Point(x=10, y=10),
            Point(x=0, y=10), Point(x=10, y=0),
        ])


def test_timezone_naive_security_detection_is_rejected():
    with pytest.raises(ValidationError):
        DetectionEvent(**make_detection(at=datetime(2026, 9, 20, 10, 0)))


def test_malformed_frigate_payload_returns_bounded_error():
    with pytest.raises(FrigateDetectionError):
        FrigateDetectionAdapter.parse({"type": "new", "after": {"id": "x"}})


def test_frigate_payload_with_invalid_confidence_is_rejected():
    payload = {
        "type": "new",
        "after": {"id": "event-1", "camera": "cam1", "label": "person",
                  "start_time": T0.timestamp(), "score": 1.4},
    }
    with pytest.raises(FrigateDetectionError):
        FrigateDetectionAdapter.parse(payload)


def test_malformed_frigate_box_is_ignored_as_missing_geometry():
    payload = {
        "type": "new",
        "after": {
            "id": "event-1", "camera": "cam1", "label": "person",
            "start_time": T0.timestamp(), "score": 0.9, "box": [1, "bad", 3, 4],
        },
    }
    assert FrigateDetectionAdapter.parse(payload).bbox is None
