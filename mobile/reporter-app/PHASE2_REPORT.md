# Phase 2 completion report

## Implemented

- Expo Router migration, protected routes and deep links, Home, Alerts/detail, Cameras/detail, Profile, Settings, and an explicit unavailable Report Incident screen.
- Real credential login, SecureStore persistence, startup server validation, session expiration, invalid-session handling, and logout with server revocation and local cache cleanup.
- Axios service layer, runtime-validated TypeScript contracts, property-scoped reads, TanStack Query caching/pagination, foreground/reconnect refresh, offline and error states.
- Real property names, assigned roles, camera/event/ACTIVE-alert counts and security events. No invented incidents or live camera status.
- Per-user local notification preferences. No push delivery.
- Authorized additive backend extension: password-hashed accounts, property membership, camera assignment, login/me/logout and scoped reporter read routes using existing surveillance tables and JWT validation.
- Local administrator provisioning command with interactive passwords and transactional camera assignment; additive Alembic migration 0005.

## Architecture and scope

The initial audit found camera/event/track reads, Frigate media proxy routes, a WebSocket stream, and JWT signature/scope validation. It found no account issuance, profile, refresh, property membership, incident confirmation, or manual-report API.

The user explicitly authorized extending backend authentication/property authorization. Reporter tokens receive `reporter:read`, separate from existing global operator `read`. Existing global routes reject reporter tokens; each new scoped read checks enabled account, token version and current property membership. This avoids changing existing operator and surveillance behavior while preventing mobile users from accessing global data.

Existing records are reused. Camera assignment lives in a new relation, so camera/event ingestion models and schema are not altered. Existing backend source changes are limited to router registration, model registration, the SQLAlchemy asyncio dependency declaration, and the metadata test's expected tables. Frigate, MQTT, security rules, dashboard, Docker and surveillance workers were not edited. Unrelated pre-existing worktree changes were preserved.

## Verified

| Check | Result |
| --- | --- |
| TypeScript `npm run typecheck` | Passed |
| API/session tests (Vitest) | 15 passed |
| Actual Expo Router layout tests (Jest Expo) | 3 passed |
| Expo dependency compatibility | Passed |
| Android and iOS Metro/Hermes exports | Passed |
| Backend suite | 189 passed, including 181 existing tests and 8 new reporter tests |
| PostgreSQL migration SQL generation (0004 → 0005) | Passed; offline, no deployed database accessed |
| Additive migration execution | Passed on isolated SQLite; existing camera preserved |
| Provisioning | Tested successful login, assignment, duplicate rejection and rollback on cross-property camera reassignment |

Session tests cover secure-storage failure, expired/malformed/wrong-server credentials, offline startup, failed login/profile validation, stale 401 responses, logout failure and logout during a pending login. API tests cover headers, property parameters, response validation and HTTP/network errors. Navigation tests use the real layouts with fixture screens/auth state and verify unauthenticated deep-link rejection, sign-in, detail routes, and removal of protected navigation history on logout.

Backend tests perform real SQL queries against an isolated in-memory test database. They cover role memberships, property-scoped lists/counts/details, unassigned cameras, cross-property ID access, internal-field redaction, missing/forged/expired/revoked tokens, disabled accounts, lockout, anonymous-mode refusal, and denial of legacy REST/media/WebSocket access to reporter tokens. No production fixtures or mock screens are shipped.

## Missing capabilities and remaining tasks

- Apply migration 0005 to the configured PostgreSQL database and provision actual users/property assignments using the README. Neither action was performed on a deployed database.
- Enable the backend's existing authentication configuration; the mobile app never bypasses it. Existing dashboard deployments must use their normal operator credentials once authentication is enabled.
- Test end-to-end sign-in, secure storage across restarts, local-network permissions, keyboard/safe-area rendering, offline/reconnect and account switching on physical Android/iOS devices. Native builds were bundled, not installed or visually tested here.
- No refresh-token endpoint exists; sessions expire after one hour and require sign-in. Password reset, public registration and account-management UI are not implemented.
- Confirmed incident state/counts, property security status and camera connectivity telemetry have no authoritative source. The app displays unavailable/unverified instead of inferring safety or connectivity from detections or camera `enabled`.
- Manual reporting and false-alarm confirmation endpoints remain absent. Their controls do not send requests or pretend to save data. No marshal dispatch or automatic marshal notification is implemented.
- Push delivery and WebRTC are outside this phase.
- Dependency audit: the retained Expo SDK 53 tree has outstanding advisories. `npm audit --omit=dev` reported 17 findings (11 moderate, 6 high) during validation, including Expo tooling/transitives and the Router-compatible query-string dependency. A framework/dependency security upgrade needs separate compatibility validation before production release; no forced major upgrade was applied.

The architecture remains: automated detections become recorded alerts for human review. No mobile operation can initiate marshal dispatch in this phase.
