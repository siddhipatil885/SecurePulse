"""Configurable person-entry decisions for camera-specific restricted zones."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

from app.security.models import EventType, Point, SecurityContext, SecurityRuleResult
from app.security.rules.base import SecurityRule
from app.security.zones.geometry import is_point_inside_polygon

logger = logging.getLogger(__name__)

_ZoneStateKey = Tuple[str, str, str]


@dataclass
class _ZoneState:
    entered_at: datetime
    last_seen_at: datetime
    emitted: bool = False


class ZoneEntryRule(SecurityRule):
    """Detect restricted-zone entry after per-zone confidence and dwell rules."""

    def __init__(self) -> None:
        self._zone_state: Dict[_ZoneStateKey, _ZoneState] = {}

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        detection = context.detection
        if detection.object_type != "person" or detection.bbox is None:
            return None

        now = context.current_time or detection.timestamp
        ground = detection.bbox.bottom_center()
        for zone in context.zones:
            if detection.confidence < zone.minimum_confidence:
                # Low-confidence geometry is unknown; it must not mark a
                # tracked person as having left the zone.
                continue

            polygon = zone.polygon
            if zone.frame_width is not None:
                if detection.frame_width is None or detection.frame_height is None:
                    logger.warning("Zone evaluation skipped: frame dimensions missing", extra={
                        "camera_id": detection.camera_id, "zone_id": zone.id,
                    })
                    continue
                scale_x = detection.frame_width / zone.frame_width
                scale_y = detection.frame_height / zone.frame_height
                polygon = [Point(x=point.x * scale_x, y=point.y * scale_y)
                           for point in zone.polygon]

            key: _ZoneStateKey = (detection.camera_id, detection.object_id, zone.id)
            inside = is_point_inside_polygon(ground, polygon)
            state = self._zone_state.get(key)

            if state is not None and now < state.last_seen_at:
                # Out-of-order updates never move track state backwards.
                continue

            if not inside:
                self._zone_state.pop(key, None)
                continue
            if state is None:
                state = _ZoneState(entered_at=now, last_seen_at=now)
                self._zone_state[key] = state
            else:
                state.last_seen_at = now

            dwell = max(0.0, (now - state.entered_at).total_seconds())
            restricted = zone.is_restricted_at(now)
            if state.emitted or not restricted or dwell < zone.minimum_dwell_seconds:
                continue

            state.emitted = True
            logger.info("Restricted zone entry detected", extra={
                "camera_id": detection.camera_id,
                "zone_id": zone.id,
                "object_id": detection.object_id,
                "dwell_seconds": dwell,
            })
            return SecurityRuleResult(
                triggered=True,
                event_type=EventType.ZONE_ENTRY,
                severity=zone.severity,
                reason=f"Person entered restricted zone '{zone.name}'",
                camera_id=detection.camera_id,
                object_id=detection.object_id,
                zone_id=zone.id,
                metadata={
                    "dwell_seconds": dwell,
                    "minimum_dwell_seconds": zone.minimum_dwell_seconds,
                    "minimum_confidence": zone.minimum_confidence,
                    "policy_zone_id": zone.id,
                },
            )
        return None

    def end_event(self, context: SecurityContext) -> None:
        self.remove_object(context.detection.camera_id, context.detection.object_id)

    def reset(self) -> None:
        self._zone_state.clear()

    def is_inside(self, camera_id: str, object_id: str, zone_id: str) -> bool:
        return (camera_id, object_id, zone_id) in self._zone_state

    def remove_object(self, camera_id: str, object_id: str) -> None:
        keys = [key for key in self._zone_state if key[:2] == (camera_id, object_id)]
        for key in keys:
            del self._zone_state[key]
