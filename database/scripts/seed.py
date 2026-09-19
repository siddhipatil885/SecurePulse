"""
Optional seed script for EDI-SecurePulse database.

Usage:
    python -m database.scripts.seed

This script inserts a dummy Camera and a dummy PERSON_DETECTED event.
Useful for providing initial data for the FastAPI developer to test against.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is importable
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.models import Camera, SecurityEvent, SessionLocal


def seed_database() -> None:
    """Insert initial seed data into the database."""
    print("Seeding database with sample data...")

    with SessionLocal() as db:
        # Check if we already have the seed camera to avoid duplicates
        camera = db.query(Camera).filter(Camera.frigate_camera_name == "cam1").first()
        if not camera:
            camera = Camera(
                name="Front Camera",
                frigate_camera_name="cam1",
                location="Main Entrance",
                enabled=True
            )
            db.add(camera)
            db.commit()
            print(f"[SUCCESS] Added Camera: {camera.name}")
        else:
            print(f"[INFO] Camera '{camera.name}' already exists.")

        # Create a sample PERSON_DETECTED event
        event = SecurityEvent(
            camera_id=camera.id,
            event_type="PERSON_DETECTED",
            object_type="person",
            confidence=0.94,
            timestamp=datetime.now(timezone.utc),
            severity="INFO",
            status="OPEN",
            frigate_event_id=f"seed_frigate_event_{datetime.now().timestamp()}"
        )
        db.add(event)
        db.commit()
        print(f"[SUCCESS] Added SecurityEvent: {event.event_type} (confidence: {event.confidence})")

    print("Seeding complete.")


if __name__ == "__main__":
    seed_database()
