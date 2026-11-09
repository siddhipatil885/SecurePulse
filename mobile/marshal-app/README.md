# SecurePulse Marshal

Separate native Expo SDK 58 app for provisioned QRT marshals. The owner app stays
in `../reporter-app`; owner accounts cannot use this marshal workspace.

Before duty, marshals complete the three-step identity, photo and emergency
contact form and wait for administrator approval. See
[private onboarding and review](../../docs/runbooks/marshal-onboarding.md).

Use Node 24.3+ (24 LTS recommended). From this directory:

```sh
npm ci
cp .env.example .env
# Set EXPO_PUBLIC_SERVER_URL to the phone-reachable backend origin, without /api/v1.
npm start -- --lan --go
```

Metro uses port 8082, so the owner app can remain running on 8081. Expo Go is
useful for UI work, but it cannot receive remote push or run the native
background location service. Use a development build on a physical phone to
validate those features.

## Urgent assignment alerts

On sign-in the app asks for notification permission, registers an Expo push
token, and enables the marshal's dispatch-alert preference. New assignment
offers use a high-priority notification, a dedicated Android alert channel,
vibration, and `assets/assignment-alarm.wav`. Tapping an alert opens that job.
The foreground repeating alarm remains as a backup while the app is open.

Link this app to an Expo project with `npx eas-cli@latest init`, set its UUID as
`EXPO_PUBLIC_EXPO_PROJECT_ID` in `.env` and in the selected EAS build
environment, then configure Android FCM v1 and iOS APNs credentials in EAS.
Set the backend's `DISPATCH_NOTIFICATION_PROVIDER=expo` and (when push security
is enabled) `EXPO_PUSH_ACCESS_TOKEN`. Build and install the native client:

```sh
npx eas-cli@latest build --profile development --platform android
# or --platform ios (requires Apple Developer credentials)
npx expo start --dev-client --port 8082
```

Notification sounds still follow the phone's channel, focus and volume
settings; those cannot be overridden by the app.
There is no web sign-in or default backend. Session credentials are kept in
SecureStore and validated before restored access. Account provisioning is an
administrator operation; no marshal is created automatically.

Deploy the updated backend, then provision a marshal from `backend/`:

```sh
python -m app.provision_reporter --email REAL_MARSHAL_EMAIL --name "Responder Name" --role marshal --property-id VERIFIED_PROPERTY_ID
```

Password is prompted. Existing accounts are never overwritten. The existing
model assigns one marshal profile to one property; multi-property response
territories require a future data-model change.

## Working flow

Sign in → complete approved onboarding → go on duty → review assignment →
accept or decline → open directions → start journey → confirm arrival → begin
investigation → attach field evidence and submit a summary → supervisor review →
closed or returned for more investigation. History contains completed, declined,
expired and cancelled assignments. Pull to refresh is available on each tab/detail.

The backend verifies active marshal membership and profile for every marshal
workspace request. Only personally assigned incidents are returned. Progress
commands retain the backend's current-version conflict checks. Duty heartbeats
are foreground-only; eligibility expires after five minutes without an update.
Going off duty does not cancel accepted work. Sign-out revokes the account's
existing application sessions, consistent with the backend auth model.

Owner dispatch offers have a five-minute deadline. Broadcast offers use first
acceptance; team invitations permit multiple responders to accept. Marshals can
request nearby backup, coordinate in a shared chat, assign task labels, capture
photos or videos, and upload field evidence. Incident and field media use
short-lived authenticated grants. Supervisors review the investigation and
either close the incident or return it to the marshal.
Navigation opens an external maps app using the supplied coordinates or property
address. During active assignments, the app requests foreground and background
location access and requests a point about every 15 seconds or after 20 metres
of movement. Android displays its required foreground-service notification. Owners
and dispatchers see the current point, recent route, and incident directions in
the owner app. The API exposes up to 24 hours of assignment-scoped GPS history.
If background permission is declined, location updates continue only while the
app is open. Location sharing ends when there is no active assignment or the
marshal signs out.

Location and push behavior still need physical-device acceptance using an EAS
development/release build; Expo Go cannot verify either background service.

## Verification

```sh
npm run typecheck
npx expo-doctor@latest
npx expo export --platform android --platform ios --output-dir dist
# from backend/
python -m pytest tests/test_marshal.py tests/test_dispatch.py -q
```

Real device sign-in, assignment handoff and maps navigation need physical-device
acceptance with a provisioned marshal and an actual dispatcher-created offer.
