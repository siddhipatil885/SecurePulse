# Mobile, dashboard and backend integration

Updated 2026-11-04 after pulling main at `524fa36` and reconciling the existing
dashboard/mobile work. Changes are local and have not been deployed.

## Shared workflow

1. Register an owner and property in the dashboard, or provision accounts using
   `app.provision_reporter`. Sign in to the reporter app with the same credentials.
2. Select an owner/reporter property. Submit a report with an address or coordinates,
   optionally attaching JPG, PNG or MP4 evidence. Each logical creation/upload keeps
   a stable retry key. A saved report is retained when its attachment fails.
3. Owners/dispatchers see both camera incidents and manual reports in the dashboard
   Incidents tab. Source-qualified references prevent overlapping IDs from mixing.
   Review location, evidence, history, and server-authorized status actions.
4. Offer an assignment to a fresh, available marshal. Cancel from the dashboard if
   necessary. The targeted marshal accepts, then progresses through EN_ROUTE,
   ON_SCENE and COMPLETED using the authenticated dispatch API. The reporter app
   is not a marshal client. Completion resolves the linked report or camera event.
5. Dashboard sockets invalidate the selected property's data; 10-second polling
   recovers missed updates. Mobile active report details poll every 10 seconds;
   history polls every 15 seconds and both screens support pull to refresh.

Camera/report data is checked against live property membership. Private manual
reports remain visible only to their creator and property operators. Logout and
password rotation revoke existing account sessions and disable registered devices.
The app clears local credentials/cache after password rotation and on logout.

## Deploy on the existing host

Follow [the main-host handoff](main-host-handoff.md) to identify the existing
project, preserve local secrets/volumes, back up the database and apply migrations
through `0017_reporter_active_assignment`. Back up the new reporter evidence volume
alongside the database. Do not replace the existing camera media directory.

Set backend authentication and a strong signing secret. Compose mounts camera media
read-only and reporter evidence separately with write access. For a direct Python
deployment, set `EVIDENCE_ROOT` to a private writable directory instead.

Set `EXPO_PUBLIC_SERVER_URL` to the phone-reachable backend origin, without
`/api/v1`. Use HTTPS for deployed native builds. The Compose backend defaults to
loopback; use the intended authenticated HTTPS gateway or a reviewed LAN binding
for development. A Metro tunnel does not expose the API. Rebuild the native app
after adding the location, picker, notification and video modules/configuration.

Notification preferences and Expo device registration are stored, but no external
delivery provider is wired. Keep `DISPATCH_NOTIFICATION_PROVIDER=disabled` for real
accounts; `recording-fake` is only for explicit local drills and never contacts a
recipient. Pending intent is not delivered push.

## Local verification

From `backend`, install `requirements-test.txt` and run `python -m pytest -q`.
From `backend/dashboard`, run `npm test`, `npm run build`, `npm run lint`, and
`npm run test:browser` (install Playwright Chromium first, or use
`PLAYWRIGHT_CHROME_CHANNEL=chrome` with installed Google Chrome).
From `mobile/reporter-app`, run `npm run typecheck`, `npm test`,
`npx expo install --check`, and
`npx expo export --platform android --platform ios --output-dir dist`.

Mobile integration tests start the real API on port 18082. Chrome tests use ports
18081 and 15173. They create temporary SQLite databases/media and never connect to
deployment databases, MQTT, camera hosts or push providers. Set
`DASHBOARD_TEST_PYTHON` if Python is not in `backend/.venv`.

## Acceptance still requiring a host or device

- Apply migrations and run the opt-in PostgreSQL disposable-schema concurrency
  suite against an authorized test database; SQLite cannot prove row-lock behavior.
- Run a physical iOS/Android report with GPS/address, interrupted creation/upload,
  image and MP4 preview, property switching, background/foreground and logout.
- Confirm the same report/evidence appears on the deployed dashboard; offer,
  cancel/reoffer, accept and complete an assignment, then observe mobile resolution.
- Configure a real notification provider before claiming push delivery; test
  opt-out categories, token replacement, logout revocation and actual receipt.
- Review the Expo SDK 53 dependency audit before a production build. The current
  dependency tree reports advisories, including high-severity findings in URI
  decoding and SDK/tooling transitive packages. A forced SDK/dependency migration
  is not included in this integration; native bundle checks are not a security
  audit or evidence that those advisories are resolved.
- Complete camera, MQTT, WebRTC and restart acceptance in the main-host handoff.
