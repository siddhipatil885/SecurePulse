# Engineer 2 Backend and Database Baseline

**Recorded:** 2026-10-16

**Branch:** `feature/engineer-2-backend-domain`

**Baseline commit:** `d293c6f59d5a8697b7dc4ad38136debcd9cd87ac` (`feat: persist tracks and alerts`)
**Scope:** PostgreSQL persistence, FastAPI core, authentication, incidents, evidence, and backend tests

## Safety boundary

This section records the initial baseline. It was superseded by the authorized
Neon validation and migration recorded under **Live validation result** below.

## Verification summary

| Check | Result | Evidence |
|---|---|---|
| Canonical Git checkout | `KEEP` | Repository at commit `d293c6f`; active local branch is `feature/engineer-2-backend-domain` |
| Python runtime | `KEEP` | Project virtual environment uses Python 3.12.10 |
| Dependency installation | `FIX` | Changed `sqlalchemy>=2.0.0` to `sqlalchemy[asyncio]>=2.0.0` so the required `greenlet` dependency is declared |
| Backend tests | `KEEP` | `181 passed in 1.61s` using the local isolated test suite |
| Live Neon schema/version | `PASS` | Upgraded from `0004_tracks_and_alerts` to `0008_camera_zones_health` on 2026-10-20 |

Test command:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
```

## Component inventory

| Component | Status | Existing evidence | Required follow-up |
|---|---|---|---|
| FastAPI application factory and lifecycle | `KEEP` | `backend/app/main.py` | Preserve current startup, MQTT listener, router registration, and shutdown behavior |
| PostgreSQL async engine/session | `KEEP / FIXED` | Async Neon connection passed after translating libpq SSL options for asyncpg | |
| Alembic migration chain | `PASS` | `backend/alembic/versions/0001` through `0008`; live head and metadata agree | Review migration 0009 before deploying it |
| Camera model and repository | `KEEP / FIX` | `backend/app/models/camera.py`, `backend/app/repositories/cameras.py` | Add property ownership only through a reviewed, backward-compatible migration |
| Security-event persistence | `KEEP / FIX` | `backend/app/models/security_event.py`, `backend/app/repositories/events.py` | Clarify source receipt versus incident semantics and lifecycle/revision deduplication |
| Evidence metadata | `KEEP / FIX` | `backend/app/models/evidence.py`, `backend/app/repositories/evidence.py` | Add authorized access and audit behavior; continue storing references rather than media bytes |
| Anonymous person tracks | `KEEP` | `backend/app/models/track.py`, `backend/app/services/person_tracker.py` | Preserve temporary non-biometric tracking contract |
| Operator alerts | `KEEP / FIX` | `backend/app/models/alert.py`, migration `0004_tracks_and_alerts` | Distinguish alerts from canonical incidents and define legal state transitions |
| Atomic event processing | `KEEP / FIX` | `backend/app/services/event_processor.py` | Existing commit/rollback and duplicate handling require concurrency and full transaction-boundary review |
| JWT validation | `KEEP / FIX` | `backend/app/core/auth.py` | Existing subject/scope validation is usable, but resource/property authorization is missing |
| Camera read API | `KEEP / FIX` | `GET /api/v1/cameras`, `GET /api/v1/cameras/{camera_id}` | Add pagination where needed and enforce property membership |
| Event read API | `KEEP / FIX` | `GET /api/v1/events`, `GET /api/v1/events/{event_id}` | Enforce property membership and align naming with the canonical incident contract |
| Realtime WebSocket | `KEEP / FIX` | `WS /api/v1/events/stream` | Add property scoping, durable recovery/cursor strategy, and permission-change handling |
| Track read API | `KEEP / FIX` | `GET /api/v1/tracks` | Scope returned camera IDs to authorized properties |
| Liveness/readiness | `KEEP / FIX` | `GET /health`, `GET /health/ready` | Keep dependency-aware readiness; verify behavior without exposing private configuration |
| Users | `IMPLEMENTED` | `backend/app/models/tenancy.py`, migration `0005` | Link the approved identity provider before production |
| Properties and memberships | `IMPLEMENTED` | `Property`, `PropertyMembership`, camera/event ownership in migration `0005` | Populate real properties through an approved administrative workflow |
| Zones and camera health | `IMPLEMENTED` | `Zone`, `CameraHealthObservation`, migration `0008`; camera reads expose latest observed state | Engineer 1 supplies observations and canonical external zone identifiers |
| Resource-level authorization | `IMPLEMENTED LOCAL` | Signed `property_ids` claims filter camera, event, incident, media, track, and realtime reads | Identity issuer must derive claims from active memberships |
| Durable source-event receipts | `IMPLEMENTED / VERIFIED` | Duplicate receipt rejected by live rollback-only transaction smoke test | |
| Canonical incident history | `IMPLEMENTED` | `IncidentStatusHistory` plus command service | Confirm final state vocabulary with Engineer 3 |
| General audit records | `IMPLEMENTED` | `AuditRecord` written with incident state commands | Add retention duration after product approval |
| Notification outbox/attempts | `IMPLEMENTED` | `NotificationOutbox`, `NotificationAttempt` | Engineer 3 still owns sender/retry behavior |
| Marshal profiles/availability/assignments | `IMPLEMENTED` | Persistence models and one-active-offer index in migration `0005` | Engineer 3 still owns eligibility and dispatch policy |
| Backup/restore evidence | `PASS (logical rehearsal)` | Dedicated test rows were exported, deleted, restored, verified, and rolled back on Neon in 4.08 seconds | A full physical/branch restore remains a production-release gate |

## Existing migration chain

| Revision | Purpose | Baseline assessment |
|---|---|---|
| `0001_initial` | Cameras, security events, and evidence | Retain; future tenant fields must be added without destroying existing rows |
| `0002_seed_front_door` | Seeds `front_door` camera | Review before tenant migration because the row currently has no property owner |
| `0003_seed_laptop_camera` | Seeds `laptop_camera` camera | Review before tenant migration because the row currently has no property owner |
| `0004_tracks_and_alerts` | Tracks, alerts, evidence metadata, and incident-key uniqueness | Retain; clarify canonical alert/incident naming and deduplication responsibility |

## Remaining cross-team contract decisions

1. **Engineer 1:** canonical normalized event fields, source-system identifier,
   `new/update/end` semantics, evidence references, and camera-health envelope.
2. **Engineer 3:** incident state machine, assignment states, one-active-offer
   constraints, notification intents, and outbox delivery/attempt semantics.
3. **Engineer 4:** REST response shapes, identity/token mechanism, property-scoped
   realtime envelope, event replay cursor, and short-lived evidence/stream access.
4. **Project lead:** identity source, organization/property ownership rules, the
   owner of the Neon project, and which Neon branch/database is safe for
   development migrations and backup/restore testing.

## Original proposed milestone

This milestone has now been implemented and validated against the authorized
Neon target. Existing rows were preserved under `legacy-unassigned` rather than
being assigned to an arbitrary real tenant.

The first acceptance target is:

- one normalized source event creates one durable incident outcome;
- replay and concurrent delivery do not create duplicates;
- receipt, incident, initial history, and outbox intent share one transaction;
- an injected failure leaves no partial state; and
- users cannot read another property's cameras, incidents, or evidence.

## Local implementation progress

The following Engineer 2 work was implemented after this baseline was recorded:

- migration `0005_tenancy_operations` adds properties, users, memberships,
  property ownership, durable receipts, history/audit, notification outbox and
  attempts, marshal persistence, availability, assignments, and assignment
  events;
- existing rows are preserved under the explicit `legacy-unassigned` system
  property rather than being attributed to a real tenant;
- migration `0008_camera_zones_health` adds per-camera zones and append-only
  health observations without modifying existing camera rows;
- camera, event, incident, evidence, track, snapshot/WebRTC, and realtime reads
  are filtered by authorized property IDs;
- detection processing writes receipt, incident, initial history, evidence,
  alert, and outbox intent in one transaction and publishes after commit;
- incident history/evidence reads and controlled acknowledge/resolve/dismiss/
  reopen commands are exposed under `/api/v1/incidents`;
- realtime incident and track delivery is property-scoped; and
- the 2026-10-20 suite passed 197 tests and OpenAPI built with 15 paths;
  see the 2026-10-21 acceptance addendum below for subsequent changes.
  Alembic reports a single `0008` head, and offline PostgreSQL SQL generation
  succeeds.

## Live validation result

- Live schema inspection, migration upgrade, async connection, API reads, row
  preservation, tenant backfill, receipt uniqueness, and transaction rollback
  were verified on 2026-10-20.
- `alembic check` reports no new upgrade operations.
- A rollback-only logical backup/restore rehearsal against dedicated test rows
  passed in 4.08 seconds. It exported property/user/membership
  rows, deleted and restored them inside one transaction, verified tenant
  ownership and values, then rolled the entire rehearsal back cleanly.
- A full physical `pg_dump` or Neon branch restore was not attempted because no
  disposable branch was supplied. That remains a production-release gate, not
  a blocker for the application-level recovery behavior verified here.

## 2026-10-21 acceptance addendum

Verification: **206 tests passed in 173.51 seconds**, including the opt-in
PostgreSQL acceptance suite. The public database remains at revision 0008 with
three cameras, one security event, and no additional domain rows. No commit or
push was performed. CI configuration is added locally; no remote CI run is claimed.

The repository now contains real PostgreSQL acceptance tests at
`backend/tests/integration/test_postgres_domain.py`. They migrate a randomly
named, isolated schema from zero, use independent database sessions, and drop
only that generated schema on completion. They never downgrade or delete public
application tables. A GitHub Actions workflow runs these checks with PostgreSQL
16; local execution is opt-in via `RUN_POSTGRES_TESTS=1`.

Coverage includes concurrent ingesters, ten exact replays, injected failure
after history/outbox flush, concurrent update receipt recovery, foreign keys,
populated migration reversal/upgrade, HTTP tenant/scope negatives, expired and
missing authentication, pagination, incident commands, and evidence auditing.
The logical restore test exports and restores all domain tables in the isolated
schema and compares every row, including incident and audit data.

Implementation fixes: eager loading of replay receipts, exact-receipt race
recovery, rollback coverage on update paths, fresh/legacy compatibility in
unreleased migration 0007, stable incident ordering, bounded camera pagination,
incident filters, media-grant endpoints, and secret redaction in application logs.

Media grants support files under `EVIDENCE_ROOT`, expire after 60 seconds, and
require the same authenticated subject and current property access at playback.
They reject traversal and unsupported file types. The existing live-camera
snapshot references are not historical recordings; archiving those frames still
requires the ingestion/media integration. No placeholder file is presented as
real historical evidence.

Remaining external decisions: identity issuer and refresh/revocation policy,
membership-derived token provisioning, media archival and camera-health producer
contracts, dispatch policy, retention periods, and a physical backup/branch restore.
These are not claimed complete by the local test suite.
