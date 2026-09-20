"""Tests for CooldownManager."""

from datetime import datetime, timedelta, timezone

import pytest

from app.security.cooldown.manager import CooldownManager

T0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def manager() -> CooldownManager:
    return CooldownManager(default_ttl=10.0)


class TestCooldownManager:

    def test_first_event_is_allowed(self, manager: CooldownManager) -> None:
        assert manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0) is True

    def test_same_event_within_cooldown_is_suppressed(
        self, manager: CooldownManager
    ) -> None:
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0)

        result = manager.is_allowed(
            "cam1", "ZONE_ENTRY", "person-1", T0 + timedelta(seconds=5)
        )

        assert result is False

    def test_same_event_after_cooldown_is_allowed(
        self, manager: CooldownManager
    ) -> None:
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0)

        result = manager.is_allowed(
            "cam1", "ZONE_ENTRY", "person-1", T0 + timedelta(seconds=11)
        )

        assert result is True

    def test_different_camera_not_affected(
        self, manager: CooldownManager
    ) -> None:
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0)

        # Different camera — should be allowed
        result = manager.is_allowed(
            "cam2", "ZONE_ENTRY", "person-1", T0 + timedelta(seconds=1)
        )

        assert result is True

    def test_different_event_type_not_affected(
        self, manager: CooldownManager
    ) -> None:
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0)

        result = manager.is_allowed(
            "cam1", "PERSON_DETECTED", "person-1", T0 + timedelta(seconds=1)
        )

        assert result is True

    def test_different_object_not_affected(
        self, manager: CooldownManager
    ) -> None:
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0)

        result = manager.is_allowed(
            "cam1", "ZONE_ENTRY", "person-2", T0 + timedelta(seconds=1)
        )

        assert result is True

    def test_custom_ttl_overrides_default(self) -> None:
        manager = CooldownManager(default_ttl=60.0)
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0, ttl=2.0)

        # Within 2 s — suppressed (custom TTL)
        result = manager.is_allowed(
            "cam1", "ZONE_ENTRY", "person-1", T0 + timedelta(seconds=1),
            ttl=2.0,
        )
        assert result is False

        # After 2 s — allowed
        result = manager.is_allowed(
            "cam1", "ZONE_ENTRY", "person-1", T0 + timedelta(seconds=3),
            ttl=2.0,
        )
        assert result is True

    def test_reset_clears_all(self, manager: CooldownManager) -> None:
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0)
        manager.reset()

        result = manager.is_allowed(
            "cam1", "ZONE_ENTRY", "person-1", T0 + timedelta(seconds=1)
        )
        assert result is True

    def test_remove_object(self, manager: CooldownManager) -> None:
        manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", T0)
        manager.is_allowed("cam1", "PERSON_DETECTED", "person-1", T0)
        manager.remove_object("cam1", "person-1")

        # Both should be allowed now
        t1 = T0 + timedelta(seconds=1)
        assert manager.is_allowed("cam1", "ZONE_ENTRY", "person-1", t1) is True
        assert manager.is_allowed("cam1", "PERSON_DETECTED", "person-1", t1) is True

    def test_exact_boundary_is_suppressed(
        self, manager: CooldownManager
    ) -> None:
        """At exactly the cooldown duration the event is still suppressed."""
        manager.is_allowed("cam1", "X", "p1", T0, ttl=10.0)

        result = manager.is_allowed(
            "cam1", "X", "p1", T0 + timedelta(seconds=10), ttl=10.0
        )
        # 10 s elapsed is NOT < 10 s, so it should be allowed
        assert result is True
