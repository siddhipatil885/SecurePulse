"""Central Phase 4 detection-to-event workflow."""

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import DetectionEvent
from app.domain.security import SecurityContext, SecurityDecision
from app.integrations.security_engine import SecurityEngine, SecurityEngineError
from app.models.camera import Camera
from app.models.security_event import SecurityEvent
from app.repositories.cameras import CameraRepository
from app.repositories.events import EventRepository
from app.realtime.publisher import EventPublisher

logger = logging.getLogger(__name__)


class EventProcessingError(RuntimeError):
    """Base error for a detection that cannot be processed."""


class CameraNotFoundError(EventProcessingError):
    """Raised when a detection references an unknown Frigate camera."""


class CameraDisabledError(EventProcessingError):
    """Raised when a detection references a disabled camera."""


class SecurityEngineUnavailableError(EventProcessingError):
    """Raised when configured security-engine failure mode is REJECT."""


class SessionProtocol(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@dataclass(frozen=True)
class EventProcessResult:
    """Result of processing, including whether idempotency found an existing event."""

    event: SecurityEvent
    duplicate: bool


class EventProcessor:
    """Validate, map, deduplicate, and persist normalized detection events."""

    def __init__(
        self,
        session: AsyncSession | SessionProtocol,
        camera_repository: CameraRepository,
        event_repository: EventRepository,
        security_engine: SecurityEngine | None = None,
        security_engine_failure_mode: str = "STORE_UNCLASSIFIED",
        publisher: EventPublisher | None = None,
    ) -> None:
        self.session = session
        self.camera_repository = camera_repository
        self.event_repository = event_repository
        self.security_engine = security_engine
        self.security_engine_failure_mode = security_engine_failure_mode
        self.publisher = publisher

    async def process(self, detection: DetectionEvent) -> EventProcessResult:
        """Process one detection with an idempotent database transaction."""

        self._validate_detection(detection)
        camera = await self.camera_repository.get_by_frigate_name(detection.camera)
        if camera is None:
            raise CameraNotFoundError(f"Camera '{detection.camera}' does not exist")
        if not camera.enabled:
            raise CameraDisabledError(f"Camera '{detection.camera}' is disabled")

        existing = await self.event_repository.get_by_frigate_event_id(
            detection.source_event_id
        )
        if existing is not None:
            logger.info(
                "Ignored duplicate detection",
                extra={"source_event_id": detection.source_event_id},
            )
            return EventProcessResult(event=existing, duplicate=True)

        decision = await self._get_security_decision(detection, camera)
        event = self._build_event(detection, camera, decision)
        try:
            await self.event_repository.create(event)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.event_repository.get_by_frigate_event_id(
                detection.source_event_id
            )
            if existing is not None:
                return EventProcessResult(event=existing, duplicate=True)
            raise
        except Exception:
            await self.session.rollback()
            raise

        if self.publisher is not None:
            try:
                await self.publisher.publish(event)
            except Exception:
                logger.exception("Failed to publish committed security event")

        logger.info(
            "Processed detection",
            extra={"source_event_id": detection.source_event_id, "camera_id": camera.id},
        )
        return EventProcessResult(event=event, duplicate=False)

    @staticmethod
    def _validate_detection(detection: DetectionEvent) -> None:
        if detection.source != "frigate":
            raise EventProcessingError("Only Frigate detections are supported")
        if not detection.camera.strip() or not detection.object_type.strip():
            raise EventProcessingError("Detection camera and object type are required")

    async def _get_security_decision(
        self, detection: DetectionEvent, camera: Camera
    ) -> SecurityDecision | None:
        if self.security_engine is None:
            return None
        try:
            return await self.security_engine.evaluate(
                SecurityContext(
                    camera_id=camera.id,
                    object_type=detection.object_type,
                    confidence=detection.confidence,
                    timestamp=detection.timestamp,
                    zone=self._zone_from_metadata(detection),
                )
            )
        except SecurityEngineError as error:
            logger.error(
                "Security engine failure",
                extra={"source_event_id": detection.source_event_id, "error": str(error)},
            )
            if self.security_engine_failure_mode == "REJECT":
                raise SecurityEngineUnavailableError(
                    "Security engine unavailable; event was not stored"
                ) from error
            return None

    @classmethod
    def _build_event(
        cls,
        detection: DetectionEvent,
        camera: Camera,
        decision: SecurityDecision | None,
    ) -> SecurityEvent:
        event_metadata = dict(detection.metadata)
        if decision is not None:
            event_metadata["security_decision"] = decision.model_dump(mode="json")
        zones = detection.metadata.get("zones")
        zone = zones[0] if isinstance(zones, list) and zones and isinstance(zones[0], str) else None
        return SecurityEvent(
            camera_id=camera.id,
            event_type=decision.event_type if decision else "DETECTION",
            object_type=detection.object_type,
            confidence=detection.confidence,
            timestamp=detection.timestamp,
            severity=decision.severity if decision else "UNCLASSIFIED",
            status="OPEN" if decision else "UNCLASSIFIED",
            score=decision.score if decision else None,
            zone=zone,
            frigate_event_id=detection.source_event_id,
            reason=decision.reason if decision else None,
            event_metadata=event_metadata,
        )

    @staticmethod
    def _zone_from_metadata(detection: DetectionEvent) -> str | None:
        zones = detection.metadata.get("zones")
        return zones[0] if isinstance(zones, list) and zones and isinstance(zones[0], str) else None