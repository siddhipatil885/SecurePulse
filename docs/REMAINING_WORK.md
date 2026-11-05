# SecurePulse completion status

Updated 2026-11-04. Repository work is prepared for the main camera PC. That PC
is unavailable from this session; host deployment and physical acceptance remain
pending. Use [the handoff](runbooks/main-host-handoff.md) for the exact sequence.

## Repository work completed

- [x] Identify canonical Compose source and document project, port, source-path,
  and volume ownership in [the inventory](DEPLOYMENT_INVENTORY.md).
- [x] Add bounded RTSP video readiness checks in the `video-readiness` Compose
  sidecar. A fresh video SDP is required for each configured publisher path.
- [x] Use dependency readiness (`/health/ready`) for backend Docker health.
- [x] Add host inventory, decoded-source/black-frame checks, CPU/memory/FPS/event
  baseline collection, and explicit single-service restart recovery commands.
- [x] Add a PowerShell host acceptance entrypoint and sanitized JSON evidence.
- [x] Disable anonymous access in both checked-in broker templates and preserve
  existing password files when running account setup.
- [x] Require explicit project selection for MQTT ACL checks; test anonymous
  rejection and use probe topics instead of changing a real detector setting.
- [x] Keep repository standalone Frigate bindings on loopback and behind an opt-in
  legacy profile. Remove the ineffective WebRTC candidate environment option;
  document the literal config field that actually controls the candidate.
- [x] Fix overlay projection when detection/playback resolutions differ, with
  cover/contain regression tests. Show LIVE on actual video playback.
- [x] Provide browser timing, moving-box, clearing and confidence diagnostics.
- [x] Add CI checks for dashboard geometry/build/lint, Compose rendering and
  PowerShell parsing. Remote CI execution remains pending a push.
- [x] Reporter JSON portability and live active-track filtering were previously
  integrated; Person 1 integration was merged into main in PR #9 (`43463fc`).

## Acceptance requiring the camera PC

Mobile reports now reach the unified operator dashboard, including evidence,
status commands, dispatch offer/cancel, and marshal progress through resolution.
The real mobile HTTP client and Chrome workflow run against temporary test
backends. See [mobile/backend integration](runbooks/mobile-backend-integration.md)
for deployment and device acceptance. Provider delivery, physical device checks,
and PostgreSQL concurrency acceptance remain pending.

- [ ] Deploy the prepared changes to the verified existing Compose project after
  inventory and database backup. Preserve `C:\SecurePulse-person1` and volumes.
- [ ] Restore the actual host capture publisher feeding `/live`; verify both
  `/live` and `/webcam` contain advancing, non-black camera frames.
- [ ] Complete an authorized-person walk-through for both cameras. Match fresh
  Frigate IDs and snapshots to backend API and PostgreSQL rows.
- [ ] Confirm browser WebRTC playback, correctly aligned moving boxes, counts,
  and clearing after departure. Use the browser helper and visual confirmation.
- [ ] If a confidence above 100% reappears, retain the exact displayed value,
  matching event ID and API confidence. Do not mark it reproduced without evidence.
- [ ] Secure the actual legacy broker's mounted, untracked config after identifying
  clients and configuring their credentials/ACLs. Repository edits do not change
  the previously observed `mosquitto-original.conf` on the PC.
- [ ] Apply reviewed network bindings to the actual legacy containers and verify
  their clients. Do not collapse projects or change volume ownership implicitly.
- [ ] Collect a baseline under representative camera load; record host hardware,
  workload, CPU/memory/FPS and persisted-event throughput.
- [ ] Run broker/backend restart recovery and controlled publisher disconnect/
  reconnect tests. Generate a fresh person event after recovery.

Historical host evidence is retained in [system health](SYSTEM_HEALTH_REPORT.md)
and [end-to-end results](END_TO_END_TEST_REPORT.md). Those observations were made
on 2026-11-03 and do not verify the new deployment.
