"""
Rule: LINE_CROSSING

Triggers when an object's trajectory (the line segment between its previous position
and current position) intersects with a configured virtual tripwire.

State key: ``(camera_id, object_id)``
State:
    last_seen_point — the point (bottom-center) where the object was last detected.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

from app.security.config import SecurityConfig
from app.security.models import (
    EventType,
    Point,
    SecurityContext,
    SecurityRuleResult,
    Severity,
)
from app.security.rules.base import SecurityRule
from app.security.zones.geometry import do_line_segments_intersect

logger = logging.getLogger(__name__)

_TrackKey = Tuple[str, str]  # (camera_id, object_id)


class LineCrossingRule(SecurityRule):
    """Detect when an object crosses a virtual tripwire."""

    def __init__(self, config: SecurityConfig) -> None:
        self._config = config
        self._state: Dict[_TrackKey, Point] = {}

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        detection = context.detection

        if detection.object_type != "person":
            return None

        if detection.bbox is None:
            return None
        
        if not context.tripwires:
            return None

        key: _TrackKey = (detection.camera_id, detection.object_id)
        current_point = detection.bbox.bottom_center()
        last_point = self._state.get(key)
        
        # Always update the state to the current point for the next frame
        self._state[key] = current_point

        if last_point is None:
            # First time we see the object, no trajectory yet
            return None

        result: SecurityRuleResult | None = None

        for tripwire in context.tripwires:
            # Check if trajectory intersects tripwire
            intersect = do_line_segments_intersect(
                last_point, current_point,
                tripwire.start_point, tripwire.end_point
            )

            if intersect:
                logger.info(
                    "Tripwire crossed: camera=%s tripwire=%s object=%s",
                    detection.camera_id,
                    tripwire.id,
                    detection.object_id,
                )
                
                # We return the first tripwire intersected. If multiple tripwires 
                # are intersected in a single frame, they could be emitted, but for now 
                # returning the first one suffices for the Engine's current design.
                result = SecurityRuleResult(
                    triggered=True,
                    event_type=EventType.LINE_CROSSING,
                    severity=Severity.HIGH,
                    reason=f"Object crossed tripwire '{tripwire.name}'",
                    camera_id=detection.camera_id,
                    object_id=detection.object_id,
                    tripwire_id=tripwire.id,
                )
                break

        return result

    def reset(self) -> None:
        self._state.clear()
