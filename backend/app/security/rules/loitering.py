"""
Rule: LOITERING

Triggers when a person remains inside a restricted zone for longer than a
configurable threshold (default 15 s).

State key: ``(camera_id, object_id, zone_id)``

State fields per key:
    entered_at      — timestamp when the object first entered the zone
    last_seen_at    — timestamp of the most recent detection inside
    triggered       — whether LOITERING was already emitted for this visit

Once triggered, the event is NOT emitted again while the person remains
in the zone.  If the person leaves and re-enters, the timer restarts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

from app.security.config import SecurityConfig
from app.security.models import (
    EventType,
    SecurityContext,
    SecurityRuleResult,
    Severity,
)
from app.security.rules.base import SecurityRule
from app.security.zones.geometry import is_point_inside_polygon

logger = logging.getLogger(__name__)

_LoiterKey = Tuple[str, str, str]  # (camera_id, object_id, zone_id)


@dataclass
class _LoiterState:
    entered_at: datetime
    last_seen_at: datetime
    triggered: bool = False


class LoiteringRule(SecurityRule):
    """Detect loitering — a person staying in a zone beyond the threshold."""

    def __init__(self, config: SecurityConfig) -> None:
        self._config = config
        self._state: Dict[_LoiterKey, _LoiterState] = {}

    # ------------------------------------------------------------------
    # SecurityRule interface
    # ------------------------------------------------------------------

    def evaluate(self, context: SecurityContext) -> SecurityRuleResult | None:
        detection = context.detection

        if detection.object_type != "person":
            return None

        if detection.bbox is None:
            return None

        now = context.current_time or detection.timestamp
        ground = detection.bbox.bottom_center()
        result: SecurityRuleResult | None = None

        for zone in context.zones:
            key: _LoiterKey = (detection.camera_id, detection.object_id, zone.id)
            is_inside = is_point_inside_polygon(ground, zone.polygon)

            if is_inside:
                state = self._state.get(key)
                if state is None:
                    # First frame inside — start tracking
                    self._state[key] = _LoiterState(
                        entered_at=now, last_seen_at=now
                    )
                    logger.debug(
                        "Loitering timer started: camera=%s zone=%s object=%s",
                        detection.camera_id,
                        zone.id,
                        detection.object_id,
                    )
                else:
                    state.last_seen_at = now
                    if not state.triggered:
                        elapsed = (now - state.entered_at).total_seconds()
                        if elapsed >= self._config.loitering_threshold_seconds:
                            state.triggered = True
                            duration = int(elapsed)
                            logger.info(
                                "Loitering threshold reached: camera=%s zone=%s "
                                "object=%s duration=%ds",
                                detection.camera_id,
                                zone.id,
                                detection.object_id,
                                duration,
                            )
                            result = SecurityRuleResult(
                                triggered=True,
                                event_type=EventType.LOITERING,
                                severity=Severity.HIGH,
                                reason=(
                                    f"Person remained in restricted zone "
                                    f"'{zone.name}' for {duration} seconds"
                                ),
                                camera_id=detection.camera_id,
                                object_id=detection.object_id,
                                zone_id=zone.id,
                                metadata={"duration_seconds": duration},
                            )
            else:
                # Person has left the zone — clear state so re-entry
                # restarts the timer.
                if key in self._state:
                    logger.debug(
                        "Loitering state cleared (left zone): camera=%s "
                        "zone=%s object=%s",
                        detection.camera_id,
                        zone.id,
                        detection.object_id,
                    )
                    del self._state[key]

        return result

    def reset(self) -> None:
        self._state.clear()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_state(
        self, camera_id: str, object_id: str, zone_id: str
    ) -> _LoiterState | None:
        """Return the current loitering state for inspection/testing."""
        return self._state.get((camera_id, object_id, zone_id))
