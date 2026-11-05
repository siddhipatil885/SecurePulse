# Engineer 1 baseline: video, Frigate, MQTT, and event ingestion

## Checkout and scope

| Item | Evidence |
|---|---|
| Repository | `C:/SecurePulse-person1` worktree; origin `https://github.com/siddhipatil885/SecurePulse.git` |
| Branch and revision | `person1/video-frigate-mqtt` at `c3ac692633421b30194d6ba8caaa33df91a92aa3`, based on fetched `origin/main` |
| Working tree at inspection | Clean before this work; no changes were made in the running `C:/SecurePulse` checkout |
| Runtime access | `docker version` and `docker compose ps` could not connect to Docker Desktop's Linux engine. Runtime checks below are BLOCKED, not PASS. |

## Feature inventory

| Feature | Exists at path | Runtime/test evidence | KEEP / FIX / MISSING | Follow-up |
|---|---|---|---|---|
| Canonical edge Compose | `backend/deployment/docker-compose.yml` | Static inspection only before edits; Docker daemon unavailable | FIX | Keep one canonical stack, pin images, avoid collisions with the separately running checkout, make all browser-facing ports localhost by default. Changes are in this branch; validate with Compose when Docker is available. |
| Duplicate Frigate Compose | `backend/frigate/docker-compose.yml` | Static inspection; had another Frigate service, `privileged: true`, and overlapping RTSP/WebRTC host ports | FIX | Marked opt-in as a legacy profile, removed unnecessary privilege, and moved its host ports. Do not use it with the canonical stack. |
| Frigate config selection | `backend/frigate/config/config.yml`, `config.yaml`, `frigate.yml` | Static inspection only; files declare Frigate 0.18 and 0.13-era schemas, while Compose selected the latter under a noncanonical filename | FIX | Canonical Compose now explicitly mounts `frigate.yml` as `/config/config.yml`; preserve all other configs for existing/manual installs. Verify the selected config against the actual pinned image before rollout. |
| Stream source and MediaMTX | `backend/mediamtx/mediamtx.yml`; `backend/deployment/docker-compose.yml` | Prior stack referenced an RTSP simulator but had no publisher; no RTSP probe available | FIX | Added a pinned FFmpeg test-pattern publisher into MediaMTX and service-name routing. This proves transport only; it contains no person footage. Test with an authorized camera or clip for detections. |
| Frigate event payloads | `backend/app/integrations/frigate.py`; `backend/tests/test_mqtt_integration.py` | Existing parser tests cover lifecycle and malformed payload cases; no fresh real broker capture available | KEEP / FIX | Retained parser and receipt integration; added range/type validation, explicit source/phase/timestamps, and versioned sanitized lifecycle fixtures under `backend/tests/fixtures/frigate/v0.13/`. Fixtures are schema examples, not claimed as real captures. |
| MQTT adapter and backend handoff | `backend/app/workers/frigate_listener.py`, `backend/app/integrations/frigate.py`, `backend/app/main.py`, `backend/app/services/event_processor.py` | Existing event processor uses database receipts keyed by source, event ID, phase, and payload revision; no live event could be captured here | KEEP / FIX | The adapter hands normalized `DetectionEvent` objects to the existing backend processor. Added a bounded thread-safe queue, serialized worker, visible overflow logs, and bounded shutdown drain. Durable idempotency remains owned by backend database receipts. |
| Broker authentication and topic limits | `backend/deployment/mosquitto/config/mosquitto.conf` | Prior config allowed anonymous access; no negative broker-auth test could run without Docker | FIX | Anonymous access is disabled; separate Frigate publisher and backend reader ACLs are configured. Password file is generated locally and ignored by Git. Verify allowed/denied clients against a live broker. |
| Camera/edge health | `backend/app/api/health.py`, `backend/app/models/camera_operations.py` | Existing readiness checked database and MQTT only; no Frigate stats request or camera was available | FIX | Added `/health/edge` to report Frigate reachability, per-camera FPS-based status, MQTT status, and queue depth. Health is observational and is not yet persisted to `camera_health_observations`. |
| Real detection, snapshot, clip, reconnect, and resource benchmarks | Frigate, camera, and media runtime | Docker Desktop unavailable; no camera or lawful sample clip was available to this worktree | BLOCKED | Run the procedures in `docs/runbooks/video-event-pipeline.md` on the target machine and attach sanitized outputs. Do not mark the real-person detection acceptance as passed using the synthetic test pattern. |

## Prior audit findings

The older repository audit described a print-only subscriber, anonymous MQTT, a missing deterministic publisher, duplicate RTSP mappings, and no dependency health checks. The fetched `main` already contains a backend Frigate client, lifecycle parser, event processor, database receipt/idempotency models, and camera health observation model; therefore the old audit is not a current statement of missing implementation. This branch addresses the static configuration and adapter gaps visible in the fetched tree. Runtime acceptance remains blocked until Docker and video source access are available.

## Verified changes versus pending runtime evidence

| Check | Result |
|---|---|
| Focused Frigate/MQTT/health tests | PASS: 46 tests |
| `docker compose ... config --quiet` with the example env | PASS |
| `git diff --check` | PASS |
| Full backend suite | 226 passed, 7 skipped, 7 errors. All errors are in pre-existing `tests/test_reporter.py`: its SQLite fixture tries to compile the PostgreSQL-only `JSONB` model type. |
| Docker daemon and live edge checks | BLOCKED: Docker Desktop Linux engine unavailable in this session. |

Still required on the target host: healthy broker and Frigate, RTSP decode, Frigate frame statistics, a real or authorized person clip producing `new/update/end`, retrievable snapshot/clip, camera disconnect/reconnect, broker restart, container recreation, automated unauthorized MQTT denial, and CPU/RAM/frame/event throughput measurements. Record image IDs, OS, commands, results, and sanitized logs; do not include passwords or private imagery.
