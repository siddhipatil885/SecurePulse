"""
Rule: MULTIPLE_PERSONS

Triggers when the number of simultaneously-detected persons on a single
camera meets or exceeds a configurable threshold (default 3).

The rule counts only ``object_type == "person"`` entries from
``context.active_detections``.

Multiple people are not automatically treated as malicious — the rule
simply identifies the configured condition.
"""

from __future__ import annotations

import logging

from app.security.config import SecurityConfig
from app.security.models import (
    EventType,
    SecurityContext,
    SecurityRuleResult,
    Severity,
)
from app.security.rules.base import SecurityRule

logger = logging.getLogger(__name__)


class MultiplePersonRule(SecurityRule):
    """Detect multiple simultaneous persons on a camera."""

    def __init__(self, config: SecurityConfig) -> None:
        self._config = config

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        detection = context.detection

        if detection.object_type != "person":
            return None

        person_count = sum(
            1
            for d in context.active_detections
            if d.object_type == "person" and d.camera_id == detection.camera_id
        )

        if person_count < self._config.multiple_person_threshold:
            return None

        logger.info(
            "Multiple persons detected: camera=%s count=%d threshold=%d",
            detection.camera_id,
            person_count,
            self._config.multiple_person_threshold,
        )

        return SecurityRuleResult(
            triggered=True,
            event_type=EventType.MULTIPLE_PERSONS,
            severity=Severity.MEDIUM,
            reason=(
                f"{person_count} people detected on camera "
                f"{detection.camera_id}"
            ),
            camera_id=detection.camera_id,
            object_id=detection.object_id,
            metadata={"person_count": person_count},
        )
