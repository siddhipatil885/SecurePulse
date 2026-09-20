# Backend Contract: Database Layer

This document outlines the database models and expectations for the FastAPI backend integration. The database layer uses SQLAlchemy 2.x with async PostgreSQL access via `asyncpg`.

## Accessing the Database

The database session is managed through FastAPI dependencies. Sessions are request-scoped and automatically rolled back on failure.

```python
from app.database.database import get_db_session
from app.models import Camera, SecurityEvent, Evidence

# FastAPI dependency injection handles sessions automatically.
# See app/core/dependencies.py for service factories.
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
| `confidence` | `float` | Detection confidence score | Yes |
| `timestamp` | `datetime` | Timezone-aware UTC timestamp | Yes |
| `severity` | `str` | E.g. `"INFO"`, `"WARNING"`, `"CRITICAL"`, `"UNCLASSIFIED"` | Yes |
| `status` | `str` | Lifecycle status (e.g. `"OPEN"`, `"UNCLASSIFIED"`, `"RESOLVED"`) | Yes |
| `score` | `int` | Security engine risk score (0–100) | No |
| `zone` | `str` | Camera zone breached | No |
| `frigate_event_id` | `str` | Frigate ID, used for deduping (unique constraint) | No |
| `reason` | `str` | Security engine classification reason | No |
| `event_metadata` | `dict` | Additional JSON payload (maps to `metadata` column) | Yes |
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
> The `frigate_event_id` column has a unique constraint. If you try to `INSERT` an event with a `frigate_event_id` that already exists, it will raise an `IntegrityError`. 
> The `EventProcessor` handles this with idempotent duplicate detection.

### 3. `Evidence`
File references for event media.

| Field | Type | Description | Required |
|---|---|---|---|
| `id` | `int` | Primary Key | Yes |
| `event_id` | `int` | Foreign Key to `security_events.id` | Yes |
| `type` | `str` | E.g., `"snapshot"`, `"clip"` | Yes |
| `file_path` | `str` | File storage path or URL | Yes |
| `timestamp` | `datetime` | Timezone-aware UTC timestamp | Yes |

> [!WARNING]
> **No Video Binaries in Postgres**: Never store raw video or image bytes in the database. Use the `evidence` table to store references/paths to file storage.

## Relationships
- `Camera.security_events`: 1-to-N relationship with `SecurityEvent`.
- `SecurityEvent.evidence`: 1-to-N relationship with `Evidence` (Cascade Delete enabled).
