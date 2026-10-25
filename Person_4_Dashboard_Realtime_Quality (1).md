# EDI-SecurePulse — Engineer 4 Work Package
## Real-Data Web Dashboard, Realtime Delivery, System Monitoring and End-to-End Quality

**Scope:** Secure web monitoring and the integration/verification layer that proves the entire system works. **Allocation:** 28 planning points (balanced with the other three work packages; relative complexity points, not hours). **Mobile applications: OUT OF SCOPE.**

> **No-rebuild rule:** Your team reported a dashboard UI was already developed and WebRTC integration was underway. The older September 12 repository audited by Codex contained only empty dashboard placeholders. **First locate the actual frontend.** Preserve completed layouts/design; do not spend this cycle redesigning screens. The objective is to replace any remaining mock data with verified backend data, connect secure camera playback, and make the entire pipeline testable.

## A. Ownership and boundaries

**You own:** existing web dashboard integration; API client and realtime dashboard channel (WebSocket or SSE implementation, in coordination with Engineer 2); camera-player integration and detection overlays; incident/timeline and operational health views; browser E2E tests, integration test orchestration, CI checks and demo acceptance evidence.

**You do not own:** Frigate/FFmpeg/MQTT configurations or camera detection (Engineer 1), domain schema/primary REST API/auth model (Engineer 2), intrusion policy/dispatch selector/notification worker (Engineer 3), mobile apps or rebuilding an already completed UI design.

**Known discrepancy:** legacy audit found `ai-cctv/dashboard/src/{pages,components,services,types}/.gitkeep` only and no `package.json`, while team chats reported a ready dashboard on another code copy/branch. This package is conditional on locating the real frontend before coding.

## B. Verify the actual dashboard — P4-00 (2 points)

1. Establish canonical Git root/HEAD and find the working dashboard directory, manifest, route components, styling/theme and environment files.
2. Inventory all actual screens/cards/widgets and classify every displayed value as `REAL API`, `REALTIME`, `LIVE STREAM`, `CONFIG`, `MOCK`, `HARDCODED`, or `UNVERIFIED`.
3. Locate camera-player code, WebRTC/go2rtc endpoints, API URL selection, authentication storage, incident page/state management and error handling.
4. Identify which UI work is already completed; mark those elements **KEEP**. Do not replace a finished dashboard with a new scaffold merely because the audited clone is empty.
5. Create `docs/status/engineer-4-baseline.md`, listing component path, source of each field, live verification result and `KEEP / FIX / MISSING / BLOCKED` status.

**Exit:** dashboard's real implementation and data gaps are known; existing design/usable components preserved.

## C. Engineering backlog

### P4-01 — Make every monitoring field real and consistent (5 points)

Audit the **existing** dashboard, then connect only disconnected or incorrect parts:

- Camera cards: verified camera name, configured property, last frame/heartbeat, actual online/offline/degraded state; no static green badges.
- Primary activity camera: choose based on active incident/activity timestamp and selected property, with sensible fallback when nothing happens. If layout already shows one large feed + two smaller feeds, retain it rather than rebuilding it.
- Incident list and detail: real `id`, severity, rule reason, source camera, zone, observed/created timestamp, state, evidence, handler/assignment and history from Engineer 2's APIs.
- Counters/charts: derive from API results or explicit aggregate endpoints with well-defined time windows. Never hardcode “live threats”, “today”, “active cameras”, or performance values. Clearly display zero, unknown or loading rather than invented placeholder numbers.
- Properties/roles: use authorized property access and avoid cross-tenant leaks by checking backend permission results; hide forbidden actions but never rely on hiding as security.
- API client: typed contracts generated or aligned to the agreed OpenAPI, pagination/filtering, cancellation/retry policy, UTC/local time presentation and consistent error states.

**Acceptance:** A seeded development database with two properties yields exactly the authorized cameras, counters and incidents; adding/closing incidents changes UI after API/realtime update; disconnecting backend produces visible error/offline state rather than unchanged stale “live” numbers. A reviewer can trace every dashboard field to a backend response.

### P4-02 — Complete live camera playback and accurate detection overlays (5 points)

- Work with Engineer 1 to use the **actual supported stream pathway**, e.g. go2rtc WebRTC/MSE/HLS via a secured gateway as applicable. Do not paste internal RTSP passwords into browser JS or expose open Frigate APIs to untrusted users.
- Use Engineer 2's property/camera authorization before providing short-lived playback grants/metadata. Handle expired grants, unauthorized cameras and revoked sessions.
- Render one clear active feed and existing smaller side previews if already part of design; show real offline/muted/reconnecting indicators and user-friendly controls.
- Correctly map detection box coordinates from source pixels to the displayed video rectangle, accounting for letterboxing, aspect ratio, scale, mirrored orientation and viewport resize. Boxes must follow objects; do not put decorative rectangles over video.
- Distinguish available metadata: live coordinates if a real synchronized metadata stream exists; otherwise show honest **snapshot-only** overlays or historical boxes. Do not pretend an asynchronous MQTT event aligns perfectly with every browser frame.
- Provide evidence viewing with incident-linked snapshots/clips under existing retention and permission policy. Handle 404/expired evidence safely.
- Preserve the team's chosen color scheme and useful, simple terminology; do not add unnecessary confidence/AI score tiles.

**Acceptance:** Authorized user can open a live camera, see accurate available box overlays and view evidence linked to a real test incident; unprivileged user cannot access the feed or files. Tests cover resize, full-screen, source disconnect, reconnect and expired playback access.

### P4-03 — Implement authenticated realtime incident/status delivery (5 points)

Engineer 2 owns shared authentication and incident REST APIs. You own the **realtime transport contract and dashboard integration**, without creating a second incident database or an unauthorized stream.

- Decide WebSocket vs SSE using real client requirements and current stack; document choice. Use existing working implementation if available.
- Subscribe only to authenticated, property-scoped events. Connect to the same persisted incidents and status transition history used by REST; never make realtime transport the sole source of truth.
- Define a versioned envelope such as `{event_id, property_id, kind, incident_id, occurred_at, sequence_or_cursor, payload}`. Agree exact schema with Engineers 2 and 3, and authorize before sending each event.
- Add missed-event recovery after network interruption using cursor/replay or refetch-diff; de-duplicate messages by event ID/sequence and preserve ordering semantics where required.
- Handle expired tokens, permission changes, connection limits, backpressure, throttling and degraded mode. No uncontrolled infinite reconnect loop.
- Show clear browser notifications/toasts for **actual** important incidents; separate informational events from actionable alerts. Browser popups are not a substitute for durable dispatch notifications.
- Surface marshal-offer/acceptance/escalation/resolution changes from Engineer 3 when they exist, without requiring a mobile app.

**Acceptance:** Opening two authorized dashboard sessions yields the same incident state; an unauthorized property receives no events; disconnect/reconnect recovers missed events without duplicate notifications; backend state still matches after hard refresh.

### P4-04 — Operations dashboard and actionable observability (4 points)

- Consume real edge health from Engineer 1 and API/database health from Engineer 2. Show camera connectivity, last observed event, MQTT consumer health, ingestion lag, API readiness and delivery worker health where metrics exist.
- Implement visible distinctions among `healthy`, `degraded`, `offline`, and `unknown` using measurements and last-update timestamps; never infer online from a configured camera row alone.
- Add incident-pipeline correlation drill-down: source event → normalized event → rule result → stored incident → realtime delivery → offer/notification status (when available). Show safe IDs/reasons, not secrets or raw biometric details.
- Provide operational diagnostics for queue backlog, unrecoverable parsing errors, repeated DB retries and notification failures, using real backend metrics/endpoints. Agree production access controls with Engineer 2.
- Include non-technical operator states: “Camera offline”, “No recent activity”, “Incident awaiting acknowledgment”, “No responder available”, “Connection lost; retrying.”

**Acceptance:** Deliberately stop a test camera/broker/DB or simulated notification sender; dashboard shows a truthful failure state and restoration, with timestamps. If a metric is not implemented, show `Unavailable` rather than a fabricated percentage.

### P4-05 — Cross-system automated checks and CI/E2E scenarios (5 points)

You orchestrate the combined quality gate; each engineer **still owns component-specific tests**. Do not centralize all debugging work on yourself.

1. Inventory already existing unit/contract/integration tests from all branches; use them before creating parallel suites.
2. Add CI checks for lint, basic type/static analysis, config rendering, Python test discovery, migration smoke tests and frontend build. Pin executable environment versions where possible.
3. Create a reproducible integration test environment with sample stream, broker, app backend, development DB and fake notification provider. Keep real camera/cloud/push credentials outside the test environment.
4. Add an end-to-end **security-event vertical slice**: deterministic person-in-zone event → MQTT → normalized adapter → one candidate → one DB incident → authorized REST → realtime dashboard.
5. Add a backend-only **dispatch vertical slice**: real/simulated candidate → incident → available marshal offer → API acceptance → en-route/on-scene/resolved → timeline/audit. Marshal actions can be invoked through tests or a minimal internal **web** operator interface; no mobile app needed.
6. Add essential negative paths: duplicate/out-of-order event, malformed payload, disconnected camera, broker reconnect, database rollback, cross-property user, unauthorized evidence, duplicate assignment, acceptance timeout, notification provider failure, stale dashboard reconnect.
7. Capture exact test commands, outputs, Git SHA, environment/service versions, test fixture IDs, known blocked dependencies and user-visible behaviors; no unexecuted test is a PASS.

**Acceptance:** A developer can reproduce core CI tests without live camera hardware using committed sanitized fixtures, and a supported host can run the full Docker-backed smoke test. CI fails on broken incident uniqueness, property isolation, alert delivery contract and frontend build. Document any Docker/Windows limitation explicitly.

### P4-06 — Integration documentation and final demonstration sign-off (2 points)

Publish `docs/runbooks/web-dashboard-e2e.md` containing:

- Current dashboard pages/components and their verified source endpoints.
- Local run commands, safe dev environment setup and browser troubleshooting.
- REST/realtime/streaming contract references and how to update typed clients.
- End-to-end demo script with expected event/DB/dashboard outcomes.
- Real-data checklist for every visible metric/card.
- Test evidence and remaining `BLOCKED`/privacy/production caveats.

Coordinate one integrated acceptance review with the team. Each owner fixes failures inside their area; you track them to closure with reproduction steps and evidence.

**Acceptance:** End-to-end demo is repeatable from documented setup. All major UI controls have real behavior or are visibly disabled with an explanation, never decorative fake interaction.

## D. Cross-team handoffs

| Partner | Receive from them | Deliver back |
|---|---|---|
| Engineer 1 | Stream gateway/grant format, source dimensions/box coordinates, camera health/status | Video player and overlay test results; browser playback requirements |
| Engineer 2 | Authorized camera/incident/evidence REST schemas, token verification, tenancy rules and stable event cursor store | Real-data client, property-scoped realtime route/client contract, API integration test failures |
| Engineer 3 | Candidate severity/reason, status timeline, offer/acknowledgment/escalation events, fake-provider test fixtures | Incident/dispatch status UI and full detection→resolution demo evidence |

**Sequencing:** recover real dashboard → agree API/auth contracts → replace mocks and connect stream → realtime replay/security → health view → full E2E/CI. You can scaffold typed tests against an agreed API specification while upstream services are being hardened.

## E. Definition of done

- [ ] Existing dashboard code was recovered and preserved; only disconnected/broken functionality changed.
- [ ] Every visible camera/incident/counter field has an identified live or persisted data source.
- [ ] Authorized video playback and correctly scaled **actual** detection overlays work; no reusable credentials leak.
- [ ] Realtime incident/status updates are property-scoped, reconnect-safe and consistent with the database.
- [ ] Operational errors/offline/unknown states are truthful, understandable and timestamped.
- [ ] End-to-end camera→incident→dashboard and incident→offer→resolution tests pass or have explicit environment blockers.
- [ ] CI executes real collected tests and frontend build rather than reporting empty suites as success.
- [ ] Web documentation, fixtures and a demo script are committed for team review.
- [ ] No mobile app development, UI redesign or hardcoded production data was added.

## F. Blockers and escalation

Escalate when the canonical frontend is missing, upstream REST contracts differ from claims, secure browser streaming is not yet exposed, no deterministic Frigate event fixture exists, or tests require forbidden real notifications. Keep test fixtures and interface adapters progressing while upstream owners address blockers; never label simulated results as production-ready.
