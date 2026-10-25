# Dependency-Aware Development Roadmap and Team Allocation

## Delivery principle

Build one auditable vertical slice before breadth: deterministic sample/camera → Frigate → MQTT → validated/idempotent event → one security rule → one incident transaction → authenticated API/realtime display. Then add minimal marshal dispatch. Mobile polish and advanced AI follow demonstrated domain reliability.

## Milestone 0 — Repair and prove the Phase 1 foundation

| ID | Task | Current state / affected modules | Dependencies | Priority | Owner | Acceptance criteria and validation |
|---|---|---|---|---|---|---|
| M0.1 | Repair Compose RTSP topology | Port collision and no publisher; `deployment/docker-compose.yml`, Frigate config | None | P0 | E3 | Clean machine starts all containers; unique host ports; deterministic sample publishes `/live`; Frigate reports healthy frames. Validate with `docker compose config/up/ps`, RTSP probe, logs. |
| M0.2 | Correct secret/env substitution | Unsupported placeholder at `frigate.yml:36` | M0.1 design | P0 | E3 + E1 | No secret defaults; supported `FRIGATE_*` reference resolves; redacted config validation passes; missing secret fails safely. |
| M0.3 | Secure local broker baseline | Anonymous broker at `mosquitto.conf:1-5` | None | P0 | E3 | TLS or explicitly isolated dev profile; unique service accounts and topic ACLs; unauthorized publish/subscribe tests fail. |
| M0.4 | Add service health/readiness and persistence | No health checks; Frigate DB persistence unclear | M0.1 | P1 | E3 + E2 | Broker, stream, and Frigate health probes gate consumers; recreate preserves intended metadata/media; documented recovery test passes. |
| M0.5 | Automate Phase 1 smoke test | Manual observer only | M0.1-M0.4 | P0 | E3 | Fixture stream causes expected person event on MQTT within agreed latency; CI assertion captures event ID/camera/label; cleanup is deterministic. |

M0.2/M0.3 can run in parallel; M0.4 follows topology decisions; M0.5 integrates all four.

## Milestone 1 — Working detection-to-database pipeline

| ID | Task | Current state / affected modules | Dependencies | Priority | Owner | Acceptance criteria and validation |
|---|---|---|---|---|---|---|
| M1.1 | Define versioned normalized event contract and fixtures | No schema; `backend/app/events` | M0.5 captured payload | P0 | E3 + E1 | New/update/end, missing, malformed, duplicate, and out-of-order fixtures validate predictably; schema version documented. |
| M1.2 | Create PostgreSQL domain schema/migrations | No DB; `backend/app/database` | Event/incident identity decisions | P0 | E2 | Fresh DB upgrades to head; required FK/unique/index/check constraints exist; rollback/forward and concurrency tests pass. |
| M1.3 | Implement durable MQTT adapter | Print-only utility; `backend/app/mqtt`, events | M1.1, M1.2 receipts | P0 | E3 | Reconnect/backoff; durable receipt/idempotency; poison message quarantine; restart/replay tests show no lost/duplicate processing. |
| M1.4 | Implement one zone/person eligibility rule | No engine; detection/zones | M1.1, persisted zones | P0 | E3 | Given threshold-passing person in zone, emit one candidate; boundary/confidence/duplicate tests cover negative cases. |
| M1.5 | Transactionally create incident/evidence references | No incident service | M1.2-M1.4 | P0 | E1 + E2 | Eligible event commits exactly one incident, history row, and outbox item; injected DB failure commits none; replay remains one. |
| M1.6 | Establish observability for pipeline | Logs only | M1.3-M1.5 | P1 | E1 + E3 | Correlation ID from source event to incident; metrics for lag/failures/duplicates; actionable alerts and redacted structured logs. |

M1.2 can begin alongside M1.1 with provisional contracts. M1.3 and M1.4 can proceed in parallel after M1.1; M1.5 is the integration gate.

## Milestone 2 — Backend and real-time monitoring dashboard

| ID | Task | Current state / affected modules | Dependencies | Priority | Owner | Acceptance criteria and validation |
|---|---|---|---|---|---|---|
| M2.1 | Build FastAPI foundation and API contracts | Dependency placeholders | M1.2 domain schema | P0 | E1 | App starts with liveness/readiness; versioned OpenAPI; typed errors; camera/incident/evidence reads and controlled transitions pass API tests. |
| M2.2 | Implement identity, roles, property isolation | None | User/property schema | P0 | E1 + E2 | Password/session/token policy reviewed; owner/marshal/admin matrix; every IDOR/cross-property negative test passes. |
| M2.3 | Implement authenticated realtime incidents/status | None | M1.5, M2.2 | P1 | E1 | Reconnect with cursor replays missed events; unauthorized connection fails; backpressure/disconnect behavior tested. |
| M2.4 | Implement camera health and secure live-view metadata | None | M0 foundation, M2.2 | P1 | E1 + E3 | Offline/online state is persisted/timestamped; clients never receive reusable camera credentials; failure UI is testable. |
| M2.5 | Build minimal real dashboard | Empty dashboard | M2.1-M2.4 | P1 | E4 | Login, one property, cameras, incident list/detail/timeline/evidence render only real test API data; no production mock fallback; browser E2E passes. |
| M2.6 | Add evidence catalog/access policy | Raw media only | M1.2, M2.2 | P1 | E2 + E1 + E4 | Content hash/storage metadata/retention recorded; authorized playback works; unauthorized access and expired URL fail/audit. |

M2.1/M2.2 should be designed together. E4 can scaffold against generated contracts while E1 implements; integration waits for M2.3/M2.4.

## Milestone 3 — Minimal emergency dispatch

| ID | Task | Current state / affected modules | Dependencies | Priority | Owner | Acceptance criteria and validation |
|---|---|---|---|---|---|---|
| M3.1 | Marshal profile, verification, service area, availability | Absent | M2.2 | P1 | E2 + E1 | Validated schema/API; stale/off-duty marshal excluded; privacy/retention rules documented/tested. |
| M3.2 | Atomic assignment and state machine | Absent | M3.1, incidents | P1 | E1 + E2 | Concurrent workers create one active offer; only assigned marshal accepts; illegal transitions return conflict and audit event. |
| M3.3 | Notification outbox/provider adapter | Absent | M1.5 outbox, M3.2 | P1 | E1 | Transactional outbox, retry/backoff, provider receipt, dedupe, poison handling; provider outage test retains delivery intent. |
| M3.4 | Timeout/reject/escalation worker | Absent | M3.2-M3.3 | P1 | E1 | Expired/rejected offer is atomically closed and next eligible marshal offered; accept/timeout race test has one winner. |
| M3.5 | Marshal client vertical slice | Absent | M3.1-M3.4 | P1 | E4 | Authenticated offer, accept/reject, en-route/on-scene/resolve; offline/retry and unauthorized tests pass. |
| M3.6 | Owner/dashboard dispatch visibility | Absent | M3.2-M3.4 | P1 | E4 | Assignment/status timeline updates in real time without exposing private marshal data beyond policy. |
| M3.7 | End-to-end emergency scenario drill | Absent | All M3 | P1 | All | Fixture detection reaches resolution with immutable history; duplicate event, notification outage, no marshal, and restart cases meet defined outcomes. |

## Milestone 4 — Mobile integration

Choose the platform after resolving the product questions in `13-open-questions.md`. Property-owner work can run parallel with the marshal client after shared auth/realtime contracts stabilize.

| ID | Task | Current state / affected modules | Dependencies | Priority | Owner | Acceptance criteria and validation |
|---|---|---|---|---|---|---|
| M4.1 | Select mobile architecture and generate shared API client | No mobile source | Stable M2 contracts | P2 | E4 + E1 | Decision record covers platforms, secure storage, push/background limits; generated client passes contract tests. |
| M4.2 | Build owner incident experience | Absent | M2.2-M2.6, M4.1 | P2 | E4 | Login, notification, incident history/detail/evidence/status work against real test backend; offline/revoked-access device tests pass. |
| M4.3 | Productionize marshal mobile workflow | M3.5 pilot client not yet built | M3.5, M4.1 | P1 | E4 | Real-device foreground/background/terminated offer delivery, token rotation, accept/status/resolution, navigation handoff, offline recovery pass. |
| M4.4 | Add device/push registration lifecycle | No device records/provider | M3.3, M4.1 | P1 | E1 + E2 | Tokens bind to authenticated device/user, rotate/revoke safely, deduplicate, and record delivery without logging secrets. |
| M4.5 | Validate secure stream compatibility | No app stream | M2.4, M4.1 | P2 | E3 + E4 | Supported devices play authorized stream without camera credentials; expiry/revocation/network-change tests pass. |

## Milestone 5 — Production hardening

| ID | Task | Current state / affected modules | Dependencies | Priority | Owner | Acceptance criteria and validation |
|---|---|---|---|---|---|---|
| M5.1 | Pin dependencies/images and add SBOM/vulnerability gates | Ranges/mutable image | Working builds | P2 | E3 + E1 | Reproducible build from lock/digests; policy blocks critical known issues or records approved exception. |
| M5.2 | Create least-privilege production deployment | Privileged local Compose only | Service topology stable | P1 | E3 | No privileged container; internal ports private; secrets externalized; TLS and network policies verified. |
| M5.3 | Validate HA, recovery, and capacity | No HA/backups/load data | M1-M4 representative load | P2 | E2 + E3 | Measured camera/event load; broker/DB/service recovery objectives; backup restore drill meets RPO/RTO. |
| M5.4 | Enforce full test/CI quality gates | No CI/automated tests | Tests from every milestone | P1 | All | Unit, contract, DB, API, security, UI, E2E, migration and recovery suites mandatory on protected branch. |
| M5.5 | Implement privacy/retention/evidence governance | Frigate retention only | Product/legal decisions | P1 | E2 + E1 | Approved retention/deletion/legal-hold/access matrix; deletion and access-audit tests pass. |
| M5.6 | Define SLOs, monitoring, and on-call runbooks | None | Instrumented services | P2 | E1 + E3 | Detection-to-incident and notification latency/error SLOs; dashboards/alerts tested by failure injection. |

## Four-person ordered backlogs

### Engineer 1 — Backend & API Integration

1. Event/incident service boundaries with E3/E2.
2. FastAPI foundation, health/readiness, error and versioning conventions.
3. Authentication, role/property authorization, audit actor context.
4. Transactional incident service and outbox orchestration.
5. Realtime incident/camera-status delivery and replay.
6. Atomic dispatch orchestration, provider adapter, timeout/escalation worker.
7. API/security/concurrency/observability tests.

### Engineer 2 — Database & Persistence

1. Domain IDs, tenant model, event receipt, incident/evidence/history schema.
2. Migration tool, constraints, indexes, transaction boundaries, fixtures.
3. Idempotency and incident/outbox atomicity with E1/E3.
4. Marshal/availability/assignment/assignment-event tables and race constraints.
5. Evidence integrity, retention/legal hold, audit/access history.
6. Backup/restore, migration rehearsal, performance/concurrency tests.

### Engineer 3 — Security Intelligence & Video Pipeline

1. Fix Compose/MediaMTX/Frigate topology and secure MQTT.
2. Deterministic video/MQTT smoke fixture and config tests.
3. Normalized Frigate event contract with captured fixtures.
4. Durable consumer, replay/dedup/order semantics with E2.
5. Zone/person rule and camera health; rule unit/integration tests.
6. Pipeline metrics, hardware profiles, failure/recovery tests.
7. Only after the pilot: line crossing, loitering, GPU optimization.

### Engineer 4 — Frontend & Mobile Integration

1. Select web/mobile architecture from product constraints; generate typed client from API contract.
2. Dashboard auth/property/camera/incident/detail/timeline/evidence vertical slice.
3. Realtime reconnection/replay and explicit loading/error/offline states.
4. Marshal offer/accept/status/resolution client.
5. Owner notifications/history/evidence/status client.
6. Accessibility, secure local session handling, browser/device E2E tests.

## Coordination gates

- E2/E3/E1 jointly own event and idempotency keys before ingestion code.
- E1/E2 jointly own authorization query patterns and dispatch transaction semantics.
- E1/E4 freeze versioned API/realtime contracts before UI integration.
- E1/E3 agree camera health and stream-access contract; camera credentials never enter frontend bundles.
- All engineers sign off the M1 vertical slice and M3 failure drill before scope expansion.

