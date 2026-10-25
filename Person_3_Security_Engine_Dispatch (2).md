# EDI-SecurePulse — Engineer 3 Work Package
## Security Intelligence, Event Correlation, Incident Decisions and Emergency Dispatch

**Scope:** Normalize the meaning of detections, decide what becomes a security incident, and coordinate a backend-only marshal/response workflow. **Allocation:** 28 planning points, balanced with the other engineers. **Mobile applications: OUT OF SCOPE.**

> **No-rebuild rule:** The team previously reported an implemented Security Engine producing `SecurityEventCandidate` objects. The Codex audit of the older September 12 checkout found none. **Do not write a replacement engine until you locate and test the team's actual implementation.** Preserve its public contract if it works; implement only proven missing rules, tests and response capabilities. No face-recognition project or bespoke model training is part of this cycle.

## A. Ownership and boundaries

**You own:** evaluation of verified Frigate detections, configurable zone/intrusion policies, incident-candidate production, suppression/correlation decision logic, incident lifecycle policy, marshal eligibility, assignment strategy, safe state transitions, notification dispatch worker/provider abstraction and escalation timer orchestration.

**You do not own:** FFmpeg/Frigate/MQTT infrastructure or raw MQTT transport adapter (Engineer 1), DB table migrations and generic transaction framework/authentication (Engineer 2), dashboard/realtime browser interface/CI platform (Engineer 4), owner or marshal mobile applications.

**Starting evidence:** the old audited source has person threshold filters in Frigate YAML, but no app-owned rule engine. Earlier chats specifically refer to a completed `SecurityEngine` and `SecurityEventCandidate` output. This package assumes **investigation first** and nonduplicative improvements second.

## B. Find and validate the real engine — P3-00 (2 points)

1. Inspect the canonical working tree, Git HEAD/branches and relevant local repositories identified by the team. Ask for the branch where the reported engine was implemented.
2. Locate engine class/modules, candidate models, policy/zone configuration, rule tests, backend calling code and integration tests. Search concrete imports/call sites rather than trusting README claims.
3. Execute existing unit tests; if a test path previously reported as `tests/security/` does not exist, resolve the repository/test location mismatch before diagnosing engine logic.
4. Use an actual sanitized Frigate event captured by Engineer 1, plus deterministic generated fixtures, to verify the current engine output. Record output event fields and how the backend consumes them.
5. Write `docs/status/engineer-3-baseline.md` classifying each rule, candidate schema and dispatch component as `KEEP / FIX / MISSING / BLOCKED` with code+test evidence.

**Exit:** existing rules/candidate contract are inventoried and protected from incompatible rewrite.

## C. Engineering backlog

### P3-01 — Complete and verify configurable security decision rules (6 points)

Use the current rule engine where it exists. Make the **minimum pilot policy** correct before adding advanced analytics.

- Define what qualifies as an actionable security event versus an informational detection. Frigate detecting `person` alone must not automatically mean intrusion.
- Implement/test `person entered configured restricted zone` using camera-specific zone definitions, approved operating hours and minimum dwell/score thresholds where appropriate. Define exactly which coordinate space zone polygons and detection boxes use; handle boundary conditions, resolution changes, malformed polygons and missing geometry.
- Ensure detection phases (`new`, `update`, `end`) are treated correctly; no new incident for every update frame.
- Produce the existing candidate model (`SecurityEventCandidate` or canonical equivalent) with `event_type`, `camera_id`, source object/event ID, `zone_id`, `severity`, `reason`, `occurred_at`, evidence references and metadata. Match Engineer 2's exact persisted incident contract; do not invent fields silently.
- Make rules explainable and tunable through versioned configuration; include a policy version in emitted decisions for later investigation. Keep defaults conservative to reduce false alerts.
- Support severity from **business policy**, not an unexplained “AI confidence score”. Confidence can be evidence input but should not be mislabeled as incident certainty.
- Define clear `NO_ACTION` / `INFORMATIONAL` outcomes and bounded error behavior for camera failure or malformed event data.

**Acceptance:** Captured `person` event in a restricted zone produces one expected candidate; same activity outside zone or outside configured rule conditions does not; rule-boundary, threshold, missing-field and phase-order fixtures pass. Existing passing implementation is kept, with missing coverage added.

### P3-02 — Incident grouping, deduplication decisions and severity policy (4 points)

- Work with Engineer 1 to understand Frigate event/object IDs and how they change between new/update/end. A tracking ID is not a permanent person identity.
- Work with Engineer 2 to establish idempotency **at the persistence boundary**. Your rules supply stable correlation keys or clustering decisions; database uniqueness enforces replay safety.
- Suppress repeat notifications for ongoing activity while preserving source observations and important severity increases. Define a documented cooldown/correlation window by camera+zone+event policy, not an arbitrary fixed global timer.
- Implement event transitions for ongoing, ended, re-entered and escalated cases. Distinguish `same tracked event` from `new incident` without biometric identity matching.
- Explain why each candidate is high/medium/low severity using policy fields visible to operators; store a reason code and policy version.
- Define false-positive dismissal and authorized re-open/escalation decisions with Engineer 2's audit mechanism.

**Acceptance:** Duplicated/updating message streams do not produce alert storms; separate qualifying incidents remain distinct; severity transitions are deterministic and tested, including simultaneous and out-of-order delivery.

### P3-03 — Implement missing emergency assignment logic and incident state machine (6 points)

This is **backend orchestration only**. There is no requirement to build a marshal mobile app.

- Define a minimal state model with explicit legal transitions, e.g. `OPEN → DISPATCHING → OFFERED → ACCEPTED → EN_ROUTE → ON_SCENE → RESOLVED`, with `DISMISSED`, `REJECTED/TIMED_OUT`, `ESCALATED`, and cancellation paths where policy permits.
- Agree the persisted state representation and relational constraints with Engineer 2, including immutable assignment-event history and one-active-offer policy.
- Implement marshal eligibility from **verified** properties: assigned service area, on-duty status, freshness of availability, organization/permissions, capacity and optional location. Do not assume live GPS exists; implement a service-area/manual or test-location method that can actually be evaluated now.
- Deterministically select an eligible marshal under an explicit priority policy; define the no-eligible-marshal fallback to an operator escalation state, not a fictional successful dispatch.
- Ensure offer creation, reassignment and acceptance are atomic using Engineer 2's transaction/repository interfaces. Compare-and-swap on status/expiration; only the authenticated targeted marshal or authorized dispatcher may accept/change an assignment.
- Add dispatcher/test API commands through Engineer 2's routers; Engineer 4 may optionally create a small **web** test control for supervised validation, but it is not a mobile app.
- Preserve full state transition history: actor, reason, time, prior/new states and correlation ID.

**Acceptance:** Two workers cannot issue conflicting active offers under the agreed policy; only the offered/authorized marshal can accept; invalid transitions return clear conflicts; no marshal available results in visible escalation, not dropped incident. All tests use deterministic fake clocks/fixtures where possible.

### P3-04 — Backend notification service and outbox delivery (5 points)

- Confirm whether any alerting service already exists before introducing another provider.
- With Engineer 2, adopt a transactional **notification outbox**: event/assignment intent stored with the same database transaction, independent worker sends asynchronously.
- Implement versioned notification intents: incident opened, marshal offer, offer reminder/expiry, escalation, acceptance and resolution. The event payload should contain authorized IDs and presentation-safe metadata, not private camera passwords or raw full-person biometrics.
- Provide a provider-neutral adapter and a **local fake provider** that records attempts. Add a real push/SMS/email integration only if an approved provider, credentials, audience and cost policy exist; do not purchase services or send real emergency messages from test runs.
- Track queued, attempted, provider-accepted, failed, exhausted states. Distinguish **provider accepted** from **human acknowledged**.
- Implement dedupe keys, bounded retry with jitter/backoff, redacted logs, delivery attempt history, and poison/manual-escalation handling. Never delete the original incident if a notification fails.

**Acceptance:** Provider outage leaves durable unsent intents; retry later produces no duplicated business assignment, and testing confirms distinct delivery versus marshal-acknowledgment states. Fake-provider E2E tests require no external account.

### P3-05 — Timeouts, escalation and operational recovery (3 points)

- Add a scheduler/worker that checks unacknowledged offers against persisted expiry and safely transitions them to timed out, rejected or escalated per approved policy.
- Design away timer/acceptance races through conditional DB state transitions; an accepted offer cannot be timed out retroactively by a slow worker.
- On rejected/expired offers, move to next eligible marshal where policy allows; otherwise surface a human operator action with reason.
- Handle process restarts: missed timer jobs are recovered from persisted DB state, not in-memory timeouts alone.
- Define maximum attempts, escalation thresholds and what actions require a human. The platform must not autonomously claim to have contacted public emergency services unless a verified, authorized integration exists.

**Acceptance:** Restarting the worker does not lose pending offers; simultaneous timeout and acceptance yields one legal outcome; no-eligible/final-failure paths remain visible and auditable.

### P3-06 — Rule/dispatch tests, documentation and incident drill (2 points)

Implement focused automated tests and a runbook:

- Positive/negative zone rule; duplicate new/update/end; cooldown; severity change and malformed payload.
- Candidate→database idempotency contract with Engineer 2.
- Concurrent offer, simultaneous accept-vs-timeout, rejected offer, stale/off-duty marshal, provider outage and restart recovery.
- Privacy and authorization negative paths (unauthorized property/marshal actor).
- One pilot walkthrough: input person event → one incident → one marshal offer → accepted → en-route → resolved → audited history. Use simulated backend marshal actions until a client exists.

Publish `docs/runbooks/rules-dispatch.md`: rule configuration, severity table, dispatch policy, state machine, notification receipts, emergency/manual fallback and failure diagnosis. Document all assumptions awaiting product approval.

**Acceptance:** One reproducible test command exercises the happy path and at least the required failure cases. No “success” assertions depend on whether a push notification was actually read by a human.

## D. Contracts to agree before implementation

| Partner | Dependency | Engineer 3 output |
|---|---|---|
| Engineer 1 | Actual event lifecycle, score/box/zone coordinates, source IDs | Versioned candidate schema, eligibility rule requirements and dedup correlation decisions |
| Engineer 2 | Receipt uniqueness, incident and assignment transactions, auth/tenant checks, outbox schema | State machine, repository command semantics, dispatcher selection/worker service, notification intents |
| Engineer 4 | Authenticated realtime event envelope and operator-facing statuses | Incident/offer/status transition events, readable reasons and UI test fixtures |

**Sequencing:** find real engine → lock event/candidate contracts → finish one person-in-zone rule → stable transactional incident creation → minimal dispatch state machine → fake notifications/timers → end-to-end failure drill. Design schema and rules jointly to avoid a second incompatible candidate model.

## E. Definition of done

- [ ] Original Security Engine located, tested and retained wherever already correct.
- [ ] One explainable, configurable intrusion rule is verified with real/fixture Frigate events.
- [ ] Repeated observations do not spam incidents or marshal offers; no biometric identity assumption.
- [ ] Candidate and policy version match Engineer 2's incident contract.
- [ ] Marshal eligibility/assignment and legal incident transitions are atomic and property-scoped.
- [ ] Notification intents survive outages and accurately distinguish dispatch from acknowledgment.
- [ ] Timeout/reassignment is restart-safe and concurrency-tested.
- [ ] No-eligible-marshal and escalation paths produce auditable, visible outcomes.
- [ ] Pilot detection-to-resolution scenario and negative tests pass using backend endpoints/fake provider.
- [ ] No mobile app, face recognition or speculative “AI dashboard” features were built.

## F. Product decisions that must be explicitly confirmed

Who may dispatch/dismiss/close an incident; which organizations employ marshals; acceptable candidate severity policy; allowable shift/service-area and location usage; offer expiry; escalation policy; whether external emergency services may ever be contacted; retention of marshal location and evidence. Flag pending decisions, document safe provisional development defaults, and do not claim unsupported integrations exist.
