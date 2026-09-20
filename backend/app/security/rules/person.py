"""
Rule: PERSON_DETECTED

The simplest rule — triggers whenever the detected object is a person.

Non-person objects (car, dog, …) do not trigger this rule.
No identification, recognition, or profiling is performed.
"""

from __future__ import annotations

import logging

from app.security.models import (
    EventType,
    SecurityContext,
    SecurityRuleResult,
    Severity,
)
from app.security.rules.base import SecurityRule

logger = logging.getLogger(__name__)


class PersonDetectedRule(SecurityRule):
    """Trigger ``PERSON_DETECTED`` when ``object_type == 'person'``."""

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        detection = context.detection

        if detection.object_type != "person":
            return None

        logger.info(
            "Person detected: camera=%s object=%s confidence=%.2f",
            detection.camera_id,
            detection.object_id,
            detection.confidence,
        )

        return SecurityRuleResult(
            triggered=True,
            event_type=EventType.PERSON_DETECTED,
            severity=Severity.INFO,
            reason="Person detected",
            camera_id=detection.camera_id,
            object_id=detection.object_id,
        )
