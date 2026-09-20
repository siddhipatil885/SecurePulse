"""
Centralised severity resolver.

Keeps severity-string logic in a single place so that rules do not
scatter magic strings throughout the codebase.

Default mapping:
    PERSON_DETECTED  → INFO
    ZONE_ENTRY       → MEDIUM
    LOITERING        → HIGH
    MULTIPLE_PERSONS → MEDIUM

Overrides can be supplied via ``SecurityConfig.severity_map``.
"""

from __future__ import annotations

from app.security.models import EventType, Severity


# Default severity for each event type.
_DEFAULTS: dict[str, Severity] = {
    EventType.PERSON_DETECTED.value: Severity.INFO,
    EventType.ZONE_ENTRY.value: Severity.MEDIUM,
    EventType.LOITERING.value: Severity.HIGH,
    EventType.MULTIPLE_PERSONS.value: Severity.MEDIUM,
}


class SeverityResolver:
    """Resolve the final severity for a given event type.

    Args:
        overrides: Optional ``{event_type_value: severity_value}`` dict
            to override the built-in defaults.
    """

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        self._map: dict[str, Severity] = dict(_DEFAULTS)
        if overrides:
            for event_type, severity_str in overrides.items():
                self._map[event_type] = Severity(severity_str)

    def get_severity(self, event_type: str | EventType) -> Severity:
        """Return the severity for *event_type*.

        Falls back to ``Severity.INFO`` for unknown event types.
        """
        key = event_type.value if isinstance(event_type, EventType) else event_type
        return self._map.get(key, Severity.INFO)
