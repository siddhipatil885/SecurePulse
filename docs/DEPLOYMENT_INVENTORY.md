# Deployment inventory

Updated 2026-11-04 from checked-in configuration. Runtime identity and legacy
entries are historical observations from 2026-11-03; confirm them on the PC with
`python backend/scripts/edge_operations.py inventory` before changes.

| Deployment | Source | Host ports / scope | Data ownership |
|---|---|---|---|
| Canonical project `securepulse` | `backend/deployment/docker-compose.yml` | 15432 PostgreSQL, 11883 MQTT, 18554 RTSP, 15000 Frigate, 18556 TCP/UDP WebRTC, 18000 backend; default loopback | `<project>_postgres_data`, `<project>_frigate_config`, `<project>_mosquitto_data`, `<project>_mosquitto_log`; media bind at `backend/frigate/media` |
| Isolated `securepulse-person1` | Historically `C:\SecurePulse-person1\backend\deployment\docker-compose.yml` | Same configured defaults; never run conflicting bindings alongside another copy | Separate named volumes with `securepulse-person1_` prefix; confirm actual media bind path |
| Legacy `deployment` | Resolve runtime Compose labels; observed source/config outside canonical tree | Historically 8000, 5432, 1883 on all interfaces | Resolve runtime mount names/paths; do not map these to canonical volumes by assumption |
| Legacy standalone Frigate | `backend/frigate/docker-compose.yml`, explicit `legacy-standalone` profile | Repository defaults 18971 UI, 28554 RTSP, 28556 TCP/UDP WebRTC on loopback; observed old container used 8971/8554/8556 on all interfaces | Bind directories `backend/frigate/config` and `backend/frigate/storage`; independent tracker and database |
| Dashboard | `backend/dashboard`, Vite | 5173; use `--host 127.0.0.1` on the camera PC | No server-side persistent volume |
| Video readiness | Canonical Compose `video-readiness` | No published ports | Ephemeral sanitized status in `/tmp`; read-only probe script mount |

The canonical backend additionally uses `<project>_reporter_evidence` for writable
manual-report attachments, mounted at `/media/evidence/reporter-incidents`.
Camera media stays read-only at `/media/evidence/camera`; legacy relative camera
references resolve through that mount. Include reporter evidence in backups.

The default project name identifies a deployment convention, not proof that the
running original database belongs to it. Runtime project/service labels and
mounts are authoritative. Existing projects must remain separate until their
consumers and data have been reconciled. Named volumes isolate databases;
bind-mounted media are isolated only when their source paths differ.

The inventory script prints all Compose-managed containers, including stopped
ones, and flags all-interface bindings. It deliberately excludes environments,
raw logs and file contents. It does not inventory host publisher processes;
record those devices/processes separately on the PC.
