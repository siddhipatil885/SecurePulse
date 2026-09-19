"""
EDI-SecurePulse Database Layer
==============================

SQLAlchemy 2.x models for the SecurePulse security surveillance system.

Models:
    - Camera: CCTV camera registration
    - SecurityEvent: Detected security events (e.g., PERSON_DETECTED)
    - Evidence: File references (snapshots, clips) attached to events
"""

from database.models.base import Base, engine, SessionLocal, get_db_url
from database.models.camera import Camera
from database.models.security_event import SecurityEvent
from database.models.evidence import Evidence

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db_url",
    "Camera",
    "SecurityEvent",
    "Evidence",
]
