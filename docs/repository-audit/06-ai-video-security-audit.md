# AI, Video, MQTT, and Security Intelligence Audit

## Camera and streaming

### What is configured

- One camera named `front_door` reads a single path for both `detect` and `record` roles (`ai-cctv/frigate/config/frigate.yml:32-44`). Additional cameras are structurally possible in Frigate but not repository-configured.
- Global and camera-specific detection are set to 1280×720 at 5 FPS (`frigate.yml:16-20`, `:40-44`).
- MediaMTX is declared as `rtsp-sim`, but there is no MediaMTX configuration, input file, FFmpeg publisher, or command (`ai-cctv/deployment/docker-compose.yml:43-49`). It is not a complete simulator.
- Frigate internally invokes FFmpeg; no repository-owned FFmpeg process manager exists (`frigate.yml:34-39`). ONVIF is mentioned only in the README (`README.md:29`, `:84`) and has no config/code.
- RTMP is absent. Frigate exposes RTSP/go2rtc and WebRTC host ports (`docker-compose.yml:23-27`), but no dashboard consumes them.

### Static blockers and risks

1. Frigate and MediaMTX both publish host `8554` (`docker-compose.yml:25`, `:49`), creating a port binding conflict.
2. The mounted Frigate YAML contains `${RTSP_STREAM_URL:-...}` (`frigate.yml:36`). Compose interpolation applies to the Compose document, not arbitrary bind-mounted file content. Frigate documents supported camera-path substitution as `{FRIGATE_*}`. The container sets `RTSP_STREAM_URL`, not a referenced `FRIGATE_*` variable (`docker-compose.yml:36-39`). Runtime behavior is therefore expected to fail or use the literal text; Docker absence prevented confirmation.
3. `depends_on` includes MQTT but not `rtsp-sim` (`docker-compose.yml:40-41`); neither dependency has a health check.
4. Linux-only mounts/devices (`/etc/localtime`, `/dev/bus/usb`) conflict with the observed Windows development host (`docker-compose.yml:21-22`, `:29`). Docker Desktop/WSL behavior requires human verification.

## Detection, tracking, and identity

| Capability | Status | Evidence / limitation |
|---|---|---|
| Object detection | CONFIGURED ONLY | Frigate CPU detector (`frigate.yml:8-11`) |
| Person detection | CONFIGURED ONLY | Only `person` tracked (`:22-30`, `:45-47`) |
| Vehicle detection | NOT IMPLEMENTED | README planned only (`README.md:40`) |
| Object filtering | CONFIGURED ONLY | `min_area`, `max_area`, `min_score`, `threshold` (`frigate.yml:25-30`) |
| Object tracking | CONFIGURED ONLY | Frigate tracking is implied by tracked objects/events; no custom tracker code/test |
| ByteTrack specifically | NOT IMPLEMENTED/UNVERIFIED | README claims it as planned (`README.md:45`, `:128-129`); no implementation/config names ByteTrack |
| Face detection | NOT IMPLEMENTED | No model/code/config |
| Face recognition | NOT IMPLEMENTED | README explicitly states no facial identity matching (`README.md:278`) |
| Persistent person identity | NOT IMPLEMENTED | Frigate event/track IDs are event-local tracking identifiers, not biometric/cross-camera identity; re-identification is deferred (`README.md:326`) |
| Restricted zones | NOT IMPLEMENTED | Empty backend zone placeholder; no Frigate zones configured |
| Intrusion/line crossing/loitering | NOT IMPLEMENTED | Planned prose only (`README.md:131-141`) |
| Custom YOLO model | NOT IMPLEMENTED | CPU detector only; no model path or model artifact |
| GPU acceleration | NOT IMPLEMENTED | CPU detector; no hwaccel/runtime GPU config |
| Coral support | PARTIALLY CONFIGURED | Full USB bus mapped with comment, but detector remains CPU (`docker-compose.yml:21-22`; `frigate.yml:8-11`) |

Detection boxes are configured on stored snapshots (`frigate.yml:57-64`) and the Frigate UI is expected to show them according to documentation (`phase1_setup.md:70-75`), but no SecurePulse UI exposes boxes or tracking IDs.

## Recordings, snapshots, and live view

- Motion-mode recordings retain seven days; event recordings retain fourteen days while objects are active (`frigate.yml:48-56`).
- Snapshots are enabled for fourteen days with timestamp and bounding box (`:57-64`).
- Media files bind to `ai-cctv/frigate/media` (`docker-compose.yml:31`); no encryption, quota, backup, evidence catalog, integrity hash, legal hold, or authorized retrieval exists.
- Frigate ports suggest its own UI/live paths (`docker-compose.yml:23-27`), but the dashboard is empty. No production reverse proxy or stream token exists.
- Camera-offline/FFmpeg failure handling is left to upstream Frigate/container restart behavior; there is no application health model, alert, retry policy, or status history.

## MQTT broker and topics

The broker listens on all interfaces, allows anonymous clients, persists broker data, and logs to stdout (`mosquitto.conf:1-5`). No username/password, ACL, TLS certificate, topic authorization, connection limit, or bridge is configured.

Frigate publishes under prefix `frigate` (`frigate.yml:1-6`). The subscriber requests:

- `frigate/events`
- `frigate/stats`
- `frigate/+/person`
- `frigate/+/person/state`

All are requested at QoS 0 (`test_mqtt_subscriber.py:13-18`). The repository contains no publisher besides the third-party Frigate image and no downstream consumer besides this utility.

## Actual event trace

1. Frigate is configured to detect a person in `front_door` (`frigate.yml:32-47`).
2. Frigate is configured to connect to `mqtt:1883` with topic prefix `frigate` (`:1-6`).
3. The manual subscriber connects to `localhost:1883`, subscribes on success, and blocks in `loop_forever()` (`test_mqtt_subscriber.py:21-29`, `:44-53`).
4. On a message, it decodes UTF-8, attempts `json.loads`, and prints parsed JSON or raw text (`:31-41`).
5. Processing ends. No normalized event, rule evaluation, API call, database write, incident, alert, or acknowledgment occurs.

The event example in `phase1_setup.md:89-103` contains `type`, `before`, and `after` with `id`, `camera`, `label`, score, snapshot, and clip flags. It is documentation, not a schema class, fixture, or captured test.

## Event failure semantics

| Scenario | Current behavior |
|---|---|
| Duplicate event | Printed again; no deduplication |
| Malformed JSON | Printed as raw text (`test_mqtt_subscriber.py:35-39`) |
| Invalid UTF-8 | Caught/logged generically (`:31-41`) |
| Missing fields | Not accessed or validated, so printed without rejection |
| Out-of-order event | No ordering/correlation logic |
| MQTT disconnect after initial connect | Paho behavior is unconfigured; no explicit backoff/status/alert |
| Initial broker unavailable | Exception logged and process exits status 1 (`:50-60`) |
| Backend unavailable | No backend call exists |
| Database failure | No database call exists |
| Consumer restart | Clean session/durable subscription not configured; QoS 0 means missed messages are not recoverable by this client |
| Processing acknowledgment | None |

## Security intelligence engine

No engine exists. There is no entrypoint, candidate schema, confidence rule code, spatial/temporal rule, severity mapping, correlation, suppression, scoring, escalation, camera-specific policy, persistence adapter, or tests. The Frigate confidence/area filters are detector input filters, not a SecurePulse incident rule engine (`frigate.yml:25-30`). The only proposed rule concepts are README prose (`README.md:121-141`).

Accordingly, no implemented rules can be explained or traced beyond: “Frigate should track objects labeled person that pass configured score/area thresholds.” A raw Frigate detection currently becomes console output, not a security incident candidate.

