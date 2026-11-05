# Integration verification — 2026-11-04

Main was fast-forwarded from `43463fc` to `524fa36` before integration. Existing
uncommitted dashboard/mobile/backend changes were preserved and reapplied; merge
conflicts in startup and dispatch orchestration were reconciled. The pre-pull
recovery stash remains available. Work is local, uncommitted and not deployed.

## Verified locally

| Check | Result |
|---|---|
| Backend pytest suite | 309 passed, 11 PostgreSQL acceptance tests skipped |
| Dashboard geometry tests | 3 passed |
| Dashboard TypeScript/production build and lint | Passed |
| Chrome browser workflows | 6 passed |
| Mobile TypeScript check | Passed |
| Mobile Vitest, including real HTTP/backend integration | 23 passed |
| Mobile Expo Router Jest tests | 3 passed |
| Expo SDK dependency compatibility | Passed |
| Android and iOS JS/Hermes bundle export | Passed |
| Git whitespace and unresolved-conflict checks | Passed |

The browser workflow verifies account registration/property onboarding, cookie
sessions, property isolation under delayed responses, camera status history and
evidence, read-only access, logout, and adding properties. Its integrated manual
report test verifies creation/upload invalidations, evidence display,
acknowledgement, dispatch offer/cancel/reoffer, marshal completion and resolution.

The real mobile HTTP client test checks bearer login/profile, role response
parsing, cross-property denial, profile/preferences updates, creation retry
receipts and payload conflicts, attachment retry deduplication and authenticated
grants, dashboard dispatch, marshal progression, mobile resolution, password
rotation and logout revocation. Multipart bytes are sent through Node's FormData;
physical React Native file serialization and video playback still need device
acceptance. Separate unit tests cover frozen creation keys/properties, failed
uploads, concurrent retries, validation correction and stale session refreshes.

These tests use isolated temporary SQLite databases/media and local API servers.
They do not verify production PostgreSQL locks, migrations against existing data,
camera/MQTT/WebRTC runtime, external notification delivery, or physical devices.
Native exports are bundles, not signed application binaries.

## Still pending

- Deploy migrations/storage configuration and run PostgreSQL concurrency tests
  using the approved test database.
- Run camera-host and physical iOS/Android acceptance.
- Wire and verify a real push provider; disabled delivery retains pending intents.
- Resolve/review the existing Expo SDK 53 dependency audit before production.
  High-severity dependency advisories remain; compatible bundle export does not
  imply security clearance. No forced SDK migration was applied.
- Run the updated CI workflow after the changes are committed and pushed.

See [the integration runbook](../runbooks/mobile-backend-integration.md) and
[main-host handoff](../runbooks/main-host-handoff.md) for the remaining checks.
