"""
Shared fixtures for the Security Intelligence test suite.

Provides reusable factory functions for creating mock detections,
zones, and engine instances — so tests can run without Frigate,
databases, or any network services.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import (
    BoundingBox,
    DetectionEvent,
    EventState,
    Point,
    Zone,
)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

DEFAULT_CAMERA = "cam1"
DEFAULT_TIMESTAMP = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
DEFAULT_BBOX = BoundingBox(x1=100, y1=100, x2=300, y2=500)


# ---------------------------------------------------------------------------
# Detection factories
# ---------------------------------------------------------------------------


def make_detection(
    *,
    source: str = "frigate",
    source_event_id: str = "evt-001",
    camera_id: str = DEFAULT_CAMERA,
    object_id: str = "person-1",
    object_type: str = "person",
    confidence: float = 0.92,
    timestamp: datetime = DEFAULT_TIMESTAMP,
    bbox: BoundingBox | None = DEFAULT_BBOX,
    frame_width: int | None = 1920,
    frame_height: int | None = 1080,
    event_state: EventState = EventState.START,
    metadata: dict | None = None,
) -> DetectionEvent:
    """Create a ``DetectionEvent`` with sensible defaults."""
    return DetectionEvent(
        source=source,
        source_event_id=source_event_id,
        camera_id=camera_id,
        object_id=object_id,
        object_type=object_type,
        confidence=confidence,
        timestamp=timestamp,
        bbox=bbox,
        frame_width=frame_width,
        frame_height=frame_height,
        event_state=event_state,
        metadata=metadata or {},
    )


def make_car_detection(**kwargs) -> DetectionEvent:
    """Shorthand for a car detection."""
    defaults = {"object_type": "car", "object_id": "car-1"}
    defaults.update(kwargs)
    return make_detection(**defaults)


def make_dog_detection(**kwargs) -> DetectionEvent:
    """Shorthand for a dog detection."""
    defaults = {"object_type": "dog", "object_id": "dog-1"}
    defaults.update(kwargs)
    return make_detection(**defaults)


# ---------------------------------------------------------------------------
# Zone factories
# ---------------------------------------------------------------------------

# A simple rectangular zone in the centre of a 1920 × 1080 frame.
SIMPLE_ZONE_POLYGON = [
    Point(x=400, y=200),
    Point(x=800, y=200),
    Point(x=800, y=600),
    Point(x=400, y=600),
]


def make_zone(
    *,
    zone_id: str = "server-room",
    name: str = "Server Room",
    camera_id: str = DEFAULT_CAMERA,
    polygon: list[Point] | None = None,
    enabled: bool = True,
) -> Zone:
    """Create a ``Zone`` with sensible defaults."""
    return Zone(
        id=zone_id,
        name=name,
        camera_id=camera_id,
        polygon=polygon or list(SIMPLE_ZONE_POLYGON),
        enabled=enabled,
    )


# ---------------------------------------------------------------------------
# BoundingBox helpers
# ---------------------------------------------------------------------------


def bbox_inside_zone() -> BoundingBox:
    """Return a bbox whose bottom-center is inside ``SIMPLE_ZONE_POLYGON``."""
    # Bottom-center will be at (600, 500) — inside [400,800] × [200,600]
    return BoundingBox(x1=500, y1=300, x2=700, y2=500)


def bbox_outside_zone() -> BoundingBox:
    """Return a bbox whose bottom-center is outside ``SIMPLE_ZONE_POLYGON``."""
    # Bottom-center will be at (200, 500) — x=200 is outside [400,800]
    return BoundingBox(x1=100, y1=300, x2=300, y2=500)


# ---------------------------------------------------------------------------
# Engine / config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config() -> SecurityConfig:
    return SecurityConfig()


@pytest.fixture
def config_with_zone() -> SecurityConfig:
    return SecurityConfig(zones=[make_zone()])


@pytest.fixture
def engine(default_config: SecurityConfig) -> SecurityEngine:
    return SecurityEngine(config=default_config)


@pytest.fixture
def engine_with_zone(config_with_zone: SecurityConfig) -> SecurityEngine:
    return SecurityEngine(config=config_with_zone)
