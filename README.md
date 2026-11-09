# SecurePulse

SecurePulse connects camera detections to incident review, property-owner alerts
and marshal response. It combines Frigate/MQTT, a FastAPI backend, PostgreSQL,
a React command dashboard, and separate Expo apps for owners and marshals.

**Status: 9 November 2026.** Core incident response features are implemented in
the current working tree. Real-camera, physical-phone and live-provider
acceptance is still required before production sign-off. The complete PRD is
not delivered.

## What is done

| Area | Implemented |
| --- | --- |
| Accounts and access | Property memberships and role checks, JWT/cookie sessions, secure mobile token storage, managed sign-in and email-code recovery, and session/device revocation. |
| Camera pipeline | Frigate MQTT parsing, event normalization, database deduplication, anonymous person-track updates, camera health, and protected live-view/evidence access. |
| Security rules | Person detection, restricted-zone entry, loitering, line crossing and multiple-person rules, with confidence, score, severity and reason. Real-world accuracy still needs validation. |
| Owner app | Expo SDK 58 login, property selection, cameras/live viewing, detection review, incident reporting with optional image/video attachments, history and marshal assignment controls. |
| Dispatch | Duty/availability/capacity checks, five-minute offers, distance-ranked selection when incident coordinates exist, multi-marshal team offers, backup requests, task labels, first-acceptance locking for broadcasts, timeout/escalation handling and assignment history. |
| Marshal app | Separate SDK 58 app with onboarding, duty controls, assigned jobs, accept/decline, external-map navigation, incident and field photo/video viewing, capture/upload, team chat, notes, task splitting and response progress. |
| Marshal onboarding | Government-ID details/photos, portrait, personal and emergency contacts, consent, encrypted storage, manual administrator approval, duty gating and withdrawal. Passport, driving licence and voter ID are supported; Aadhaar is excluded from this manual flow. |
| Command dashboard | Property-scoped incident queue, filters, incident and marshal evidence, timeline, status actions, supervisor review, assignment/cancellation, team chat, and authenticated realtime updates with polling fallback. |
| Responder position | Active-job foreground/background location capture and up to 24 hours of assignment-scoped history. Owner mobile shows the recent route and current location; the dashboard shows latest position, age, distance and ETA. Physical-device cadence and background behavior remain to be verified; capture requests updates at 15 seconds/20 metres. |
| Incident downloads | On-demand JSON reports with the full timeline, notes, evidence metadata, assignments and notification history. Automatic closure reports, media bundles, GPS history and printable/shareable exports remain. |
| Notification infrastructure | Owner and marshal Expo registration, outbox delivery, receipts and notification taps; SMS, voice, WhatsApp and agency-webhook adapters. Live operation requires configured credentials and device acceptance. |
| Deployment foundations | Canonical Compose stack, migrations through `0023`, health checks, host handoff/recovery scripts, provider-setting passthrough, and a dedicated persistent volume for encrypted identity documents. |

The current marshal workflow is:

```text
Onboarding → Administrator approval → On duty → Offer / team invite
Accept → En route → Arrived → Investigating → Supervisor review → Closed
Decline / Expiry → Dispatcher follow-up or configured retry
```

Broadcast offers use first acceptance. Team offers let several responders
accept, coordinate in a shared chat, and take task labels. Supervisors approve
the investigation before the incident is resolved.

## What is left to build

| Workstream | Remaining work |
| --- | --- |
| Dependable marshal alerts and tracking | Push and background task code is present. Configure EAS project/APNs/FCM credentials and verify alerts and location on physical Android/iOS builds, including background/terminated states. The current tracking request interval is 15 seconds; the PRD target is 5 seconds. |
| Intelligent dispatch | Add skill matching, geographic coverage, incident-priority policy and traffic-aware travel estimates. Distance ranking needs incident coordinates; automatic camera-incident dispatch needs a reliable destination source and acceptance policy. |
| Response workflow acceptance | Team invites, backup requests, task labels, shared chat, field photo/video capture and upload, investigation, supervisor review and final closure are implemented locally. Add focused automated coverage and complete owner-to-marshal-to-supervisor drills on real devices. |
| Complete incident reports | Automatic report generation/storage at closure, printable/shareable exports, GPS history and a media package. Current on-demand JSON reports contain evidence references rather than embedded media and omit GPS history. |
| Sensors and SOS | Dedicated intrusion-sensor registration/adapters, sensor-camera event fusion, and a panic SOS workflow. A manual report form is already available. |
| Additional analytics | Weapon, tailgating, object-removal, camera-tamper and validated vehicle detection; explicit recommended actions and priority policies. |
| Operational tools | Administrator onboarding-review UI, contact verification where required, identity-key rotation, retention/deletion processes, SLA indicators, response-time analytics and QRT utilization. Review currently uses a trusted local CLI. |
| Scale and resilience | Durable pre-database ingestion, recoverable/shared realtime and rule state, load testing, high availability, monitoring/alerting and full data/media/key disaster recovery. |

One marshal profile currently belongs to one property. Owner multi-property
access exists; a shared response fleet spanning properties remains future work.

Facial recognition, ANPR, smart geofencing, dedicated medical/fire and other
safety workflows, wearables, predictive analytics, drones, city-wide networking
and insurance integration remain roadmap capabilities. Resolve the PRD's
placement of weapon detection in both functional scope and phase two before
making it an MVP release requirement.

## What still needs live verification

- Deploy to the verified camera PC and complete real person walk-throughs,
  streaming/evidence playback and false-alarm evaluation.
- Run an owner → incident → marshal → resolution drill on Android and iPhone,
  including permissions, maps handoff, stale locations, network loss and recovery.
- Configure HTTPS, Expo/platform push credentials and any selected external
  providers; verify real delivery and receipts. Agency webhooks need an approved
  receiving integration and do not directly connect to public emergency services.
- Exercise container replacement and backup/restore for the database, camera
  media, reporter attachments, encrypted identity documents and separate keys.
- Measure the PRD's availability, incident/notification/dispatch latency,
  five-second tracking and device-capacity targets. These targets are not yet
  demonstrated by the automated tests.
- Complete the production security/privacy review and required compliance work.
  Identity encryption and scoped API/media access do not establish end-to-end
  encryption for the whole platform or ISO 27001 certification.

**Next priorities:** validate the response workflow on physical devices, configure
push and background services, then finish skill/coverage-aware dispatch and
complete reports. Expand sensor and advanced-AI coverage after the security
pilot is accepted.

## Repository layout

| Directory | Purpose |
| --- | --- |
| `backend/app/` | API, authentication, incidents, security rules, dispatch, notifications and onboarding. |
| `backend/alembic/` | Database migrations. |
| `backend/dashboard/` | Owner/command-center React dashboard. |
| `mobile/reporter-app/` | Property-owner/reporter Expo app. |
| `mobile/marshal-app/` | Marshal response Expo app. |
| `backend/deployment/` | Canonical Compose stack and environment example. |
| `backend/scripts/` | Host setup, diagnostics, acceptance and recovery tools. |
| `docs/runbooks/` | Setup, deployment and operating instructions. |

## Local development

Use Python 3.12 and Node 24 LTS. Keep database URLs, signing keys, provider
credentials and private environment files out of Git and client-side variables.

1. Configure the intended development backend using
   [`backend/.env.example`](backend/.env.example) and the
   [backend setup guide](backend/README.md). Preserve existing private settings.
   Enable authentication, use a strong signing key and apply reviewed migrations
   to the intended database. Camera ingestion additionally needs Frigate/MQTT.
2. From `backend/`, activate its virtual environment, install
   `requirements-test.txt`, then run
   `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
3. From `backend/dashboard/`, run `npm ci` and `npm run dev`. For the direct
   backend above, set `VITE_BACKEND_URL=http://127.0.0.1:8000` in the private
   dashboard `.env.local`. The default Compose backend port is `18000`.
4. Configure `EXPO_PUBLIC_SERVER_URL` in each mobile app's private `.env` to the
   phone-reachable backend origin, without `/api/v1`. From each app directory,
   run `npm ci` and `npm start -- --lan --go`. Owner Metro uses `8081`; marshal
   Metro uses `8082`. Both require SDK 58-compatible Expo Go for this mode.

Expo Go supports the development app flow; remote push requires a configured
native development/release build. Identity uploads require HTTPS, a dedicated
`MARSHAL_IDENTITY_KEY` and private storage. Marshals must complete onboarding and
receive approval before going on duty.

Detailed guides: [owner app](mobile/reporter-app/README.md),
[marshal app](mobile/marshal-app/README.md),
[dashboard](docs/runbooks/dashboard.md),
[onboarding and review](docs/runbooks/marshal-onboarding.md),
[environment/phone setup](docs/runbooks/environment-setup.md), and
[Neon database/auth with host-local media](docs/runbooks/neon.md).

## Deploy on the camera PC

Follow the [main-host handoff](docs/runbooks/main-host-handoff.md) and
[deployment inventory](docs/DEPLOYMENT_INVENTORY.md) before selecting an existing
Compose project. Canonical configuration lives at
`backend/deployment/docker-compose.yml`. Preserve its data and volumes; copying
code or environment files does not copy camera footage or uploaded documents.

Delivery defaults to `DISPATCH_NOTIFICATION_PROVIDER=disabled`. Use `expo` for
app push or `routing` for app push plus configured external destinations.
Encrypted identity files persist separately in the `marshal_identities` volume;
back up their key separately. See the [dashboard deployment settings](docs/runbooks/dashboard.md#compose-notification-and-identity-settings).

After deploying on the verified host, run from the repository root:

```powershell
./backend/scripts/acceptance_host.ps1 -ProjectName YOUR_VERIFIED_PROJECT
```

During maintenance, `-RestartRecovery` also exercises broker/backend restarts.
Sanitized results go to ignored `backend/operational-evidence/`. Physical camera
walk-throughs and playback checks are still part of acceptance.

## Validation

Recorded on 7 November 2026: feature CI passed **406 backend tests**, including
PostgreSQL and Compose checks. The committed dashboard passed **22 browser
checks across Chromium and WebKit**, plus unit tests, build and lint. Owner-app
tests, type checks and Android/iOS bundle exports also passed. Both mobile apps
have passed local type checks and bundle exports; marshal-app CI coverage remains
to be added. These results do not replace the live checks above.

| Location | Checks |
| --- | --- |
| `backend/` | Install `requirements-test.txt`; run `python -m pytest -q`. PostgreSQL acceptance requires its isolated test setup and `RUN_POSTGRES_TESTS=1`. Compose-rendering checks require the Compose CLI. |
| `backend/dashboard/` | `npm test`, `npm run build`, `npm run lint`; install Playwright Chromium/WebKit, then `npm run test:browser`. |
| `mobile/reporter-app/` | `npm run typecheck`, `npm test`, `npx expo-doctor@latest`. |
| `mobile/marshal-app/` | `npm run typecheck`, `npx expo-doctor@latest`. |

Browser tests use an isolated fixture backend rather than deployment data.
Older audits and status files are dated snapshots and may predate features
listed here. This README is the current overview; runbooks provide detailed
procedures and prerequisites.
