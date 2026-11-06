# SecurePulse Reporter

Live camera playback, current camera health/counts, Managed Auth email-code
recovery and the Expo push sender/receipts/tap flow are implemented. Use
[the reporter completion runbook](../../docs/runbooks/reporter-completion.md)
for native build setup and the actual host/device acceptance still required.

Native Expo SDK 58 / React Native / TypeScript app in this directory. Install and run commands here, not at the repository root.

## Mobile setup

1. Use Node 24.3+ (24 LTS recommended) and run `npm ci`.
2. Copy `.env.example` to `.env` and set `EXPO_PUBLIC_SERVER_URL` to the existing FastAPI server's LAN address or deployed HTTPS URL. Include any reverse-proxy prefix, but not `/api/v1`.
3. Run `npm start -- --go`, then open an SDK 58-compatible Expo Go installation. Use `npm run android` / `npm run ios` for an available emulator/simulator. Remote push requires a configured development or release build; notification modules are loaded only in supported builds so Expo Go can still open the app.
4. Sign in with an administrator-provisioned account after completing the backend setup below.

There is no default server and loopback addresses are rejected. On a physical device, use the machine's actual LAN IP; both devices must be able to reach it. Android emulator users can use `http://10.0.2.2:8000`. A Metro tunnel does not tunnel FastAPI. Restart Metro after changing environment variables.

For LAN development, start the existing FastAPI app with `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Grant iOS local-network permission. Use HTTPS for deployed builds; native cleartext restrictions can reject HTTP in standalone builds. No TLS verification bypass is included. Native requests do not require browser CORS changes. Web authentication is not supported by this native-only app.

Never include JWT signing secrets, passwords, Frigate credentials, or access tokens in `EXPO_PUBLIC_*` variables. Passwords are sent only to the configured server and are not persisted. Sessions use Expo SecureStore, bound to the configured server, and are revalidated against `/auth/me` on launch.

## Backend setup (existing backend and database)

The mobile app uses the same backend, `users`, properties and active property memberships as the dashboard. Cameras belong to properties through `cameras.property_id`. Manual reports and their private evidence are separate from camera detections.

From `backend/`, with its existing virtual environment activated:

```sh
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

Apply migrations through `0020_marshal_onboarding` before using the integrated workflow. This requires marshals to complete onboarding and receive approval before going on duty. Review/back up existing data according to your normal deployment process.

Configure `AUTH_ENABLED=true`, a strong `JWT_SECRET` of at least 32 characters, and optionally `JWT_ISSUER`. Sign-in refuses anonymous development mode. The dashboard uses its own HTTP-only cookie session; mobile bearer credentials cannot access legacy global operator APIs. Owners can register an account and property in the dashboard, then sign in to the mobile app with the same credentials. Additional reporter memberships can be provisioned below.

Provision a real account using the local administrator command (replace values):

```sh
python -m app.provision_reporter --email owner@your-domain.example --name "Property owner" --role owner --property-name "Your property" --camera-id 1
```

The password is requested interactively with confirmation (12–128 characters). Repeat `--camera-id` for multiple existing cameras. The command prints the new property ID. To give another user access to the same property:

```sh
python -m app.provision_reporter --email reporter@your-domain.example --name "Reporter" --role reporter --property-id 1
```

Existing accounts are never overwritten, camera assignments to other properties are rejected, and the transaction rolls back on failure. A camera belongs to at most one property. Unassigned cameras are excluded from reporter reads. Owner and reporter membership both permit reviewing their property's data. Owners can offer an incident to several eligible marshals with a five-minute deadline; the first acceptance closes the other offers. Reporter memberships cannot assign marshals.

## API contract

All paths below are relative to `/api/v1`.

| Endpoint | Behavior |
| --- | --- |
| POST `/auth/login` | JSON `{email, password}`; returns `access_token`, `token_type: bearer`, `expires_at` |
| GET `/auth/me` | Server-validated user ID, name, email and property memberships/roles |
| POST `/auth/logout` | Revokes all existing tokens for that reporter account; 204 |
| GET `/reporter/cameras` | Property-scoped cameras, excluding Frigate identifiers |
| GET `/reporter/cameras/{id}` | Direct camera access checked against the property |
| GET `/reporter/events` | Property-scoped paginated security events; `page` and `page_size` |
| GET `/reporter/events/{id}` | Direct event access checked against the property |
| GET `/reporter/summary` | Property-scoped camera/event counts and ACTIVE operator alert count |

Camera, event and summary requests require `property_id`. Manual incident requests check report ownership and current active owner/reporter membership; history covers the user's authorized properties. Profile responses accept all backend roles, while the reporter app only permits selecting owner/reporter properties. Tokens carry `reporter:read`, not the legacy global `read` scope. Dependencies check signatures, expiration, issuer, active account and token version. Legacy global REST/media/track/WebSocket routes reject reporter tokens.

Passwords use salted scrypt hashes. Five failed attempts lock an account for 15 minutes; errors do not reveal whether an account exists. Deploy login behind your normal HTTPS edge and request-rate limits. Access tokens expire after one hour. No refresh endpoint existed, and none is assumed: expiration or a 401 ends the local session and requires sign-in. Logout clears local session/query data even offline; if revocation cannot reach the server, the UI says so and the remote token remains valid until expiration.

## App behavior and limitations

- Expo Router protects all main screens and deep links. Home, Alerts, Cameras, Profile, Settings and detail routes are present.
- Axios centralizes bearer headers, timeout, cancellation and error normalization. Zod validates network responses and derives TypeScript types.
- TanStack Query caches only in memory for five minutes, treats data as stale after 30 seconds, and refetches on foreground/reconnection. Cache keys include user and property; logout cancels requests and clears private data.
- Offline startup cannot unlock saved data before the server validates the session. A saved token can be retried through “Restore saved session.”
- Home uses actual property names and server counts. ACTIVE operator alerts are distinct from confirmed incidents. Camera `enabled` does not mean connected.
- Camera health comes from a short-lived Frigate stats projection. Open incident
  counts use scoped SQL records; unavailable health stays explicitly unverified.
- Alerts display recorded event type, camera, timestamp, severity and status. List pagination and details use real responses.
- Active alerts can be confirmed or dismissed once by an authorized property member.
- Live HLS/fMP4 camera playback uses signed, resource-scoped URLs through the
  authorized backend; host reachability and actual camera codecs require device acceptance.
- Manual incident submission requires private writable evidence storage. Creation and upload retries retain their idempotency keys; a failed attachment does not create another report. History supports status and active-assignment filters. Active details poll every 10 seconds and support pull to refresh.
- Phase 7 history and accessibility work is documented in [the Phase 7 report](docs/mobile/phase-7-history-accessibility.md).
- Evidence uses short-lived audited grants plus the current bearer session. Images and MP4 video have on-demand native previews; failed/expired access can be refreshed. The backend accepts JPG, PNG and MP4 up to its configured limit (10 MB by default).
- Phase 9 exposes all server-backed notification categories in Settings. See [the Phase 9 report](docs/mobile/phase-9-notification-preferences.md).
- Phase 10 adds reporter name updates and secure password rotation. See [the Phase 10 report](docs/mobile/phase-10-account-self-service.md).
- Notification preferences and device registration use migration `0015`. The real
  Expo sender, tickets/receipts and retries are implemented. Deployment activation,
  platform credentials and physical receipt verification remain pending.
- No media streams, simulated events, mock production data, Frigate credentials, or marshal-facing client are included. Dispatch status is shown only when the existing server-side assignment state machine has a real assignment.

## Checks

```sh
npm run typecheck
npm test
npx expo install --check
npx expo export --platform android --platform ios --output-dir dist
```

From `backend/`:

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
```

`npm test` also starts a temporary FastAPI process on loopback port 18082 using `backend/.venv` (override with `DASHBOARD_TEST_PYTHON`). Install backend test requirements first. It exercises the real mobile HTTP client, report retry receipts, evidence grants, dashboard dispatch, marshal completion and password/logout revocation. Run `npm run test:unit` and `npm run test:navigation` independently without Python, or `npm run test:integration` for the backend path. Test databases and media are temporary; deployment services are never contacted. PostgreSQL locking tests and physical SecureStore, media playback, LAN and push checks still require their respective environments. See [the integration runbook](../../docs/runbooks/mobile-backend-integration.md).

See [PHASE2_REPORT.md](PHASE2_REPORT.md) for completed validation and outstanding deployment tasks.
