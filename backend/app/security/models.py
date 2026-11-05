"""
Security Intelligence domain models.

All models in this file are pure data containers with no database, network,
or Frigate dependencies.  They form the integration contract between:

    Person 2 (Frigate) → DetectionEvent
    Security Engine    → SecurityEventCandidate → Person 1 (Backend)

Coordinate system
-----------------
All bounding-box coordinates are in **pixel space** (origin at top-left).
If normalised (0–1) coordinates are received from Frigate, the caller must
scale them using ``frame_width`` / ``frame_height`` before constructing a
``BoundingBox``.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from enum import Enum
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator, model_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Classifiable security event types produced by the rule engine."""

    PERSON_DETECTED = "PERSON_DETECTED"
    ZONE_ENTRY = "ZONE_ENTRY"
    LOITERING = "LOITERING"
    MULTIPLE_PERSONS = "MULTIPLE_PERSONS"
    LINE_CROSSING = "LINE_CROSSING"


class Severity(str, Enum):
    """Severity levels ordered from least to most critical."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventState(str, Enum):
    """Lifecycle state of a detection event from the upstream source."""

    START = "start"
    UPDATE = "update"
    END = "end"


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

class Point(BaseModel):
    """A 2-D point in pixel coordinates."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def require_finite_coordinates(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("coordinates must be finite numbers")
        return value


class BoundingBox(BaseModel):
    """Axis-aligned bounding box in pixel coordinates (origin top-left).

    Attributes:
        x1: Left edge.
        y1: Top edge.
        x2: Right edge (must be >= x1).
        y2: Bottom edge (must be >= y1).
    """

    model_config = ConfigDict(frozen=True)

    x1: float = Field(ge=0)
    y1: float = Field(ge=0)
    x2: float = Field(ge=0)
    y2: float = Field(ge=0)

    @field_validator("x1", "y1", "x2", "y2")
    @classmethod
    def require_finite_coordinates(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("coordinates must be finite numbers")
        return value

    def center(self) -> Point:
        """Geometric center of the box."""
        return Point(x=(self.x1 + self.x2) / 2, y=(self.y1 + self.y2) / 2)

    def bottom_center(self) -> Point:
        """Bottom-center point — used as a person's ground position."""
        return Point(x=(self.x1 + self.x2) / 2, y=self.y2)

    def width(self) -> float:
        return self.x2 - self.x1

    def height(self) -> float:
        return self.y2 - self.y1

    def area(self) -> float:
        return self.width() * self.height()


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------

class Zone(BaseModel):
    """A restricted zone defined as a polygon for a specific camera.

    The polygon must have at least 3 vertices.  Coordinates are in pixel
    space matching the camera's frame dimensions.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    polygon: list[Point] = Field(min_length=3)
    enabled: bool = True
    severity: Severity = Severity.MEDIUM
    minimum_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    minimum_dwell_seconds: float = Field(default=0.0, ge=0.0)
    restricted_hours: list["OperatingWindow"] = Field(default_factory=list)
    timezone: str = "UTC"
    frame_width: int | None = Field(default=None, gt=0)
    frame_height: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_configuration(self) -> "Zone":
        if (self.frame_width is None) != (self.frame_height is None):
            raise ValueError("frame_width and frame_height must be configured together")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown zone timezone: {self.timezone}") from error
        from app.security.zones.geometry import is_valid_polygon

        if not is_valid_polygon(self.polygon):
            raise ValueError("polygon must be a finite, non-degenerate, non-self-intersecting polygon")
        return self

    def is_restricted_at(self, instant: datetime) -> bool:
        """Return whether configured restricted hours include this instant.

        Empty hours mean the zone is restricted at all times. Window start is
        inclusive and end is exclusive. Overnight windows are supported.
        """
        if not self.restricted_hours:
            return True
        local = instant.astimezone(ZoneInfo(self.timezone))
        weekday, clock = local.weekday(), local.timetz().replace(tzinfo=None)
        for window in self.restricted_hours:
            if window.start < window.end:
                if weekday in window.weekdays and window.start <= clock < window.end:
                    return True
            else:
                previous_day = (weekday - 1) % 7
                if ((weekday in window.weekdays and clock >= window.start)
                        or (previous_day in window.weekdays and clock < window.end)):
                    return True
        return False


class OperatingWindow(BaseModel):
    """Local recurring hours during which a zone is restricted."""

    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1)
    start: time
    end: time

    @model_validator(mode="after")
    def validate_window(self) -> "OperatingWindow":
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("weekdays must use ISO values from 0 (Monday) to 6 (Sunday)")
        if self.start == self.end:
            raise ValueError("operating window start and end cannot be equal")
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("operating window times must be local and timezone-naive")
        return self


# ---------------------------------------------------------------------------
# Tripwire
# ---------------------------------------------------------------------------

class Tripwire(BaseModel):
    """A virtual tripwire defined as a line segment for a specific camera.

    Coordinates are in pixel space matching the camera's frame dimensions.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    start_point: Point
    end_point: Point
    enabled: bool = True


# ---------------------------------------------------------------------------
# Input: DetectionEvent
# ---------------------------------------------------------------------------

class DetectionEvent(BaseModel):
    """Normalised detection from an upstream source (e.g. Frigate).

    This is the **input** to the Security Engine.  It is intentionally
    richer than ``app.domain.events.DetectionEvent`` (Person 2's model)
    because the security engine requires spatial data (bounding box,
    frame size) for zone and loitering analysis.

    A thin adapter can map Person 2's model to this one.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    camera_id: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    track_id: str | None = Field(default=None, min_length=1)
    object_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    bbox: BoundingBox | None = None
    frame_width: int | None = Field(default=None, gt=0)
    frame_height: int | None = Field(default=None, gt=0)
    event_state: EventState = EventState.START
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Rule output
# ---------------------------------------------------------------------------

class SecurityRuleResult(BaseModel):
    """Structured result produced by a single security rule.

    If ``triggered`` is False the remaining fields are still populated so
    that downstream code can log the reason a rule was *not* triggered.
    """

    model_config = ConfigDict(frozen=True)

    triggered: bool
    event_type: EventType
    severity: Severity
    reason: str
    camera_id: str
    object_id: str
    zone_id: str | None = None
    tripwire_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine output
# ---------------------------------------------------------------------------

class SecurityEventCandidate(BaseModel):
    """A security event candidate ready for persistence by Person 1.

    This is the **output** of the Security Engine.  Person 1 converts it
    into a database ``SecurityEvent`` record.
    """

    model_config = ConfigDict(frozen=True)

    event_type: EventType
    camera_id: str
    source_event_id: str
    object_id: str
    track_id: str | None = Field(default=None, min_length=1)
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    zone_id: str | None = None
    tripwire_id: str | None = None
    reason: str
    policy_version: str = "1"
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal context passed to rules
# ---------------------------------------------------------------------------

class SecurityContext(BaseModel):
    """Aggregated context passed to every rule during evaluation.

    Attributes:
        detection: The current detection being evaluated.
        active_detections: All *currently active* detections on the same
            camera (needed by ``MultiplePersonRule``).
        zones: Restricted zones configured for the detection's camera.
        current_time: Evaluation timestamp (allows deterministic testing).
        config: Reference to the active ``SecurityConfig`` (injected by
            the engine so that rules don't import global config).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    detection: DetectionEvent
    active_detections: list[DetectionEvent] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    tripwires: list[Tripwire] = Field(default_factory=list)
    current_time: datetime | None = None
