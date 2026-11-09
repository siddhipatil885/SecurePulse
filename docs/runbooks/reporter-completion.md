# Reporter features and live acceptance

Prepared 2026-11-05. Camera/media bytes remain on the host. Neon holds identity,
permissions, incident metadata and notification outbox/receipt metadata.

## Implemented behavior

- Reporter cameras show live Frigate health (`online`, `offline`, `disabled` or
  `unknown`). Failed/stale health is never represented as a connected camera.
  Health is cached for five seconds in memory; it does not create Neon telemetry
  rows. Summary counts distinguish active actionable/confirmed camera records,
  the user's own open reports, and active alerts. They do not claim a property is safe.
- Native live video uses go2rtc HLS/fMP4 through the backend. Every playlist/init/
  segment URL is signed for its exact resource, user, property and camera. Access
  rechecks account/membership/version and camera state, and cannot outlive the
  parent login. Upstream credentials/stream names are not returned to the app.
  External playlist URIs are rejected. Reads are bounded; nothing is saved to
  Neon. Stop/background/unmount releases the native player; grants refresh while viewing.
- Password recovery and email verification use Managed Auth email OTP APIs.
  Requests give a generic acknowledgement to avoid account enumeration; requests
  and verification are rate limited. Reset revokes managed-account application
  sessions/devices. Existing local-hash accounts still require administrator help.
  No provider credentials, OTPs or passwords are stored on the device.
- Expo push resolves current active devices, property membership and explicit
  category opt-in for every attempt. Messages contain generic text and authorized
  record references, not incident descriptions, locations or media. Provider
  tickets are polled for receipts, acknowledged devices are not resent on receipt
  polling, bad registrations are disabled, and send retries stop after five attempts.
  Receipt polling reuses metadata rather than growing a row per poll. Accepted
  tickets are not called delivered. `SENT` means provider hand-off was confirmed;
  it does not prove that a device displayed or a person saw the notification.
- Notification taps check the signed-in user/property and open the report/alert.
  Sign-in refreshes registered tokens for existing opt-in without prompting for
  permission. Settings handles permissions and offers a self-test with receipt status.
- Dashboard acceptance runs against isolated fixtures in Chromium and WebKit.
  Firefox is excluded at the user's request. Test reset routes exist only in the
  isolated test server, never in the production application.

## Main PC acceptance

The actual PC address/remote access was not supplied. Run these commands on that
PC after deploying the changes and preserving its private env/media/volumes.

```powershell
python backend/scripts/configure_client_host.py
python backend/scripts/accept_reporter_host.py --email YOUR_REPORTER_EMAIL --decode
```

The second command prompts for the password. It reads readiness, authorized
properties/counts/cameras, obtains scoped live playlists and uses FFmpeg to decode
one camera frame. It does not mutate reports/devices, restart services, migrate,
or send notifications. Missing dependencies, disabled/offline cameras or decode
failure produce a failure result. Sanitized evidence is written under ignored
`backend/operational-evidence/`; passwords/tokens/media grants are not included.
Use `--url` if the host does not expose the backend at `127.0.0.1:18000`.

For host capture, MQTT, moving overlays and restart recovery, also run the
existing [main-PC acceptance sequence](main-host-handoff.md). Confirm the actual
publisher paths and perform both camera walk-throughs; synthetic tests are not
evidence of a functioning physical camera. HLS compatibility/codecs depend on the
actual go2rtc/camera/player combination; prefer H.264 for broad device support.

## Configure push and a development build

Repository inspection found no Expo login, no project ID in mobile env, no native
signing/push credentials and no physical Android/iOS device access. Do not invent
project IDs or mark push delivery passed based on mocked requests.

From `mobile/reporter-app`, use your own Expo account:

```sh
npx eas-cli login
npx eas-cli init
```

Set the actual `EXPO_PUBLIC_EXPO_PROJECT_ID` and phone-reachable
`EXPO_PUBLIC_SERVER_URL` in the private mobile env. Register those public values
in the matching EAS development environment as well when building in the cloud;
ignored local env files are not a replacement for EAS environment configuration.
`app.config.js` validates the project UUID and provides configurable native IDs
(`EXPO_ANDROID_PACKAGE` / `EXPO_IOS_BUNDLE_IDENTIFIER`). Confirm those identifiers
belong to this app before release. `eas.json` includes development, preview and
production profiles, and the SDK-compatible development-client package is installed.

Configure Android FCM v1 / iOS APNs credentials with your Expo/platform accounts,
then build a native development client:

```sh
npx eas-cli build --profile development --platform android
# For an appropriately provisioned iOS device:
npx eas-cli build --profile development --platform ios
npx expo start --dev-client
```

Use HTTPS for deployed builds. For development the phone must reach the actual
PC on the same network; Metro does not tunnel the backend. Camera media remains
on that PC. Remote push is not validated by Expo Go or by a JS bundle export.

On the backend, explicitly select `DISPATCH_NOTIFICATION_PROVIDER=expo` and restart.
If Expo enhanced push security is enabled, put its token only in the backend's
private `EXPO_PUSH_ACCESS_TOKEN`. Delivery remains `disabled` in current private
runtime configuration because the required Expo project/credentials are absent.
No external notifications were sent from this workspace.

On the physical device, enable a category in Settings and use **Send test
notification**. Check the device banner and server receipt status. Repeat in
background/terminated states, tap a real incident update, and check category
opt-out, token refresh, logout, permission denial and property revocation. Network
timeouts cannot guarantee exactly-once delivery; app data access remains authorized.

## Recovery and physical-device checklist

- Use an inbox you control to request a password code, reset once, reject a reused/
  expired code, and verify the old password and application sessions stop working.
- Verify an email using its code and sign in afterward. Confirm Managed Auth mail
  delivery/OTP configuration in the actual Neon project; a mocked API response
  does not prove email reached an inbox. The backend reports provider configuration/
  delivery errors without exposing provider payloads.
- Android and iOS: keyboard/scrolling, large text, location/photos permissions,
  property switching during requests, app background/foreground and deep links.
- Play each real camera, stop it, lose/recover Wi-Fi, revoke property access and
  sign out while streaming. Confirm no old-property video remains visible.
- Submit an image and MP4 report; interrupt/retry upload, reopen evidence and seek
  the MP4. Confirm no duplicate report and that bytes exist only on the PC.
- Complete the dashboard offer/cancel/reoffer and marshal resolution workflow.

## Local commands and sources

```sh
# backend/
python -m pytest -q
# backend/dashboard/
npm test
npm run build
npm run lint
npm run test:browser
# mobile/reporter-app/
npm run typecheck
npm test
npx expo install --check
npx expo export --platform android --platform ios --output-dir dist
```

Install Chromium/WebKit with Playwright first. Installed Google Chrome can be
selected with `PLAYWRIGHT_CHROME_CHANNEL=chrome`. Tests use temporary SQLite/media
and a controlled upstream/provider; no deployment data or external notifications
are touched. Real camera playback, mail receipt and push/device receipt still
require the acceptance above.

Primary references: [go2rtc HLS](https://github.com/AlexxIT/go2rtc/blob/master/internal/hls/README.md),
[Expo push tickets and receipts](https://docs.expo.dev/push-notifications/sending-notifications/),
and the branch's published Managed Auth `/open-api/generate-schema` OTP contract.
