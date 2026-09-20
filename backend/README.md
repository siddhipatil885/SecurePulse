# EDI-SecurePulse Backend

Phase 1 provides the FastAPI application foundation, typed environment settings, logging, safe exception responses, and health endpoints. Phase 2 adds async PostgreSQL access through SQLAlchemy, persistence models, repositories, and Alembic metadata support. Phase 3 adds a Frigate MQTT adapter that normalizes detection events and survives temporary broker failures. Phase 4 adds the transactional event processor with camera mapping and idempotency. Phase 5 adds the typed security-engine contract, HTTP adapter, decision validation, and configurable failure fallback. Phase 6 adds versioned camera and security-event read APIs with filtering, pagination, and structured errors. Phase 7 adds in-process real-time publishing and a WebSocket stream. Phase 8 adds JWT authentication and scope-based authorization.

## Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The liveness endpoint is available at `http://localhost:8000/health`. Readiness checks PostgreSQL and returns `503` when the database is unavailable; Frigate and security-engine checks remain explicit `not_checked` placeholders until their service integration phases.

Frigate events are consumed from `FRIGATE_MQTT_TOPIC` (default `frigate/events`). The adapter drops malformed payloads, uses Frigate's stable event ID, and reconnects with bounded Paho backoff after broker interruptions.

The `EventProcessor` maps the normalized camera identifier to an enabled camera, ignores duplicate Frigate event IDs, and stores new detections as `UNCLASSIFIED` until the Phase 5 security engine returns a decision.

The security engine receives a typed context and returns an event type, score, severity, and optional reason. Set `SECURITY_ENGINE_FAILURE_MODE=STORE_UNCLASSIFIED` to retain observations without inventing a risk classification, or `REJECT` to avoid storing events when the engine is unavailable.

REST endpoints are available under `/api/v1`: `GET /cameras`, `GET /cameras/{camera_id}`, `GET /events`, and `GET /events/{event_id}`. Event listing supports `camera_id`, `event_type`, `severity`, `start_time`, `end_time`, `page`, and `page_size`.

Committed events are published to `/api/v1/events/stream` as WebSocket messages with `type: security_event`. The current publisher is process-local and intentionally avoids introducing Redis or another event broker at this edge-prototype stage.

Set `AUTH_ENABLED=true` and configure `JWT_SECRET` before exposing the API outside a trusted local environment. Protected HTTP APIs require a bearer JWT with `sub`, `exp`, and `read` scope claims. WebSocket clients may use an `Authorization: Bearer` header; browser clients may use `access_token` during the connection handshake.

## Test

```powershell
pytest
```

## Architecture

```text
Camera -> MediaMTX -> Frigate -> MQTT adapter -> EventProcessor
											 -> Security Engine
											 -> PostgreSQL / Cloud SQL
											 -> REST API and WebSocket stream
```

The backend keeps Frigate parsing, security decisions, persistence, and HTTP delivery behind separate adapters and services. Detection observations are not security classifications; an unavailable security engine produces `UNCLASSIFIED` events by default.

## Database migrations

Configure `DATABASE_URL` with a PostgreSQL URL, then run:

```powershell
alembic upgrade head
```

The application uses `postgresql+asyncpg` for runtime access. Alembic automatically converts that URL to the synchronous `psycopg2` driver for migrations.

## Troubleshooting

- `GET /health/ready` returns `503`: verify `DATABASE_URL` and PostgreSQL/Cloud SQL network access.
- No detection events: verify Frigate publishes to MQTT and that `MQTT_HOST`, `MQTT_PORT`, and `FRIGATE_MQTT_TOPIC` match the broker.
- Events are `UNCLASSIFIED`: the security engine is unavailable or `SECURITY_ENGINE_FAILURE_MODE=STORE_UNCLASSIFIED` is active.
- Duplicate events are ignored by the stable Frigate event ID and database uniqueness constraint.
- Protected API calls return `401`: send a JWT bearer token with `sub`, `exp`, and `read` scope claims.
- Cloud SQL connection failures: verify authorized networking, database credentials, TLS policy, and the PostgreSQL URL scheme.

## Planned phases

1. Foundation: FastAPI, configuration, logging, health, and readiness.
2. Database: SQLAlchemy, PostgreSQL/Cloud SQL connectivity, models, and repositories.
3. Frigate adapter: normalized detection events and resilient connection handling.
4. Event processing: validation, camera lookup, deduplication, and persistence.
5. Security engine: adapter interface, decisions, and failure handling.
6. REST API: cameras, events, filtering, pagination, and structured errors.
7. Real-time delivery: WebSocket or SSE event publishing.
8. Security and reliability: authentication, authorization, and hardening.
9. Verification: unit, integration, end-to-end tests, migrations, and documentation.