"""Central Phase 4 detection-to-event workflow."""

import logging
import inspect
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.events import DetectionEvent
from app.domain.security import SecurityContext, SecurityDecision
from app.integrations.security_engine import SecurityEngine, SecurityEngineError
from app.models.camera import Camera
from app.models.security_event import SecurityEvent
from app.models.alert import Alert
from app.models.track import Track
from app.models.evidence import Evidence
from app.models.operations import (AuditRecord, IncidentStatusHistory, NotificationOutbox,
    SourceEventReceipt)
from app.repositories.cameras import CameraRepository
from app.repositories.events import EventRepository
from app.realtime.publisher import EventPublisher
from app.services.person_tracker import PersonTracker, TrackedPerson
from app.services.metadata_budget import compact_metadata, metadata_digest

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
        try:
            return await self._process(detection)
        except IntegrityError:
            await self.session.rollback()
            lifecycle, revision = self._receipt_identity(detection)
            receipt = await self.event_repository.get_receipt(
                source_system=detection.source,
                source_event_id=detection.source_event_id,
                event_phase=lifecycle,
                revision=revision,
            )
            if receipt is not None and receipt.security_event is not None:
                return EventProcessResult(event=receipt.security_event, duplicate=True)
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def _process(self, detection: DetectionEvent) -> EventProcessResult:

        self._validate_detection(detection)
        camera = await self.camera_repository.get_by_frigate_name(detection.camera)
        if camera is None:
            raise CameraNotFoundError(f"Camera '{detection.camera}' does not exist")
        if not camera.enabled:
            raise CameraDisabledError(f"Camera '{detection.camera}' is disabled")

        lifecycle, revision = self._receipt_identity(detection)
        prior_receipt = await self.event_repository.get_receipt(
            source_system=detection.source,
            source_event_id=detection.source_event_id,
            event_phase=lifecycle,
            revision=revision,
        )
        if prior_receipt is not None:
            prior_event = getattr(prior_receipt, "security_event", None)
            if prior_event is None:
                prior_event = await self.event_repository.get_by_frigate_event_id(
                    detection.source_event_id
                )
            if prior_event is not None:
                return EventProcessResult(event=prior_event, duplicate=True)

        receipt = SourceEventReceipt(
            property_id=camera.property_id,
            camera_id=camera.id,
            source_system=detection.source,
            source_event_id=detection.source_event_id,
            event_phase=lifecycle,
            revision=revision,
            observed_at=detection.timestamp,
            # Receipt identity already records source/phase/revision. Keep a
            # checksum rather than copying raw camera metadata on every update.
            payload={"metadata_sha256": metadata_digest(detection.metadata), "object_type": detection.object_type},
        )

        # Frigate's event ID is its native object-track identifier. Project
        # every lifecycle update into a live anonymous track before deciding
        # whether the related security incident is new or a database update.
        track: TrackedPerson | None = None
        if self.person_tracker is not None:
            track = self.person_tracker.observe(detection, str(camera.id))
            if track is not None:
                await self._persist_track(track, camera.id)
            await self._publish_tracks(str(camera.id), camera.property_id)

        existing = await self.event_repository.get_by_frigate_event_id(
            detection.source_event_id
        )
        
        # If event already exists, it's an update or end
        if existing is not None:
            if lifecycle == "update" and self.security_engine is not None:
                decision = await self._get_security_decision(detection, camera, track)
                if decision is not None and decision.event_type != "DETECTION":
                    incident_key = self._incident_key(detection, decision, track)
                    incident = await self.event_repository.get_by_incident_key(
                        incident_key, for_update=True
                    )
                    was_created = incident is None
                    escalated = False
                    if incident is None:
                        incident = self._build_event(detection, camera, decision, track)
                        incident.incident_key = incident_key
                        await self.event_repository.create(incident)
                        await self._add_initial_incident_records(incident, detection, lifecycle, revision)
                        if incident.severity in {"HIGH", "CRITICAL"}:
                            await self._add(Alert(camera_id=incident.camera_id,
                                security_event_id=incident.id, severity=incident.severity,
                                status="ACTIVE"))
                    else:
                        escalated = await self._apply_correlated_decision(
                            incident, detection, decision, track
                        )
                    receipt.security_event = incident
                    await self.event_repository.create_receipt(receipt)
                    await self.session.commit()
                    if escalated and self.publisher is not None:
                        try:
                            await self.publisher.publish(incident)
                        except Exception:
                            logger.exception("Failed to publish committed incident escalation")
                    return EventProcessResult(event=incident, duplicate=not was_created and not escalated)
            if lifecycle in {"update", "end"}:
                previous_status = existing.status
                existing.object_type = detection.object_type
                existing.confidence = detection.confidence
                existing.event_metadata = compact_metadata({
                    **(existing.event_metadata or {}),
                    **detection.metadata,
                    **self._track_metadata(track),
                })

                # End events carry the final timestamp and close the record.
                if lifecycle == "end":
                    if existing.status in {"OPEN", "UNCLASSIFIED"}:
                        existing.status = "CLOSED"
                    end_time = self._parse_event_timestamp(
                        detection.metadata.get("end_time")
                    )
                    if end_time is not None:
                        existing.timestamp = end_time

                receipt.security_event = existing
                await self.event_repository.create_receipt(receipt)
                if existing.status != previous_status:
                    await self._add(
                        IncidentStatusHistory(
                            security_event_id=existing.id,
                            previous_status=previous_status,
                            new_status=existing.status,
                            actor_subject="system:ingestion",
                            reason=f"Source lifecycle phase {lifecycle}",
                            correlation_id=self._correlation_id(detection, lifecycle, revision),
                        )
                    )

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
                except IntegrityError:
                    # The outer boundary resolves the exact winning receipt.
                    raise
                except Exception:
                    await self.session.rollback()
                    raise

                if self.publisher is not None:
                    try:
                        await self.publisher.publish(existing)
                    except Exception:
                        logger.exception("Failed to publish updated security event")
            else:
                receipt.security_event = existing
                await self.event_repository.create_receipt(receipt)
                await self.session.commit()
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
        if decision is not None:
            event.incident_key = self._incident_key(detection, decision, track)
        snapshot_url = None
        if detection.metadata.get("has_snapshot"):
            snapshot_url = f"/api/v1/frigate/cameras/{camera.frigate_camera_name}/snapshot"
            event.event_metadata = {**event.event_metadata, "snapshot_url": snapshot_url}
        try:
            await self.event_repository.create(event)
            receipt.security_event = event
            await self.event_repository.create_receipt(receipt)
            await self._add_initial_incident_records(event, detection, lifecycle, revision)
            if detection.metadata.get("has_snapshot"):
                await self._add(
                    Evidence(
                        event_id=event.id,
                        type="SNAPSHOT",
                        file_path=snapshot_url or "",
                        timestamp=detection.timestamp,
                        evidence_metadata={
                            "bounding_box": track.bbox if track else None,
                            "face_visible": track.face_visible if track else None,
                        },
                    )
                )
            if event.severity in {"HIGH", "CRITICAL"}:
                await self._add(
                    Alert(
                        camera_id=event.camera_id,
                        security_event_id=event.id,
                        severity=event.severity,
                        status="ACTIVE",
                    )
                )
            await self.session.commit()
        except IntegrityError:
            # Do not hide unrelated constraint failures as successful replays.
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

    async def _persist_track(self, track: TrackedPerson, camera_id: int) -> None:
        """Upsert the anonymous live projection without storing biometric data."""
        statement = select(Track).where(Track.track_id == track.track_id)
        persisted = await self.session.scalar(statement)
        values = {
            "camera_id": camera_id,
            "source_event_id": track.source_event_id,
            "first_seen": track.first_seen,
            "last_seen": track.last_seen,
            "state": track.state,
            "confidence": track.confidence,
            "bounding_box": track.bbox,
            "frame_width": track.frame_width,
            "frame_height": track.frame_height,
            "face_visible": track.face_visible,
        }
        if persisted is None:
            await self._add(Track(track_id=track.track_id, **values))
        else:
            for key, value in values.items():
                setattr(persisted, key, value)

    async def _add(self, entity: object) -> None:
        """Support SQLAlchemy sessions and lightweight async test doubles."""
        result = self.session.add(entity)  # type: ignore[attr-defined]
        if inspect.isawaitable(result):
            await result

    async def _add_initial_incident_records(
        self,
        event: SecurityEvent,
        detection: DetectionEvent,
        lifecycle: str,
        revision: str,
    ) -> None:
        correlation_id = self._correlation_id(detection, lifecycle, revision)
        await self._add(
            IncidentStatusHistory(
                security_event_id=event.id,
                previous_status=None,
                new_status=event.status,
                actor_subject="system:ingestion",
                reason=event.reason or "Detection ingested",
                correlation_id=correlation_id,
            )
        )
        if event.status == "OPEN":
            incident_key = event.incident_key or detection.source_event_id
            dedupe_hash = hashlib.sha256(incident_key.encode()).hexdigest()
            await self._add(
                NotificationOutbox(
                    property_id=event.property_id,
                    security_event_id=event.id,
                    kind="INCIDENT_OPENED",
                    dedupe_key=f"incident:{dedupe_hash}:opened",
                    status="PENDING",
                    payload={
                        "camera_id": event.camera_id,
                        "severity": event.severity,
                        "event_type": event.event_type,
                    },
                )
            )

    async def _apply_correlated_decision(
        self,
        incident: SecurityEvent,
        detection: DetectionEvent,
        decision: SecurityDecision,
        track: TrackedPerson | None,
    ) -> bool:
        """Update evidence and emit one audited notification for severity increases."""
        ranked = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        incident.confidence = max(incident.confidence, detection.confidence)
        incident.event_metadata = {
            **(incident.event_metadata or {}),
            **detection.metadata,
            **self._track_metadata(track),
            "security_decision": decision.model_dump(mode="json"),
        }
        if ranked.get(decision.severity, 0) <= ranked.get(incident.severity, 0):
            return False

        previous_severity = incident.severity
        previous_event_type = incident.event_type
        incident.severity = decision.severity
        incident.event_type = decision.event_type
        incident.score = decision.score
        incident.reason = decision.reason
        correlation_id = self._correlation_id(
            detection, "severity_escalation", str(decision.metadata.get("policy_version", "0"))
        )
        await self._add(AuditRecord(property_id=incident.property_id,
            actor_subject="system:security_engine", action="INCIDENT_SEVERITY_ESCALATED",
            resource_type="security_event", resource_id=str(incident.id),
            correlation_id=correlation_id,
            details={"previous_severity": previous_severity,
                     "new_severity": decision.severity,
                     "previous_event_type": previous_event_type,
                     "new_event_type": decision.event_type, "reason": decision.reason,
                     "policy_version": decision.metadata.get("policy_version")}))
        digest = hashlib.sha256((incident.incident_key or str(incident.id)).encode()).hexdigest()
        await self._add(NotificationOutbox(property_id=incident.property_id,
            security_event_id=incident.id, kind="INCIDENT_SEVERITY_ESCALATED",
            destination=f"property:{incident.property_id}:dispatchers",
            dedupe_key=f"incident:{digest}:severity:{decision.severity}", status="PENDING",
            payload={"incident_id": incident.id, "previous_severity": previous_severity,
                     "severity": decision.severity, "event_type": decision.event_type,
                     "reason": decision.reason,
                     "policy_version": decision.metadata.get("policy_version")}))
        if incident.severity in {"HIGH", "CRITICAL"}:
            await self._add(Alert(camera_id=incident.camera_id,
                security_event_id=incident.id, severity=incident.severity, status="ACTIVE"))
        return True

    @staticmethod
    def _receipt_identity(detection: DetectionEvent) -> tuple[str, str]:
        """Use the same normalized identity for receipt writes and race recovery."""
        lifecycle = str(detection.metadata.get("lifecycle") or "new")
        raw = detection.metadata.get("revision", "0")
        revision = str(raw) if isinstance(raw, (str, int)) and not isinstance(raw, bool) else "0"
        return lifecycle, revision

    @staticmethod
    def _correlation_id(detection: DetectionEvent, lifecycle: str, revision: str) -> str:
        return f"{detection.source}:{detection.source_event_id}:{lifecycle}:{revision}"

    async def publish_expired_tracks(self, camera_ids: set[str]) -> None:
        """Emit camera snapshots after the track-expiry housekeeping task."""
        for camera_id in camera_ids:
            await self._publish_tracks(camera_id)

    async def _publish_tracks(self, camera_id: str, property_id: int | None = None) -> None:
        if self.person_tracker is None or self.publisher is None:
            return
        await self.publisher.publish_tracks(
            camera_id,
            self.person_tracker.tracks_for_camera(camera_id, include_lost=False),
            property_id,
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
                "evidence_refs": self._evidence_refs(detection),
            }
            # Existing separately deployed engines may reject unknown JSON
            # fields.  Keep their contract stable until they opt into the
            # anonymous tracking extension explicitly.
            if self.security_engine_supports_tracking:
                context.update(
                    track_id=track.track_id if track else None,
                    bounding_box=track.bbox if track else None,
                    frame_width=track.frame_width if track else None,
                    frame_height=track.frame_height if track else None,
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
        zone = decision.metadata.get("zone_id") if decision is not None else None
        if not isinstance(zone, str):
            zone = zones[0] if isinstance(zones, list) and zones and isinstance(zones[0], str) else None
        return SecurityEvent(
            property_id=camera.property_id,
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
            event_metadata=compact_metadata(event_metadata),
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
    def _incident_key(
        detection: DetectionEvent,
        decision: SecurityDecision,
        track: TrackedPerson | None,
    ) -> str:
        # Frigate's event id scopes one source activity across update frames.
        # Zone events share a key so loitering can raise the same incident's
        # severity; no physical-person identity is inferred.
        zone_id = decision.metadata.get("zone_id") or EventProcessor._zone_from_metadata(detection)
        policy_scope = f"zone:{zone_id}" if zone_id else f"type:{decision.event_type}"
        return f"{detection.source}:{detection.source_event_id}:{policy_scope}"

    @staticmethod
    def _zone_from_metadata(detection: DetectionEvent) -> str | None:
        zones = detection.metadata.get("zones")
        return zones[0] if isinstance(zones, list) and zones and isinstance(zones[0], str) else None

    @staticmethod
    def _evidence_refs(detection: DetectionEvent) -> list[str]:
        raw = detection.metadata.get("evidence_refs", [])
        references = [value for value in raw if isinstance(value, str)] if isinstance(raw, list) else []
        if detection.metadata.get("has_snapshot"):
            references.append(f"frigate:{detection.source_event_id}:snapshot")
        if detection.metadata.get("has_clip"):
            references.append(f"frigate:{detection.source_event_id}:clip")
        return list(dict.fromkeys(references))[:20]
