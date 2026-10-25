# SecurePulse web dashboard integration and acceptance

Prepared 2026-10-25 (Asia/Calcutta), starting Git SHA
`c3ac692633421b30194d6ba8caaa33df91a92aa3`. This describes working-tree changes;
no commit, deployment, live-camera certification or team approval is claimed.
See [baseline](../status/engineer-4-baseline.md) for the complete field inventory
and [realtime/media contract](../contracts/dashboard-realtime-v1.md).

## Local setup

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-test.txt
Set-Location backend
Copy-Item .env.example .env
# Edit .env to use an isolated development PostgreSQL DB, MQTT and stream gateway.
# Set JWT_SECRET to a unique random value with at least 32 characters.
# Set AUTH_ENABLED=true when verifying authorization; APP_ENV=production requires it.
# Keep all credentials out of Git and out of VITE_* variables.
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a separate terminal from the repository root:

```powershell
Set-Location backend/dashboard
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Use an Engineer 2-issued monitoring JWT with
`read`, optional `write`, and authorized integer `property_ids`; enter it in
Access token / Use session. The token lives only in process memory; refresh
requires re-entering it. Clear session removes it. An empty token works only
with the explicit auth-disabled development backend. Reporter-app credentials
have `reporter:read` and intentionally cannot access monitoring APIs.
The shared auth owner must supply the production monitoring login/session UI;
this integration does not mint privileged browser tokens.

The Vite `/api` and `/health` proxies target `VITE_BACKEND_URL`. Browser REST
defaults to `/api/v1`; the socket derives from the same base and uses wss on
HTTPS. `VITE_WS_URL` overrides it if required. Production must proxy these
routes, support WebSocket upgrade, use TLS, and set `CORS_ORIGINS` to the actual
dashboard origin. Do not expose Frigate, RTSP credentials, MQTT or go2rtc
management endpoints publicly. Run one backend worker for the in-memory
publisher; see the contract for multi-worker limitations.

## Pages, components and endpoints

There is one existing dashboard with working section anchors (Dashboard,
Cameras, Events, Alerts), one large primary feed and up to two side previews.
All configured authorized cameras are selectable, including those beyond the
first three. Incident details are opened from Recent Incidents.

| UI | Authoritative source |
|---|---|
| Property selector / permitted write controls | GET `/api/v1/properties`, `/api/v1/dashboard/session`; backend still enforces every request |
| Camera name, property, location, enabled config | GET `/api/v1/cameras?page=N&page_size=100` |
| Camera connectivity / observed timestamp | CameraResponse.health_status / health_observed_at; 90s freshness; absent/stale = unknown |
| Active feed priority | Active stored incident first, then recent timestamp in selected property; healthy/configured fallback; manual selection wins |
| Incident fields / reason / zone / source ID | GET `/api/v1/incidents` and `/api/v1/incidents/{id}` |
| Alert counts | All retained authorized incident pages; OPEN/ACKNOWLEDGED + HIGH/CRITICAL only; not a today counter |
| Recent list | First 100 records of authorized incident results, with total retained count explicitly labeled |
| Track count | GET `/api/v1/tracks`, property/camera filtered; latest asynchronous observations, not current video-frame coordinates |
| Timeline / actor / correlation | GET `/api/v1/incidents/{id}/history` |
| Commands | POST `/api/v1/incidents/{id}/commands`; reason required; state and read/write enforced server-side |
| Evidence catalog | GET `/api/v1/incidents/{id}/evidence` |
| Evidence playback | POST `/api/v1/evidence/{id}/access`, then authenticated GET returned content route, blob viewer; no arbitrary metadata URLs |
| Camera playback | POST `/api/v1/frigate/cameras/{id}/playback-access`, POST SDP `/webrtc` with bearer + X-Playback-Grant |
| DB/MQTT readiness | GET `/health/ready` (503 is a measured degraded result, not a JSON failure) |
| Realtime invalidation | `/api/v1/events/stream`; REST refetch on connect/reconnect/overflow and 15s polling |

API interfaces are aligned manually in `backend/dashboard/src/api.ts`; they
are **not** generated. Engineer 2's `/openapi.json`,
`backend/app/schemas/{camera,event,incident,property}.py` and
[backend domain contract](../contracts/backend-domain-v1.md) are the reference.
Update wire interfaces and fixture responses together; run typecheck, Python
contracts and browser tests before merging. Pagination is bounded at 100 pages
per collection; exceeding it displays an error instead of a fabricated total.
The current REST API does not provide a transactionally frozen pagination
snapshot or aggregate endpoint; rapidly changing collections are eventually
reconciled by resync. Add aggregates with Engineer 2 before large deployments.

## Real-data checklist

- Camera configured/enabled is not evidence of online health. Unknown stays unknown.
- Counts have an explicit all-retained scope and selected-property filter.
- Empty successful responses show zero/no recent activity; unavailable APIs
  remove the monitoring cards and show an error instead of stale live numbers.
- Times come from source observation, persisted creation/history or measured
  health fields and render in browser-local time. No wall-clock overlay claims
  to be the camera frame time.
- Live indicators require actual video playing; the normal feed is muted.
- Detection rectangles are suppressed on asynchronous live video. The reusable
  geometry utility supports contain/cover/mirror/resize and rejects invalid
  coordinates. Frame-synchronized live metadata or retained incident-frame
  metadata is required before enabling those overlays.
- Evidence requires both the user's bearer session and a short-lived grant;
  blobs are revoked when replaced/unmounted and after 60s. 401/403/404 shows an
  explanatory retry state. No latest-camera snapshot is presented as incident evidence.
- Dispatch assignment/worker delivery, queue backlog, parsing errors, lag and
  DB retry metrics display Unavailable until real owner endpoints exist.
- Camera reconnect is disabled with an explanation for disabled configuration.
  Incident commands require a reason and are hidden for read-only sessions.

## Automated checks and local evidence

Environment: Windows PowerShell, Python **3.14.3**, Node **24.14.1**;
Vite **8.3.5**, React **19.2.8**, Playwright **1.64.1** / Chromium build **1248**.
Python package versions are recorded in
[engineer-4-python-environment.txt](../status/engineer-4-python-environment.txt).
Frontend resolved versions are in `backend/dashboard/package-lock.json`.
CI uses Python 3.12, Node 24.14.1 and PostgreSQL 16. No live/cloud/push
credentials were used by the tests.

Executed from `backend`:

```powershell
New-Item -ItemType Directory -Path .test-tmp -Force | Out-Null
..\.venv\Scripts\python.exe -m pytest -q --basetemp=.test-tmp/acceptance-final
..\.venv\Scripts\python.exe -m compileall -q app tests
..\.venv\Scripts\python.exe -m alembic heads
```

Observed: **232 passed, 8 skipped**, 1 upstream Starlette TestClient
deprecation warning (5.51s). Compileall succeeded; migration graph reports
`0010_reporter_credentials (head)`. Seven skipped PostgreSQL integration tests
need `RUN_POSTGRES_TESTS=1` and a disposable DB; one new broker-stack test needs
`RUN_STACK_TESTS=1` in the isolated compose setup. They are **not PASS** locally.
The existing PostgreSQL head assertion was updated from 0009 to actual 0010.
Initial test execution hit Windows temp access restrictions; a workspace-local
`--basetemp` resolves that without changing the media-security test.

Executed from `backend/dashboard`:

```powershell
npm.cmd run typecheck
npm.cmd run build
npm.cmd run lint
$env:PLAYWRIGHT_BROWSERS_PATH = "$((Resolve-Path ../..).Path)\.cache\playwright"
npx.cmd playwright install chromium
```

Typecheck, production build and lint succeeded (Vite 8.3.5; 33 modules).
`npm audit fix` applied compatible patches; its result was **0 vulnerabilities**.
Use `npm.cmd` on this host because PowerShell blocks npm.ps1.

On Linux/CI, `npm test` starts/stops Vite through Playwright. This Windows
sandbox left the automatic server-teardown process waiting after tests;
start `node node_modules/vite/bin/vite.js --host 127.0.0.1` in another terminal
and run:

```powershell
$env:PLAYWRIGHT_EXTERNAL_SERVER = '1'
npm.cmd test
```

Observed: **6 passed (5.4s)**, exit 0, covering property filtering, persisted
incident commands/history, degraded MQTT readiness, expired evidence, token
headers/clearing, socket expiry, reconnect, duplicate/out-of-order invalidation,
stale backend removal, simulated playback failure/renewal/fullscreen/resize and
box geometry validation. These browser tests stub APIs/signaling intentionally;
they do not prove a real camera or dispatch worker is operational.
Desktop/narrow screenshots were generated and visually inspected in
`backend/dashboard/test-results/dashboard-{desktop,narrow}.png`. They are
generated, ignored artifacts; CI uploads browser reports/traces/screenshots.

Existing suites remain authoritative for parser, tracking, rule engine,
idempotency, rollback, broker client reconnect, tenant isolation, media security,
auth, database and migration behavior. New delivery tests verify actual
WebSocket sessions share event IDs, foreign properties receive no incident,
queues/connection counts are bounded, expired sessions close, failed commands
emit nothing, playback grants reject actor/camera/property mismatch and expiry.

## Disposable Docker integration

Requires a Linux Docker host or Docker Desktop with Linux containers.
Docker is **not installed on the implementation host**, so the following
compose render/build/run and PostgreSQL smoke tests are unexecuted here.

```sh
docker compose -f backend/tests/compose.yml --profile stream config --quiet
docker compose -f backend/tests/compose.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f backend/tests/compose.yml logs --no-color
docker compose -f backend/tests/compose.yml down --volumes
```

The test-only project uses tmpfs PostgreSQL, isolated Mosquitto, backend,
fake HTTP rule/notification providers and an executable broker vertical slice.
It exposes no host service ports and reads no production .env. Test DB URL is
guarded before test writes. The fixture is
`backend/tests/fixtures/person-in-zone.json` (`p4-person-zone-001`); the test
adds a unique suffix for replay-safe runs, creates North/South test properties,
and uses a real MQTT message, adapter and DB transaction. It asserts one stored
incident/receipt after duplicate delivery, authorized REST, foreign-property
denial, WebSocket delivery and acknowledgment/resolution history. The rule
decision is deliberately simulated at the owner boundary. It is not a live
Frigate detector acceptance or marshal dispatch acceptance.

The optional `stream` profile adds MediaMTX 1.9.3 and an FFmpeg-generated test
pattern at `rtsp://sample-gateway:8554/pattern`, without camera hardware:

```sh
docker compose -f backend/tests/compose.yml --profile stream up --build sample-stream
```

This is a test signal for Engineer 1's gateway integration, not a second
production stream configuration. The Alpine image version is pinned but its
package repository resolves FFmpeg; record the resolved image/package digest
in the team acceptance run. Fake `/notifications` supports success or explicit
503 via `simulate_failure`; no production provider is contacted and no missing
notification worker is replaced by that stub.

CI: existing `.github/workflows/backend.yml` collects and executes Python
tests with PostgreSQL and migration smoke coverage; it now installs test
requirements (including SQLite for isolated auth tests) and compiles sources.
`.github/workflows/dashboard.yml` executes lint/type/build/browser tests and
Docker config + broker slice, uploads evidence, and tears down its own test
project. Neither workflow has been run remotely from this session.

## Integrated demo and sign-off agenda

1. Record Git SHA, image/package versions, fixture suffix and property/camera IDs.
   Run core checks and Docker slice above; attach outputs, never infer PASS.
2. Engineer 2 supplies North-only and South-only read tokens plus a North
   write token. Open two North browser sessions and one South session. Verify
   each camera/incident list and every direct media/API URL is property scoped.
3. Engineer 1 connects the sample stream through the actual secured go2rtc
   gateway. Open the enabled camera, fullscreen/resize/mute indicator, stop and
   restore source. Capture reconnect and measured health timestamps. Invalid or
   expired playback grants must not negotiate. Mark server-side peer revocation
   separately until implemented.
4. Publish the sanitized fixture on test MQTT, via the executable stack test.
   Expect one candidate decision, one committed incident, one source receipt,
   authorized REST, matching event IDs in both permitted sessions and no foreign
   event. Repeat identical delivery and confirm no duplicate incident.
5. Open incident details and retained evidence; check source/zone/reason,
   observed and created times, history actors and correlation IDs. Engineer 1/2
   must first persist the actual incident frame under EVIDENCE_ROOT; a Frigate
   latest snapshot URL does not satisfy this step. Expired/deleted/forbidden
   media must show a safe error.
6. Disconnect dashboard networking, change persisted incident state, reconnect
   and hard refresh. Expect REST truth restored, no duplicate in-session alert,
   resolved incidents removed from active counts. New HIGH/CRITICAL OPEN
   incidents trigger one in-page notice after the initial baseline.
7. Stop/restore the test broker and DB; verify measured degraded/unknown/error
   states with timestamps. Where worker/queue/lag metrics are unavailable,
   record BLOCKED rather than pretending a percentage is healthy.
8. Engineer 3 provides real candidate → offer → acceptance → en-route → on-scene
   → resolved API/worker integration with timeout, duplicate acceptance,
   unavailable responder and provider-failure fixtures. Run via tests or an
   internal web operator; no mobile app required. This checkout cannot execute
   that vertical slice yet.
9. Collect owner reproduction steps and sign-offs below. No acceptance review
   was scheduled or messages sent by this implementation session.

| Owner | Required handoff / evidence | Current acceptance |
|---|---|---|
| Engineer 1 | Actual stream gateway, source dimensions/orientation, synchronized metadata, retained frame and measured camera heartbeat | BLOCKED live verification |
| Engineer 2 | Monitoring session issuance/revocation, authoritative permission changes, server peer shutdown, retained evidence references, aggregates/trace endpoints and production diagnostics ACL | BLOCKED production guarantees; current REST integration implemented |
| Engineer 3 | Dispatch/offer/acceptance/escalation/worker APIs and deterministic timeout/failure cases | BLOCKED; tables alone are insufficient |
| Engineer 4 | Existing UI integration, authenticated client, realtime recovery, available health, quality gate and runbook | Core local checks PASS; infrastructure acceptance pending |

## Troubleshooting

401/403: use monitoring scopes and property claims, not reporter scope; expired
tokens require a new session. Playback 503: configure a 32+ character signing
secret and reachable gateway. Media 404/503: check retained file under configured
EVIDENCE_ROOT, signing secret and evidence ownership; do not bypass authorization
with raw file URLs. No video: check browser autoplay/muted and ICE connectivity
with Engineer 1, proxy SDP route and authorized grant before investigating UI.
Unknown camera health: require a recent measured observation, not an enabled row.
Socket failure: check proxy upgrade/CORS/TLS and use Retry after bounded retries;
REST polling remains active. Readiness 503: DB/MQTT measurements are degraded.
No boxes on live video is expected until synchronized metadata exists.
