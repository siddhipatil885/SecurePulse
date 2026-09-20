"""Tests for SeverityResolver."""

import pytest

from app.security.models import EventType, Severity
from app.security.severity.resolver import SeverityResolver


@pytest.fixture
def resolver() -> SeverityResolver:
    return SeverityResolver()


class TestSeverityResolver:

    def test_person_detected_default(self, resolver: SeverityResolver) -> None:
        assert resolver.get_severity("PERSON_DETECTED") == Severity.INFO

    def test_zone_entry_default(self, resolver: SeverityResolver) -> None:
        assert resolver.get_severity("ZONE_ENTRY") == Severity.MEDIUM

    def test_loitering_default(self, resolver: SeverityResolver) -> None:
        assert resolver.get_severity("LOITERING") == Severity.HIGH

    def test_multiple_persons_default(self, resolver: SeverityResolver) -> None:
        assert resolver.get_severity("MULTIPLE_PERSONS") == Severity.MEDIUM

    def test_unknown_event_type_returns_info(
        self, resolver: SeverityResolver
    ) -> None:
        assert resolver.get_severity("UNKNOWN_TYPE") == Severity.INFO

    def test_accepts_enum(self, resolver: SeverityResolver) -> None:
        assert resolver.get_severity(EventType.LOITERING) == Severity.HIGH

    def test_override_changes_severity(self) -> None:
        resolver = SeverityResolver(
            overrides={"PERSON_DETECTED": "CRITICAL"}
        )
        assert resolver.get_severity("PERSON_DETECTED") == Severity.CRITICAL

    def test_override_does_not_affect_others(self) -> None:
        resolver = SeverityResolver(
            overrides={"PERSON_DETECTED": "HIGH"}
        )
        # Other defaults remain intact
        assert resolver.get_severity("ZONE_ENTRY") == Severity.MEDIUM
        assert resolver.get_severity("LOITERING") == Severity.HIGH

    def test_all_defaults_are_valid_severity_enums(
        self, resolver: SeverityResolver
    ) -> None:
        for event_type in EventType:
            result = resolver.get_severity(event_type)
            assert isinstance(result, Severity)
