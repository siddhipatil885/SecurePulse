# SecurePulse system health

**Observed:** 2026-11-03, live host state at audit time. Health can change after this snapshot.

## Person 1 runtime (`securepulse-person1`)

| Component | Health | Notes |
|---|---|---|
| Backend | Healthy | `127.0.0.1:18000`; `/health/edge` reports `status=ok`. |
| PostgreSQL | Healthy | `127.0.0.1:15432`; no migration was run in this audit. |
| Mosquitto | Healthy | `127.0.0.1:11883`; authenticated ACL smoke checks passed. |
| Frigate | Healthy after restart | `127.0.0.1:15000`; both cameras currently enabled for detection; last observed global detection FPS 8.9. |
| MediaMTX | Running | `127.0.0.1:18554`; RTSP paths `/live` and `/webcam` decoded as H.264, 640x480 and 1280x720 respectively, at 15 fps. No healthcheck is configured. |
| Dashboard dev server | Responded HTTP 200 | Port 5173; Vite proxy targets Person 1 API at port 18000. |

After rebuilding only the Person 1 backend, `/health/edge` reported MQTT connected, Frigate reachable, both cameras online, `detection_enabled: true`, queue depth 0/256, zero queue rejections, zero processing failures, zero invalid events, and detection FPS ~19.5. A later check found both cameras toggled off; the deployed health route correctly returned `degraded` and `detection_disabled`. Sending ON commands over Frigate's local WebSocket restored both and a subsequent response returned `status: ok`; final stats showed both enabled but detection FPS was temporarily 0. Recheck during the controlled acceptance test.

Two new person-labeled Frigate events from `laptop_camera` were observed at 2026-11-03 13:48:03 and 13:50:50 UTC. Frigate returned event details and snapshots (HTTP 200); PostgreSQL rows 21 and 22 matched the Frigate IDs; `/api/v1/events` returned them; health `last_event_at` matched the last ingest. No fresh front-door event or controlled walk-through was captured. The sample proves a live laptop event reached persistence, not that both cameras passed human acceptance.

The effective go2rtc WebRTC candidate was initially the unexpanded string `{FRIGATE_WEBRTC_CANDIDATE}` even though the container environment had `127.0.0.1:18556`. The candidate field does not use that template substitution in this Frigate/go2rtc setup. It is now set to the literal `127.0.0.1:18556`, and the running config reports that address after a Person 1 Frigate restart. The host mapping remains loopback-only. This validates candidate configuration, not browser media playback.

## Other active projects

- Legacy `deployment`: backend/Postgres healthy; anonymous MQTT is exposed on TCP 1883 to all interfaces. This needs a controlled security change.
- Standalone Frigate: container healthcheck passed, ports exposed on all interfaces; independent from Person 1 stack.
- A stopped/exited Person 1 sample publisher is not a service failure. It is opt-in and supplies synthetic video only.

## Build and automated checks

- Dashboard `npm run build`: PASS.
- Dashboard `npm run lint`: PASS.
- Backend `python -m pytest -q`: **236 passed, 7 skipped** after the event metadata column was changed to SQLAlchemy `JSON` with a PostgreSQL `JSONB` variant. Assertions and test cases were retained.
- Compose rendering, Frigate configuration parsing, ACL smoke script, and whitespace check: PASS.

## Health interpretation

The `detection_disabled` repair is deployed in the Person 1 backend. The backend image was rebuilt from `C:\SecurePulse-person1` and only that service was recreated; databases, volumes, and other services were left in place. Current runtime camera state was verified through Frigate stats and `/health/edge`.

After the latest ON control, both Person 1 Frigate cameras were enabled and online; detection FPS varied with activity (up to 12.5 in one sample and 8.9 at the last stats check). Laptop person events reached Frigate and PostgreSQL (row 27 matched event `1793715902.951306-86y7l4`, snapshot HTTP 200; later rows were also created). A backend WebSocket observer received real active laptop track messages with normalized bounding boxes/confidence, then empty sets when tracks ended. At the latest database count there were 35 events and 35 track rows, all `TEMPORARILY_LOST`; live `/api/v1/tracks` was empty. No controlled walk-through or browser-rendered overlay was verified.

The dashboard uses raw WebRTC video plus a backend `person_tracks` HTML overlay. It does not use Frigate annotated video. Current API confidence samples (0.701–0.844) format to 70–84%; 271–284% was not reproduced. Front Door `/live` frames are black at the MediaMTX source and through the go2rtc restream; `/webcam` frames did not trigger black-frame detection. Dashboard WebRTC playback and visible overlay rendering were not independently confirmed. Backend suite: 236 passed, 7 skipped; dashboard build/lint passed.

The Frigate UI on port 8971 is a separate standalone deployment from the Person 1 Frigate API on port 15000 that the dashboard backend uses. Both reference the `/webcam` RTSP path, but runtime detections/tracks are not shared between those Frigate instances.
