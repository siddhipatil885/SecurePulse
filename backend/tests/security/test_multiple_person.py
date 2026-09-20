"""Tests for MultiplePersonRule."""

import pytest

from app.security.config import SecurityConfig
from app.security.models import EventType, SecurityContext
from app.security.rules.multiple_person import MultiplePersonRule

from tests.security.conftest import make_detection


@pytest.fixture
def config() -> SecurityConfig:
    return SecurityConfig(multiple_person_threshold=3)


@pytest.fixture
def rule(config: SecurityConfig) -> MultiplePersonRule:
    return MultiplePersonRule(config)


def _persons(count: int):
    """Create *count* person detections on cam1."""
    return [
        make_detection(object_id=f"person-{i}", source_event_id=f"evt-{i}")
        for i in range(1, count + 1)
    ]


class TestMultiplePersonRule:

    def test_one_person_does_not_trigger(self, rule: MultiplePersonRule) -> None:
        detections = _persons(1)
        ctx = SecurityContext(detection=detections[0], active_detections=detections)
        assert rule.evaluate(ctx) is None

    def test_two_persons_does_not_trigger(self, rule: MultiplePersonRule) -> None:
        detections = _persons(2)
        ctx = SecurityContext(detection=detections[0], active_detections=detections)
        assert rule.evaluate(ctx) is None

    def test_three_persons_triggers(self, rule: MultiplePersonRule) -> None:
        detections = _persons(3)
        ctx = SecurityContext(detection=detections[0], active_detections=detections)

        result = rule.evaluate(ctx)

        assert result is not None
        assert result.triggered is True
        assert result.event_type == EventType.MULTIPLE_PERSONS
        assert "3" in result.reason

    def test_four_persons_triggers(self, rule: MultiplePersonRule) -> None:
        detections = _persons(4)
        ctx = SecurityContext(detection=detections[0], active_detections=detections)

        result = rule.evaluate(ctx)

        assert result is not None
        assert result.triggered is True

    def test_non_person_ignored(self, rule: MultiplePersonRule) -> None:
        detection = make_detection(object_type="car", object_id="car-1")
        ctx = SecurityContext(detection=detection, active_detections=[detection])
        assert rule.evaluate(ctx) is None

    def test_mixed_objects_only_counts_persons(
        self, rule: MultiplePersonRule
    ) -> None:
        persons = _persons(2)
        car = make_detection(object_type="car", object_id="car-1", source_event_id="c1")
        all_detections = persons + [car]

        ctx = SecurityContext(
            detection=persons[0], active_detections=all_detections
        )
        assert rule.evaluate(ctx) is None  # only 2 persons

    def test_custom_threshold(self) -> None:
        config = SecurityConfig(multiple_person_threshold=2)
        rule = MultiplePersonRule(config)
        detections = _persons(2)
        ctx = SecurityContext(detection=detections[0], active_detections=detections)

        result = rule.evaluate(ctx)

        assert result is not None
        assert result.triggered is True

    def test_metadata_contains_person_count(self, rule: MultiplePersonRule) -> None:
        detections = _persons(3)
        ctx = SecurityContext(detection=detections[0], active_detections=detections)

        result = rule.evaluate(ctx)

        assert result is not None
        assert result.metadata["person_count"] == 3
