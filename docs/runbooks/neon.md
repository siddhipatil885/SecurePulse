# Neon identity/database with media on the host

Current configuration: 2026-11-05. Project `hidden-tree-86231075` (Secure-Pulse),
organization `org-tiny-resonance-74526967`, branch `production`, AWS Singapore.

## Where data lives

| Data | Location |
|---|---|
| Account credentials for new accounts | Neon Auth (`neon_auth` schema) |
| Properties, memberships, incident/report details, timeline, assignments and media metadata | Neon Postgres |
| Reporter images and MP4 bytes, direct Python runtime | Private `backend/operational-evidence/media/` on the host |
| Reporter images and MP4 bytes, Docker runtime | Existing `<project>_reporter_evidence` volume |
| Camera snapshots and any recordings | Existing local Frigate media storage |

`EVIDENCE_STORAGE=local` is set in both backend env files. Runtime cloud-storage
credentials are cleared. No image/video binary or base64 content is inserted into
Postgres. Postgres stores media type, filename, size, checksum and a relative local
file reference. Camera footage is not uploaded to Neon. The already-provisioned
private `assets` bucket is preserved but unused by the app. A tiny test image was
uploaded only on the verification branch before the offline-media instruction;
the current runtime and current live verification use local media.

The direct Python directory and Docker volume are distinct. Copying env files to
another PC does not copy images/videos: preserve/migrate and back up the actual
media directory/volume with the database metadata. A cloud database backup cannot
restore an offline video. The host must be running and reachable to view media.
Do not run different backends with the same database and unrelated media roots.

## Auth and database architecture

FastAPI keeps SQLAlchemy with asyncpg. Application requests use Neon's pooled
`DATABASE_URL`; Alembic uses the direct `DATABASE_URL_UNPOOLED`. Browser/mobile
clients continue calling the same authenticated API; database URLs, signing keys
and service credentials are never placed in client variables.

When `NEON_AUTH_BASE_URL` is configured, new registration and admin provisioning
use Managed Better Auth. The backend keeps the provider's signed cookie only in
an ephemeral HTTP client, validates the session, then signs it out. It issues its
existing revocable SecurePulse JWT/cookie, preserving property permissions,
device revocation, websocket access and the mobile API contract. Neon identity is
mapped by provider ID (`users.subject = neon:<id>`), never linked merely by email.
New Neon-backed accounts have no local password hash. Password changes go through
Neon and revoke existing application sessions. Existing local-hash accounts keep
their established login path; they are not silently migrated or reassigned.

The server uses the first configured `CORS_ORIGINS` origin for Managed Auth.
Localhost is allowed in the current Neon configuration. Before deploying at a
new domain, register that actual app origin with Neon Auth and configure backend
CORS accordingly. No guessed production domain is installed.

## Storage protections

| Variable | Default |
|---|---|
| `REPORTER_EVIDENCE_MAX_BYTES` | 10,000,000 bytes per file |
| `REPORTER_EVIDENCE_MAX_FILES` | 5 attachments per report |
| `REPORTER_EVIDENCE_MAX_INCIDENT_BYTES` | 50,000,000 bytes per report |
| `REPORTER_EVIDENCE_MAX_PROPERTY_BYTES` | 1,000,000,000 bytes per property |
| `REPORTER_EVIDENCE_MIN_FREE_BYTES` | Keep at least 1,000,000,000 bytes free on the host |

Limits apply before writing a new attachment. Property/report locks serialize
quota decisions across concurrent requests. Idempotent retries return the existing
attachment even when the quota is reached. The upload middleware rejects oversized
Content-Length early and bounds chunked multipart uploads before a large video can
fill temporary storage. Uploading stops at limits; existing evidence is never
automatically deleted. These limits cover reporter media, not other programs or
Frigate's own storage. Camera recording is currently disabled in the checked-in
Frigate config and local snapshots have its existing 14-day retention.

Mobile incident history requests `include_details=false`, avoiding repeated
attachment/timeline loads. Full incident details remain available when opened.
Assignment lookups return only the latest assignment per incident. Lists stay
paginated; downloads stream local files and support byte ranges for video.
Database permissions are still checked live; they are not bypassed by caching.
No automatic incident/audit deletion policy has been applied.

### 1 GB Neon budget

`DATABASE_STORAGE_BUDGET_BYTES=1000000000` records the requested database budget.
Use `npm run neon:storage` to check live size, including Auth and indexes. It warns
at 80% and exits nonzero at 90%, before the configured budget. This is a read-only
monitor, not a provider billing estimate or a hard write quota. Other Neon branches
and restore history may contribute to provider usage separately.

Camera receipts now store the source identity plus a SHA-256 fingerprint instead
of another copy of the full camera metadata for every lifecycle revision. Stored
camera-event JSON is bounded to 8 KB; embedded media fields are omitted and oversized
diagnostic fields are marked/truncated with an original-payload checksum. Normal
rule/zone/track metadata and the input sent to the security engine are preserved.
Existing incident/audit rows are not deleted. Metadata will still grow over time:
archive/review retention before the budget warning rather than assuming a finite
database can retain unlimited camera history.
The backend Docker context also excludes private env/recovery files, local media,
runtime databases and development dependencies, keeping them out of image layers.

## Commands and private configuration

```sh
neon deploy
npm run neon:sync
npm run neon:storage
npm run build
npm run test:neon
```

`neon deploy` provisions Neon services, not the Python server, camera publishers,
MQTT or the frontend website. It writes the managed vars into ignored `.env.local`.
`neon:sync` merges Postgres/Auth variables into the existing private backend and
deployment env files, keeps local media selected, clears cloud-storage credentials
from those runtime files, and creates private `.env.pre-neon-*` recovery copies.
Other settings, original local database/broker credentials and the supplied `env`
source are preserved. The old local database is not migrated/copied automatically.

Run Python from `backend/` so its `.env` loads. Install `requirements.txt` in its
virtual environment. The root npm Python launcher detects that environment on
Windows/macOS, or accepts `SECUREPULSE_PYTHON`. The root `npm run build` delegates
to the dashboard production build. Set the phone API URL on the actual host with
`python backend/scripts/configure_client_host.py`; this is still required because
the host PC address is unknown here. Restart the backend/Vite/Expo after env changes.

`test:neon` starts the real FastAPI app on loopback port 18083, verifies real Neon
Auth/Postgres plus authenticated local evidence, then stops it. It creates and
retains clearly identified `example.invalid` verification accounts/properties/
reports. It does not delete existing data or upload test media to cloud storage.
Use `-- --env-source <private-preview-env>` for a Neon verification branch.

Normal pytest/browser/mobile suites use isolated databases and no live Neon auth.
The explicitly enabled PostgreSQL suite creates/drops only random test schemas;
it never drops or clears `public` or `neon_auth`.

See [the verification record](../status/neon-20261105.md) for results and limitations.
