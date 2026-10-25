# EDI-SecurePulse Repository Audit — Executive Summary

Audit date: 2026-10-13 (Asia/Calcutta)

Audited revision: `0e039d6bbe952e43c4f844d31fadb1e3cc3c8f21` on `main`

Scope: all tracked repository files and visible local branches

## Project purpose

SecurePulse, also described as an Intelligent Emergency Response & Surveillance Network, is intended to turn RTSP/ONVIF camera feeds into detected security events and coordinated physical response. The stated future pipeline includes motion filtering, object detection, tracking, rule evaluation, alerting, a dashboard, event storage, and QRT/emergency response (`README.md:56-88`, `README.md:92-117`, `README.md:145-165`). The README explicitly labels those capabilities as planned and the project as an early prototype (`README.md:15`, `README.md:33-52`, `README.md:284-315`).

## What the repository actually contains

The repository is a Phase 1 infrastructure scaffold, not an application. Its substantive implementation consists of:

- Docker Compose declarations for Mosquitto, Frigate 0.13.2, and a MediaMTX container (`ai-cctv/deployment/docker-compose.yml:3-53`).
- A one-camera Frigate configuration that requests CPU person detection, recording, snapshots, and MQTT publication (`ai-cctv/frigate/config/frigate.yml:1-66`).
- An unauthenticated Mosquitto listener (`ai-cctv/deployment/mosquitto/config/mosquitto.conf:1-5`).
- A manual Python MQTT subscriber that prints messages to stdout (`ai-cctv/tests/test_mqtt_subscriber.py:1-64`).
- Empty placeholder directories for a future backend and dashboard. Every tracked file below `backend/app` and `dashboard/src` is a one-line `.gitkeep` placeholder.

There is no FastAPI application, API endpoint, event adapter, security intelligence engine, PostgreSQL schema, migration, application persistence, dashboard implementation, mobile application, authentication, authorization, notification service, marshal model, dispatch workflow, CI/CD pipeline, or production deployment definition.

## Overall assessment

**Classification: initial implementation.** The repository is beyond pure architecture/design because concrete Frigate, MQTT, and Compose configuration exists. It is not a functional prototype because the default video stack has static blockers, no automated test is discoverable, and the configured event stream terminates at a console-printing utility rather than an incident system. It is not an MVP, pilot-ready, or production-ready.

Operational readiness could not be demonstrated: Docker is not installed in the audit environment, and `pytest --collect-only` found zero tests. Python syntax parsing of the subscriber passed. See `10-testing-audit.md`.

## Major findings

| Priority | Finding | Evidence | Consequence |
|---|---|---|---|
| P0 | The default Compose stack assigns host port `8554` to both Frigate and MediaMTX. | `ai-cctv/deployment/docker-compose.yml:23-27`, `:44-49` | Both services cannot bind that port concurrently on a normal Docker host. |
| P0 | The supposed RTSP simulator only starts a default MediaMTX image; no sample-video publisher, path source, or MediaMTX config is supplied. | `ai-cctv/deployment/docker-compose.yml:43-49`; complete repository inventory | Default `/live` has no demonstrated media producer. |
| P0 | The camera URL uses Compose substitution syntax inside a file mounted into Frigate. | `ai-cctv/frigate/config/frigate.yml:32-39`; `ai-cctv/deployment/docker-compose.yml:28-39` | Compose does not render mounted file contents, and Frigate's supported substitution syntax is different; ingestion is likely to receive the literal placeholder. Runtime validation is blocked. |
| P0 | No application consumes events into incidents or storage. | Only consumer: `ai-cctv/tests/test_mqtt_subscriber.py:31-41`; backend placeholders | Camera detections cannot become SecurePulse incidents. |
| P0 | No FastAPI entry point, routers, services, or repositories exist. | `ai-cctv/backend/requirements.txt:1-9`; `backend/app/**/.gitkeep` | No application API exists. |
| P0 | No application database schema or migrations exist. | SQL packages only at `ai-cctv/backend/requirements.txt:5-7`; repository-wide inventory | No users, properties, incidents, evidence, assignments, or audit history can persist. |
| P1 | MQTT accepts anonymous network clients and has no TLS/ACL configuration. | `ai-cctv/deployment/mosquitto/config/mosquitto.conf:1-5`; exposed port at Compose `:8-13` | Any reachable client can publish/subscribe and spoof or observe events. |
| P1 | Frigate runs privileged and maps the full USB bus even though the configured detector is CPU-only. | Compose `:18-22`; Frigate `:8-11` | Unnecessary host access expands compromise impact and harms portability. |
| P1 | No health checks, readiness gates, application-level retries, durable consumer, idempotency, or dead-letter path exist. | Compose `:3-49`; subscriber `:21-60` | Startup races and outages can drop or duplicate security events. |
| P1 | Frigate metadata is configured under `/config/frigate.db`, but only the YAML file—not the `/config` directory/database—is persisted. | Frigate `:13-14`; Compose `:28-35` | Metadata persistence across container recreation is not established. |

## Completed or configured capabilities

- One logical camera (`front_door`) is configured for 1280×720 detection at 5 FPS (`ai-cctv/frigate/config/frigate.yml:16-20`, `:32-47`). Status: **CONFIGURED ONLY**.
- Person-only tracking filters and confidence thresholds are configured (`ai-cctv/frigate/config/frigate.yml:22-30`, `:45-47`). Status: **CONFIGURED ONLY**.
- Seven-day motion recording, fourteen-day event retention, and snapshots with bounding boxes are configured (`ai-cctv/frigate/config/frigate.yml:48-64`). Status: **CONFIGURED ONLY**.
- Frigate MQTT publication to broker host `mqtt` and topic prefix `frigate` is configured (`ai-cctv/frigate/config/frigate.yml:1-6`). Status: **CONFIGURED ONLY**.
- The subscriber has defensive UTF-8/JSON exception handling but only displays payloads (`ai-cctv/tests/test_mqtt_subscriber.py:31-41`). Status: **IMPLEMENTED, UNVERIFIED** as a manual diagnostic.

No feature is classified **VERIFIED WORKING** because no appropriate end-to-end or service runtime check succeeded.

## Top ten immediate actions

1. Make the three-container Phase 1 stack deterministic: eliminate the port collision, configure an actual MediaMTX source/publisher, correct Frigate environment substitution, and add readiness health checks.
2. Add a reproducible smoke test proving camera/sample → Frigate event → MQTT event, with captured command evidence.
3. Define and migrate the minimum PostgreSQL model for users, properties, cameras, incidents, evidence, event receipts, notifications, assignments, and status/audit history.
4. Implement a durable MQTT adapter with schema validation, reconnect/backoff, idempotency keyed by source event ID, and a retry/dead-letter strategy.
5. Implement the smallest security rule: eligible `person` detection in a configured zone creates exactly one incident transactionally.
6. Build the FastAPI application with health/readiness, authentication, property-scoped authorization, camera/incident/evidence APIs, and versioned schemas.
7. Implement authenticated real-time incident delivery and camera status; define delivery/replay semantics.
8. Build one real dashboard path using those APIs and live endpoints; do not introduce mock production fallbacks.
9. Implement the minimal marshal dispatch state machine with atomic assignment, acknowledgment timeout, escalation, resolution, and immutable history.
10. Add CI for lint/type/unit/API/integration/security tests, pinned dependencies/images, secret scanning, backup/restore verification, and least-privilege deployment.

Detailed, dependency-aware tasks and acceptance criteria are in `12-development-roadmap.md`.

## Evidence limitations

- Docker/Compose was unavailable, so containers, stream flow, config parsing, and service health were not run.
- There are no local divergent branches; only `main` and its matching `origin/main` were visible. Remote-only or unpushed work cannot be assessed.
- External camera, notification, cloud, property, and marshal systems were not present.
- Frigate is a third-party image; its internal tables and behavior are not application source in this repository.

