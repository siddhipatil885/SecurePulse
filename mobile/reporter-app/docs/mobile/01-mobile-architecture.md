# SecurePulse Mobile Architecture

## Architectural objective

Keep the mobile app a thin, secure client of FastAPI. Authentication, authorization, incident state transitions, evidence access, dispatch, notifications, and camera stream authorization remain server-controlled. The app must never connect directly to PostgreSQL or infer dispatch state from local data.

## Current architecture

```text
Expo Router screens
        |
shared UI components
        |
TanStack Query hooks ---- AuthProvider / SessionManager
        |                         |
typed Axios API client       Expo SecureStore
        |
FastAPI API (external to this audit)
```

## Proposed feature organization

Preserve the current `src/api`, `src/auth`, `src/components`, and `src/screens` structure for the completed read-only reporter flow. Add feature modules incrementally rather than replacing the working app:

```text
src/
  api/
    client.ts
    types.ts
    queries.ts
    incidents.ts       # Phase 3, only after backend contract verification
    notifications.ts   # Phase 6, only after backend contract verification
  features/
    incidents/         # form, review, detail, status timeline
    notifications/     # registration, preferences, deep links
    camera/             # authorized stream/evidence handling
  hooks/
  components/
  screens/
```

The exact module split should follow the existing code once a phase has a verified contract. Do not add a package merely to match the reference structure.

## State boundaries

- **Server state:** TanStack Query. Query keys must include authenticated user and selected property where authorization depends on them.
- **Session state:** `SessionManager` and `AuthProvider`. Tokens remain in SecureStore and memory only.
- **Form state:** local component state initially; use a form library only if the Phase 3 form complexity justifies the dependency.
- **Device state:** small hooks for connectivity, location permission, notification permission, and app focus.
- **Navigation state:** Expo Router. Deep links must pass through protected routes and server authorization.

## Security invariants

1. Client-side role checks only control presentation; every resource request must be authorized by FastAPI.
2. Never place tokens, passwords, Frigate credentials, or signing secrets in public Expo environment variables.
3. Never trust decoded token claims for property ownership or incident ownership without a server response.
4. Never show a success state until the server confirms the operation.
5. Incident submission must use an idempotency strategy before retries are exposed to users.
6. Media and stream URLs must be short-lived or server-authorized; raw RTSP must never be rendered directly.
7. Offline mode may display cached data but must not claim that a report, escalation, assignment, or cancellation succeeded.
