# Main camera PC handoff

Prepared 2026-11-04. Repository checks ran on macOS. The Windows camera PC was
unavailable, so none of the commands below have been run against its containers.
The 2026-11-03 reports remain historical observations, not deployment evidence.

## Install the changes

Copy the updated repository, or overlay the supplied changes archive onto a
checkout of main at `43463fc` or newer. Extract at the repository root so that
`backend/scripts/acceptance_host.ps1` exists. Preserve local `.env`, password
files, camera media, Frigate databases, and existing Docker volumes. Back up any
locally modified files before overlaying the archive. Do not remove
`C:\SecurePulse-person1`.

On the PC, install/use Python 3.11+, Docker Desktop with Compose, FFmpeg on PATH,
and Node 22.18+ for the dashboard. In PowerShell, from the repository root:

```powershell
python backend/scripts/edge_operations.py inventory
docker compose ls
```

The inventory prints project/source labels, images, port bindings and volume
ownership, never container environments or credentials. Identify the project
actually serving the intended database and cameras. The canonical source file
is `backend/deployment/docker-compose.yml`, with default project `securepulse`.
`securepulse-person1` remains an isolated project; old project `deployment` and
the standalone `frigate` are separate. A new project name creates different
volumes; changing a name does not migrate existing data.

Set `$project` to that verified project, not a guessed default:

```powershell
$project = "securepulse-person1" # Replace only after inspecting inventory.
$composeArgs = @("compose", "--project-name", $project, "--env-file",
    "backend/deployment/.env", "-f", "backend/deployment/docker-compose.yml")
docker @composeArgs config --quiet
docker @composeArgs ps
```

Use the PC's existing ignored `backend/deployment/.env`. Merge new template
options rather than replacing secrets. `RTSP_REQUIRED_PATHS=live,webcam` checks
both publisher paths. If Front Door is a direct IP camera, remove `live` from
that list and validate that camera via Frigate/edge health. WebRTC still uses
literal `127.0.0.1:18556` in `backend/frigate/config/frigate.yml`; changing an
environment variable cannot change that candidate.

Before replacing the backend, take a verified database backup using the existing
[database runbook](backend-database.md). Build the backend, then check the current
revision before applying pending migrations from that built image:

```powershell
docker @composeArgs build backend
docker @composeArgs run --rm --no-deps backend alembic current
docker @composeArgs run --rm --no-deps backend alembic upgrade head
docker @composeArgs up -d --no-deps backend video-readiness
```

Check each exit code before continuing. Run migrations only against the verified
project after backup. These commands do not redeploy PostgreSQL, the broker, or
Frigate. If their checked-in configuration also needs applying, update each
identified service during its maintenance step rather than replacing all stacks.
Do not use `down -v`, volume removal, or a project rename for deployment.

The readiness sidecar is necessary because MediaMTX's minimal image lacks probe
tools. Its Docker health checks fresh RTSP DESCRIBE results containing video SDP
for every required path. Missing publishers make `video-readiness` unhealthy;
this is expected until cameras publish. It does not block MediaMTX startup or
restart another container. SDP availability alone cannot prove visible frames;
the source acceptance check below decodes actual frames and checks for black.
Backend Docker health now uses `/health/ready`, including database and MQTT.

## Restore the Front Door capture

Inventory the existing publisher process/device first. On Windows, list devices:

```powershell
ffmpeg -hide_banner -list_devices true -f dshow -i dummy
```

Close an application holding the intended device only after identifying it.
Check the camera privacy permission, physical shutter, selected device, capture
format, and publisher output. Do not change camera mappings or thresholds to
mask the black input. Start the real Front Door camera with its actual device
name and a format the device supports, for example:

```powershell
ffmpeg -hide_banner -f dshow -framerate 15 -video_size 640x480 -i 'video=YOUR EXACT FRONT DOOR DEVICE NAME' -an -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:18554/live
```

Keep that publisher running. Keep the separate authorized laptop source on
`/webcam`; one device may not support two simultaneous DirectShow consumers.
Use the existing working laptop publisher rather than duplicating it. Never use
the `test-pattern` profile as evidence of person detection.

```powershell
python backend/scripts/edge_operations.py sources
docker @composeArgs ps video-readiness
Invoke-RestMethod http://127.0.0.1:18000/health/ready
Invoke-RestMethod http://127.0.0.1:18000/health/edge
```

Both sources must decode at least five seconds with no one-second black interval;
both cameras must be online with detection enabled. A genuinely dark scene can
also fail black detection: inspect the actual source rather than weakening the
check. No frames or source URLs are saved by the diagnostic.

## Broker and network cleanup

The repository's canonical and legacy broker templates now disable anonymous
access. The observed PC broker used an untracked `mosquitto-original.conf`:
changing repository templates alone cannot secure it. Use inventory mount and
project labels to find its real configuration. Inventory clients from sanitized
broker connection records; never expose a password or dump camera payloads.

For each required client, provision a separate account and the minimum topic
ACL, configure its credentials, and verify connectivity before disabling
anonymous access in the actual mounted configuration. Mount the password file
and ACL at `/mosquitto/config/passwordfile` and `/mosquitto/config/mosquitto.acl`.
The canonical ACL covers Frigate and backend only; add known legacy clients
deliberately. Keep backups and confirm every client after reloading/restarting
that exact broker. Existing password files must not be recreated with `-c`.
`setup_mqtt_auth.ps1` now refuses to overwrite them.

The canonical service ports and opt-in standalone Frigate ports are loopback
bound. For legacy running services, change the actual Compose source identified
by inventory and recreate only the services whose bindings changed. Retain
documented network access required by existing clients. For host-local dashboard
acceptance use `http://127.0.0.1:5173`; LAN streaming requires a reachable ICE
candidate and matching deliberate network bindings. Keep the current host-local
scope unless LAN access is required.

Verify the canonical broker with:

```powershell
./backend/scripts/smoke_mqtt_acl.ps1 -ProjectName $project
```

The probe uses `frigate/engineer1/acl-probe/set`, not a camera control or event
topic. It checks allow/deny behavior, invalid credentials and anonymous rejection.
This does not test a different legacy broker or authorize its retirement.

## Run baseline and recovery acceptance

The default script reads the host without restarting services:

```powershell
./backend/scripts/acceptance_host.ps1 -ProjectName $project -BaselineSeconds 120
```

If API authentication is enabled, provide a read-scoped operator token using
`SECUREPULSE_OPERATOR_TOKEN` in the process environment. It is not printed. Keep
both expected camera streams active and use representative activity. Results
include container CPU/memory, camera/inference FPS, queue errors and net persisted
event throughput. Zero throughput with no activity is not a load test. Record
the camera count, source resolution/rate, host hardware and activity alongside
the evidence when selecting the workload.

During maintenance, opt in to broker and backend restart checks:

```powershell
./backend/scripts/acceptance_host.ps1 -ProjectName $project -RestartRecovery
```

Each restart requires a healthy baseline and resolves exactly one running service
with matching project/service labels. Recovery requires three consecutive ready,
online observations without new processing/delivery failures. This does not prove
fresh post-restart detections: perform a new walk-through afterwards.

For camera disconnect/reconnect, stop only the known publisher you started, check
that its camera becomes offline and the readiness sidecar becomes unhealthy,
then restart that same publisher. Repeat for each source. Confirm video advances,
new events persist, and camera health returns online. Do not stop MediaMTX or
kill unspecified FFmpeg processes to simulate this. Record recovery times and
sanitized results; private imagery is unnecessary.

JSON evidence is saved under ignored `backend/operational-evidence/<timestamp>/`.
Any failed/blocked check makes the acceptance script exit nonzero.

## Browser and person acceptance

Install/build/check the dashboard and start Vite from `backend/dashboard`:

```powershell
npm ci
npm test
npm run build
npm run lint
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173` on the camera PC. Paste the complete contents of
`backend/dashboard/scripts/browser-acceptance.js` into DevTools' console. Over
the next 60 seconds, have an authorized person enter, move across, and leave
each camera view. The JSON result checks sustained advancing playback, moving
boxes, clearing after departure, and invalid confidence percentages. Both camera
IDs must appear. Results are also at `window.securePulseAcceptance`. No images
or requests are generated by that helper. A failure to observe movement or
clearing leaves overlays `not_verified`; repeat under controlled conditions.
Visually confirm the boxes follow the actual person and are correctly aligned.

The dashboard now marks LIVE when the video emits `playing`, rather than merely
when an RTC track is received. Its normalized box mapping also handles playback
resolution differing from detector resolution; cover/contain geometry has
regression tests.

Follow the full [event acceptance procedure](../END_TO_END_TEST_REPORT.md) for
each camera: match a fresh Frigate person event ID and snapshot HTTP 200 to the
backend API and database row; verify WebSocket active/end messages and browser
overlays. Record times in UTC. If confidence exceeds 100%, capture the displayed
value, matching event ID, and API numeric confidence without private imagery.
Only mark host acceptance complete after all of these checks pass.

## Rollback

Preserve the previous backend image tag and configuration backups before rollout.
If a service fails, restore its previous config/image and recreate only that
service in the same project. Do not automatically downgrade a migrated database;
use the verified backup and database runbook if schema recovery is necessary.
Keep `securepulse-person1` and all volumes until the intended integrated project
has passed its runtime checks.
