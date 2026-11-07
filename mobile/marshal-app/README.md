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

Metro uses port 8082, so the owner app can remain running on 8081. Open the QR
in SDK 58 Expo Go on the same network. This app currently has no remote push
integration; keep it foregrounded to receive updates through 10-second polling.
Incoming offers repeat an offline two-tone alarm and vibrate while foregrounded.
The alert stops on accept, decline, expiry, cancellation, sign-out or
backgrounding. Silence affects current offers; a new job sounds again. Device
media volume controls audibility. Background/terminated delivery requires
configured remote push in a development/release build.
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

Sign in → go on duty → review assignment → accept or decline → open directions
→ start journey → confirm arrival → record investigation/resolution notes →
confirm resolution. History contains completed, declined, expired and cancelled
assignments. Pull to refresh is available on each tab/detail.

The backend verifies active marshal membership and profile for every marshal
workspace request. Only personally assigned incidents are returned. Progress
commands retain the backend's current-version conflict checks. Duty heartbeats
are foreground-only; eligibility expires after five minutes without an update.
Going off duty does not cancel accepted work. Sign-out revokes the account's
existing application sessions, consistent with the backend auth model.

Owner dispatch offers have a five-minute deadline and can target several
selected on-duty marshals. The first acceptance wins and closes other offers.
Incident photos and camera snapshots appear in assigned jobs through
short-lived authenticated grants. Cancelled/expired offers lose media access.
Image errors offer a fresh-link retry. Video playback remains a command-center
task in this client.

The UI requires an on-scene note before resolution, but the existing general
dispatch API retains its previous completion contract. `ON_SCENE` covers arrival
and investigation; `COMPLETED` resolves the incident. Distinct investigating and
closed states, supervisor closure, evidence capture/upload, chat,
push dispatch and background availability are **not implemented** in this first
version. Navigation opens an external maps app using the supplied coordinates
or property address. During active assignments the app requests foreground
location permission and publishes its latest position. Owners can see that
position and an estimated arrival time for incidents with coordinates. Estimates
use GPS speed or a documented fallback, without traffic data. Background location
tracking and historical GPS storage are not implemented.

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
