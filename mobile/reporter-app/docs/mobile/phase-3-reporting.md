# Phase 3 — Manual reporting and evidence

## Status

**Implemented but not fully validated.** The reporter can create a property-authorized incident, retry safely with an idempotency key, attach a bounded image/video upload, and retrieve the persisted report and timeline. Production PostgreSQL deployment and physical-device verification remain pending.

## Implemented

- Incident categories: theft, break-in, suspicious activity, assault, property damage, fire, medical emergency, and other.
- Address entry or explicit foreground GPS capture. GPS is optional when an address is supplied.
- Description validation and 4,000-character limit.
- Confirmation/submission action with loading and error states.
- Idempotent incident creation using `X-Idempotency-Key`.
- Reporter-owned incident history and detail routes.
- JPG, PNG, and MP4 evidence uploads with a configurable byte limit.
- Evidence is stored below `EVIDENCE_ROOT/reporter-incidents/{incident_id}` using generated filenames.
- Initial `RECEIVED` timeline entry and server timestamps.
- Server-side property membership and reporter ownership checks.

## Existing features reused

- Existing Expo Router protection and `AuthProvider`.
- Existing Axios/Zod API boundary and normalized errors.
- Existing TanStack Query cache and invalidation.
- Existing SecureStore session handling and property selection.
- Existing PostgreSQL/Alembic setup and FastAPI exception responses.

## Files created or modified

Backend:

- `backend/app/models/reporter_incident.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/reporter.py`
- `backend/app/api/reporter.py`
- `backend/app/core/config.py`
- `backend/alembic/versions/0013_reporter_incidents.py`
- `backend/requirements.txt`
- `backend/tests/test_reporter.py`

Mobile:

- `mobile/reporter-app/src/api/types.ts`
- `mobile/reporter-app/src/api/client.ts`
- `mobile/reporter-app/src/api/queries.ts`
- `mobile/reporter-app/src/screens/ReportScreen.tsx`
- `mobile/reporter-app/src/screens/IncidentScreens.tsx`
- `mobile/reporter-app/src/screens/HomeScreen.tsx`
- `mobile/reporter-app/app/(app)/_layout.tsx`
- `mobile/reporter-app/app/(app)/incidents/index.tsx`
- `mobile/reporter-app/app/(app)/incidents/[id].tsx`
- `mobile/reporter-app/tests/api.test.ts`
- `mobile/reporter-app/package.json`
- `mobile/reporter-app/package-lock.json`

## Database changes

Migration `0013_reporter_incidents` adds:

- `reporter_incidents`
- `reporter_incident_timeline`
- `reporter_incident_evidence`

The migration does not alter surveillance `security_events` or the existing evidence model.

## API contracts

All routes are under `/api/v1` and require a reporter bearer token:

- `POST /reporter/incidents` — JSON incident payload plus required `X-Idempotency-Key`.
- `GET /reporter/incidents` — authenticated reporter-owned paginated history.
- `GET /reporter/incidents/{id}` — authenticated reporter-owned detail, timeline, and evidence metadata.
- `POST /reporter/incidents/{id}/evidence` — multipart `file`; accepts JPG, PNG, or MP4 within `REPORTER_EVIDENCE_MAX_BYTES`.

Incident creation requires an active `owner` or `reporter` membership for the supplied property. The server records the authenticated reporter identity; client-supplied ownership is ignored.

## Configuration and deployment

Before enabling uploads, configure a private writable `EVIDENCE_ROOT` on the backend. Apply migrations with the normal deployment process:

```sh
python -m alembic upgrade head
```

Do not expose `EVIDENCE_ROOT` directly as a public static directory. Evidence download/authorization endpoints for reporter-created media remain a Phase 6/retention-policy dependency; this phase returns metadata only.

## Validation

Passed:

```sh
cd mobile/reporter-app
npm run typecheck
npm test

cd ../../backend
python3 -m pytest -q tests/test_reporter.py
DATABASE_URL=postgresql://user:pass@localhost/db python3 -m alembic upgrade head --sql
```

Results at implementation time:

- Mobile TypeScript check passed.
- Mobile unit/navigation suite passed (16 Vitest/API tests and 3 Jest navigation tests).
- Reporter backend suite passed (10 tests).
- Alembic SQL rendered through `0013_reporter_incidents`.
- No deployed PostgreSQL, real account, upload storage, Android device, or iOS device was available for end-to-end verification.

## Security considerations

- Reporter tokens and property memberships are checked server-side.
- Incident detail and uploads are restricted to the creating reporter.
- Idempotency prevents sequential duplicate submissions for the same reporter/key.
- Upload type, content signature for images, filename, and size are validated.
- Generated storage names prevent user-controlled path traversal.
- Raw storage paths are never returned to the mobile client.
- The app does not claim that a report guarantees emergency-service attendance.

## Remaining blockers

- Add authenticated evidence retrieval with short-lived grants or equivalent policy before exposing evidence in incident detail.
- Add backend-driven incident state transitions, cancellation, dispatch integration, notifications, and realtime updates in Phase 4+.
- Run migration and provision storage on the configured deployment.
- Verify permissions, camera/gallery behavior, GPS denial, keyboard/safe-area layout, offline drafts, and uploads on physical Android and iOS devices.
- Reassess the existing dependency audit findings before release.

## Phase 4 integration note

The additive Phase 4 dispatch link is implemented in migration `0014_reporter_dispatch_link`. Once deployed, incident detail includes only a real assignment returned by the backend; `RECEIVED` alone never implies a responder.
