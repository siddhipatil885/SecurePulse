# Remaining SecurePulse work

## Required to finish Person 1 acceptance

- [ ] Restore the host capture/publisher feeding MediaMTX `/live`; direct `/live` and go2rtc `front_door` frames trigger black-frame detection. Check the capture device and publisher logs, then verify non-black frames on `/live` before changing camera mappings.
- [ ] Complete a controlled authorized-person walk-through for both cameras. A new natural laptop event was traced through Frigate, snapshot, backend API, and PostgreSQL, but the active track ended before it could be seen in the live track API/browser. `front_door` has no fresh event. Follow the detailed checks in [the end-to-end report](END_TO_END_TEST_REPORT.md).
- [ ] Exercise browser WebRTC playback on the host for both cameras and verify advancing video. Laptop playback was reported by the user but not independently observed in this check; Front Door is upstream-black. The effective ICE candidate is fixed to `127.0.0.1:18556` and the port remains bound to loopback. Decide separately whether LAN clients need playback before changing exposure.
- [x] Resolve reporter test setup errors with a dialect-aware JSON type: generic SQLAlchemy `JSON` with a PostgreSQL `JSONB` variant. Full backend suite passes: 236 passed, 7 skipped.
- [x] Rebuild/redeploy only the Person 1 backend and verify `/health/edge` reports `detection_enabled` and `detection_disabled` status accurately. During this work it detected both cameras disabled; ON control restored them and the endpoint returned `ok` with both enabled. Recheck at acceptance time because Frigate runtime toggles can change.
- [x] Make live overlays and counts camera-specific and active-track-only, show object class/confidence with stable colors, and clear boxes at the Frigate end lifecycle. Backend tests and dashboard build/lint pass; backend WebSocket emitted real active laptop boxes and empty sets at end. Browser rendering/movement still needs direct visual confirmation.
- [ ] If confidence above 100% reappears, capture the exact dashboard event and matching `/api/v1/events` response. Current sampled values were 0.701–0.844 and display correctly as 70–84%; formatter was not changed.

## Security and deployment cleanup

- [ ] Schedule a maintenance window to disable anonymous access on the legacy MQTT broker exposed on all interfaces at TCP 1883. Inventory its actual clients first and verify they work with authenticated ACLs afterwards. The broker was intentionally not reconfigured during this audit because it is part of a live legacy deployment.
- [ ] Review all-interface exposure for standalone Frigate and legacy services. Restrict bindings to the required host/network and align WebRTC ICE candidates with the chosen access scope.
- [ ] Identify and document the canonical long-term Compose project. Keep Person 1, legacy deployment, and standalone Frigate separate until their data and consumers are understood.
- [ ] After code review, commit the intended integration changes on the integration branch. No commit or push was made as part of this audit. Preserve `C:\SecurePulse-person1` until the original integrated project has passed its runtime verification, as requested.

## Operational follow-up

- [ ] Add a healthcheck for MediaMTX (or a bounded RTSP readiness probe) so Compose can detect a process that is running but not serving streams.
- [ ] Add a non-secret deployment inventory with Compose project names, source paths, ports, and volume ownership.
- [ ] Capture a baseline for CPU, memory, inference FPS, and event throughput under expected camera load.
- [ ] Test camera disconnect/reconnect and broker/backend restart recovery in a planned window, then record sanitized results.
