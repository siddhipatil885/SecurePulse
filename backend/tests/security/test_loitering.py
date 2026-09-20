"""Tests for LoiteringRule."""

from datetime import datetime, timedelta, timezone

import pytest

from app.security.config import SecurityConfig
from app.security.models import EventType, SecurityContext, Zone
from app.security.rules.loitering import LoiteringRule

from tests.security.conftest import (
    bbox_inside_zone,
    bbox_outside_zone,
    make_detection,
    make_zone,
)


T0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


@pytest.fixture
def config() -> SecurityConfig:
    return SecurityConfig(loitering_threshold_seconds=15.0)


@pytest.fixture
def rule(config: SecurityConfig) -> LoiteringRule:
    return LoiteringRule(config)


@pytest.fixture
def zone() -> Zone:
    return make_zone()


class TestLoiteringRule:

    def test_no_loitering_before_threshold(
        self, rule: LoiteringRule, zone: Zone
    ) -> None:
        """5 s, 10 s, 14 s — no LOITERING yet."""
        for secs in (0, 5, 10, 14):
            detection = make_detection(bbox=bbox_inside_zone(), timestamp=_at(secs))
            ctx = SecurityContext(
                detection=detection, zones=[zone], current_time=_at(secs)
            )
            result = rule.evaluate(ctx)
            assert result is None, f"Should not trigger at {secs}s"

    def test_loitering_at_threshold(
        self, rule: LoiteringRule, zone: Zone
    ) -> None:
        """Exactly at 15 s the rule should trigger."""
        # Seed the entry
        d0 = make_detection(bbox=bbox_inside_zone(), timestamp=T0)
        rule.evaluate(SecurityContext(detection=d0, zones=[zone], current_time=T0))

        # At threshold
        d15 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(15))
        result = rule.evaluate(
            SecurityContext(detection=d15, zones=[zone], current_time=_at(15))
        )

        assert result is not None
        assert result.triggered is True
        assert result.event_type == EventType.LOITERING
        assert result.zone_id == zone.id
        assert "15" in result.reason

    def test_no_duplicate_after_trigger(
        self, rule: LoiteringRule, zone: Zone
    ) -> None:
        """After the first LOITERING, further frames should NOT re-trigger."""
        for secs in (0, 5, 10, 15):
            d = make_detection(bbox=bbox_inside_zone(), timestamp=_at(secs))
            rule.evaluate(SecurityContext(detection=d, zones=[zone], current_time=_at(secs)))

        # 16 s — should not fire again
        d16 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(16))
        result = rule.evaluate(
            SecurityContext(detection=d16, zones=[zone], current_time=_at(16))
        )
        assert result is None

    def test_leave_and_reenter_restarts_timer(
        self, rule: LoiteringRule, zone: Zone
    ) -> None:
        """After leaving the zone and re-entering, the timer should restart."""
        # Enter and trigger at 15 s
        for secs in (0, 15):
            d = make_detection(bbox=bbox_inside_zone(), timestamp=_at(secs))
            rule.evaluate(SecurityContext(detection=d, zones=[zone], current_time=_at(secs)))

        # Leave at 20 s
        d_out = make_detection(bbox=bbox_outside_zone(), timestamp=_at(20))
        rule.evaluate(SecurityContext(detection=d_out, zones=[zone], current_time=_at(20)))

        # State should be cleared
        state = rule.get_state("cam1", "person-1", zone.id)
        assert state is None

        # Re-enter at 25 s
        d_re = make_detection(bbox=bbox_inside_zone(), timestamp=_at(25))
        rule.evaluate(SecurityContext(detection=d_re, zones=[zone], current_time=_at(25)))

        # Should NOT trigger yet (just entered)
        d30 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(30))
        result = rule.evaluate(
            SecurityContext(detection=d30, zones=[zone], current_time=_at(30))
        )
        assert result is None  # only 5 s since re-entry

        # Should trigger at 25 + 15 = 40 s
        d40 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(40))
        result = rule.evaluate(
            SecurityContext(detection=d40, zones=[zone], current_time=_at(40))
        )
        assert result is not None
        assert result.triggered is True

    def test_non_person_ignored(
        self, rule: LoiteringRule, zone: Zone
    ) -> None:
        detection = make_detection(
            object_type="car", object_id="car-1", bbox=bbox_inside_zone()
        )
        ctx = SecurityContext(detection=detection, zones=[zone])
        assert rule.evaluate(ctx) is None

    def test_no_bbox_ignored(
        self, rule: LoiteringRule, zone: Zone
    ) -> None:
        detection = make_detection(bbox=None)
        ctx = SecurityContext(detection=detection, zones=[zone])
        assert rule.evaluate(ctx) is None

    def test_custom_threshold(self, zone: Zone) -> None:
        """A different threshold fires at the correct time."""
        config = SecurityConfig(loitering_threshold_seconds=5.0)
        rule = LoiteringRule(config)

        d0 = make_detection(bbox=bbox_inside_zone(), timestamp=T0)
        rule.evaluate(SecurityContext(detection=d0, zones=[zone], current_time=T0))

        d5 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(5))
        result = rule.evaluate(
            SecurityContext(detection=d5, zones=[zone], current_time=_at(5))
        )
        assert result is not None
        assert result.triggered is True

    def test_metadata_contains_duration(
        self, rule: LoiteringRule, zone: Zone
    ) -> None:
        d0 = make_detection(bbox=bbox_inside_zone(), timestamp=T0)
        rule.evaluate(SecurityContext(detection=d0, zones=[zone], current_time=T0))

        d20 = make_detection(bbox=bbox_inside_zone(), timestamp=_at(20))
        result = rule.evaluate(
            SecurityContext(detection=d20, zones=[zone], current_time=_at(20))
        )
        assert result is not None
        assert result.metadata["duration_seconds"] == 20
