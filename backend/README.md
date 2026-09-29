# SecurePulse Backend

This directory contains the active FastAPI backend for SecurePulse.

For the full architecture, feature overview, and project setup, see the canonical project guide in [../README.md](../README.md).

## Backend-specific setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

## Backend responsibilities

- Frigate MQTT ingestion and normalization
- Async PostgreSQL persistence with SQLAlchemy
- Event deduplication and lifecycle handling
- Security rule evaluation and severity resolution
- Camera and event REST APIs
- WebSocket real-time event streaming
- Anonymous Frigate-native person-track projection and bounding-box streaming
- JWT auth and scope validation

## Required environment

Use the values in [.env.example](.env.example) as the backend template. At minimum, configure:

- `DATABASE_URL`
- `FRIGATE_URL`
- `MQTT_HOST` and `MQTT_PORT`
- `FRIGATE_MQTT_TOPIC`
- `SECURITY_ENGINE_URL`
- `AUTH_ENABLED`
- `JWT_SECRET` when auth is enabled

## Live person tracking contract

Frigate remains the sole object detector and tracker. The backend does not run
a second detector, does not create face embeddings, and does not infer real
world identities. Its MQTT adapter converts Frigate's stable object event ID
into a temporary `person_track_<frigate-id>` session.

- `GET /api/v1/tracks` returns active tracks, grouped by backend camera ID.
- The existing WebSocket additionally sends `person_tracks` messages whenever
  a track is created, updated, temporarily lost, or expires.
- Boxes are normalised (`x`, `y`, `width`, `height` in the 0–1 range) before
  being sent to the browser. `frame_width` and `frame_height` are retained for
  coordinate validation.
- Frigate `new`/`update` messages preserve one track; `end` puts it into a
  configurable grace period (`TRACKING_LOST_TRACK_TIMEOUT_SECONDS`, default
  3 seconds) before it is removed.
- Security-event database idempotency is keyed by the Frigate source ID. A
  camera-wide cooldown is deliberately not used to suppress a second person.

Set `SECURITY_ENGINE_SUPPORTS_TRACKING=true` only after the separately deployed
security engine accepts the optional `track_id`, normalized `bounding_box`, and
`active_person_count` fields. The default preserves the existing engine's JSON
contract; tracking and the dashboard work independently of that opt-in.

`face_visible` is currently always `null` because Frigate does not emit that
signal. It is reserved only as an evidence-quality field; it must never hold a
name, facial embedding, or permanent biometric identity.

## Tests

```powershell
pytest
```

## Database migrations

```powershell
alembic upgrade head
```

This backend is the authoritative runtime implementation for the project. Keep the root README as the single source of truth for high-level project documentation.
