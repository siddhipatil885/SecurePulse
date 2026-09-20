"""Tests for PersonDetectedRule."""

import pytest

from app.security.models import EventType, SecurityContext
from app.security.rules.person import PersonDetectedRule

from tests.security.conftest import (
    make_detection,
    make_car_detection,
    make_dog_detection,
)


@pytest.fixture
def rule() -> PersonDetectedRule:
    return PersonDetectedRule()


class TestPersonDetectedRule:
    """PersonDetectedRule test suite."""

    def test_person_triggers(self, rule: PersonDetectedRule) -> None:
        detection = make_detection(object_type="person")
        ctx = SecurityContext(detection=detection)

        result = rule.evaluate(ctx)

        assert result is not None
        assert result.triggered is True
        assert result.event_type == EventType.PERSON_DETECTED
        assert result.camera_id == detection.camera_id
        assert result.object_id == detection.object_id

    def test_car_does_not_trigger(self, rule: PersonDetectedRule) -> None:
        detection = make_car_detection()
        ctx = SecurityContext(detection=detection)

        result = rule.evaluate(ctx)

        assert result is None

    def test_dog_does_not_trigger(self, rule: PersonDetectedRule) -> None:
        detection = make_dog_detection()
        ctx = SecurityContext(detection=detection)

        result = rule.evaluate(ctx)

        assert result is None

    @pytest.mark.parametrize(
        "object_type",
        ["vehicle", "bicycle", "motorcycle", "bird", "cat"],
    )
    def test_non_person_objects_do_not_trigger(
        self, rule: PersonDetectedRule, object_type: str
    ) -> None:
        detection = make_detection(object_type=object_type, object_id=f"{object_type}-1")
        ctx = SecurityContext(detection=detection)

        result = rule.evaluate(ctx)

        assert result is None

    def test_result_contains_correct_reason(
        self, rule: PersonDetectedRule
    ) -> None:
        detection = make_detection()
        ctx = SecurityContext(detection=detection)

        result = rule.evaluate(ctx)

        assert result is not None
        assert "Person detected" in result.reason
