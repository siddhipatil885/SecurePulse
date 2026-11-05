# Unified operator cases — v1

This additive backend contract combines camera-generated `SecurityEvent` records
and manually submitted `ReporterIncident` records for property operators. It does
not rename, merge, reassign or duplicate either source table. Existing dashboard
`/incidents`, reporter mobile `/reporter/incidents`, and bearer dispatch APIs retain
their existing response contracts. Wiring the dashboard UI to this new queue is a
separate integration step; no mobile screens were changed for this backend work.

## Identity, access, and status

Base: `/api/v1/dashboard/properties/{property_id}/cases`.

Use the existing dashboard login and HttpOnly cookie session. Mutations require
`X-Dashboard-Request: 1` and a trusted browser origin. Every endpoint checks the
current active account, property, membership and role. This property-wide queue
is limited to **owner/dispatcher** memberships because manual reports contain
private descriptions and evidence. Reporter users retain their existing
own-report mobile APIs and camera read APIs; marshal-only memberships do not
grant access to the operator queue.

Every record has a source-qualified key, `camera:123` or `reporter:123`, plus
`source`, `source_id` and `property_id`. Numeric IDs alone are never interchangeable
between sources. Detail routes take both `{source}` and `{source_id}`. Switching
properties requires loading a new property URL; changing request-body fields
cannot override the authorized path.

The queue normalizes only `ReporterIncident.status=RECEIVED` to `status=OPEN`.
`source_status` always exposes the original stored state. Reopening a manual
report stores `RECEIVED`, preserving the mobile contract. Assignment status is
separate from incident status. Manual reports have `severity=null`, not an
invented severity; a severity filter therefore selects only matching camera
records. Camera confidence and camera ID are also null for manual reports.

## Endpoints

All paths below are relative to the base.

| Method | Path | Result |
|---|---|---|
| GET | empty | Paginated combined queue |
| GET | `/overview` | Total, active, and counts by source |
| GET | `/eligible-marshals` | Available candidate IDs, names, service areas and capacity |
| GET | `/{source}/{source_id}` | Detail, location, latest assignment, allowed actions and dispatch eligibility |
| GET | `/{source}/{source_id}/timeline` | Merged incident-status and assignment-status history |
| GET | `/{source}/{source_id}/evidence` | Evidence catalog without filesystem paths |
| POST | `/{source}/{source_id}/commands` | Audited state change with conflict/retry protection |
| GET | `/{source}/{source_id}/assignments` | Paginated assignment history |
| POST | `/{source}/{source_id}/offers` | Create/replay an offer via the existing dispatch service |
| POST | `/{source}/{source_id}/assignments/{id}/cancel` | Cancel this case's assignment using its current version |
| POST | `/{source}/{source_id}/evidence/{id}/access` | User/case/property-bound signed media grant |
| GET | `/{source}/{source_id}/evidence/{id}/content?grant=...` | Authorized media playback |

List filters: `source=camera|reporter`, normalized `status`, and
`severity=INFO|LOW|MEDIUM|HIGH|CRITICAL`. Pagination uses `page>=1` and
`page_size=1..100` (default 50), and returns `items`, `total`, `page`, `page_size`.
Timeline, evidence and assignment history use the same pagination parameters.
Queue order is newest occurrence first, then source, then source ID descending;
this disambiguates equal timestamps and IDs. Timeline order is oldest first,
with kind/ID tie-breakers. Offset pagination is not a snapshot of a changing queue.

Queue rows include the latest assignment. The database selects only the latest
assignment per case for the current page rather than fetching full assignment
histories. The overview aggregates both tables independently of the list page.
Active means normalized `OPEN` or `ACKNOWLEDGED`.

Details include the original description/type, camera confidence/zone when
present, and location. Camera location uses the camera's configured location,
falling back to the property address. Manual reports use their submitted address,
latitude/longitude and reported accuracy. Missing data remain null.

## Incident commands

Example body:

```json
{
  "command": "acknowledge",
  "expected_status": "OPEN",
  "reason": "Reviewed the report and attached evidence",
  "correlation_id": "a-unique-logical-request-id"
}
```

Valid transitions:

| Current normalized state | Actions |
|---|---|
| OPEN | acknowledge, resolve, dismiss |
| ACKNOWLEDGED | resolve, dismiss |
| UNCLASSIFIED | dismiss |
| RESOLVED, DISMISSED, CLOSED | reopen |

The server requires a nonblank reason and a request ID. Reuse the same
`correlation_id` only when retrying that exact logical request; use a new one for
a new action. A successful retry returns the current case without adding history
or notifications again, including when the incident has since been reopened.
Reusing a request ID with a different actor, action, reason or expected status
returns `409 IDEMPOTENCY_CONFLICT`. State mismatches/illegal transitions return
`409 CASE_CONFLICT`.

A status change writes the source status, source history/timeline, audit record,
and notification outbox intent in one transaction. Manual history keeps the
existing mobile timeline format. The new timeline also merges assignment events
and includes stable item keys, actor, reason, time and assignment ID where relevant.

Resolve/dismiss is blocked while the case has an OFFERED, ACCEPTED, EN_ROUTE or
ON_SCENE assignment. Cancel that assignment first; the older camera command
service now applies the same guard. This prevents an incident being closed while
a response remains active. This change does not introduce responder en-route,
on-scene or completion command endpoints.

## Dispatch

Offer body:

```json
{
  "marshal_profile_id": 12,
  "expires_in_seconds": 60,
  "idempotency_key": "a-unique-offer-request-id"
}
```

The path determines the source and property. Unexpected body fields are rejected.
The idempotency key binds the property, source incident and marshal. A replay
returns the original offer and never extends its deadline; changed business
identity returns a conflict. Another active assignment on that case also returns
a conflict. Cancel body: `{"expected_version": 1}`; stale versions return 409.

Eligibility requires active account/profile/marshal membership, on-duty and
available state updated within five minutes, and capacity. Unexpired OFFERED
records now reserve capacity alongside ACCEPTED/EN_ROUTE/ON_SCENE records. Expired
offers do not consume marshal capacity, but must still be expired/cancelled before
that incident receives a replacement. Acceptance rechecks the profile and capacity.
No distance-based matching or automatic reassignment is added here.

Offer creation atomically writes the assignment, append-only assignment event
and notification intent. Source-row and marshal-row locks serialize PostgreSQL
workers, and partial unique indexes enforce one active assignment per incident
for both sources. A savepoint rolls back all offer-side records if history/outbox
writing fails. No outbound push/SMS delivery occurs inside these transactions.

Existing bearer `/api/v1/dispatch` accept/decline/expire/cancel endpoints remain
available. Their updates are reflected in the new case detail and timeline, and
the reporter's existing detail response still exposes the actual linked dispatch.

## Evidence and realtime

Catalog responses never contain storage paths, reusable upstream credentials or
push tokens. A media grant expires after 60 seconds and binds the actor, property,
source, incident and evidence ID. Playback rechecks the live session/role and all
bindings. Reporter attachments are served only from beneath `EVIDENCE_ROOT` with
allowed media types. Camera files and per-event Frigate snapshots use the existing
authorized evidence implementation. A camera's latest frame is never substituted
for an incident snapshot.

The existing property-scoped dashboard socket publishes this invalidation message
after operator commands, offer changes, marshal responses, manual report creation
and manual evidence upload:

```json
{"type":"case_updated","property_id":1,"data":{"key":"reporter:123"}}
```

Clients should refetch the affected case/list/counts after receiving it. Existing
`security_event` messages continue to signal camera ingestion/legacy updates.
Messages contain no report descriptions or media. Delivery remains process-local
and non-durable; reconnecting clients must refetch, and polling is still necessary
for changes made outside these API publishers, such as timeout-worker execution.
The application schedules offer expiry. Notification delivery defaults to disabled;
the recording fake provider requires an explicit development-only opt-in. No live
push provider is configured. Marshal progress through `EN_ROUTE`, `ON_SCENE`, and
`COMPLETED` publishes invalidations and completion resolves the linked camera or
manual incident.

## Migration and verification

After reviewing/backing up the intended database, apply migrations through
`0017_reporter_active_assignment`. It adds the missing active-assignment unique
index for manual reports. Existing duplicate active manual assignments cause a
safe migration failure requiring operator reconciliation; no rows are deleted or
automatically reassigned. The ORM now also uses partial indexes on SQLite rather
than an unconditional camera-assignment uniqueness constraint.

Local checks from `backend`:

```sh
python -m pytest tests/test_operator_cases.py tests/test_dispatch.py tests/test_dashboard.py -q
python -m pytest -q
```

PostgreSQL concurrency acceptance runs with `RUN_POSTGRES_TESTS=1` and a configured
test `DATABASE_URL`, following the existing generated-schema fixture. Tests cover
same-key concurrent replay, different-key offers for one report, shared marshal
capacity across incidents, and concurrent incident commands. They create/drop
only a generated test schema. These checks remain unverified locally when no real
PostgreSQL connection is available.
