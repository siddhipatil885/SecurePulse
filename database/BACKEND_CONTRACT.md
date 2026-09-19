# Backend Contract: Database Layer

This document outlines the database models and expectations for the FastAPI backend integration. The database layer uses SQLAlchemy 2.x and Psycopg 3.

## Accessing the Database

The database session factory and engine are exported from the `database.models` package.

```python
from database.models import SessionLocal, engine
from database.models import Camera, SecurityEvent, Evidence

# Typical usage in a FastAPI dependency:
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## ORM Models

### 1. `Camera`
Represents a physical CCTV camera stream.

| Field | Type | Description | Required |
|---|---|---|---|
| `id` | `int` | Primary Key | Yes |
| `name` | `str` | Display name (e.g. "Front Door") | Yes |
| `frigate_camera_name` | `str` | Camera identifier from Frigate (e.g. "cam1") | Yes |
| `location` | `str` | Physical location description | No |
| `enabled` | `bool` | Active status (Default: True) | Yes |
| `created_at` / `updated_at` | `datetime` | Timezone-aware UTC timestamps | Auto |

### 2. `SecurityEvent`
Represents a detected threat/event.

| Field | Type | Description | Required |
|---|---|---|---|
| `id` | `int` | Primary Key | Yes |
| `camera_id` | `int` | Foreign Key to `cameras.id` | Yes |
| `event_type` | `str` | Type of event (e.g. `"PERSON_DETECTED"`) | Yes |
| `object_type` | `str` | Object detected (e.g. `"person"`) | Yes |
| `confidence` | `float` | Score between 0.0 and 1.0 (Checked in DB) | No |
| `timestamp` | `datetime` | Timezone-aware UTC timestamp | Yes |
| `severity` | `str` | E.g. `"INFO"`, `"WARNING"`, `"CRITICAL"` | Yes |
| `status` | `str` | Lifecycle status (e.g. `"OPEN"`, `"RESOLVED"`) | Yes |
| `zone` | `str` | Camera zone breached | No |
| `frigate_event_id` | `str` | Frigate ID, used for deduping | No |
| `metadata_` | `dict` | Additional JSON payload (maps to `metadata` column) | No |
| `created_at` | `datetime` | Timezone-aware UTC timestamp | Auto |

**Example Event Creation Payload:**
```json
{
    "camera_id": 1,
    "event_type": "PERSON_DETECTED",
    "object_type": "person",
    "confidence": 0.94,
    "timestamp": "2026-09-19T10:00:00Z",
    "severity": "INFO",
    "status": "OPEN",
    "frigate_event_id": "1695123456.789123-abc123"
}
```

> [!NOTE]
> **Frigate Event Lifecycle Strategy**
> The `frigate_event_id` column has a partial unique index. If you try to `INSERT` an event with a `frigate_event_id` that already exists, it will raise an `IntegrityError`. 
> For Frigate updates (where the event is "ongoing"), use an SQLAlchemy UPSERT (ON CONFLICT DO UPDATE) or query/update the existing record.

### 3. `Evidence`
File references for event media.

| Field | Type | Description | Required |
|---|---|---|---|
| `id` | `int` | Primary Key | Yes |
| `event_id` | `int` | Foreign Key to `security_events.id` | Yes |
| `type` | `str` | E.g., `"snapshot"`, `"clip"` | Yes |
| `file_path` | `str` | File storage path or URL | Yes |
| `created_at` | `datetime` | Timezone-aware UTC timestamp | Auto |

## Relationships
- `Camera.events`: 1-to-N relationship with `SecurityEvent` (Cascade Delete enabled).
- `SecurityEvent.evidence_items`: 1-to-N relationship with `Evidence` (Cascade Delete enabled).
