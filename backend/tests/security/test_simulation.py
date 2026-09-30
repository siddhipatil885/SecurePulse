"""
End-to-end simulation tests for the Security Intelligence engine.

These tests simulate realistic scenarios (e.g., a person walking into a frame,
entering a zone, loitering, and another person joining) over a continuous
timeline, verifying that the correct events are emitted and cooldowns are
respected.
"""

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import (
    BoundingBox,
    DetectionEvent,
    EventType,
    SecurityEventCandidate,
    Zone,
)
from tests.security.conftest import (
    bbox_inside_zone,
    bbox_outside_zone,
    make_detection,
    make_zone,
)

T0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


class TestRealisticScenarios:

    def test_complex_timeline_scenario(self) -> None:
        """
        Simulates a 60-second scenario:
        - T=0: Person 1 appears outside zone -> PERSON_DETECTED.
        - T=5: Person 1 enters zone -> ZONE_ENTRY. (Cooldowns start)
        - T=10: Person 1 stays in zone. Cooldown prevents duplicate ZONE_ENTRY.
        - T=20: Person 1 reaches loitering threshold (15s after entry) -> LOITERING.
        - T=25: Person 2 appears outside zone -> PERSON_DETECTED (for person 2).
        - T=30: Person 2 enters zone -> ZONE_ENTRY (for person 2).
        - T=30: MULTIPLE_PERSONS triggers (if threshold is 2).
        - T=35: Person 1 leaves frame.
        - T=45: Person 2 reaches loitering threshold -> LOITERING (for person 2).
        """
        zone = make_zone()
        config = SecurityConfig(
            zones=[zone],
            loitering_threshold_seconds=15.0,
            multiple_person_threshold=2,
            # Set small cooldowns so we can test expiry if needed, or keep defaults
            person_detected_cooldown_seconds=60.0,
            zone_entry_cooldown_seconds=60.0,
            loitering_cooldown_seconds=60.0,
            multiple_person_cooldown_seconds=60.0,
        )
        engine = SecurityEngine(config=config)

        emitted_events: List[SecurityEventCandidate] = []
        active_detections = {}

        def process_frame(timestamp: datetime, current_detections: List[DetectionEvent]):
            # Evaluate all current detections
            for det in current_detections:
                candidates = engine.evaluate(
                    detection=det,
                    active_detections=current_detections,
                    current_time=timestamp,
                )
                emitted_events.extend(candidates)

        # T=0: Person 1 appears outside zone
        d_p1_t0 = make_detection(
            object_id="p1", bbox=bbox_outside_zone(), timestamp=_at(0)
        )
        process_frame(_at(0), [d_p1_t0])
        
        # Verify T=0
        assert len(emitted_events) == 1
        assert emitted_events[-1].event_type == EventType.PERSON_DETECTED
        assert emitted_events[-1].object_id == "p1"
        emitted_events.clear()

        # T=5: Person 1 enters zone
        d_p1_t5 = make_detection(
            object_id="p1", bbox=bbox_inside_zone(), timestamp=_at(5)
        )
        process_frame(_at(5), [d_p1_t5])

        # Verify T=5
        assert len(emitted_events) == 1
        assert emitted_events[-1].event_type == EventType.ZONE_ENTRY
        assert emitted_events[-1].object_id == "p1"
        assert emitted_events[-1].zone_id == zone.id
        emitted_events.clear()

        # T=10: Person 1 stays in zone. Cooldown prevents duplicate ZONE_ENTRY and PERSON_DETECTED.
        d_p1_t10 = make_detection(
            object_id="p1", bbox=bbox_inside_zone(), timestamp=_at(10)
        )
        process_frame(_at(10), [d_p1_t10])
        assert len(emitted_events) == 0

        # T=20: Person 1 reaches loitering threshold (entered at T=5, so 15s elapsed)
        d_p1_t20 = make_detection(
            object_id="p1", bbox=bbox_inside_zone(), timestamp=_at(20)
        )
        process_frame(_at(20), [d_p1_t20])
        
        # Verify T=20
        assert len(emitted_events) == 1
        assert emitted_events[-1].event_type == EventType.LOITERING
        assert emitted_events[-1].object_id == "p1"
        assert emitted_events[-1].metadata["duration_seconds"] == 15
        emitted_events.clear()

        # T=25: Person 2 appears outside zone. Person 1 is still inside.
        d_p1_t25 = make_detection(
            object_id="p1", bbox=bbox_inside_zone(), timestamp=_at(25)
        )
        d_p2_t25 = make_detection(
            object_id="p2", bbox=bbox_outside_zone(), timestamp=_at(25)
        )
        process_frame(_at(25), [d_p1_t25, d_p2_t25])

        # Verify T=25
        # p1 emits MULTIPLE_PERSONS. p2 emits PERSON_DETECTED and MULTIPLE_PERSONS.
        assert len(emitted_events) == 3
        types = {c.event_type for c in emitted_events}
        assert types == {EventType.PERSON_DETECTED, EventType.MULTIPLE_PERSONS}
        # Check we got MULTIPLE_PERSONS for both objects
        mp_objects = {c.object_id for c in emitted_events if c.event_type == EventType.MULTIPLE_PERSONS}
        assert mp_objects == {"p1", "p2"}
        emitted_events.clear()

        # T=30: Person 2 enters zone. Person 1 is still inside.
        d_p1_t30 = make_detection(
            object_id="p1", bbox=bbox_inside_zone(), timestamp=_at(30)
        )
        d_p2_t30 = make_detection(
            object_id="p2", bbox=bbox_inside_zone(), timestamp=_at(30)
        )
        process_frame(_at(30), [d_p1_t30, d_p2_t30])

        # Verify T=30
        # MULTIPLE_PERSONS is in cooldown (60s). p2 emits ZONE_ENTRY.
        assert len(emitted_events) == 1
        assert emitted_events[-1].event_type == EventType.ZONE_ENTRY
        assert emitted_events[-1].object_id == "p2"
        emitted_events.clear()

        # T=35: Person 1 leaves frame (not passed to process_frame). Person 2 stays.
        d_p2_t35 = make_detection(
            object_id="p2", bbox=bbox_inside_zone(), timestamp=_at(35)
        )
        process_frame(_at(35), [d_p2_t35])
        assert len(emitted_events) == 0

        # T=45: Person 2 reaches loitering threshold (entered at T=30, so 15s elapsed)
        d_p2_t45 = make_detection(
            object_id="p2", bbox=bbox_inside_zone(), timestamp=_at(45)
        )
        process_frame(_at(45), [d_p2_t45])

        # Verify T=45
        assert len(emitted_events) == 1
        assert emitted_events[-1].event_type == EventType.LOITERING
        assert emitted_events[-1].object_id == "p2"
        assert emitted_events[-1].metadata["duration_seconds"] == 15
        emitted_events.clear()

    def test_person_leaving_and_reentering_zone(self) -> None:
        """
        Tests state reset when a person leaves the zone and re-enters.
        """
        zone = make_zone()
        config = SecurityConfig(
            zones=[zone],
            loitering_threshold_seconds=10.0,
            zone_entry_cooldown_seconds=10.0, # short cooldown so we can trigger again
            person_detected_cooldown_seconds=60.0,
        )
        engine = SecurityEngine(config=config)

        # T=0: Enters zone
        d_in_0 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(0))
        results = engine.evaluate(d_in_0, current_time=_at(0))
        assert any(r.event_type == EventType.ZONE_ENTRY for r in results)

        # T=5: Leaves zone
        d_out_5 = make_detection(bbox=bbox_outside_zone(), timestamp=_at(5))
        results = engine.evaluate(d_out_5, current_time=_at(5))
        assert not any(r.event_type == EventType.ZONE_ENTRY for r in results)
        assert not any(r.event_type == EventType.LOITERING for r in results)

        # T=12: Re-enters zone (cooldown expired)
        d_in_12 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(12))
        results = engine.evaluate(d_in_12, current_time=_at(12))
        assert any(r.event_type == EventType.ZONE_ENTRY for r in results)

        # T=22: Loitering triggers (10s after re-entry)
        d_in_22 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(22))
        results = engine.evaluate(d_in_22, current_time=_at(22))
        assert any(r.event_type == EventType.LOITERING for r in results)
