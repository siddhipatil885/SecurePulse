# SecurePulse Mobile Phase 0 Audit

## Scope and boundary

This audit covers only `/Users/eklavvyaaa/PROJECTS/SecurePulse/mobile`. The repository-level backend, dashboard, Frigate, MQTT, MediaMTX, database, migration, and deployment directories were not read or modified because another agent is working outside the mobile folder.

Consequently, backend route ownership, database schema, dispatch behavior, notification services, and stream capabilities are **not verified by this audit**. The mobile app's own documentation describes an existing backend extension, but that description is treated as an integration reference rather than independent verification.

## Mobile repository inventory

The mobile workspace contains one Expo application:

`mobile/reporter-app`

Relevant areas:

- `app/`: Expo Router layouts and protected routes.
- `src/auth/`: SecureStore-backed session restoration, login, expiry, logout, and invalid-session handling.
- `src/api/`: Axios client, Zod response contracts, and TanStack Query hooks.
- `src/components/`: shared screen, content, status, card, and button primitives.
- `src/screens/`: login, home, alerts, cameras, profile, settings, report, and detail screens.
- `tests/`: API, session, and navigation tests.
- `README.md`: setup, API contract, security limitations, and deployment prerequisites.
- `PHASE2_REPORT.md`: prior implementation and validation report.

## Feature classification

| Capability | Classification | Evidence / limitation |
| --- | --- | --- |
| React Native + Expo + TypeScript | Already implemented and verified | `package.json`; typecheck passed |
| Expo Router navigation | Already implemented and verified | `app/`; navigation tests passed |
| Protected routes and deep-link guards | Already implemented and verified | `app/_layout.tsx`; navigation tests passed |
| Login and server profile validation | Already implemented and verified | `src/auth/session.ts`, `src/api/client.ts` |
| Secure token storage | Already implemented and verified | Expo SecureStore in `src/auth/AuthProvider.tsx` |
| Session expiry, logout, stale 401 handling | Already implemented and verified | `src/auth/session.ts`; session tests passed |
| Property selection | Partially implemented | Selection state exists; no visible property-switch control was found in the inspected screens |
| Property-scoped cameras/events/summary | Already implemented and verified at contract level | `src/api/client.ts`, `src/api/queries.ts`; server integration remains environment-dependent |
| Home dashboard | Already implemented and verified at contract level | `src/screens/HomeScreen.tsx` |
| Profile and settings | Already implemented | `src/screens/ProfileScreen.tsx`, `src/screens/SettingsScreen.tsx` |
| Alerts and alert details | Already implemented | `src/screens/ActivityScreen.tsx`, `src/screens/DetailScreens.tsx` |
| Camera list and details | Already implemented | `src/screens/CamerasScreen.tsx`, `src/screens/DetailScreens.tsx` |
| Manual incident creation | Missing / blocked | Report screen is explicitly unavailable because no supported server mutation is wired |
| Location permissions and selection | Missing | No location package or flow is present |
| Evidence selection/upload | Missing | No image/video picker or upload flow is present |
| Incident history and tracking | Missing / blocked | No mobile incident API contract is present |
| Marshal dispatch tracking | Blocked by unverified external dependency | No dispatch contract was inspected inside the mobile boundary |
| Push notifications | Missing | Settings stores a local preference only; no device registration or delivery |
| Live camera streaming | Missing / blocked | Current UI states that live streaming is unavailable |
| Confirm threat / dismiss false alarm | Missing / blocked | Current UI exposes an unavailable disabled action |
| Offline query behavior | Already implemented and verified at contract level | NetInfo and TanStack Query online manager are wired |
| Android/iOS bundle generation | Already implemented and verified | Expo Android and iOS exports succeeded |

## Reusable implementation

The current app provides a usable foundation for later phases:

1. `createApi` centralizes base URL validation, bearer headers, timeouts, cancellation, response parsing, and error normalization.
2. Zod schemas in `src/api/types.ts` establish runtime validation at the network boundary.
3. `SessionManager` is isolated and testable, including generation checks to prevent stale login/restore work from replacing newer state.
4. TanStack Query hooks provide property- and user-scoped cache keys and paginated event loading.
5. The shared `Screen`, `QueryState`, `PropertyBanner`, `EventCard`, and `PrimaryButton` components should be extended rather than replaced.
6. Existing Expo Router protected layouts should remain the navigation boundary.
7. The existing README documents the known backend contract and must be updated whenever a verified mobile API is added.

## Validation performed

From `mobile/reporter-app`:

- `npm run typecheck` — passed.
- `npm test` — passed: 15 Vitest tests and 3 Jest navigation tests.
- `npx expo install --check` — passed.
- `npx expo export --platform android --platform ios` — passed.

These checks validate the mobile code and bundle contracts. They do not prove that a deployed backend, device permissions, push provider, camera stream, or dispatch service works end to end.
