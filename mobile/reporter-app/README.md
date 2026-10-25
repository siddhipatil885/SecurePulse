# SecurePulse Reporter — Phase 2

Native Expo SDK 53 / React Native / TypeScript app in this directory. Install and run commands here, not at the repository root.

## Mobile setup

1. Use Node 20.19+ and run `npm ci`.
2. Copy `.env.example` to `.env` and set `EXPO_PUBLIC_SERVER_URL` to the existing FastAPI server's LAN address or deployed HTTPS URL. Include any reverse-proxy prefix, but not `/api/v1`.
3. Run `npm start`, then open an SDK 53-compatible Expo Go installation or development build. Use `npm run android` / `npm run ios` for an available emulator/simulator.
4. Sign in with an administrator-provisioned account after completing the backend setup below.

There is no default server and loopback addresses are rejected. On a physical device, use the machine's actual LAN IP; both devices must be able to reach it. Android emulator users can use `http://10.0.2.2:8000`. A Metro tunnel does not tunnel FastAPI. Restart Metro after changing environment variables.

For LAN development, start the existing FastAPI app with `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Grant iOS local-network permission. Use HTTPS for deployed builds; native cleartext restrictions can reject HTTP in standalone builds. No TLS verification bypass is included. Native requests do not require browser CORS changes. Web authentication is not supported by this native-only app.

Never include JWT signing secrets, passwords, Frigate credentials, or access tokens in `EXPO_PUBLIC_*` variables. Passwords are sent only to the configured server and are not persisted. Sessions use Expo SecureStore, bound to the configured server, and are revalidated against `/auth/me` on launch.

## Backend setup (existing backend and database)

The audit found JWT validation and surveillance read APIs, but no account issuance or property authorization. The authorized extension adds four tables to the same database: `reporter_users`, `properties`, `property_memberships`, and `property_cameras`. Detection tables and ingestion are unchanged.

From `backend/`, with its existing virtual environment activated:

```sh
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

The migration is `0005_reporter_access`. No production migration or account provisioning was performed during implementation. Apply it to your configured PostgreSQL database before using the new APIs. Review/back up existing data according to your normal deployment process.

Configure the backend's existing `AUTH_ENABLED=true`, a strong `JWT_SECRET` of at least 32 characters, and optionally `JWT_ISSUER`. Reporter sign-in refuses to operate in anonymous development mode. Enabling authentication also requires the existing dashboard to send its normal read-scoped operator token; reporter credentials intentionally cannot access those global APIs.

Provision a real account using the local administrator command (replace values):

```sh
python -m app.provision_reporter --email owner@your-domain.example --name "Property owner" --role owner --property-name "Your property" --camera-id 1
```

The password is requested interactively with confirmation (12–128 characters). Repeat `--camera-id` for multiple existing cameras. The command prints the new property ID. To give another user access to the same property:

```sh
python -m app.provision_reporter --email reporter@your-domain.example --name "Reporter" --role reporter --property-id 1
```

Existing accounts are never overwritten, camera assignments to other properties are rejected, and the transaction rolls back on failure. A camera belongs to at most one property. Unassigned cameras are excluded from reporter reads. Owner and reporter membership both permit reviewing their property's data; no incident mutation or dispatch permission exists.

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

Every `/reporter/*` request requires `property_id` and an authenticated membership. Tokens carry `reporter:read`, not the legacy global `read` scope. The existing validator checks JWT signatures, expiration, and issuer; reporter dependencies also check enabled status and the server-side token version. No profile or ownership claim is trusted merely because it was decoded on the phone. Legacy global REST/media/track/WebSocket routes reject reporter tokens.

Passwords use salted scrypt hashes. Five failed attempts lock an account for 15 minutes; errors do not reveal whether an account exists. Deploy login behind your normal HTTPS edge and request-rate limits. Access tokens expire after one hour. No refresh endpoint existed, and none is assumed: expiration or a 401 ends the local session and requires sign-in. Logout clears local session/query data even offline; if revocation cannot reach the server, the UI says so and the remote token remains valid until expiration.

## App behavior and limitations

- Expo Router protects all main screens and deep links. Home, Alerts, Cameras, Profile, Settings and detail routes are present.
- Axios centralizes bearer headers, timeout, cancellation and error normalization. Zod validates network responses and derives TypeScript types.
- TanStack Query caches only in memory for five minutes, treats data as stale after 30 seconds, and refetches on foreground/reconnection. Cache keys include user and property; logout cancels requests and clears private data.
- Offline startup cannot unlock saved data before the server validates the session. A saved token can be retried through “Restore saved session.”
- Home uses actual property names and server counts. ACTIVE operator alerts are distinct from confirmed incidents. Camera `enabled` does not mean connected.
- Connection health, property security status and confirmed incident counts remain unavailable because no authoritative backend source exists.
- Alerts display recorded event type, camera, timestamp, severity and status. List pagination and details use real responses.
- False Alarm and incident submission are explicitly unavailable. Opening Report Incident never sends a mutation.
- Notification preferences are saved locally per user. No push registration or notification delivery is implemented.
- No media streams, simulated events, mock production data, Frigate credentials, or marshal dispatch code are included.

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

The API tests use an isolated in-memory SQLite database with actual SQL queries and test-only accounts. Production remains PostgreSQL. The native navigation tests exercise the actual Expo Router layouts with screen/auth fixtures. They do not substitute for testing SecureStore, keyboard behavior, LAN access, and UI rendering on physical iOS/Android devices.

See [PHASE2_REPORT.md](PHASE2_REPORT.md) for completed validation and outstanding deployment tasks.
