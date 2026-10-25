# Engineer 4 baseline and implementation ledger

Recorded 2026-10-25 (Asia/Calcutta). Canonical Git root:
`C:/Users/patil/OneDrive/Desktop/projects/SecurePulse`.
Starting HEAD: `c3ac692633421b30194d6ba8caaa33df91a92aa3`.
The starting working tree was clean. Changes are prepared in the working tree for review; no commit or team sign-off is implied.

The actual frontend is **backend/dashboard**, with React 19, TypeScript, Vite,
`package.json` and lockfile. `src/App.tsx` renders `components/Dashboard.tsx`;
this is one dashboard, not an empty scaffold. Theme is `src/index.css` and
component CSS. Dev proxy is `vite.config.ts`; configuration template is now
`.env.example`. No AGENTS.md was found in the repository.

## Screen and field inventory

| Component / fields | Starting classification and finding | Current source / status |
|---|---|---|
| `Header.tsx`: branding, nav, avatar | CONFIG / HARDCODED: brand, generic OP avatar; nav links were placeholders | KEEP brand/theme; FIX links target real dashboard sections; connection label describes dashboard, not whole system |
| `Dashboard.tsx`: primary + two previews | REAL API cameras/events; first configured camera always primary | KEEP layout; FIX property filter, all-camera selector, prioritize active incident then recent activity then healthy/configured fallback; manual selection wins |
| `api.ts`: camera name/config | REAL API `/cameras?enabled=true`, first page only | FIX fetch authorized pages including disabled cameras, property/location from CameraResponse |
| `CameraStatus.tsx`: status/last seen | CONFIG enabled, not connectivity; UNVERIFIED timestamps used camera configuration update time | FIX measured `health_status` + `health_observed_at`, 90-second freshness; stale/missing measurement = unknown; disabled distinct |
| `SecuritySummary.tsx`: counters | REAL API but limited to first 100 events; enabled cameras counted online | FIX fetch retained authorized incident pages; active HIGH/CRITICAL OPEN/ACKNOWLEDGED alerts; healthy measured cameras only; explicit all-retained scope |
| `RecentEvents.tsx`: type/time/camera/confidence/evidence | REAL API `/events`; unsafe metadata snapshot URL could point to current rather than incident frame | KEEP list styling; FIX `/incidents`, local observed time, persisted reason/state/severity; detail control; remove auto-loading arbitrary/latest URLs and score tile |
| `ActiveAlerts.tsx`: severity/type/time | REAL API derived high/critical, resolved updates could remain active | FIX derive alerts from current persisted states; actual HIGH/CRITICAL label; acknowledgment state |
| `CameraFeed.tsx`: live video | LIVE STREAM via authorized `/frigate/cameras/{id}/webrtc`; no browser auth; live asserted on track arrival | KEEP player/card; FIX bearer requests, 60s signaling grants, live after playing, timeout/retry, disconnect state, muted/fullscreen/reconnect controls |
| `DetectionOverlay.tsx`: boxes | REALTIME `/tracks` and `person_tracks`; geometric cover mapping but MQTT not video-frame synchronized | KEEP geometry utility, tested cover/contain/mirror/resize; BLOCKED synchronized live metadata; live boxes suppressed with explanation |
| Person observation counts | REAL API `/tracks` and realtime projection | latest anonymous observations, scoped by authorized camera and property; not claimed frame-aligned |
| `IncidentDetail.tsx` | MISSING | FIX persisted detail, zone/reason/source/timestamps, history/correlation IDs, scoped commands with reason and backend permission; read-only actions explained |
| Incident evidence | UNVERIFIED: processor persisted a latest-snapshot proxy URL as file_path | FIX grant+authenticated blob viewer and expiry/errors; BLOCKED upstream retention: current ingestion does not store incident snapshots under EVIDENCE_ROOT |
| `Operations.tsx` | MISSING | FIX real `/health/ready` DB/MQTT and checked timestamp, accepts degraded 503; unsupported diagnostics explicitly Unavailable |
| Auth / property choices | MISSING dashboard token handling; backend scopes/property claims exist | FIX memory-only token form, bearer REST, WebSocket subprotocol, `/dashboard/session`, `/properties`; backend enforces all actions |
| Realtime | REALTIME WebSocket, one attempt, no recovery | FIX versioned envelope, bounded queues/connections, resync on overflow/connect, REST refetch-diff, dedup/throttling, heartbeat/expiry recheck, bounded reconnect and polling |
| Dispatch offers / assignment / notifications | MISSING implementation; schema tables alone exist | BLOCKED Engineer 3 APIs/worker; explicitly Unavailable, no fake responder/status |
| Pipeline trace / lag / queue diagnostics | MISSING endpoints | Source ID, decision reason and history correlation displayed; remaining trace and metrics BLOCKED Engineers 1–3 |

## Verification and work-package status

| Package | Status | Evidence / remaining work |
|---|---|---|
| P4-00 baseline | Implemented | Actual frontend and field inventory above; no redesign |
| P4-01 real monitoring | Implemented against current API; live acceptance blocked | All retained authorized records paginated; property filter and truthful failures; real two-property PostgreSQL tests committed, local execution needs PostgreSQL |
| P4-02 media | Implemented client/grant/geometry tests; physical acceptance BLOCKED | Mocked browser signaling is labeled simulated; Engineer 1 gateway/source dimensions/synchronized metadata + Engineer 2 peer revocation and retained media required |
| P4-03 realtime | Implemented for single-process backend | Tests exercise two sessions, foreign property isolation, expiry, overflow, reconnect/dedup; durable state is REST/DB; multi-process delivery needs shared publisher |
| P4-04 operations | Implemented available measurements | DB/MQTT readiness and measured camera state; missing worker/lag/error metrics explicitly Unavailable |
| P4-05 quality | Core checks executed; full infrastructure BLOCKED locally | 232 Python tests passed; 8 infrastructure tests skipped; browser/type/build/lint evidence in runbook; Docker stack and CI prepared, not run locally |
| P4-06 docs/demo | Runbook implemented; team sign-off pending | No team messages sent or fabricated approval; review agenda and owner handoffs in runbook |

Live camera, broker, DB and notification failure/restoration have **not** been
verified on this host. Browser route fixtures prove UI integration behavior,
not deployment readiness. Docker executable is absent. See the runbook for
exact commands, test evidence and owner-specific blockers.
