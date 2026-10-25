# EDI-SecurePulse — Engineer 2 Work Package
## PostgreSQL, FastAPI Core, Authentication, Incidents and Evidence

**Scope:** Application persistence and authenticated HTTP domain APIs. **Allocation:** 28 planning points (balanced with all other assignments; points are relative, not hours). **Mobile applications: OUT OF SCOPE.**

> **No-rebuild rule:** The team previously reported that the backend, database connection and initial security hardening were implemented. The October 13 Codex audit of an older September 12 tree saw only `ai-cctv/backend/requirements.txt` and `.gitkeep` placeholders. **First locate the later work and test it.** Reuse existing working APIs/models/migrations; fix only demonstrated gaps. Avoid a second unrelated backend or database schema.

## A. Ownership boundaries

**You own:** canonical PostgreSQL domain model, migrations, repositories and transaction boundaries; FastAPI foundation, identity and role/property authorization; camera/incident/evidence HTTP contracts; durable source-event receipts, incident persistence and audit tables; database backup/restore and API/database tests.

**You do not own:** camera/Frigate/MQTT runtime or transport adapter (Engineer 1), detection/security decisions or marshal-dispatch algorithms and notification workers (Engineer 3), browser dashboard or authenticated realtime/SSE/WS delivery (Engineer 4), any mobile client. Coordinate with Engineer 3 on assignment schema and with Engineer 4 on authentication of realtime endpoints.

**Audited legacy evidence:** only Python package requirements and empty directories under `ai-cctv/backend/app/*`; no models, migrations or API routes in that specific revision. Earlier team reports are stronger evidence that additional work may exist outside this audited copy.

## B. Canonical codebase verification — P2-00 (2 points)

1. Inspect the agreed team repository and latest revision; capture root, HEAD, branch, remotes, and worktree status.
2. Find the actual FastAPI app entrypoint, routers, Pydantic models, SQLAlchemy/SQL definitions, Neon/PostgreSQL configuration, migrations, tests, user authentication and existing incident service.
3. Run read-only checks: API route/OpenAPI enumeration; unit tests; **read-only database metadata introspection** using a development database with explicit credentials. Do not run production migrations or alter data merely to audit.
4. Create `docs/status/engineer-2-baseline.md` documenting each component as `KEEP`, `FIX`, `MISSING`, or `BLOCKED` with path, test command and outcome.
5. Reconcile differences between teammates' copies without overriding uncommitted work. Report undocumented tables or hidden credentials securely.

**Exit:** A single authoritative schema/contract is identified; existing working backend and persistence are preserved.

## C. Deliverable backlog

### P2-01 — Verify and complete the domain schema/migration chain (6 points)

Inspect and retain existing tables before proposing changes. Minimum needed domain capabilities are:

- `users`, role grants and property membership (or existing equivalent); property isolation must work for multi-tenant data.
- `properties`, `cameras`, `zones` and camera-health observations.
- Source-event receipts with stable `(source_system, source_event_id, event_phase/revision)` dedup key and event timestamps.
- `incidents`, evidence metadata, incident status history and auditable actor changes.
- Notification outbox/attempts and marshal profile/availability/assignment/assignment-event tables **in consultation with Engineer 3**. You implement DB structure, Engineer 3 implements dispatch decisions and sender/worker behavior.

Only add missing fields/tables through versioned migration scripts (for example Alembic if compatible with the existing stack). Do not directly mutate a shared production database. Define appropriate PK/FK, per-property scoping, `NOT NULL`, unique constraints, indexes, timestamps, and legal state constraints without making migrations unsafe for existing data.

For example, enforce unique processed-message receipts and prevent more active offers than a dispatch policy allows; the exact indexes and state representation must match the actual engine/dispatch contracts.

**Acceptance:** Fresh development DB can migrate from zero, populated test DB can migrate without data loss, schema version is observable, and a rollback/roll-forward strategy is documented. Constraint tests demonstrate duplicate receipt rejection, referential integrity and property scope. If migrations already meet this, keep them and add tests/evidence rather than creating new ones.

### P2-02 — Verify or complete transactional detection-to-incident persistence (5 points)

- Agree one canonical normalized event type with Engineer 1 and one `SecurityEventCandidate` (or existing equivalent) with Engineer 3. No silent field translation between teams.
- Ensure the ingest service stores source-event receipt and creates an incident **atomically**, including initial status/history and a notification/outbox intent if required by the agreed architecture.
- If an event is duplicated or replayed, return an idempotent result pointing to the same incident; do not create multiple records or dispatches. Decide the policy for valid `new/update/end` revisions and multiple camera events correlated to one incident.
- Persist clear UTC `observed_at`, `received_at`, and `created_at` timestamps; store external source IDs separately from application UUIDs.
- Separate detector confidence (measurement) from rule severity (business decision); keep original payload if policy permits, redact tokens and sensitive camera strings.
- Exercise explicit transaction rollback: injected failure during history/outbox write should not leave a half-created incident.

**Acceptance:** A fixture event creates exactly one incident, evidence reference/history and required outbox row; 10 repeats return the same incident; simultaneous ingesters do not double-write; transaction-failure test leaves no partial data. Show SQL/API assertions and link to test execution.

### P2-03 — FastAPI foundation, roles and tenant isolation (6 points)

**Preserve any functioning app/auth already built.** Fill missing hardening and test coverage rather than replacing it.

- Review app factory/startup, versioned `/v1` routing, request/response schemas, OpenAPI, consistent error objects, health liveness/readiness and DB pool lifetime.
- Provide secure session/JWT or the project's existing identity-provider integration, with credential handling, expiry, refresh/revocation as applicable and fail-closed validation.
- Define roles such as admin/operator, property owner and marshal only if product design requires them; permissions must be **resource-scoped**, not just globally role-scoped.
- Implement/verify object-level access for property, camera, incident, evidence, marshal offer and audit record. Do not allow a user to read a different property's incident by guessing an ID.
- Add rate limiting and safe logging for sensitive authentication and mutating routes; configure CORS narrowly for the web dashboard origin(s).
- Make all state-changing endpoints validate allowed transitions and authenticated actor intent; no unrestricted `PATCH status` or caller-controlled `property_id` trust.
- Provide a narrow, reusable authentication dependency for Engineer 4's WebSocket/SSE route and Engineer 3's dispatch commands.

**Acceptance:** Authenticated users access only permitted resources; anonymous, expired-token, cross-property and wrong-role negative tests fail predictably. API documentation matches actual source. Existing login flows keep working.

### P2-04 — Complete minimum camera, incident and evidence HTTP API (4 points)

For any existing endpoints, test and harden first. Proposed **contracts** (actual routes may differ; publish a canonical inventory instead of duplicating):

| Capability | Expected behavior | Notes |
|---|---|---|
| List property cameras | Authorized, paginated camera details/online state | Never return reusable RTSP credentials |
| Read incident list/detail | Property-scoped, filtered, paginated, stable sort | Severity, status, times, source ref |
| Read incident history | Immutable transitions with actor and time | Needed by dashboard and dispatch |
| Read evidence | Authorized catalog and short-lived playback access | Audit every sensitive access |
| Create incident | Internal ingestion identity only | Ordinary web users should not forge detections |
| Update incident | Intent-specific commands, state checks, audit | Coordinate with Engineer 3 dispatch |
| Health/readiness | Liveness and dependency-aware readiness | Do not leak private config |

- Define OpenAPI schemas and typed validation; version breaking changes.
- Establish `GET` error semantics, pagination, stable IDs, date filtering and responses for empty/offline states.
- Document the camera stream access contract with Engineer 1 and Engineer 4; no direct exposure of raw passwords.

**Acceptance:** OpenAPI-generated client or contract tests can consume the routes; backend returns actual persisted test data, not hardcoded event counts. Authorized and unauthorized evidence retrieval both tested.

### P2-05 — Data integrity, audit and recovery operations (3 points)

- Ensure audit histories for incident and dispatch mutations are append-only and include actor, source, action, previous/new state, timestamp and correlation/request ID.
- Establish data retention categories separately for raw media, source events, incidents, assignments, notifications and marshal location. Do not invent retention policy; require project decision for values.
- Decide on PostgreSQL deployment (existing Neon or containerized DB), connection pooling, backups, secret injection, migration-on-deploy controls and basic observability.
- Rehearse backup/restore **only on dedicated test data**, verify no property cross-contamination and record the actual recovery time.
- Define what happens when the database is unavailable: clear readiness failure and explicit retry boundaries, not silently dropped events.

**Acceptance:** An event and its audit history survive service restart; backup restore works in a nonproduction environment; private credentials do not appear in logs/repository.

### P2-06 — Automated backend/database tests and handover (2 points)

Provide and run the appropriate existing or new checks:

- Migration up/down or safe forward migration test on an ephemeral DB.
- Repository tests for unique receipts, FK constraints, transaction rollbacks and concurrent inserts.
- Auth/API integration tests for cross-property/role negatives, pagination, evidence permissions and invalid transitions.
- Consumer-to-incident integration test using Engineer 1's real sanitized fixture and Engineer 3's rule candidate.
- API contract artifacts and a DB schema diagram under `docs/contracts/`.

**Acceptance:** The test suite collects real test cases and passes in documented dev/CI conditions; blocked tests are identified with reasons, not called passing.

## D. Cross-team contracts and sequencing

| Partner | What you must agree | Your deliverable |
|---|---|---|
| Engineer 1 | Normalized source ID, lifecycle/revision semantics, camera health, adapter→backend path | Durable receipt service/ingestion endpoint and DB uniqueness |
| Engineer 3 | Candidate severity/zone/evidence fields; incident state machine; marshal eligibility and assignment constraints | Persistence tables, transaction APIs and outbox schema (not dispatch selector logic) |
| Engineer 4 | Auth token/session mechanism, REST response types, realtime auth dependency, stream/evidence grants | Versioned OpenAPI and production-data endpoints |

**Ordering:** baseline → contract agreement → schema/migrations → atomic incident service → auth/RBAC/API hardening → integration and security tests. Bootstrap initial auth in parallel with schema if an existing implementation allows it.

## E. Definition of done

- [ ] Audited-revision mismatch was resolved for your ownership; existing functioning code left intact.
- [ ] There is exactly one canonical domain schema and migration chain; no ad hoc shadow database.
- [ ] Detection replay, concurrency and rollback tests prove one consistent incident outcome.
- [ ] Auth, role checks and property isolation cover REST and reusable realtime dependencies.
- [ ] Camera/incident/history/evidence APIs serve persisted real test data with verified permissions.
- [ ] Evidence is cataloged and accessed through authorized, auditable pathways.
- [ ] Database outage, recovery, backup and migration behavior are documented and tested safely.
- [ ] API and DB contract tests run automatically with clear evidence and pass criteria.
- [ ] No mobile application was built or assigned.

## F. Stop-and-escalate conditions

Stop before irreversible schema changes if a different production schema, uncommitted teammate work, unapproved data deletion, unknown owner of the Neon database, or incompatible event schema appears. Produce a proposed migration diff and request project-level review; do not discard existing data.
