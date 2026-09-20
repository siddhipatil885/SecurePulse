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

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Classifiable security event types produced by the rule engine."""

    PERSON_DETECTED = "PERSON_DETECTED"
    ZONE_ENTRY = "ZONE_ENTRY"
    LOITERING = "LOITERING"
    MULTIPLE_PERSONS = "MULTIPLE_PERSONS"


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


class BoundingBox(BaseModel):
    """Axis-aligned bounding box in pixel coordinates (origin top-left).

    Attributes:
        x1: Left edge.
        y1: Top edge.
        x2: Right edge (must be >= x1).
        y2: Bottom edge (must be >= y1).
    """

    model_config = ConfigDict(frozen=True)

    x1: float
    y1: float
    x2: float = Field(ge=0)
    y2: float = Field(ge=0)

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
    object_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    bbox: BoundingBox | None = None
    frame_width: int | None = Field(default=None, gt=0)
    frame_height: int | None = Field(default=None, gt=0)
    event_state: EventState = EventState.START
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime
    zone_id: str | None = None
    reason: str
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
    current_time: datetime | None = None
