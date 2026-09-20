"""Tests for ZoneEntryRule."""

import pytest

from app.security.models import EventType, SecurityContext, Zone
from app.security.rules.zone import ZoneEntryRule

from tests.security.conftest import (
    bbox_inside_zone,
    bbox_outside_zone,
    make_detection,
    make_zone,
)


@pytest.fixture
def rule() -> ZoneEntryRule:
    return ZoneEntryRule()


@pytest.fixture
def zone() -> Zone:
    return make_zone()


class TestZoneEntryRule:

    def test_outside_to_outside_does_not_trigger(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        d1 = make_detection(bbox=bbox_outside_zone())
        d2 = make_detection(bbox=bbox_outside_zone())

        r1 = rule.evaluate(SecurityContext(detection=d1, zones=[zone]))
        r2 = rule.evaluate(SecurityContext(detection=d2, zones=[zone]))

        assert r1 is None
        assert r2 is None

    def test_outside_to_inside_triggers(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        d_out = make_detection(bbox=bbox_outside_zone())
        d_in = make_detection(bbox=bbox_inside_zone())

        rule.evaluate(SecurityContext(detection=d_out, zones=[zone]))
        result = rule.evaluate(SecurityContext(detection=d_in, zones=[zone]))

        assert result is not None
        assert result.triggered is True
        assert result.event_type == EventType.ZONE_ENTRY
        assert result.zone_id == zone.id

    def test_inside_to_inside_does_not_repeat(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        d_out = make_detection(bbox=bbox_outside_zone())
        d_in1 = make_detection(bbox=bbox_inside_zone())
        d_in2 = make_detection(bbox=bbox_inside_zone())

        rule.evaluate(SecurityContext(detection=d_out, zones=[zone]))
        rule.evaluate(SecurityContext(detection=d_in1, zones=[zone]))
        result = rule.evaluate(SecurityContext(detection=d_in2, zones=[zone]))

        assert result is None

    def test_inside_to_outside_clears_state(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        d_out1 = make_detection(bbox=bbox_outside_zone())
        d_in = make_detection(bbox=bbox_inside_zone())
        d_out2 = make_detection(bbox=bbox_outside_zone())

        rule.evaluate(SecurityContext(detection=d_out1, zones=[zone]))
        rule.evaluate(SecurityContext(detection=d_in, zones=[zone]))
        rule.evaluate(SecurityContext(detection=d_out2, zones=[zone]))

        assert rule.is_inside("cam1", "person-1", zone.id) is False

    def test_re_entry_triggers_again(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        d_out = make_detection(bbox=bbox_outside_zone())
        d_in = make_detection(bbox=bbox_inside_zone())

        rule.evaluate(SecurityContext(detection=d_out, zones=[zone]))
        r1 = rule.evaluate(SecurityContext(detection=d_in, zones=[zone]))

        # Leave
        rule.evaluate(SecurityContext(detection=d_out, zones=[zone]))
        # Re-enter
        r2 = rule.evaluate(SecurityContext(detection=d_in, zones=[zone]))

        assert r1 is not None and r1.triggered
        assert r2 is not None and r2.triggered

    def test_first_detection_inside_triggers(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        """If the very first frame has the person inside, that's an entry."""
        d_in = make_detection(bbox=bbox_inside_zone())

        result = rule.evaluate(SecurityContext(detection=d_in, zones=[zone]))

        assert result is not None
        assert result.triggered is True

    def test_no_bbox_returns_none(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        detection = make_detection(bbox=None)

        result = rule.evaluate(SecurityContext(detection=detection, zones=[zone]))

        assert result is None

    def test_non_person_returns_none(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        detection = make_detection(object_type="car", object_id="car-1",
                                   bbox=bbox_inside_zone())

        result = rule.evaluate(SecurityContext(detection=detection, zones=[zone]))

        assert result is None

    def test_result_contains_zone_name(
        self, rule: ZoneEntryRule, zone: Zone
    ) -> None:
        d_in = make_detection(bbox=bbox_inside_zone())
        result = rule.evaluate(SecurityContext(detection=d_in, zones=[zone]))

        assert result is not None
        assert zone.name in result.reason
