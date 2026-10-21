# SecurePulse Backend Domain Contract v1

## Safety and deployment status

Migrations `0005_tenancy_operations`, `0006_repair_json`,
`0007_align_legacy`, and `0008_camera_zones_health` were applied to the
authorized Neon target on 2026-10-20.
The upgrade preserved the three camera rows and one security-event row,
backfilled tenant ownership, repaired legacy JSON nullability, and aligned the
live schema with SQLAlchemy metadata. `alembic check` reported no pending
upgrade operations after validation.

## Ownership model

```text
User --< PropertyMembership >-- Property --< Camera
                                      |        |
                                      |        +--< SourceEventReceipt
                                      |        +--< SecurityEvent (incident)
                                      |                    |
                                      |                    +--< Evidence
                                      |                    +--< IncidentStatusHistory
                                      |                    +--< NotificationOutbox
                                      |                    +--< Assignment
                                      +--< AuditRecord
```

- A signed access token supplies `property_ids` as a list of positive integer
  IDs. Resource queries are filtered by those IDs.
- Auth-disabled local development uses an explicit unrestricted principal.
- Missing or unauthorized resources return the same not-found response, which
  avoids confirming the existence of another property's object.
- `PropertyMembership` is the durable source for application membership. The
  identity/token issuer must derive or validate its property claims against
  active memberships before production deployment.

## Source-event receipt identity

A receipt is unique by:

```text
(source_system, source_event_id, event_phase, revision)
```

For Frigate, `event_phase` is `new`, `update`, or `end`. The normalized
observation time is stored separately from receipt time. A receipt may point to
the security event/incident produced or updated by that message. Replaying the
same receipt identity is idempotent.

## Camera operations

- A zone is owned by exactly one camera and is unique by
  `(camera_id, external_id)`. Its coordinates remain JSON so Engineers 1 and 3
  can agree the frame-coordinate contract without a destructive schema rewrite.
- Camera health is append-only and timestamped. Camera list/detail responses
  include `health_status` and `health_observed_at` from the latest observation;
  both are `null` until an adapter records health.
- Tenant ownership is derived through the camera foreign key, avoiding a second
  property identifier that could disagree with the camera's property.

## Incident transaction

For a new actionable event, one database transaction writes:

1. the source-event receipt;
2. the security event/incident;
3. initial append-only status history;
4. evidence metadata when available;
5. an operator alert for high/critical severity; and
6. an `INCIDENT_OPENED` notification-outbox intent.

Publishing to the in-memory realtime channel happens only after commit.
Database uniqueness remains the concurrency boundary.

## Incident commands

`POST /api/v1/incidents/{incident_id}/commands` accepts an authenticated
`write` principal and one of these intent-specific commands:

| Command | Allowed current states | New state |
|---|---|---|
| `acknowledge` | `OPEN` | `ACKNOWLEDGED` |
| `resolve` | `OPEN`, `ACKNOWLEDGED` | `RESOLVED` |
| `dismiss` | `OPEN`, `ACKNOWLEDGED`, `UNCLASSIFIED` | `DISMISSED` |
| `reopen` | `RESOLVED`, `DISMISSED`, `CLOSED` | `OPEN` |

Each successful command locks the incident row and writes status history plus
an audit record in the same transaction. Invalid transitions return HTTP 409.
Commands are limited per authenticated subject by
`MUTATION_RATE_LIMIT_PER_MINUTE` (default 30); production deployments with
multiple API instances must also apply a shared gateway limit.

Read endpoints:

- `GET /api/v1/incidents/{id}/history`
- `GET /api/v1/incidents/{id}/evidence`
- Existing camera and event endpoints remain available and are property-scoped.

Camera lists preserve their array response shape and accept `page` (default 1)
and `page_size` (default 50, maximum 100), sorted by camera ID. Incident lists
accept camera, event type, severity, and timezone-aware start/end filters. Event
ordering uses timestamp then ID for stable pagination.

### Evidence media access

`POST /api/v1/evidence/{id}/access` authorizes the evidence through its incident,
audits grant creation, and returns a URL and expiry. The grant lasts 60 seconds.
`GET /api/v1/evidence/{id}/content?grant=...` requires both the grant and a current
read bearer token for the same subject/property. Each content access is audited.
The UI must fetch content with its Authorization header; a bare video URL is
not sufficient. Files must exist below configured `EVIDENCE_ROOT` and use an
allowed JPEG/PNG/MP4/WebM extension. Missing storage/signing configuration gives
503; unavailable media gives 404; expired/tampered grants give 401.

Stored live snapshot URLs are not immutable historical evidence and are not
silently served as such. The media ingestion adapter must archive actual files
and persist their relative paths before these endpoints can serve them.

## Realtime envelope

Committed incident messages include:

```json
{
  "type": "security_event",
  "event_id": "security-event:42:OPEN",
  "property_id": 1,
  "kind": "incident.updated",
  "incident_id": 42,
  "occurred_at": "2026-10-16T10:00:00+00:00",
  "data": {}
}
```

The in-process publisher filters subscribers by authorized property IDs. This
transport is not durable; cursor/replay storage remains future work and clients
must refetch persisted state after reconnect.

## Neon validation checklist

1. The supplied target was inspected read-only at revision `0004` before migration.
2. Schema and row counts were recorded without printing credentials.
3. Migrations through `0008` completed transactionally.
4. Legacy cameras/events were assigned only to `legacy-unassigned`.
5. A rollback-only transaction smoke test proved receipt uniqueness and atomic
   receipt/incident/history/outbox persistence without leaving test rows.
6. Camera, event, and incident read APIs passed against the live schema.
7. `alembic check` reported no model/schema drift.
8. A rollback-only logical backup/restore rehearsal using dedicated test rows
   passed in 4.08 seconds and left no residual data. A full physical `pg_dump`
   or Neon branch restore still requires a disposable branch before production.
