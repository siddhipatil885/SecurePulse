"""Privacy-preserving live person tracks backed by Frigate's native tracker.

Frigate already associates detections over time.  This service intentionally
does not run another detector or attempt biometric re-identification; it turns
Frigate's object lifecycle into a small, UI-ready active-track projection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.events import DetectionEvent

logger = logging.getLogger(__name__)


@dataclass
class TrackedPerson:
    """An anonymous, temporary person track for one camera."""

    track_id: str
    camera_id: str
    source_event_id: str
    first_seen: datetime
    last_seen: datetime
    bbox: dict[str, float] | None
    confidence: float
    frame_width: int
    frame_height: int
    state: str = "ACTIVE"
    face_visible: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "object_type": "person",
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "bounding_box": self.bbox,
            "confidence": self.confidence,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "state": self.state,
            # Frigate does not provide a face-visibility signal.  Keep this
            # explicitly unknown rather than inferring an identity or face.
            "face_visible": self.face_visible,
        }


class PersonTracker:
    """Maintain live tracks using Frigate lifecycle and object identifiers."""

    def __init__(
        self,
        *,
        lost_track_timeout_seconds: float = 3.0,
        minimum_detection_confidence: float = 0.5,
        default_frame_width: int = 1280,
        default_frame_height: int = 720,
    ) -> None:
        self.lost_track_timeout = timedelta(seconds=lost_track_timeout_seconds)
        self.minimum_detection_confidence = minimum_detection_confidence
        self.default_frame_width = default_frame_width
        self.default_frame_height = default_frame_height
        self._tracks: dict[tuple[str, str], TrackedPerson] = {}

    def observe(self, detection: DetectionEvent, camera_id: str) -> TrackedPerson | None:
        """Apply one Frigate lifecycle message and return the changed track.

        ``source_event_id`` is Frigate's native tracked-object ID.  It is the
        only association mechanism used here, so a new physical appearance
        after Frigate closes a track receives a new anonymous session.
        """
        if (
            detection.object_type != "person"
            or detection.confidence < self.minimum_detection_confidence
        ):
            return None

        now = self._observation_time(detection)
        self.expire_stale(now)
        key = (camera_id, detection.source_event_id)
        lifecycle = detection.metadata.get("lifecycle")
        track = self._tracks.get(key)

        if lifecycle == "end":
            if track is not None:
                track.last_seen = now
                track.state = "TEMPORARILY_LOST"
                self._log("TRACK_TEMPORARILY_LOST", track)
            return track

        bbox, frame_width, frame_height = self._normalised_bbox(detection)
        if track is None:
            track = TrackedPerson(
                track_id=f"person_track_{detection.source_event_id}",
                camera_id=camera_id,
                source_event_id=detection.source_event_id,
                first_seen=now,
                last_seen=now,
                bbox=bbox,
                confidence=detection.confidence,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            self._tracks[key] = track
            self._log("TRACK_CREATED", track)
            return track

        was_lost = track.state == "TEMPORARILY_LOST"
        track.last_seen = now
        track.bbox = bbox or track.bbox
        track.confidence = detection.confidence
        track.frame_width = frame_width
        track.frame_height = frame_height
        track.state = "ACTIVE"
        self._log("TRACK_REACQUIRED" if was_lost else "TRACK_UPDATED", track)
        return track

    def expire_stale(self, now: datetime | None = None) -> list[TrackedPerson]:
        """Close tracks that exceeded the configured loss grace period."""
        now = now or datetime.now(timezone.utc)
        expired: list[TrackedPerson] = []
        for key, track in tuple(self._tracks.items()):
            if track.state == "TEMPORARILY_LOST" and now - track.last_seen >= self.lost_track_timeout:
                track.state = "EXPIRED"
                expired.append(track)
                del self._tracks[key]
                self._log("TRACK_EXPIRED", track)
        return expired

    def tracks_for_camera(self, camera_id: str, *, include_lost: bool = True) -> list[dict[str, Any]]:
        tracks = [
            track.as_dict()
            for track in self._tracks.values()
            if track.camera_id == camera_id and (include_lost or track.state == "ACTIVE")
        ]
        return sorted(tracks, key=lambda track: (str(track["first_seen"]), str(track["track_id"])))

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        cameras = {track.camera_id for track in self._tracks.values()}
        return {camera_id: self.tracks_for_camera(camera_id) for camera_id in cameras}

    def _normalised_bbox(self, detection: DetectionEvent) -> tuple[dict[str, float] | None, int, int]:
        width = self._positive_int(detection.metadata.get("frame_width"), self.default_frame_width)
        height = self._positive_int(detection.metadata.get("frame_height"), self.default_frame_height)
        box = detection.metadata.get("bounding_box")
        if not isinstance(box, list) or len(box) != 4 or not all(isinstance(v, (int, float)) for v in box):
            return None, width, height

        x1, y1, x2, y2 = (float(value) for value in box)
        # Frigate boxes are pixel [x1, y1, x2, y2]. Clamp malformed edge
        # coordinates so a single upstream anomaly cannot break the overlay.
        x1, x2 = sorted((max(0.0, min(x1, width)), max(0.0, min(x2, width))))
        y1, y2 = sorted((max(0.0, min(y1, height)), max(0.0, min(y2, height))))
        return {
            "x": x1 / width,
            "y": y1 / height,
            "width": (x2 - x1) / width,
            "height": (y2 - y1) / height,
        }, width, height

    @staticmethod
    def _positive_int(value: object, fallback: int) -> int:
        return int(value) if isinstance(value, (int, float)) and value > 0 else fallback

    @staticmethod
    def _observation_time(detection: DetectionEvent) -> datetime:
        value = detection.metadata.get("observed_at")
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    return parsed.astimezone(timezone.utc)
            except ValueError:
                pass
        return detection.timestamp

    @staticmethod
    def _log(event: str, track: TrackedPerson) -> None:
        """Emit a machine-searchable lifecycle record without biometric data."""
        logger.info(
            event,
            extra={
                "tracking_event": event,
                "camera_id": track.camera_id,
                "track_id": track.track_id,
                "state": track.state,
            },
        )
