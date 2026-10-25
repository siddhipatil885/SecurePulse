# Backend and API Audit

## Conclusion

There is no backend application. `ai-cctv/backend/requirements.txt:1-9` lists FastAPI, Uvicorn, Pydantic, SQLAlchemy, two PostgreSQL drivers, HTTPX, MQTT, and pytest, but the repository has no Python module beneath `backend/app` beyond `.gitkeep` placeholders. Dependency declaration is not implementation.

## Application structure

| Expected layer | Repository evidence | Status |
|---|---|---|
| ASGI entry point | No `main.py`, app factory, or `FastAPI()` call found | NOT IMPLEMENTED |
| Routers | Empty `alerts`, `cameras`, `health`, `incidents`, `zones` directories | NOT IMPLEMENTED |
| MQTT adapter | Empty `backend/app/mqtt/.gitkeep:1` | NOT IMPLEMENTED |
| Event schemas/normalization | Empty `events/.gitkeep:1`; Pydantic declared only | NOT IMPLEMENTED |
| Detection/security service | Empty `detection/.gitkeep:1` | NOT IMPLEMENTED |
| Repositories/database session | Empty `database/.gitkeep:1`; SQL packages declared | NOT IMPLEMENTED |
| Configuration | Empty `config/.gitkeep:1` | NOT IMPLEMENTED |
| Middleware/error handling/logging | No application source | NOT IMPLEMENTED |
| Authentication/authorization | No source or dependency specific to password/JWT/session handling | NOT IMPLEMENTED |
| WebSocket/SSE/background tasks | No source | NOT IMPLEMENTED |
| Rate limiting/CORS | No source/configuration | NOT IMPLEMENTED |
| OpenAPI documentation | Would be provided by FastAPI only after an app exists | NOT IMPLEMENTED |

## Complete API inventory

No API endpoints exist.

| Method | Route | Purpose | Authentication | Request Schema | Response Schema | Implementation Status | Source File |
|---|---|---|---|---|---|---|---|
| — | — | No routes found | — | — | — | NOT IMPLEMENTED | No router/application file exists |

## Capability assessment

| Capability | Status | Evidence / missing layers |
|---|---|---|
| Property management | NOT IMPLEMENTED | No module, route, schema, model, or table |
| Camera registration | NOT IMPLEMENTED | Empty camera placeholder only |
| Camera status | NOT IMPLEMENTED | Frigate has a configured camera, but no backend health/status adapter |
| Security incident creation/retrieval/update | NOT IMPLEMENTED | Empty incident placeholder only |
| Real-time alerts | NOT IMPLEMENTED | No WebSocket/SSE/broker-to-client bridge |
| User management | NOT IMPLEMENTED | No user model/routes/auth |
| Property-owner access | NOT IMPLEMENTED | No ownership model or authorization |
| Marshal onboarding/assignment | NOT IMPLEMENTED | No marshal code or schema |
| Incident acknowledgment | NOT IMPLEMENTED | No endpoint/state model |
| Emergency escalation | NOT IMPLEMENTED | No workflow/timer/job runner |
| Incident resolution | NOT IMPLEMENTED | No endpoint/state transition/history |
| Evidence retrieval | NOT IMPLEMENTED | Frigate media config exists, but no authorized application access |

## Router → service → repository → database traces

No such trace can be constructed. The only executable data path is MQTT callback → JSON decoding → stdout (`ai-cctv/tests/test_mqtt_subscriber.py:31-41`). It does not import or call a backend module.

## Contract gaps that must be settled first

The next implementation should version and test explicit contracts for:

- Frigate event envelope → normalized source event.
- Normalized event → security candidate → incident.
- Incident summary/detail/evidence/status-history responses.
- Camera registration/status/live-stream metadata.
- Authenticated realtime event envelope with sequence/replay cursor.
- Marshal offer, acceptance/rejection, response-status, and resolution commands.

Every mutating command needs authenticated actor identity, property/tenant authorization, an idempotency strategy, validated state transitions, and auditable before/after state. These are requirements derived from absent controls, not claims about current code.

## Recommended minimum API surface

This is proposed work, not current inventory:

- `POST /v1/auth/login`, token/session refresh and logout.
- `GET/POST /v1/properties`, `GET/POST /v1/properties/{id}/cameras`.
- `GET /v1/cameras/{id}/status` and authorized live-view metadata.
- `GET/POST /v1/incidents`, `GET/PATCH /v1/incidents/{id}` with transition commands rather than arbitrary status writes.
- `GET /v1/incidents/{id}/evidence` using short-lived authorized URLs or streamed access.
- `GET /v1/events/stream` (authenticated SSE/WebSocket) with replay cursor.
- Marshal profile/availability/assignment endpoints and explicit accept/reject/arrive/resolve commands.
- `/health/live` and dependency-aware `/health/ready`.

Acceptance tests for this proposed surface are specified in `12-development-roadmap.md`.

