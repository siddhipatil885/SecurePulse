"""
Security Intelligence Engine
==============================

Central orchestrator that:

1. Validates incoming detections.
2. Builds a ``SecurityContext`` with zones and active detections.
3. Runs every registered rule (catching per-rule errors).
4. Applies cooldown / deduplication.
5. Resolves final severity.
6. Returns a list of ``SecurityEventCandidate`` objects.

The engine does NOT:
    - Write to the database.
    - Send notifications.
    - Know how Frigate works.

Pipeline::

    DetectionEvent
          ↓
    SecurityEngine
          ↓
    Person Rule → Zone Rule → Loitering Rule → Multiple Person Rule
          ↓
    Cooldown Manager
          ↓
    Severity Resolver
          ↓
    SecurityEventCandidate[]

NOTE — In-memory state
    Runtime state (zone membership, loitering timers, cooldowns) lives in
    process memory.  This is acceptable for the edge-device prototype.
    For horizontal scaling, replace with Redis or another shared store.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.security.config import SecurityConfig
from app.security.cooldown.manager import CooldownManager
from app.security.models import (
    DetectionEvent,
    SecurityContext,
    SecurityEventCandidate,
    SecurityRuleResult,
)
from app.security.rules.base import SecurityRule
from app.security.rules.loitering import LoiteringRule
from app.security.rules.multiple_person import MultiplePersonRule
from app.security.rules.person import PersonDetectedRule
from app.security.rules.zone import ZoneEntryRule
from app.security.severity.resolver import SeverityResolver

logger = logging.getLogger(__name__)


class SecurityEngine:
    """The central security intelligence engine.

    Args:
        config: Immutable engine configuration.
        rules: Optional explicit rule list.  When ``None`` the engine
            instantiates the default rule set (person, zone, loitering,
            multiple-person).
    """

    def __init__(
        self,
        config: SecurityConfig | None = None,
        rules: list[SecurityRule] | None = None,
    ) -> None:
        self._config = config or SecurityConfig()
        self._severity_resolver = SeverityResolver(
            overrides=self._config.severity_map
        )
        self._cooldown = CooldownManager()

        if rules is not None:
            self._rules = list(rules)
        else:
            self._rules: list[SecurityRule] = [
                PersonDetectedRule(),
                ZoneEntryRule(),
                LoiteringRule(self._config),
                MultiplePersonRule(self._config),
            ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> SecurityConfig:
        return self._config

    @property
    def rules(self) -> list[SecurityRule]:
        return list(self._rules)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        detection: DetectionEvent,
        active_detections: list[DetectionEvent] | None = None,
        current_time: datetime | None = None,
    ) -> list[SecurityEventCandidate]:
        """Evaluate *detection* against all registered rules.

        Args:
            detection: The normalised detection to analyse.
            active_detections: All currently active detections on the
                same camera (used by ``MultiplePersonRule``).  If
                ``None`` only the current detection is considered.
            current_time: Override the evaluation clock (makes tests
                deterministic).  Falls back to ``detection.timestamp``.

        Returns:
            A (possibly empty) list of ``SecurityEventCandidate`` objects
            for events that passed rule evaluation **and** cooldown.
        """
        # 1. Validate
        if not self._is_valid(detection):
            return []

        # 2. Build context
        now = current_time or detection.timestamp
        zones = self._config.zones_for_camera(detection.camera_id)
        context = SecurityContext(
            detection=detection,
            active_detections=active_detections or [detection],
            zones=zones,
            current_time=now,
        )

        # 3. Run rules (catch per-rule errors)
        triggered: list[SecurityRuleResult] = []
        for rule in self._rules:
            try:
                result = rule.evaluate(context)
                if result is not None and result.triggered:
                    triggered.append(result)
            except Exception:
                logger.exception(
                    "Rule '%s' raised an error — skipping",
                    rule.name,
                )

        # 4. Apply cooldown + severity, build candidates
        candidates: list[SecurityEventCandidate] = []
        for result in triggered:
            event_type_str = result.event_type.value
            cooldown_ttl = self._config.cooldown_for(event_type_str)

            if not self._cooldown.is_allowed(
                camera_id=result.camera_id,
                event_type=event_type_str,
                object_id=result.object_id,
                now=now,
                ttl=cooldown_ttl,
            ):
                continue

            # 5. Resolve severity (config override may change it)
            severity = self._severity_resolver.get_severity(event_type_str)

            candidates.append(
                SecurityEventCandidate(
                    event_type=result.event_type,
                    camera_id=result.camera_id,
                    source_event_id=detection.source_event_id,
                    object_id=result.object_id,
                    severity=severity,
                    confidence=detection.confidence,
                    timestamp=now,
                    zone_id=result.zone_id,
                    reason=result.reason,
                    metadata=result.metadata,
                )
            )

        return candidates

    def reset(self) -> None:
        """Clear all internal state (rules + cooldowns)."""
        for rule in self._rules:
            rule.reset()
        self._cooldown.reset()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_valid(self, detection: DetectionEvent) -> bool:
        """Return ``False`` (with a log) if the detection should be dropped."""
        if detection.confidence < self._config.confidence_threshold:
            logger.debug(
                "Detection dropped (low confidence): camera=%s "
                "object=%s confidence=%.2f threshold=%.2f",
                detection.camera_id,
                detection.object_id,
                detection.confidence,
                self._config.confidence_threshold,
            )
            return False
        return True
