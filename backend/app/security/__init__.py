"""
Security Intelligence Module
=============================

Standalone rule engine that evaluates normalized detection events against
configurable security rules (person detection, zone entry, loitering,
multiple-person detection) and produces security event candidates.

This module is deliberately decoupled from:
- Database / SQLAlchemy (Person 1's responsibility)
- Frigate / MQTT internals (Person 2's responsibility)
- Dashboard / alert providers (Person 4's responsibility)

Integration:
    Person 2 → DetectionEvent → SecurityEngine → SecurityEventCandidate → Person 1
"""

from app.security.engine import SecurityEngine
from app.security.models import (
    BoundingBox,
    DetectionEvent,
    EventState,
    EventType,
    Point,
    SecurityContext,
    SecurityEventCandidate,
    SecurityRuleResult,
    Severity,
    Zone,
)
from app.security.config import SecurityConfig

__all__ = [
    "SecurityEngine",
    "SecurityConfig",
    "BoundingBox",
    "DetectionEvent",
    "EventState",
    "EventType",
    "Point",
    "SecurityContext",
    "SecurityEventCandidate",
    "SecurityRuleResult",
    "Severity",
    "Zone",
]
