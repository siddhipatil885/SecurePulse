"""
Database schema validation tests for EDI-SecurePulse.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from database.models import Camera, SecurityEvent, Evidence


def test_database_connection(db_session):
    """Test 1: Verify database connection works."""
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_camera_insertion(db_session):
    """Test 2: Verify camera insertion."""
    camera = Camera(
        name="Test Camera",
        frigate_camera_name="test_cam_1",
        location="Front Door"
    )
    db_session.add(camera)
    db_session.commit()

    assert camera.id is not None
    assert camera.enabled is True  # Default value
    assert camera.created_at is not None
    assert camera.updated_at is not None


def test_security_event_insertion(db_session):
    """Test 3: Verify security event insertion."""
    camera = Camera(name="Cam", frigate_camera_name="cam1")
    db_session.add(camera)
    db_session.commit()

    event = SecurityEvent(
        camera_id=camera.id,
        event_type="PERSON_DETECTED",
        object_type="person",
        confidence=0.85,
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        status="OPEN",
        frigate_event_id="test_frigate_123"
    )
    db_session.add(event)
    db_session.commit()

    assert event.id is not None
    assert event.camera_id == camera.id
    assert event.created_at is not None


def test_evidence_insertion(db_session):
    """Test 4: Verify evidence insertion."""
    camera = Camera(name="Cam", frigate_camera_name="cam1")
    db_session.add(camera)
    db_session.commit()

    event = SecurityEvent(
        camera_id=camera.id,
        event_type="PERSON_DETECTED",
        object_type="person",
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        status="OPEN"
    )
    db_session.add(event)
    db_session.commit()

    evidence = Evidence(
        event_id=event.id,
        type="snapshot",
        file_path="/media/frigate/clips/test.jpg"
    )
    db_session.add(evidence)
    db_session.commit()

    assert evidence.id is not None
    assert evidence.event_id == event.id


def test_relationships(db_session):
    """Test 5 & 6: Verify Camera -> Event -> Evidence relationships."""
    camera = Camera(name="Cam", frigate_camera_name="cam1")
    event = SecurityEvent(
        event_type="PERSON_DETECTED",
        object_type="person",
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        status="OPEN"
    )
    evidence = Evidence(type="snapshot", file_path="/tmp/test.jpg")
    
    # Append through relationships
    event.evidence_items.append(evidence)
    camera.events.append(event)
    
    db_session.add(camera)
    db_session.commit()

    # Query from DB to verify
    stmt = select(Camera).where(Camera.id == camera.id)
    saved_camera = db_session.execute(stmt).scalar_one()
    
    assert len(saved_camera.events) == 1
    saved_event = saved_camera.events[0]
    assert saved_event.event_type == "PERSON_DETECTED"
    
    assert len(saved_event.evidence_items) == 1
    assert saved_event.evidence_items[0].type == "snapshot"


def test_invalid_camera_fk_rejection(db_session):
    """Test 7: Verify invalid camera foreign key rejection."""
    event = SecurityEvent(
        camera_id=999999,  # Non-existent ID
        event_type="PERSON_DETECTED",
        object_type="person",
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        status="OPEN"
    )
    db_session.add(event)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_confidence_less_than_zero_rejection(db_session):
    """Test 8: Verify confidence < 0 rejection."""
    camera = Camera(name="Cam", frigate_camera_name="cam1")
    db_session.add(camera)
    db_session.commit()

    event = SecurityEvent(
        camera_id=camera.id,
        event_type="PERSON_DETECTED",
        object_type="person",
        confidence=-0.1,  # Invalid
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        status="OPEN"
    )
    db_session.add(event)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_confidence_greater_than_one_rejection(db_session):
    """Test 9: Verify confidence > 1 rejection."""
    camera = Camera(name="Cam", frigate_camera_name="cam1")
    db_session.add(camera)
    db_session.commit()

    event = SecurityEvent(
        camera_id=camera.id,
        event_type="PERSON_DETECTED",
        object_type="person",
        confidence=1.1,  # Invalid
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        status="OPEN"
    )
    db_session.add(event)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_required_fields(db_session):
    """Test 10: Verify required fields rejection."""
    # Camera missing required name
    camera = Camera(frigate_camera_name="cam1")
    db_session.add(camera)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_event_querying(db_session):
    """Test 11: Verify event querying via indexes (camera_id, timestamp)."""
    camera = Camera(name="Cam", frigate_camera_name="cam1")
    db_session.add(camera)
    db_session.commit()

    now = datetime.now(timezone.utc)
    event1 = SecurityEvent(
        camera_id=camera.id,
        event_type="PERSON_DETECTED",
        object_type="person",
        timestamp=now,
        severity="INFO",
        status="OPEN"
    )
    db_session.add(event1)
    db_session.commit()

    # Query recent events for this camera
    stmt = select(SecurityEvent).where(
        SecurityEvent.camera_id == camera.id
    ).order_by(SecurityEvent.timestamp.desc())
    
    results = db_session.execute(stmt).scalars().all()
    assert len(results) >= 1
    assert results[0].camera_id == camera.id


def test_duplicate_frigate_event_behavior(db_session):
    """Test 12: Verify duplicate Frigate event ID rejection (Unique constraint)."""
    camera = Camera(name="Cam", frigate_camera_name="cam1")
    db_session.add(camera)
    db_session.commit()

    event1 = SecurityEvent(
        camera_id=camera.id,
        event_type="PERSON_DETECTED",
        object_type="person",
        timestamp=datetime.now(timezone.utc),
        severity="INFO",
        status="OPEN",
        frigate_event_id="unique_frigate_id_1"
    )
    db_session.add(event1)
    db_session.commit()

    # Attempt to insert same frigate_event_id
    event2 = SecurityEvent(
        camera_id=camera.id,
        event_type="VEHICLE_DETECTED",
        object_type="car",
        timestamp=datetime.now(timezone.utc),
        severity="WARNING",
        status="OPEN",
        frigate_event_id="unique_frigate_id_1"
    )
    db_session.add(event2)
    with pytest.raises(IntegrityError):
        db_session.commit()
