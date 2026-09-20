"""
Security Intelligence configuration.

All tunables are gathered here so that no rule hard-codes thresholds or
cooldown durations.  Values can be overridden at construction time or,
in a future iteration, loaded from environment variables or a config file.

NOTE — In-memory state
    The current prototype keeps all runtime state (zone membership,
    loitering timers, cooldowns) in process memory.  For horizontal
    scaling this must be replaced with a shared store (e.g. Redis).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.security.models import Severity, Tripwire, Zone


@dataclass(frozen=True)
class SecurityConfig:
    """Immutable configuration for the Security Intelligence engine.

    Attributes:
        confidence_threshold: Minimum detection confidence to evaluate.
            Detections below this value are silently dropped.
        loitering_threshold_seconds: How long a person must remain in a
            restricted zone before a LOITERING event is raised.
        multiple_person_threshold: Number of simultaneous persons on a
            single camera required to trigger MULTIPLE_PERSONS.
        person_detected_cooldown_seconds: Cooldown for PERSON_DETECTED.
        zone_entry_cooldown_seconds: Cooldown for ZONE_ENTRY.
        loitering_cooldown_seconds: Cooldown for LOITERING.
        multiple_person_cooldown_seconds: Cooldown for MULTIPLE_PERSONS.
        line_crossing_cooldown_seconds: Cooldown for LINE_CROSSING.
        severity_map: Override default severity for any event type.
        zones: Restricted zones to evaluate against.
        tripwires: Virtual tripwires to evaluate against.
    """

    # --- Detection filtering ---
    confidence_threshold: float = 0.5

    # --- Rule thresholds ---
    loitering_threshold_seconds: float = 15.0
    multiple_person_threshold: int = 3

    # --- Cooldown durations (seconds) ---
    person_detected_cooldown_seconds: float = 5.0
    zone_entry_cooldown_seconds: float = 30.0
    loitering_cooldown_seconds: float = 60.0
    multiple_person_cooldown_seconds: float = 30.0
    line_crossing_cooldown_seconds: float = 30.0

    # --- Severity overrides  (EventType.value → Severity.value) ---
    severity_map: dict[str, str] = field(default_factory=dict)

    # --- Zones & Tripwires ---
    zones: list[Zone] = field(default_factory=list)
    tripwires: list[Tripwire] = field(default_factory=list)

    # --- Helpers ---

    def cooldown_for(self, event_type: str) -> float:
        """Return the cooldown duration for *event_type*."""
        mapping: dict[str, float] = {
            "PERSON_DETECTED": self.person_detected_cooldown_seconds,
            "ZONE_ENTRY": self.zone_entry_cooldown_seconds,
            "LOITERING": self.loitering_cooldown_seconds,
            "MULTIPLE_PERSONS": self.multiple_person_cooldown_seconds,
            "LINE_CROSSING": self.line_crossing_cooldown_seconds,
        }
        return mapping.get(event_type, 0.0)

    def zones_for_camera(self, camera_id: str) -> list[Zone]:
        """Return enabled zones configured for *camera_id*."""
        return [z for z in self.zones if z.camera_id == camera_id and z.enabled]

    def tripwires_for_camera(self, camera_id: str) -> list[Tripwire]:
        """Return enabled tripwires configured for *camera_id*."""
        return [t for t in self.tripwires if t.camera_id == camera_id and t.enabled]
