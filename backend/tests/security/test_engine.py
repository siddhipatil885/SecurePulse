"""Tests for SecurityEngine — end-to-end integration and error isolation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import (
    EventType,
    Severity,
    SecurityContext,
    SecurityRuleResult,
)
from app.security.rules.base import SecurityRule

from tests.security.conftest import (
    bbox_inside_zone,
    bbox_outside_zone,
    make_detection,
    make_car_detection,
    make_zone,
)


T0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Basic engine tests
# ---------------------------------------------------------------------------


class TestSecurityEngineBasic:

    def test_person_detection_produces_candidate(self) -> None:
        engine = SecurityEngine()
        detection = make_detection()

        candidates = engine.evaluate(detection, current_time=T0)

        assert len(candidates) == 1
        c = candidates[0]
        assert c.event_type == EventType.PERSON_DETECTED
        assert c.camera_id == "cam1"
        assert c.object_id == "person-1"
        assert c.confidence == 0.92

    def test_non_person_produces_no_candidates(self) -> None:
        engine = SecurityEngine()
        detection = make_car_detection()

        candidates = engine.evaluate(detection, current_time=T0)

        assert candidates == []

    def test_low_confidence_is_dropped(self) -> None:
        engine = SecurityEngine(config=SecurityConfig(confidence_threshold=0.9))
        detection = make_detection(confidence=0.5)

        candidates = engine.evaluate(detection, current_time=T0)

        assert candidates == []

    def test_exactly_at_threshold_is_accepted(self) -> None:
        engine = SecurityEngine(config=SecurityConfig(confidence_threshold=0.5))
        detection = make_detection(confidence=0.5)

        candidates = engine.evaluate(detection, current_time=T0)

        assert len(candidates) >= 1


# ---------------------------------------------------------------------------
# Zone integration
# ---------------------------------------------------------------------------


class TestSecurityEngineZone:

    def test_zone_entry_produces_candidate(self) -> None:
        zone = make_zone()
        config = SecurityConfig(zones=[zone])
        engine = SecurityEngine(config=config)

        detection = make_detection(bbox=bbox_inside_zone())

        candidates = engine.evaluate(detection, current_time=T0)

        types = {c.event_type for c in candidates}
        assert EventType.ZONE_ENTRY in types

    def test_zone_entry_not_repeated(self) -> None:
        zone = make_zone()
        config = SecurityConfig(zones=[zone], zone_entry_cooldown_seconds=0.0)
        engine = SecurityEngine(config=config)

        d1 = make_detection(bbox=bbox_inside_zone())
        d2 = make_detection(bbox=bbox_inside_zone())

        engine.evaluate(d1, current_time=T0)
        candidates = engine.evaluate(d2, current_time=T0 + timedelta(seconds=1))

        # The zone rule itself doesn't re-trigger (inside→inside),
        # so no new ZONE_ENTRY candidate.
        zone_entries = [c for c in candidates if c.event_type == EventType.ZONE_ENTRY]
        assert len(zone_entries) == 0

    def test_person_outside_zone_no_zone_entry(self) -> None:
        zone = make_zone()
        config = SecurityConfig(zones=[zone])
        engine = SecurityEngine(config=config)

        detection = make_detection(bbox=bbox_outside_zone())

        candidates = engine.evaluate(detection, current_time=T0)

        zone_entries = [c for c in candidates if c.event_type == EventType.ZONE_ENTRY]
        assert len(zone_entries) == 0


# ---------------------------------------------------------------------------
# Loitering integration
# ---------------------------------------------------------------------------


class TestSecurityEngineLoitering:

    def test_loitering_triggers_after_threshold(self) -> None:
        zone = make_zone()
        config = SecurityConfig(
            zones=[zone],
            loitering_threshold_seconds=10.0,
            # Disable cooldowns for test clarity
            person_detected_cooldown_seconds=0.0,
            zone_entry_cooldown_seconds=0.0,
            loitering_cooldown_seconds=0.0,
        )
        engine = SecurityEngine(config=config)

        # Enter zone
        d0 = make_detection(bbox=bbox_inside_zone(), timestamp=T0)
        engine.evaluate(d0, current_time=T0)

        # After threshold
        d11 = make_detection(bbox=bbox_inside_zone(), timestamp=T0 + timedelta(seconds=11))
        candidates = engine.evaluate(d11, current_time=T0 + timedelta(seconds=11))

        types = {c.event_type for c in candidates}
        assert EventType.LOITERING in types


# ---------------------------------------------------------------------------
# Multiple persons integration
# ---------------------------------------------------------------------------


class TestSecurityEngineMultiplePerson:

    def test_multiple_person_triggers(self) -> None:
        config = SecurityConfig(
            multiple_person_threshold=2,
            person_detected_cooldown_seconds=0.0,
            multiple_person_cooldown_seconds=0.0,
        )
        engine = SecurityEngine(config=config)

        d1 = make_detection(object_id="person-1", source_event_id="e1")
        d2 = make_detection(object_id="person-2", source_event_id="e2")

        candidates = engine.evaluate(
            d1, active_detections=[d1, d2], current_time=T0
        )

        types = {c.event_type for c in candidates}
        assert EventType.MULTIPLE_PERSONS in types


# ---------------------------------------------------------------------------
# Cooldown integration
# ---------------------------------------------------------------------------


class TestSecurityEngineCooldown:

    def test_person_detected_cooldown_suppresses_second(self) -> None:
        config = SecurityConfig(person_detected_cooldown_seconds=10.0)
        engine = SecurityEngine(config=config)

        d1 = make_detection(source_event_id="e1")
        d2 = make_detection(source_event_id="e2")

        c1 = engine.evaluate(d1, current_time=T0)
        c2 = engine.evaluate(d2, current_time=T0 + timedelta(seconds=3))

        assert len(c1) == 1
        assert len(c2) == 0  # suppressed by cooldown

    def test_cooldown_expires_allows_again(self) -> None:
        config = SecurityConfig(person_detected_cooldown_seconds=5.0)
        engine = SecurityEngine(config=config)

        d1 = make_detection(source_event_id="e1")
        d2 = make_detection(source_event_id="e2")

        engine.evaluate(d1, current_time=T0)
        c2 = engine.evaluate(d2, current_time=T0 + timedelta(seconds=6))

        assert len(c2) == 1


# ---------------------------------------------------------------------------
# Severity override
# ---------------------------------------------------------------------------


class TestSecurityEngineSeverity:

    def test_severity_override_applied(self) -> None:
        config = SecurityConfig(
            severity_map={"PERSON_DETECTED": "CRITICAL"},
            person_detected_cooldown_seconds=0.0,
        )
        engine = SecurityEngine(config=config)

        detection = make_detection()
        candidates = engine.evaluate(detection, current_time=T0)

        assert candidates[0].severity == Severity.CRITICAL


# ---------------------------------------------------------------------------
# Error isolation
# ---------------------------------------------------------------------------


class _BrokenRule(SecurityRule):
    """A rule that always raises."""

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        raise RuntimeError("deliberate test failure")


class _WorkingRule(SecurityRule):
    """A rule that always triggers."""

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        return SecurityRuleResult(
            triggered=True,
            event_type=EventType.PERSON_DETECTED,
            severity=Severity.INFO,
            reason="Works fine",
            camera_id=context.detection.camera_id,
            object_id=context.detection.object_id,
        )


class TestSecurityEngineErrorIsolation:

    def test_broken_rule_does_not_crash_engine(self) -> None:
        config = SecurityConfig(person_detected_cooldown_seconds=0.0)
        engine = SecurityEngine(
            config=config,
            rules=[_BrokenRule(), _WorkingRule()],
        )

        detection = make_detection()
        candidates = engine.evaluate(detection, current_time=T0)

        # The working rule should still have produced a candidate
        assert len(candidates) == 1
        assert candidates[0].reason == "Works fine"

    def test_all_broken_rules_return_empty(self) -> None:
        engine = SecurityEngine(rules=[_BrokenRule()])

        detection = make_detection()
        candidates = engine.evaluate(detection, current_time=T0)

        assert candidates == []


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestSecurityEngineReset:

    def test_reset_clears_cooldown(self) -> None:
        config = SecurityConfig(person_detected_cooldown_seconds=60.0)
        engine = SecurityEngine(config=config)

        d1 = make_detection(source_event_id="e1")
        d2 = make_detection(source_event_id="e2")

        engine.evaluate(d1, current_time=T0)
        engine.reset()
        c2 = engine.evaluate(d2, current_time=T0 + timedelta(seconds=1))

        assert len(c2) == 1  # cooldown was cleared


# ---------------------------------------------------------------------------
# End-to-end mock pipeline
# ---------------------------------------------------------------------------


class TestEndToEndPipeline:
    """Mock DetectionEvent → SecurityEngine → SecurityEventCandidate."""

    def test_full_pipeline_without_frigate(self) -> None:
        """Verifies the complete pipeline using only mock data."""
        zone = make_zone()
        config = SecurityConfig(
            zones=[zone],
            loitering_threshold_seconds=10.0,
            multiple_person_threshold=3,
            # Disable cooldowns for clear assertions
            person_detected_cooldown_seconds=0.0,
            zone_entry_cooldown_seconds=0.0,
            loitering_cooldown_seconds=0.0,
            multiple_person_cooldown_seconds=0.0,
        )
        engine = SecurityEngine(config=config)

        # 1. Person enters the zone at T0
        d_enter = make_detection(
            bbox=bbox_inside_zone(),
            timestamp=T0,
            source_event_id="e1",
        )
        results = engine.evaluate(d_enter, current_time=T0)
        types = {r.event_type for r in results}
        assert EventType.PERSON_DETECTED in types
        assert EventType.ZONE_ENTRY in types

        # 2. Person remains inside at T0 + 11s → LOITERING
        d_stay = make_detection(
            bbox=bbox_inside_zone(),
            timestamp=T0 + timedelta(seconds=11),
            source_event_id="e2",
        )
        results = engine.evaluate(d_stay, current_time=T0 + timedelta(seconds=11))
        types = {r.event_type for r in results}
        assert EventType.LOITERING in types

        # 3. Verify each candidate has expected fields
        for candidate in results:
            assert candidate.camera_id == "cam1"
            assert candidate.source_event_id == "e2"
            assert candidate.confidence == 0.92
            assert candidate.timestamp == T0 + timedelta(seconds=11)
