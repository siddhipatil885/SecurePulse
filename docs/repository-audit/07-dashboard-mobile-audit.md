# Dashboard and Mobile Audit

## Dashboard conclusion

No frontend application exists. The repository contains four one-line placeholders:

- `ai-cctv/dashboard/src/components/.gitkeep:1`
- `ai-cctv/dashboard/src/pages/.gitkeep:1`
- `ai-cctv/dashboard/src/services/.gitkeep:1`
- `ai-cctv/dashboard/src/types/.gitkeep:1`

There is no `package.json`, lockfile, HTML entry point, JavaScript/TypeScript source, React/Vite/Tailwind configuration, build script, API client, state store, router, component, page, test, or deployment definition. React/Vite/Tailwind are planned technologies only (`README.md:197-200`).

## Existing screens

None.

The Frigate third-party web UI may be reachable on the configured host port and the setup guide expects it to display a live stream, detections, snapshots, and clips (`ai-cctv/deployment/docker-compose.yml:23-27`; `ai-cctv/docs/phase1_setup.md:70-75`). That upstream UI is not a SecurePulse dashboard, is not implemented in this repository, and was not runtime-verified.

## Dashboard element/data-source classification

| Element | UI implementation | Data source | Status |
|---|---|---|---|
| Camera feeds | None | Frigate port configured; no app consumer | NOT IMPLEMENTED |
| Security alerts | None | No incident API/realtime channel | NOT IMPLEMENTED |
| Incident counters | None | No database/API | NOT IMPLEMENTED |
| User statistics | None | No users/API | NOT IMPLEMENTED |
| Camera status | None | No status service/API | NOT IMPLEMENTED |
| Detection overlays | None | Bounding boxes only configured for Frigate snapshots (`frigate.yml:57-64`) | NOT IMPLEMENTED in dashboard |
| Event history | None | No event persistence/API | NOT IMPLEMENTED |
| Incident timeline | None | No incident/status history | NOT IMPLEMENTED |
| Property details | None | No property model/API | NOT IMPLEMENTED |
| Notification indicators | None | No notification system | NOT IMPLEMENTED |
| Charts | None | No frontend source | NOT IMPLEMENTED |

There are no polished or disconnected mock screens to classify as UI ONLY. There are also no frontend/backend contract mismatches because neither contract side exists yet.

## Property owner mobile application

No Android, iOS, Flutter, React Native, Expo, or PWA application/manifests were found.

| Capability | UI | Backend API | DB support | Real integration | Automated tests |
|---|---|---|---|---|---|
| Login/registration | No | No | No | No | No |
| Property overview | No | No | No | No | No |
| Camera viewing | No | No | No | No | No |
| Incident notifications | No | No | No | No | No |
| Evidence playback | No | No | No | No | No |
| Incident history/status | No | No | No | No | No |
| Emergency help | No | No | No | No | No |
| Assigned marshal info | No | No | No | No | No |
| Push notifications | No | No | No | No | No |

## Security marshal mobile application

No marshal application exists.

| Capability | UI | Backend API | DB support | Real integration | Automated tests |
|---|---|---|---|---|---|
| Login/onboarding/role verification | No | No | No | No | No |
| Availability/service area | No | No | No | No | No |
| Incoming incidents | No | No | No | No | No |
| Push notification | No | No | No | No | No |
| Accept/reject assignment | No | No | No | No | No |
| Navigation/location | No | No | No | No | No |
| Response status | No | No | No | No | No |
| Incident resolution | No | No | No | No | No |
| Response history | No | No | No | No | No |

## Required integration order

Do not build independent visual prototypes first. Establish versioned API schemas, property-scoped authorization, incident/evidence persistence, authenticated realtime delivery, and dispatch commands; then implement one owner/dashboard incident flow and one marshal assignment flow against contract tests. Camera playback also needs a secure restream/proxy decision—directly exposing Frigate/RTSP credentials to clients is unacceptable.

