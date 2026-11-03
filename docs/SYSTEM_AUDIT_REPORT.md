# SecurePulse system audit

**Audit date:** 2026-11-03
**Scope:** `C:\SecurePulse`, the Person 1 checkout at `C:\SecurePulse-person1`, and Docker services visible on this host.

## Repository and runtime layout

There are multiple stacks running on this host. They are distinct deployments and must not be treated as one Compose project.

| Stack | Evidence and role | Status |
|---|---|---|
| Person 1 stack | Compose source `C:\SecurePulse-person1\backend\deployment\docker-compose.yml`; project `securepulse-person1`; backend `127.0.0.1:18000`, Frigate `127.0.0.1:15000`, MediaMTX `127.0.0.1:18554`, MQTT `127.0.0.1:11883`, PostgreSQL `127.0.0.1:15432` | Running; backend, Frigate, PostgreSQL, and MQTT healthy. `sample-publisher` is opt-in and exited. This is the validated Person 1 runtime. |
| Integrated checkout | `C:\SecurePulse`, branch `integration/person1-video-frigate-mqtt-20261103` | Working tree contains uncommitted integration work and user changes. It is not the source of the currently running Person 1 containers. |
| Legacy `deployment` stack | Services include `securepulse-backend`, `securepulse-postgres`, and `securepulse-mqtt`; ports 8000/5432/1883 bound on all interfaces | Running. Backend/Postgres healthy. MQTT permits anonymous access in the active untracked `mosquitto-original.conf` and is exposed on all interfaces; treat as a security finding. It was not changed during this audit. |
| Standalone Frigate | Container `frigate`; ports 8554, 8556, and 8971 exposed on all interfaces; bind mounts use `C:\SecurePulse\frigate\config` and `storage` | Running and healthy. This is separate from Person 1 Frigate. |

The Person 1 directory was preserved. No commit or push was performed, no volumes or databases were deleted, and no migrations were applied. The Person 1 Frigate service was restarted to load its corrected config; the Person 1 Mosquitto ACL was reloaded in place. Recovery copies are under `C:\SecurePulse-recovery-20261103\live-audit-20261103`; the previously created recovery branches/bundle remain available.

## Findings and repairs

1. **Person 1 detector was disabled at runtime.** Frigate 0.13.2 had `front_door.detect.enabled=false` despite a valid YAML config. The runtime UI/WebSocket command had switched it off. Detection was enabled through Frigate's supported local control channel, and the Frigate service was restarted after the camera config was corrected. Both cameras now report detection enabled and global detection FPS was approximately 14.6 after restart.
2. **Person 1 had a camera mapping gap.** The backend database listed `front_door` and `laptop_camera`, but Person 1 Frigate only exposed `front_door`. A go2rtc restream and Frigate camera entry were added for `laptop_camera`.
3. **The front-door detection dimensions did not match the actual source.** The stream is 640x480, so its configured detect size is now 640x480. `laptop_camera` is 1280x720. Both sources were confirmed as H.264 at 15 fps using a bounded ffprobe from the Frigate network.
4. **Snapshots were not enabled for these cameras.** Snapshots are now enabled with 14-day retention; recording remains disabled.
5. **Person 1 MQTT ACL did not permit Frigate to receive camera control topics.** Least-privilege read access to `frigate/+/+/set` was added for the Frigate user. The broker ACL was reloaded and a five-case ACL smoke check passed. The backend can subscribe to events; Frigate can receive its control topic; unauthorized publish/read and invalid credentials were denied.
6. **Health status could hide disabled detection.** Integrated code now includes per-camera `detection_enabled` and global `detection_fps`, and marks an explicitly disabled detector as `detection_disabled`. Regression assertions were added. The health module was synced to `C:\SecurePulse-person1`, then only the Person 1 backend image was rebuilt and its container recreated. `/health/edge` correctly reported `detection_disabled` during a runtime-off sample; after ON control the final status was `ok` with both cameras enabled.
7. **A fake publisher was part of the default edge stack.** It is now opt-in via the `test-pattern` Compose profile and no longer starts as a Frigate dependency. It must not be used as evidence of real-person detection.
8. **The observed dashboard percentage above 100% was not reproduced.** The two APIs inspected returned confidence values in the 0..1 range (Person 1 max 0.805; legacy max 0.844); the dashboard multiplies valid confidence by 100. No confidence-format code change was indicated by the live data.

9. **WebRTC candidate template was not expanded.** Running go2rtc config showed literal `{FRIGATE_WEBRTC_CANDIDATE}` despite the container variable being `127.0.0.1:18556`. Frigate's [configuration docs](https://docs.frigate.video/configuration/advanced/system/) describe environment substitution for supported fields and the go2rtc section's separate handling; its [live view guide](https://docs.frigate.video/configuration/live/) requires a reachable WebRTC candidate. Both Person 1 and integrated Frigate configs now contain the literal host-local candidate `127.0.0.1:18556`; only Person 1 Frigate was restarted. Effective go2rtc config confirmed the candidate. The bind stays loopback-only. Browser playback remains to be checked manually.

## Security and operational risks

- The legacy broker is anonymously accessible and published on all interfaces. Its live config is untracked at `C:\SecurePulse\mosquitto-original.conf`; it was intentionally left running and untouched. Secure it during an approved maintenance window, then verify dependent clients.
- Standalone Frigate and legacy service ports are exposed on all interfaces. The Person 1 service ports are loopback-bound. Review whether LAN access is actually required before changing bindings or WebRTC ICE candidates.
- The Vite dashboard listens on all interfaces while its API proxy targets Person 1 backend port 18000. This is useful for LAN browser access, but the Person 1 WebRTC candidate is loopback-only, so remote LAN browser streaming may fail.
- The old `deployment` backend and the Person 1 backend have separate databases, brokers, ports, and Compose project/volumes. Use the Person 1 URLs above for this feature verification.

## Verification summary

- Person 1 Frigate config parsed with installed 0.13.2 schema; Compose config validated with default and `test-pattern` profile. The latest Frigate restart loaded the corrected candidate and health reported both cameras enabled and online.
- Both camera snapshots returned HTTP 200. Both go2rtc streams had active producer and consumer.
- Person 1 `/health/edge`: MQTT connected, Frigate reachable, both cameras online, queue depth 0, no invalid messages or processing failures. `last_event_at` was null.
- Backend full test suite after repair: **236 passed, 7 skipped**. Reporter tests use SQLite with SQLAlchemy `JSON` and a PostgreSQL `JSONB` variant; no tests or assertions were removed.
- Dashboard production build and lint passed. Smoke-test PowerShell syntax and `git diff --check` passed.
- Two live person-labeled events from `laptop_camera` were traced through Frigate event details/snapshots, backend MQTT listener health, PostgreSQL rows, and the backend events API. The observation was not a controlled person walk-through; `front_door` still needs a fresh event and browser WebRTC playback remains unverified.

See [system health](SYSTEM_HEALTH_REPORT.md), [end-to-end results](END_TO_END_TEST_REPORT.md), and [remaining work](REMAINING_WORK.md).

## Dashboard overlay and camera follow-up (2026-11-03)

- **Overlay path/root cause:** `CameraFeed` plays raw go2rtc WebRTC video in an HTML `<video>` element. It does not use Frigate's annotated video. `DetectionOverlay` draws HTML boxes from backend `person_tracks` WebSocket updates. At inspection, both Frigate runtime detectors had been toggled off, `/api/v1/tracks` was empty, and all 26 persisted track rows were `TEMPORARILY_LOST`. Historical person events therefore had no current boxes to draw. The UI label also omitted class confidence except in debug mode.
- **Frigate instance distinction:** `https://localhost:8971` is the separate standalone `frigate` container (stable/0.18 config, camera `webcam` from MediaMTX `/webcam`). SecurePulse dashboard backend points to Person 1 Frigate on `127.0.0.1:15000` (0.13.2, cameras `front_door` and `laptop_camera`). Both can consume the laptop `/webcam` path, but their live trackers/configuration are separate. A box seen in the standalone UI is not evidence that the Person 1 backend received a corresponding track.
- **Live track/count repair:** the backend live track snapshot and WebSocket projection now exclude `TEMPORARILY_LOST` tracks; an end lifecycle publishes an empty active set. Dashboard rendering filters by camera and active person state, removes duplicate track IDs, draws class-colored boxes with class/confidence labels, and counts only active person tracks. “Live person tracks” describes camera sessions, not unique identities; no re-identification is implemented.
- **Confidence investigation:** live Person 1 and Vite-proxied APIs/track messages returned fractional confidence 0.701–0.844. `RecentEvents` multiplies those values by 100 once, which yields 70–84%. The reported 271–284% discrepancy was not reproduced, so confidence conversion was not changed. Capture a fresh matching UI/API sample if it recurs.
- **Front Door root cause:** the path is host capture publisher → MediaMTX `/live` → go2rtc `front_door` → Frigate. Backend camera id 1 is enabled; Frigate camera/process FPS were positive; latest snapshot returned HTTP 200; go2rtc had an active producer. Bounded FFmpeg decoded H.264 640x480 but black-frame detection flagged direct MediaMTX `/live` and the go2rtc `front_door` restream. The independent `/webcam` laptop source decoded without a black-frame indication. The black content originates at the capture/publisher feeding `/live`, before Frigate. No camera/publisher config was changed.
- **Live track verification:** after detection was enabled through Frigate's local control channel, both cameras reported `detection_enabled=true`; backend health was `ok`. A later backend WebSocket observer received real `person_tracks` updates for laptop camera id 2, with one active track, normalized bounding boxes, confidence 0.70–0.73, followed by empty sets at track end. The track API was empty after those end messages. The Vite WebSocket proxy accepted a connection but no camera event occurred during its separate observation window. No synthetic event was sent. Browser box rendering/playback was not independently observed.
- **Additional live events:** after detection was re-enabled, Frigate emitted laptop person events including `1793715902.951306-86y7l4` (snapshot HTTP 200, matching PostgreSQL row 27) and later detections. At the latest check PostgreSQL had 35 security events/track rows, all tracks `TEMPORARILY_LOST`. Current Person 1 confidence values remain fractional. This verifies real event-to-database processing and the backend live track publisher, not visible browser overlay rendering or a controlled walk-through.
- **Verification after overlay repair:** backend suite **236 passed, 7 skipped**; dashboard production build and lint passed. Person 1 backend was rebuilt/recreated only; its database count rose naturally from 26 to 27 due to the live event, not a reset. Frigate, MediaMTX, MQTT, and PostgreSQL volumes were preserved.

See [the end-to-end report](END_TO_END_TEST_REPORT.md) for test details and remaining manual acceptance.
