# Main host readiness — 2026-11-04

Repository checks ran on macOS. The user confirmed remote access to the Windows
camera PC is unavailable; this deliverable prepares code and instructions for
transfer to that PC. No host deployment, broker reconfiguration, camera capture,
database migration, container restart or physical acceptance was performed.

## Local verification

| Check | Result |
|---|---|
| Full backend suite | 256 passed, 7 skipped |
| New operational tests | 15 passed within that suite |
| Dashboard geometry tests | 3 passed |
| Dashboard production build and lint | Passed, no lint warnings |
| Reporter TypeScript check | Passed |
| Reporter unit tests | 15 passed |
| Reporter navigation tests | 3 passed |
| Canonical/standalone Compose and new CI YAML syntax | Parsed successfully |
| `git diff --check` | Passed |
| Missing Docker/FFmpeg handling | Reports blocked with nonzero exit |
| RTSP probe against absent local sources | Reports not ready with nonzero exit |

The seven skipped backend cases are opt-in PostgreSQL acceptance tests. No
PostgreSQL server was available here. Docker Compose rendering, image builds,
PowerShell parsing, actual RTSP decoding, and remote CI execution have not been
run locally: Docker, FFmpeg, and PowerShell are unavailable. CI configuration now
includes Compose rendering and PowerShell parsing on an Ubuntu runner.

## Prepared changes

The canonical stack now has an unprivileged, read-only video readiness sidecar
that requires fresh successful video SDP checks for its configured MediaMTX paths.
Backend Docker health checks dependency readiness. Both broker templates disable
anonymous access; account setup preserves existing password files, and ACL tests
require explicit project selection without toggling a real camera.

Operational scripts provide sanitized container inventory, decoded non-black
source checks, CPU/memory/inference-FPS/event-throughput sampling, and explicit
project-scoped broker/backend restart recovery. The host wrapper saves JSON
evidence and skips restarts when preflight checks fail.

The dashboard waits for actual playback before showing LIVE. Overlay geometry
now maps normalized boxes directly through the rendered video rectangle, fixing
misalignment when playback resolution differs from detector resolution. Browser
diagnostics observe sustained playback, box movement/clearing and confidence
range without saving images.

The full source transfer archive excludes `.git`, local secrets, virtual
environments, installed dependencies, build output, databases and camera media.
Existing PC secrets and runtime data must be retained.

## Outstanding host evidence

Use [the handoff](../runbooks/main-host-handoff.md) to deploy and collect actual
results. Front Door capture repair, legacy broker/client migration, legacy port
restriction, fresh events for both cameras, browser visuals, a representative
load baseline, and disconnect/restart recovery remain pending on that PC. The
2026-11-03 health reports are preserved as historical evidence.
