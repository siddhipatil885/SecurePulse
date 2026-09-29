"""Central Phase 4 detection-to-event workflow."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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
from app.services.person_tracker import PersonTracker, TrackedPerson

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
        event_cooldown_seconds: float = 30.0,
        person_tracker: PersonTracker | None = None,
        security_engine_supports_tracking: bool = False,
    ) -> None:
        self.session = session
        self.camera_repository = camera_repository
        self.event_repository = event_repository
        self.security_engine = security_engine
        self.security_engine_failure_mode = security_engine_failure_mode
        self.publisher = publisher
        self.event_cooldown_seconds = event_cooldown_seconds
        self.person_tracker = person_tracker
        self.security_engine_supports_tracking = security_engine_supports_tracking

    async def process(self, detection: DetectionEvent) -> EventProcessResult:
        """Process one detection with an idempotent database transaction."""

        self._validate_detection(detection)
        camera = await self.camera_repository.get_by_frigate_name(detection.camera)
        if camera is None:
            raise CameraNotFoundError(f"Camera '{detection.camera}' does not exist")
        if not camera.enabled:
            raise CameraDisabledError(f"Camera '{detection.camera}' is disabled")

        # Frigate's event ID is its native object-track identifier. Project
        # every lifecycle update into a live anonymous track before deciding
        # whether the related security incident is new or a database update.
        track: TrackedPerson | None = None
        if self.person_tracker is not None:
            track = self.person_tracker.observe(detection, str(camera.id))
            await self._publish_tracks(str(camera.id))

        existing = await self.event_repository.get_by_frigate_event_id(
            detection.source_event_id
        )
        
        # Handle lifecycle events: new, update, end
        lifecycle = detection.metadata.get("lifecycle")
        
        # If event already exists, it's an update or end
        if existing is not None:
            if lifecycle in {"update", "end"}:
                existing.object_type = detection.object_type
                existing.confidence = detection.confidence
                existing.event_metadata = {
                    **(existing.event_metadata or {}),
                    **detection.metadata,
                    **self._track_metadata(track),
                }

                # End events carry the final timestamp and close the record.
                if lifecycle == "end":
                    existing.status = "CLOSED"
                    end_time = self._parse_event_timestamp(
                        detection.metadata.get("end_time")
                    )
                    if end_time is not None:
                        existing.timestamp = end_time

                try:
                    await self.session.commit()
                    logger.info(
                        "EVENT_UPDATED",
                        extra={
                            "event_lifecycle": "EVENT_UPDATED",
                            "source_event_id": detection.source_event_id,
                            "lifecycle": lifecycle,
                        },
                    )
                except Exception:
                    await self.session.rollback()
                    raise

                if self.publisher is not None:
                    try:
                        await self.publisher.publish(existing)
                    except Exception:
                        logger.exception("Failed to publish updated security event")
            else:
                logger.debug(
                    "EVENT_DEDUPLICATED",
                    extra={
                        "event_lifecycle": "EVENT_DEDUPLICATED",
                        "source_event_id": detection.source_event_id,
                        "lifecycle": lifecycle,
                    },
                )
            return EventProcessResult(event=existing, duplicate=True)

        # NEW event - create it
        decision = await self._get_security_decision(detection, camera, track)
        event = self._build_event(detection, camera, decision, track)
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
            "EVENT_CREATED",
            extra={
                "event_lifecycle": "EVENT_CREATED",
                "source_event_id": detection.source_event_id,
                "camera_id": camera.id,
            },
        )
        return EventProcessResult(event=event, duplicate=False)

    async def publish_expired_tracks(self, camera_ids: set[str]) -> None:
        """Emit camera snapshots after the track-expiry housekeeping task."""
        for camera_id in camera_ids:
            await self._publish_tracks(camera_id)

    async def _publish_tracks(self, camera_id: str) -> None:
        if self.person_tracker is None or self.publisher is None:
            return
        await self.publisher.publish_tracks(
            camera_id,
            self.person_tracker.tracks_for_camera(camera_id),
        )

    @staticmethod
    def _parse_event_timestamp(value: object) -> datetime | None:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        return None

    @staticmethod
    def _validate_detection(detection: DetectionEvent) -> None:
        if detection.source != "frigate":
            raise EventProcessingError("Only Frigate detections are supported")
        if not detection.camera.strip() or not detection.object_type.strip():
            raise EventProcessingError("Detection camera and object type are required")

    async def _get_security_decision(
        self, detection: DetectionEvent, camera: Camera, track: TrackedPerson | None
    ) -> SecurityDecision | None:
        if self.security_engine is None:
            return None
        try:
            context = {
                "camera_id": camera.id,
                "object_type": detection.object_type,
                "confidence": detection.confidence,
                "timestamp": detection.timestamp,
                "zone": self._zone_from_metadata(detection),
            }
            # Existing separately deployed engines may reject unknown JSON
            # fields.  Keep their contract stable until they opt into the
            # anonymous tracking extension explicitly.
            if self.security_engine_supports_tracking:
                context.update(
                    track_id=track.track_id if track else None,
                    bounding_box=track.bbox if track else None,
                    active_person_count=(
                        len(self.person_tracker.tracks_for_camera(str(camera.id)))
                        if self.person_tracker else None
                    ),
                )
            return await self.security_engine.evaluate(SecurityContext(**context))
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
        track: TrackedPerson | None,
    ) -> SecurityEvent:
        event_metadata = dict(detection.metadata)
        event_metadata.update(cls._track_metadata(track))
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
    def _track_metadata(track: TrackedPerson | None) -> dict[str, object]:
        if track is None:
            return {}
        return {
            "track_id": track.track_id,
            "tracking_state": track.state,
            "bounding_box_normalized": track.bbox,
            "face_visible": track.face_visible,
        }

    @staticmethod
    def _zone_from_metadata(detection: DetectionEvent) -> str | None:
        zones = detection.metadata.get("zones")
        return zones[0] if isinstance(zones, list) and zones and isinstance(zones[0], str) else None
