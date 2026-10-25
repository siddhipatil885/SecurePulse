# EDI-SecurePulse — Engineer 1 Work Package
## Video Infrastructure, Frigate, Mosquitto and Event Ingestion

**Scope:** Camera → FFmpeg/MediaMTX → Frigate → MQTT → normalized event adapter. **Allocation:** 28 planning points (comparable to the other three work packages; points are relative, not hours). **Mobile applications: OUT OF SCOPE.**

> **No-rebuild rule:** The team previously demonstrated a working laptop-camera stream, Frigate person detection and MQTT event messages. Do **not** reinstall, recreate or replace those components if the current shared repository and a fresh smoke test prove they work. The October 13 Codex audit examined an older September 12 repository revision (`0e039d6`), in which only configuration and a print-only MQTT subscriber were visible. Treat missing code in that copy as an investigation trigger, not proof that teammates did not implement it elsewhere.

## A. What you own and what you do not

**You own:** camera and edge runtime, stream topology, Frigate configuration/compatibility, broker transport controls, capture of real Frigate events, a reliable event adapter up to the agreed ingestion interface, camera health signals, edge-focused tests and operating procedures.

**You do not own:** application PostgreSQL migrations (Engineer 2), incident rule decisions and dispatch (Engineer 3), REST auth and domain APIs (Engineer 2), the web dashboard or WebSocket client (Engineer 4), mobile apps.

**Existing evidence:** `ai-cctv/deployment/docker-compose.yml`, `ai-cctv/frigate/config/frigate.yml`, `ai-cctv/deployment/mosquitto/config/mosquitto.conf` and `ai-cctv/tests/test_mqtt_subscriber.py` exist in the audited scaffold. Earlier team tests reported live detections and observed MQTT payloads in a potentially different `C:\SecurePulse` checkout.

## B. Mandatory initial verification — P1-00 (2 points)

Before editing code, inspect the **actual shared working tree**, not a stale Antigravity scratch clone.

1. Record `git rev-parse --show-toplevel`, `git rev-parse HEAD`, `git branch -avv`, `git status --short`, `git remote -v`; ask the lead which repository/branch is canonical.
2. Locate the edge Compose files, Frigate YAML, MediaMTX config, FFmpeg launch script, Mosquitto config, MQTT adapter, and any tests. Check other teammate branches **without destructive Git operations**.
3. Build `docs/status/engineer-1-baseline.md` with columns `Feature | Exists at path | Runtime/test evidence | KEEP / FIX / MISSING | Follow-up`.
4. Run safe checks (`docker compose config`, container health/log inspection, an RTSP probe, and a real Frigate event capture) **only where Docker and equipment are available**. If not available, record BLOCKED; do not mark PASS.
5. Compare against the old audit issues; close those already fixed, linking commit/path/test evidence. Preserve existing working configs and video secrets.

**Exit:** canonical paths and actual implementation state identified. No duplicate Frigate/MQTT installation or redundant pipeline has been created.

## C. Implementation / improvement backlog

### P1-01 — Make stream topology reproducible and portable (5 points)

**Run only the unfinished portions.** Earlier audited configuration had a host-port conflict (`8554` assigned twice), an empty MediaMTX “simulator”, a questionable `${RTSP_STREAM_URL:-...}` expression inside a bind-mounted YAML, and Linux-only volume/device assumptions.

- Check current Compose for published port collisions; keep only one externally published RTSP endpoint or use nonconflicting host ports. Prefer service-name DNS for container-to-container traffic.
- Define an explicit stream-source strategy: **(a)** real RTSP/IP camera or Windows laptop FFmpeg publisher and **(b)** deterministic local sample-video publisher for tests. MediaMTX alone does not generate video.
- Correct the active Frigate stream variable mechanism using the syntax supported by the **pinned installed Frigate version**; do not assume Compose expands files mounted verbatim.
- Validate host Windows + Docker Desktop / WSL and Linux profiles separately. Make optional USB/Coral mounts opt-in; avoid `privileged` mode without a documented, demonstrable hardware requirement.
- Pin supported image versions; provide a sample `.env.example` with **no real credentials** and a clear list of required environment variables.
- Add restart/readiness behavior that waits for the relevant broker and stream endpoints rather than merely container startup order.

**Acceptance:** From a clean supported host, `docker compose config` succeeds, containers start without published-port collision, `ffprobe` (or an equivalent) decodes the configured test stream, and Frigate reports incoming frames. Evidence records image versions, host OS, command and result. If the current stack already meets this, mark KEEP and spend these points on multi-camera/long-run reliability testing, not reimplementation.

### P1-02 — Verify Frigate detections, boxes, clips and camera lifecycle (4 points)

- Confirm the current camera identifier(s), role mapping (`detect`/`record`), resolution/FPS, detection thresholds, motion masks and configured zones; do not change thresholds arbitrarily.
- Collect repeatable **person enters / remains / exits** observations. Save sanitized `new`, `update`, `end` events and expected camera/object identifiers. Ensure snapshots/clip references remain accessible under configured retention.
- Check recorded image dimensions against detection-box coordinate systems. Document how the web client can obtain **correctly scaled** bounding boxes; Engineer 4 will render them.
- Distinguish object detection, per-event tracking, face detection and long-term identity. **Do not implement face recognition or promise stable person identity**; that is neither verified nor needed for the current MVP.
- Verify behavior when camera is disconnected/reconnected or FFmpeg crashes, and record state transitions and logs.

**Acceptance:** Test footage causes expected tracked-person events, a valid snapshot with visible overlay, a retrievable clip/reference where enabled, and a documented camera-offline response. False detections and uncertainty are measured, not silently filtered out.

### P1-03 — Secure and document Mosquitto transport (4 points)

- Inspect whether production/development broker authentication is already implemented. Keep it if working; otherwise replace audited `allow_anonymous true` with per-service credentials and topic ACLs. Avoid publishing `1883` beyond trusted development networks.
- Use private Docker networking; document when TLS is needed for remote brokers (or TLS/mTLS deployment profile) and how secrets are injected without embedding them in tracked YAML.
- Define topic contract and service authority: upstream Frigate produces `frigate/events` and other approved topics; normalized events are not written back onto an unrestricted upstream topic.
- Apply reconnect/backoff limits and least privilege; test unauthorized publishing and subscribing, plus authorized Frigate/adapter operation.
- Preserve logs without printing credentials or full private imagery.

**Acceptance:** Unauthorized access is rejected; permitted clients can still exchange real events; network exposure is documented. No hardcoded/default production secrets.

### P1-04 — Validate or complete the durable event adapter (6 points)

**Do not replace an existing Security Engine adapter without inspecting its interface.** Engineer 2 owns database transaction/idempotency persistence and Engineer 3 owns rule evaluation; agree the shared schema **first**.

- Consume the actual Frigate event payloads for supported version(s), validate required `camera`, `label`, source object/event ID, event lifecycle, timestamps and optional zone/evidence fields.
- Normalize to versioned `SourceDetectionEvent` or the canonical equivalent; include `source_system`, `source_event_id`, `camera_id`, `event_phase`, `occurred_at` (UTC), `ingested_at`, object label/score, box, zones, and sanitized evidence references. Decide exact fields with Engineers 2 and 3; never invent incompatible schemas independently.
- Handle `new/update/end`, missing fields, malformed JSON, duplicate/out-of-order messages, unrelated objects and clock skew. Reject/quarantine invalid messages with reason codes.
- Implement broker reconnect, bounded work queues, nonblocking callback behavior, retries and a visible poison-event path; do **not** promise end-to-end exactly-once delivery. The receiver/database must own durable idempotency.
- Choose explicitly between: direct adapter-to-backend authenticated ingestion API, durable queue, or internal service call. Record choice in `docs/contracts/event-ingestion.md` and build contract tests with Engineer 2.
- Emit correlation IDs and safe structured logs (source ID, camera, processing stage, reason, latency) without logging secrets.

**Acceptance:** For a captured event set, a single normalized object reaches the agreed backend boundary; duplicates do not create additional incidents; invalid messages are quarantined or explicitly rejected; restart/disconnection tests expose no silent loss. End-to-end incident uniqueness is jointly tested with Engineer 2.

### P1-05 — Reliability, performance and camera health (4 points)

- Add/verify edge health information: MQTT connected, Frigate reachable, stream available, last successful frame/event timestamp, queue depth/failure counts.
- Provide a health/status interface or agreed message for Engineer 2 to persist and Engineer 4 to display; clarify `online`, `offline`, `degraded` and `unknown` semantics.
- Measure practical performance on target prototype hardware: camera count, frame rate, CPU/RAM, dropped frames, event throughput, detection-to-MQTT latency. Record data and environmental limitations.
- Rehearse broker restart, source disconnect, Frigate restart, container recreation and full machine restart; confirm retention of media/Frigate metadata through container recreation where intended.
- Document cleanup, log retention and bounded disk consumption; alert on media volume pressure.

**Acceptance:** Defined failure conditions produce observable status and recovery behavior, not phantom “camera online” indicators; benchmark evidence is reproducible.

### P1-06 — Edge tests, handover and operating runbook (3 points)

Deliver automated checks where feasible:

- Compose/config lint and no-colliding-port check.
- Fixture-based Frigate event contract tests, including malformed, duplicate and lifecycle variants.
- Broker auth/ACL negative tests.
- Deterministic RTSP → Frigate → MQTT smoke test (mark hardware-only dependencies separately).
- Manual recovery matrix for no-camera, no-Docker, no-broker and failed-FFmpeg environments.

Update `docs/runbooks/video-event-pipeline.md` with launch/stop commands, topology, port chart, expected logs, diagnostics, and redacted evidence references.

**Acceptance:** Teammates can reproduce and diagnose the stream using the runbook without requiring your laptop-specific private paths.

## D. Handoffs and interfaces

| Recipient | Deliverable | Required coordination |
|---|---|---|
| Engineer 2 | Normalized event contract, receipt/dedup assumptions, camera health envelope, stream/evidence identifiers | Decide stable IDs, ingestion transaction and authorized endpoint before coding adapter |
| Engineer 3 | Captured sanitized real events (`new/update/end`), zones/score semantics, tracker lifetime behavior | Agree event lifecycle and precisely when a detection becomes rule-eligible |
| Engineer 4 | Secure live-stream playback contract, bounding-box coordinates, camera online/offline payload, test URLs without credentials | Do not embed permanent RTSP passwords or expose internal Frigate ports in the dashboard |

**Suggested sequencing:** Baseline → stream+broker fixes → event fixtures/schema agreement → adapter/recovery work → integrated tests. Your work is on the critical path for the first end-to-end incident demo.

## E. Definition of done (all must pass)

- [ ] Current shared repository and preexisting work were inspected; every task marked **KEEP / FIX / MISSING** with evidence.
- [ ] RTSP/Frigate/MQTT run reproducibly on supported prototype equipment; no known host-port collisions.
- [ ] Broker has documented boundaries and negative authorization tests.
- [ ] Person events and box/clip semantics are captured in versioned fixtures.
- [ ] Event adapter uses the agreed schema, handles malformed/duplicate events and recovers from disconnects.
- [ ] Camera/offline/queue metrics can be consumed by other components.
- [ ] Automated edge checks and runbook are committed through team review.
- [ ] A real or deterministic test event reaches Engineer 2/3's ingest boundary and is traceable by correlation ID.
- [ ] No app or mobile UI work was introduced.

## F. Blockers to escalate (do not silently guess)

Missing access to the correct codebase, unavailable video device, Frigate version/config incompatibility, broker credentials, missing sample clip rights, unknown camera codec or unavailable Docker. Publish exact evidence and impact in the team's issue tracker; continue fixture tests/documentation while a blocker is resolved.
