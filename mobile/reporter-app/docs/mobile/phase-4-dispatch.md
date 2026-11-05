# Phase 4 — Dispatch integration

## Status

**Partially complete; implemented but not fully validated.**

The existing server-controlled marshal offer/accept/decline/expire/cancel state machine now supports both automated security events and reporter-created incidents. Reporter incident details expose the latest assignment only when a real assignment exists.

## Implemented

- Additive `assignments.reporter_incident_id` foreign key.
- Database check constraint requiring exactly one assignment source.
- Existing dispatcher offer creation accepts either `incident_id` or `reporter_incident_id`.
- Existing idempotency, availability freshness, capacity, compare-and-swap response, timeout, cancellation, audit event, and notification-outbox behavior is preserved.
- Reporter-owned incident detail includes assignment status, timestamps, version, and marshal profile identifier.
- No ETA, marshal identity, location, or “help is coming” claim is shown without a real assignment.

## API changes

- `POST /api/v1/dispatch/offers`: provide exactly one of `incident_id` or `reporter_incident_id`; existing dispatcher/owner authorization remains required.
- `POST /api/v1/dispatch/offers/{id}/accept` and `/decline`: marshal-only compare-and-swap response.
- `POST /api/v1/dispatch/offers/{id}/expire` and `/cancel`: authorized dispatcher operations.
- `GET /api/v1/reporter/incidents/{id}`: returns optional `dispatch` state for the authenticated incident owner.

## Database

Migration `0014_reporter_dispatch_link`:

- Makes legacy `assignments.security_event_id` nullable.
- Adds `assignments.reporter_incident_id`.
- Adds a foreign key, source check constraint, and lookup index.

Apply with:

```sh
python -m alembic upgrade head
```

## Validation

The existing dispatch suite must continue passing, plus the reporter-incident offer test. Physical devices, production PostgreSQL, real marshal accounts, and notification-provider delivery remain unverified.

## Explicit blocker

There is no configured marshal-facing mobile client or automatic eligible-marshal selection/dispatch worker for reporter incidents in this repository. A dispatcher or owner must select an eligible marshal through the existing authorized API. The Reporter App does not assign or impersonate marshals.

## Next phase

Phase 5 should add device-token registration and backend notification delivery only after a real provider configuration and notification policy are established.
