"""Tests for virtual tripwire line-crossing detection."""

from datetime import datetime, timezone

from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import (
    BoundingBox,
    EventType,
    Point,
    SecurityContext,
    Tripwire,
)
from app.security.rules.line_crossing import LineCrossingRule

from tests.security.conftest import make_car_detection, make_detection


T0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)


def make_tripwire() -> Tripwire:
    return Tripwire(
        id="front-door",
        name="Front Door",
        camera_id="cam1",
        start_point=Point(x=600, y=200),
        end_point=Point(x=600, y=800),
    )


def make_bbox(center_x: float) -> BoundingBox:
    return BoundingBox(x1=center_x - 50, y1=300, x2=center_x + 50, y2=500)


class TestLineCrossingRule:

    def test_crossing_tripwire_triggers(self) -> None:
        rule = LineCrossingRule(SecurityConfig())
        tripwire = make_tripwire()
        first = make_detection(bbox=make_bbox(500))
        second = make_detection(bbox=make_bbox(700))

        first_context = SecurityContext(detection=first, tripwires=[tripwire])
        second_context = SecurityContext(detection=second, tripwires=[tripwire])

        assert rule.evaluate(first_context) is None
        result = rule.evaluate(second_context)

        assert result is not None
        assert result.event_type == EventType.LINE_CROSSING
        assert result.tripwire_id == "front-door"

    def test_non_person_does_not_trigger_or_update_track(self) -> None:
        rule = LineCrossingRule(SecurityConfig())
        tripwire = make_tripwire()
        car = make_car_detection(bbox=make_bbox(500))
        person = make_detection(bbox=make_bbox(700))

        assert rule.evaluate(
            SecurityContext(detection=car, tripwires=[tripwire])
        ) is None
        assert rule.evaluate(
            SecurityContext(detection=person, tripwires=[tripwire])
        ) is None


class TestLineCrossingEngine:

    def test_engine_propagates_tripwire_candidate(self) -> None:
        config = SecurityConfig(
            tripwires=[make_tripwire()],
            person_detected_cooldown_seconds=0.0,
            line_crossing_cooldown_seconds=0.0,
        )
        engine = SecurityEngine(config=config)

        engine.evaluate(make_detection(bbox=make_bbox(500)), current_time=T0)
        candidates = engine.evaluate(
            make_detection(bbox=make_bbox(700)),
            current_time=T0,
        )

        crossing = [
            candidate
            for candidate in candidates
            if candidate.event_type == EventType.LINE_CROSSING
        ]
        assert len(crossing) == 1
        assert crossing[0].tripwire_id == "front-door"
