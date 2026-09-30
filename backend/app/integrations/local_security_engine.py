"""Adapter that exposes the in-process security rules through the async contract."""

from __future__ import annotations

from app.domain.security import SecurityContext, SecurityDecision
from app.security.engine import SecurityEngine as RuleEngine
from app.security.models import BoundingBox, DetectionEvent, EventState


class LocalSecurityEngine:
    """Run the shared rule engine without requiring a second HTTP service."""

    def __init__(self, engine: RuleEngine | None = None) -> None:
        self.engine = engine or RuleEngine()

    async def evaluate(self, context: SecurityContext) -> SecurityDecision:
        track_id = context.track_id or f"object_{context.camera_id}"
        detection = DetectionEvent(
            source="frigate",
            source_event_id=track_id,
            camera_id=str(context.camera_id),
            object_id=track_id,
            track_id=context.track_id,
            object_type=context.object_type,
            confidence=context.confidence,
            timestamp=context.timestamp,
            bbox=self._bbox(
                context.bounding_box, context.frame_width, context.frame_height
            ),
            event_state=EventState.UPDATE,
            metadata={"active_person_count": context.active_person_count},
        )
        candidates = self.engine.evaluate(detection, current_time=context.timestamp)
        if not candidates:
            return SecurityDecision(
                event_type="DETECTION", score=0, severity="INFO", reason=None
            )
        # A single HTTP-style decision must represent the most urgent rule
        # result.  The person-detected rule runs first, so returning index 0
        # would otherwise hide zone, loitering, and tripwire incidents.
        candidate = max(
            candidates,
            key=lambda item: self._score(item.severity.value),
        )
        return SecurityDecision(
            event_type=candidate.event_type.value,
            score=self._score(candidate.severity.value),
            severity=candidate.severity.value,
            reason=candidate.reason,
            metadata={
                **candidate.metadata,
                "track_id": candidate.track_id,
                "zone_id": candidate.zone_id,
                "tripwire_id": candidate.tripwire_id,
            },
        )

    @staticmethod
    def _bbox(
        value: dict[str, float] | None,
        frame_width: int | None,
        frame_height: int | None,
    ) -> BoundingBox | None:
        if value is None:
            return None
        x = value.get("x", 0.0)
        y = value.get("y", 0.0)
        width = value.get("width", 0.0)
        height = value.get("height", 0.0)
        # PersonTracker emits normalized coordinates for the UI.  Security
        # zones and tripwires are intentionally configured in source-frame
        # pixels, so restore that coordinate system before rule evaluation.
        if frame_width and frame_height and all(
            0.0 <= coordinate <= 1.0 for coordinate in (x, y, width, height)
        ):
            x *= frame_width
            y *= frame_height
            width *= frame_width
            height *= frame_height
        return BoundingBox(
            x1=x,
            y1=y,
            x2=x + width,
            y2=y + height,
        )

    @staticmethod
    def _score(severity: str) -> int:
        return {"INFO": 20, "LOW": 35, "MEDIUM": 55, "HIGH": 75, "CRITICAL": 95}.get(
            severity, 0
        )
