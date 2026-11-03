# SecurePulse Backend

This directory contains the active FastAPI backend for SecurePulse.

For the full architecture, feature overview, and project setup, see the canonical project guide in [PROJECT_README.md](PROJECT_README.md).

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
- The base detection record is keyed by the Frigate source ID, while derived
  security incidents use a separate track/event/timestamp key. A camera-wide
  cooldown is deliberately not used to suppress a second person.

Set `SECURITY_ENGINE_SUPPORTS_TRACKING=true` only after the separately deployed
security engine accepts the optional `track_id`, normalized `bounding_box`, and
`active_person_count` fields. The default preserves the existing engine's JSON
contract; tracking and the dashboard work independently of that opt-in.

Set `USE_LOCAL_SECURITY_ENGINE=true` to use the built-in rule adapter instead
of the separate HTTP service. It always receives the anonymous tracking
extension and converts normalized UI boxes back to source-frame pixels before
evaluating zones and tripwires.

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

## Marshal dispatch persistence

The tenancy migration introduced property-scoped marshal profiles, assignments,
assignment events, a durable notification outbox, and delivery-attempt receipts.
Migration `0011_dispatch_orchestration` completes their worker/idempotency fields
and enforces append-only assignment events. A `SecurityEvent` is the incident anchor.
Only property `owner`/`dispatcher` memberships may create, expire, or cancel an
offer; only its assigned `marshal` may accept or decline it. Marshal eligibility
requires an enabled account, marshal membership and service mapping, on-duty and
available flags observed within five minutes, and unused assignment capacity.

Dispatch endpoints are under `/api/v1/dispatch`:

- `PUT /marshal/availability`
- `GET /eligible-marshals?property_id=...`
- `POST /offers`
- `POST /offers/{id}/accept`, `/decline`, `/expire`, or `/cancel`

Offer creation writes the offer, history entry, and notification intent in one
transaction. PostgreSQL row locks plus a partial unique index permit at most one
`OFFERED` or `ACCEPTED` record per incident. `TimeoutEscalator` and
`NotificationDispatcher` in `app/services/dispatch_workers.py` are scheduler-
neutral `run_once` workers; deployment code should invoke them from its existing
job runner. Provider calls occur after the outbox claim transaction commits, and
each result is persisted as an attempt receipt in a new transaction.

Provision marshal accounts with `--role marshal`; optional
`--service-area` and `--max-active-assignments` arguments initialize eligibility.
New marshals start off duty and unavailable and must publish availability before
they can receive an offer.

This backend is the authoritative runtime implementation for the project. Keep the root README as the single source of truth for high-level project documentation.
