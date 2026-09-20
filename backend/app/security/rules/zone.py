"""
Rule: ZONE_ENTRY

Triggers when a person transitions from **outside** a restricted zone to
**inside** it.  Repeated detections while the person *remains* inside do
NOT generate new events — only the transition fires.

State key: ``(camera_id, object_id, zone_id)``

When the person leaves the zone the state is cleared so that a future
re-entry can trigger a new event.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

from app.security.models import (
    EventType,
    SecurityContext,
    SecurityRuleResult,
    Severity,
)
from app.security.rules.base import SecurityRule
from app.security.zones.geometry import is_point_inside_polygon

logger = logging.getLogger(__name__)

# (camera_id, object_id, zone_id) → was_inside_last_frame
_ZoneStateKey = Tuple[str, str, str]


class ZoneEntryRule(SecurityRule):
    """Detect outside → inside transitions for restricted zones."""

    def __init__(self) -> None:
        # Tracks whether each (camera, object, zone) was inside on the
        # previous evaluation.  ``True`` means the object was inside.
        self._zone_state: Dict[_ZoneStateKey, bool] = {}

    # ------------------------------------------------------------------
    # SecurityRule interface
    # ------------------------------------------------------------------

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        detection = context.detection

        if detection.object_type != "person":
            return None

        if detection.bbox is None:
            return None

        ground = detection.bbox.bottom_center()
        result: SecurityRuleResult | None = None

        for zone in context.zones:
            key: _ZoneStateKey = (detection.camera_id, detection.object_id, zone.id)
            is_inside = is_point_inside_polygon(ground, zone.polygon)
            was_inside = self._zone_state.get(key, False)

            if is_inside and not was_inside:
                # Transition: outside → inside
                logger.info(
                    "Zone entry detected: camera=%s zone=%s object=%s",
                    detection.camera_id,
                    zone.id,
                    detection.object_id,
                )
                result = SecurityRuleResult(
                    triggered=True,
                    event_type=EventType.ZONE_ENTRY,
                    severity=Severity.MEDIUM,
                    reason=f"Person entered restricted zone '{zone.name}'",
                    camera_id=detection.camera_id,
                    object_id=detection.object_id,
                    zone_id=zone.id,
                )

            # Update state (including inside→inside or outside→outside)
            self._zone_state[key] = is_inside

        return result

    def reset(self) -> None:
        self._zone_state.clear()

    # ------------------------------------------------------------------
    # Public helpers for other rules (e.g. LoiteringRule)
    # ------------------------------------------------------------------

    def is_inside(self, camera_id: str, object_id: str, zone_id: str) -> bool:
        """Return whether *object_id* is currently inside *zone_id*."""
        return self._zone_state.get((camera_id, object_id, zone_id), False)

    def remove_object(self, camera_id: str, object_id: str) -> None:
        """Purge all zone state for an object that has left the frame."""
        keys_to_remove = [
            k for k in self._zone_state
            if k[0] == camera_id and k[1] == object_id
        ]
        for k in keys_to_remove:
            del self._zone_state[k]
