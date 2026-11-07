# Dashboard accounts, properties, and incident workflow

Implemented 2026-11-04. This work covers the web dashboard and its supporting API.
Production camera playback still requires the main camera PC and real sources.

## Enable and start

Use the existing database and back it up before applying migrations. From
`backend`, install `requirements-test.txt` for local development/testing, then
run `python -m alembic upgrade head`. Dashboard onboarding requires migration
`0012_property_address`; later existing migrations must remain in the same chain.

In the backend's existing private environment configure:

```dotenv
AUTH_ENABLED=true
JWT_SECRET=<your random secret of at least 32 characters>
DASHBOARD_REGISTRATION_ENABLED=true
```

Retain the host's existing database, Frigate and MQTT settings. Use
`DASHBOARD_REGISTRATION_ENABLED=false` for administrator-provisioned accounts.
For production set `APP_ENV=production`, serve the dashboard/API over HTTPS and
configure the allowed origin. Production session cookies require HTTPS. The
canonical Compose file passes these flags through to the backend; it mounts
Frigate media read-only at `/media/evidence` for stored file evidence.

Start the backend normally. From `backend/dashboard` with Node 22.18+:

```sh
npm ci
npm run dev -- --host 127.0.0.1
```

Use `VITE_BACKEND_URL` to point the Vite proxy to the real backend. Keep
`VITE_API_BASE_URL=/api/v1` and use one browser origin for the dashboard and
proxied API. Cookies are HttpOnly and are used for HTTP, WebSocket, video
negotiation and evidence; browser JavaScript never stores the JWT. Production
hosting must proxy `/api` and WebSocket upgrades to the backend, and serve the
dashboard build with SPA fallback. Do not expose `dist` alone without that API
proxy. Custom deployment origins must be included in `CORS_ORIGINS` (configure
that variable in the actual service environment for non-default origins).

## Account and property flow

Registration has two steps: full name, email, password and confirmation, followed
by property name and address. Passwords require 12–128 characters, including a
letter and a number. Inputs are validated on both browser and server. The server
normalizes the email and hashes the password; account, new property and owner
membership are committed together. Duplicate emails fail without orphan records.

Registration creates a **new, empty property**. It never attaches an account to
an existing property's cameras or incidents, even when names/addresses match.
For the camera PC's existing property, use an already provisioned owner account,
or have the administrator provision a new account for its verified property ID:

```sh
# From backend; the password is prompted interactively.
python -m app.provision_reporter --email owner@example.com --name "Owner Name" --role owner --property-id VERIFIED_PROPERTY_ID
```

The property ID in that example must be replaced with the real ID. Provisioning
refuses to overwrite an existing account. Granting an existing user additional
memberships remains an administrator operation; the dashboard cannot claim access.

An existing owner whose property lacks an address is asked to complete it before
entering the workspace. Users without properties can create one. “Add property”
creates a separate property owned by the signed-in user; it does not move cameras,
incidents or other users. Authorized properties are listed in the top selector.
The selected ID is remembered per user in browser session storage and revalidated
against live memberships after reload; tokens are not stored there.

Switching properties remounts the workspace, closes the old WebSocket and video
connections, cancels old reads, and resets camera selection, incident selection,
filters, details and evidence. Delayed responses cannot refill the new workspace
with the previous property's data. Every API request independently verifies the
current user's active membership and property's active status in the database.

Sign-out revokes the existing user token version and clears the cookie. This
invalidates other sessions using that account's token version, consistent with
the existing authentication model. Expired/revoked sessions return to sign-in.
Revoked/changed property permissions trigger a profile refresh and clear the
workspace while access is rechecked.

## Incidents and evidence

“Live monitoring” shows the selected property's cameras, current person tracks,
recent events and active alerts. “Incidents” provides server-side pagination and
status/severity filters over the complete property history. Summary counts come
from database aggregates, independently of the latest-100 monitoring feed.

Select an incident to see its status, severity, camera, timestamp, confidence,
zone, history and evidence. Owners and dispatchers may perform legal transitions:

| Current state | Available actions |
|---|---|
| OPEN | Acknowledge, resolve, dismiss as false alarm |
| ACKNOWLEDGED | Resolve, dismiss as false alarm |
| UNCLASSIFIED | Dismiss as false alarm |
| RESOLVED, DISMISSED, CLOSED | Reopen |

Every action requires a nonblank reason. Buttons disable during submission.
The server checks the state and role, commits the change with actor/history/audit
records, then publishes a property-scoped update. Illegal or stale transitions
return a conflict and the details reload from the server. Reporter memberships
can read but cannot perform incident actions. Marshal-only memberships do not
grant access to this owner/operator dashboard.

Evidence access uses short-lived signed grants bound to the current user,
evidence and property. The content endpoint also checks the live session and
membership. Stored files must resolve beneath `EVIDENCE_ROOT`. Frigate snapshot
references are proxied by the incident's Frigate event ID, never the camera's
latest frame. Missing/expired media and unavailable services show an error;
the UI does not invent or substitute evidence.

The dashboard reconnects its live socket and periodically refreshes property
data. Camera “enabled” configuration is distinguished from observed connection
health; unknown health is not reported as online. Cross-process durable replay
and email verification/password reset are separate capabilities, not supplied by
this dashboard change.

## Responder position and incident downloads

Owners and dispatchers can select an incident to see a responder's last reported
position after acceptance, while the assignment is accepted, en route or on
scene. Location events refresh the selected property automatically; periodic
refresh provides a fallback when the socket reconnects. Pending offers and
completed/cancelled assignments do not show responder positions.

The panel shows the update time and reported accuracy. Updates older than 30
seconds, invalid timestamps and timestamps unexpectedly ahead of the browser
clock are labelled stale/unavailable. Arrival estimates are hidden in that
state. Fresh estimates use straight-line distance and reported speed or a
fallback, without traffic data. The maps link opens the last reported coordinate
on an external map after the operator clicks it; there is no embedded route map
or background GPS capture in this change.

**Download incident report** saves a property/incident-named JSON file containing
the full timeline, notes, evidence metadata, assignments and notification
history. Evidence beyond the first 100 records is included. Media bytes and
historical GPS are not embedded. Failed downloads can be retried; switching
properties or signing out cancels a pending download. Offers default to 300
seconds and the form accepts only 10–300 seconds, matching the backend.

## Compose notification and identity settings

Use the canonical `backend/deployment/docker-compose.yml` and its private
`.env`. Delivery defaults to `DISPATCH_NOTIFICATION_PROVIDER=disabled`.
Use `expo` for app push, or `routing` for app push plus explicitly configured
SMS/voice/WhatsApp/agency destinations. The deployment passes the Expo token,
Twilio credentials/senders, agency endpoints/signing secret and
`ALERT_ROUTING_DESTINATIONS` to the backend only. Configure real provider
credentials and approved receiving endpoints before selecting a live mode.
No provider is enabled by populating an example file alone.

Set a dedicated `MARSHAL_IDENTITY_KEY` before collecting onboarding data.
Compose uses the `marshal_identities` volume and the fixed private root
`/var/lib/securepulse/marshal-identities/documents`, separately from media.
Preserve this volume, the database and its separate encryption-key backup when
replacing containers. See [onboarding and review](marshal-onboarding.md) for
HTTPS, administrator access and retention requirements.

Validate configuration without printing secrets:

```sh
# From backend/deployment, using the existing project and private .env:
docker compose config --quiet
```

After reviewing the resulting changes, rebuild/recreate only the backend in the
verified existing project. Do not remove volumes or silently select a different
project. This configuration change does not deploy an HTTPS proxy, create
provider credentials or validate delivery to a real device or agency.

## Verification

From `backend`:

```sh
python -m pytest tests/test_dashboard.py -q
python -m pytest -q
```

From `backend/dashboard`:

```sh
npm test
npm run build
npm run lint
npx playwright install chromium webkit
npm run test:browser
```

Browser tests start an isolated SQLite API on loopback port 18081 and Vite on
15173. They never connect to deployment databases, MQTT, cameras or Frigate.
Use `DASHBOARD_TEST_PYTHON` if the backend's virtualenv is elsewhere; the default
is `backend/.venv`. To use installed Chrome instead of downloaded Chromium, set
`PLAYWRIGHT_CHROME_CHANNEL=chrome` for the command.

Coverage includes registration/password confirmation, required property details,
cookie sessions across reload/logout, delayed-response property switching,
cross-property access denial, saved incident actions/history, evidence rendering,
read-only restrictions, revoked sessions and adding an empty property.
The response-tools suite also exercises marshal location updates through the
authenticated API, realtime rendering, stale/missing positions, completed-job
privacy, actual report downloads, failure/retry, property-switch cancellation
and the five-minute offer limit in Chromium and WebKit.

With Docker Compose CLI installed, backend tests also render the deployment with
isolated test settings and check provider configuration and private named-volume
wiring. These tests do not start containers or read the deployment `.env`.
