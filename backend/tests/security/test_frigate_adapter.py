"""Tests for the Frigate to Security Engine adapter."""

from datetime import datetime, timezone

import pytest

from app.security.adapters.frigate import FrigateDetectionAdapter
from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import EventState, EventType, Zone, Point


@pytest.fixture
def raw_mqtt_payload() -> dict:
    return {
        "type": "update",
        "before": {},
        "after": {
            "id": "1789898622.985494-7n794l",
            "camera": "laptop_camera",
            "label": "person",
            "zones": [],
            "start_time": 1789898620.000,
            "frame_time": 1789898622.985494,
            "end_time": None,
            "has_clip": True,
            "has_snapshot": True,
            "box": [390, 289, 949, 717],
            "score": 0.70703125,
            "path_data": []
        }
    }


class TestFrigateAdapterMappings:

    def test_camera_is_mapped_correctly(self, raw_mqtt_payload: dict) -> None:
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert detection.camera_id == "laptop_camera"
        assert detection.source_event_id == "1789898622.985494-7n794l"
        assert detection.object_id == "1789898622.985494-7n794l"

    def test_confidence_from_score(self, raw_mqtt_payload: dict) -> None:
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert detection.confidence == 0.70703125

    def test_timestamp_from_frame_time(self, raw_mqtt_payload: dict) -> None:
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        expected_time = datetime.fromtimestamp(1789898622.985494, tz=timezone.utc)
        assert detection.timestamp == expected_time

    def test_timestamp_fallback_to_start_time(self, raw_mqtt_payload: dict) -> None:
        del raw_mqtt_payload["after"]["frame_time"]
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        expected_time = datetime.fromtimestamp(1789898620.000, tz=timezone.utc)
        assert detection.timestamp == expected_time

    def test_active_event_has_correct_lifecycle_state(self, raw_mqtt_payload: dict) -> None:
        # payload type is update, end_time is null
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert detection.event_state == EventState.UPDATE

    def test_new_event_has_start_state(self, raw_mqtt_payload: dict) -> None:
        raw_mqtt_payload["type"] = "new"
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert detection.event_state == EventState.START

    def test_ended_event_has_correct_lifecycle_state(self, raw_mqtt_payload: dict) -> None:
        raw_mqtt_payload["type"] = "end"
        raw_mqtt_payload["after"]["end_time"] = 1789898625.123
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert detection.event_state == EventState.END

    def test_bounding_box_from_absolute_pixels(self, raw_mqtt_payload: dict) -> None:
        # Values > 1 are treated as pixels automatically
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        
        assert detection.bbox is not None
        assert detection.bbox.x1 == 390
        assert detection.bbox.y1 == 289
        assert detection.bbox.x2 == 949
        assert detection.bbox.y2 == 717

    def test_bounding_box_normalized_requires_dimensions(self, raw_mqtt_payload: dict) -> None:
        raw_mqtt_payload["after"]["box"] = [0.10, 0.20, 0.50, 0.80]
        # Without dimensions -> None
        det_none = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert det_none.bbox is None

        # With dimensions -> scaled
        det_scaled = FrigateDetectionAdapter.parse(
            raw_mqtt_payload, frame_width=1280, frame_height=720
        )
        assert det_scaled.bbox is not None
        assert det_scaled.bbox.x1 == pytest.approx(128)
        assert det_scaled.bbox.y1 == pytest.approx(144)
        assert det_scaled.bbox.x2 == pytest.approx(640)
        assert det_scaled.bbox.y2 == pytest.approx(576)

    def test_bounding_box_invalid_rejected(self, raw_mqtt_payload: dict) -> None:
        # x2 < x1
        raw_mqtt_payload["after"]["box"] = [900, 200, 500, 800]
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert detection.bbox is None

        # y2 < y1
        raw_mqtt_payload["after"]["box"] = [100, 800, 500, 200]
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        assert detection.bbox is None


class TestAdapterIdentityAndIntegration:

    def test_consecutive_updates_preserve_identity(self, raw_mqtt_payload: dict) -> None:
        # First update
        payload1 = dict(raw_mqtt_payload)
        payload1["after"] = dict(raw_mqtt_payload["after"])
        payload1["after"]["frame_time"] = 1789898622.0
        
        # Second update for same object
        payload2 = dict(raw_mqtt_payload)
        payload2["after"] = dict(raw_mqtt_payload["after"])
        payload2["after"]["frame_time"] = 1789898623.0
        
        det1 = FrigateDetectionAdapter.parse(payload1)
        det2 = FrigateDetectionAdapter.parse(payload2)
        
        # Object ID must match exactly so engine tracking works
        assert det1.object_id == det2.object_id
        assert det1.object_id == "1789898622.985494-7n794l"

    def test_person_event_produces_person_detected(self, raw_mqtt_payload: dict) -> None:
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        engine = SecurityEngine()
        
        candidates = engine.evaluate(detection)
        
        # Verify PERSON_DETECTED is triggered
        assert len(candidates) == 1
        assert candidates[0].event_type == EventType.PERSON_DETECTED
        assert candidates[0].object_id == "1789898622.985494-7n794l"

    def test_existing_zone_detection_still_works(self, raw_mqtt_payload: dict) -> None:
        detection = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        # Bbox: [390, 289, 949, 717]
        # Bottom center = x: (390+949)/2 = 669.5, y: 717
        
        # Create a zone that encompasses this point (669, 717)
        zone = Zone(
            id="test-zone",
            name="Test Zone",
            camera_id="laptop_camera",
            polygon=[
                Point(x=600, y=700),
                Point(x=700, y=700),
                Point(x=700, y=800),
                Point(x=600, y=800),
            ]
        )
        
        config = SecurityConfig(zones=[zone], person_detected_cooldown_seconds=0.0)
        engine = SecurityEngine(config=config)
        
        candidates = engine.evaluate(detection)
        
        types = {c.event_type for c in candidates}
        assert EventType.ZONE_ENTRY in types
        assert EventType.PERSON_DETECTED in types

    def test_existing_loitering_tests_still_pass(self, raw_mqtt_payload: dict) -> None:
        detection_start = FrigateDetectionAdapter.parse(raw_mqtt_payload)
        
        zone = Zone(
            id="test-zone",
            name="Test Zone",
            camera_id="laptop_camera",
            polygon=[
                Point(x=600, y=700),
                Point(x=700, y=700),
                Point(x=700, y=800),
                Point(x=600, y=800),
            ]
        )
        
        config = SecurityConfig(
            zones=[zone], 
            loitering_threshold_seconds=10.0,
            person_detected_cooldown_seconds=0.0,
            zone_entry_cooldown_seconds=0.0,
            loitering_cooldown_seconds=0.0
        )
        engine = SecurityEngine(config=config)
        
        # First frame - Zone entry
        engine.evaluate(detection_start, current_time=detection_start.timestamp)
        
        # 11 seconds later - Loitering
        later_timestamp = detection_start.timestamp.timestamp() + 11.0
        payload_later = dict(raw_mqtt_payload)
        payload_later["after"] = dict(raw_mqtt_payload["after"])
        payload_later["after"]["frame_time"] = later_timestamp
        
        detection_later = FrigateDetectionAdapter.parse(payload_later)
        
        candidates = engine.evaluate(detection_later, current_time=detection_later.timestamp)
        
        types = {c.event_type for c in candidates}
        assert EventType.LOITERING in types
