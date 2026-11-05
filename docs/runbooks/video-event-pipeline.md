# Video and Frigate event pipeline runbook

For the current copy-to-PC deployment and acceptance sequence, see
[main host handoff](main-host-handoff.md) and the
[deployment inventory](../DEPLOYMENT_INVENTORY.md). Existing live deployments
must use their verified project identity and preserved credentials.

This runbook uses `backend/deployment/docker-compose.yml` as the single canonical stack. The separate `backend/frigate/docker-compose.yml` is a legacy opt-in profile and must not be started alongside the canonical stack. The default Compose project name is `securepulse`, matching the original deployment and its named volumes. Use `--project-name securepulse-person1` only for a deliberately isolated test deployment with its own `.env`; never use that name when verifying the original database.

## Topology and host ports

```text
authorized RTSP camera or host publisher
                  │ RTSP
                  ▼
          MediaMTX :8554 ──► Frigate / go2rtc
                                  │ MQTT frigate/events
                                  ▼
                         Mosquitto :1883
                                  │
                                  ▼
                 bounded backend queue → EventProcessor
```

The optional FFmpeg `testsrc2` source checks RTSP transport and frame flow but contains no person. It is disabled unless the `test-pattern` profile is enabled. Use a configured camera or authorized person clip for object detections. Frigate, broker, RTSP, API, and database containers use service-name DNS internally.

| Host port (default) | Service | Purpose |
|---:|---|---|
| 15432 | PostgreSQL | Local backend database |
| 11883 | Mosquitto | Local diagnostics; host loopback only |
| 18554 | MediaMTX | Host publisher and RTSP probe; host loopback only |
| 15000 | Frigate | Local UI and API; host loopback only |
| 18556 TCP/UDP | Frigate WebRTC | Local live view; candidate must match the address reachable by the browser |
| 18000 | Backend | Local API and `/health/edge`; host loopback only |

These defaults are intentionally distinct from the existing common ports to support side-by-side inspection. Change the bind addresses and candidate only for a deliberate LAN deployment; do not publish MQTT or Frigate's internal ports to an untrusted network.

## First start

From PowerShell in `backend`:

```powershell
Copy-Item deployment/.env.example deployment/.env
.\scripts\setup_mqtt_auth.ps1
```

Edit `deployment/.env` and replace all `CHANGE_ME` values. Use separate random passwords for PostgreSQL, Frigate's MQTT publisher, and the backend MQTT reader. Enter the same Frigate and backend MQTT passwords in the password-file prompts and `.env`. Keep `.env` and `deployment/mosquitto/config/passwordfile` private; both are ignored by Git.

Validate the isolated test deployment. The project-name override keeps its containers, network, and named volumes separate from the original `securepulse` deployment:

```powershell
docker compose --project-name securepulse-person1 --env-file deployment/.env -f deployment/docker-compose.yml config --quiet
docker compose --project-name securepulse-person1 --env-file deployment/.env -f deployment/docker-compose.yml up -d
docker compose --project-name securepulse-person1 --env-file deployment/.env -f deployment/docker-compose.yml ps
```

Starting Compose changes Docker state, creates named volumes, and binds the listed host ports. Do this only on the separate test deployment you intend to use. The stack stores PostgreSQL data and Frigate metadata in named volumes, Frigate recordings under `backend/frigate/media`, and broker persistence/logs in named volumes. Do not run `up` against project `securepulse` until its current containers and database have been identified and a database backup is available; Compose may recreate services when configuration changes.

The synthetic publisher is opt-in and test-only. To check RTSP transport in the isolated test project, start it with `--profile test-pattern`; do not enable that profile for the original deployment:

```powershell
docker compose --project-name securepulse-person1 --profile test-pattern --env-file deployment/.env -f deployment/docker-compose.yml up -d
```

## Source choices

1. **RTSP/IP camera:** set `FRIGATE_RTSP_URL` in ignored `deployment/.env` to a URL reachable from the Frigate container. Keep usernames and passwords in that ignored file. Restart only Frigate after changing the source.
2. **Windows laptop camera:** run an FFmpeg publisher on the host to `rtsp://127.0.0.1:18554/live`, then leave `FRIGATE_RTSP_URL=rtsp://mediamtx:8554/live`. Keep the DirectShow device name and any source credentials out of committed files.
3. **Authorized sample clip:** publish a locally owned/authorized clip to the same MediaMTX path in real-time mode. Do not commit the clip. The bundled test pattern is not a substitute for person footage.

Frigate supports `FRIGATE_` environment substitution using braces, such as `{FRIGATE_RTSP_URL}`. Compose expands `.env` for containers; it does not expand arbitrary `$VAR` syntax inside bind-mounted YAML. Keep any deployed credentials in ignored local env/secrets, not YAML.

## Smoke checks and evidence

Run these only when Docker and a source are available:

```powershell
docker compose --project-name securepulse-person1 --env-file deployment/.env -f deployment/docker-compose.yml logs --tail 100 mqtt mediamtx frigate backend
ffprobe -v error -rtsp_transport tcp -show_streams rtsp://127.0.0.1:18554/live
Invoke-RestMethod http://127.0.0.1:18000/health/edge
```

Expected: broker healthy; Frigate logs show MQTT connection and incoming frames; `ffprobe` reports an H.264 stream; `/health/edge` shows MQTT connected and Frigate reachable. The test pattern should not trigger person events. For a real smoke test, use an authorized clip/camera, subscribe with the authorized backend account, capture sanitized `new`, `update`, and `end` event fields, then verify event processing and snapshot/clip retrieval. Record OS, image tags/digests, command, result, and sanitized logs.

Run the automated allow/deny checks after the broker is healthy:

```powershell
.\scripts\smoke_mqtt_acl.ps1 -ProjectName securepulse-person1
```

It publishes only to `frigate/engineer1/acl-probe` and `frigate/engineer1/acl-probe/set`, which the backend does not subscribe to. The latter matches the control-topic ACL without toggling a real camera. The script checks authorized publishing/subscribing, denied cross-role access, invalid credentials, and anonymous rejection. Do not paste passwords into shell history, tickets, or logs.

## Diagnostics and recovery

| Condition | Check | Expected status/action |
|---|---|---|
| No Docker daemon | `docker version` | Mark all runtime checks BLOCKED; do not infer a pass from static config. |
| No camera/clip | `docker compose ... logs frigate` | The optional test pattern can confirm transport only; person detection remains BLOCKED. |
| No RTSP frames | `ffprobe` then Frigate logs | Verify source reachability from the container and its codec; do not change detection thresholds to hide stream faults. |
| MQTT unavailable | `docker compose ... logs mqtt frigate backend` and `/health/edge` | Check password file, ACL, local listener, then restart broker before Frigate/backend. Reconnect uses bounded Paho backoff. |
| FFmpeg publisher exits | `docker compose --project-name securepulse-person1 --profile test-pattern ... logs sample-publisher` | Check RTSP path and MediaMTX logs; Compose restarts the test publisher. |
| Frigate camera health | `/health/edge` and Frigate logs | `offline` means Frigate reports 0 camera FPS; `detection_disabled` means its runtime camera detection toggle is off; `unknown` means stats/FPS are unavailable. Confirm detection is enabled and recovery after reconnect. |
| Broker/container recreation | Compose logs and `/health/edge` | Confirm reconnect and recovery; database receipts deduplicate already persisted revisions. MQTT source delivery itself is not durable. |
| Disk pressure | `docker system df` and media volume size | Check Frigate retention and host free space; remove generated media only through Frigate retention/approved cleanup procedures. |

Stop the branch stack without deleting its data:

```powershell
docker compose --project-name securepulse-person1 --env-file deployment/.env -f deployment/docker-compose.yml down
```

This command is only for the isolated `securepulse-person1` test project. Never run it against the original `securepulse` project without explicit approval. Do not add `-v`; that would delete database, Frigate, and broker volumes.
