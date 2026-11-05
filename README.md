# SecurePulse

SecurePulse connects Frigate video detections to a FastAPI/PostgreSQL backend,
live React dashboard, reporter mobile app, and marshal dispatch workflows.

## Deploy on the main camera PC

Start with [the main host handoff](docs/runbooks/main-host-handoff.md). It covers
copying this source, identifying the existing Docker project, preserving data,
deploying changes, restoring real publishers, and running acceptance checks.

The canonical Compose file is `backend/deployment/docker-compose.yml`. The
isolated `securepulse-person1` project, historical `deployment` project, and
standalone Frigate have independent runtime data. See the
[deployment inventory](docs/DEPLOYMENT_INVENTORY.md) before selecting a project.

After deployment, from the repository root on the camera PC:

```powershell
./backend/scripts/acceptance_host.ps1 -ProjectName YOUR_VERIFIED_PROJECT
```

During maintenance, add `-RestartRecovery` to test broker/backend restarts. JSON
evidence goes to ignored `backend/operational-evidence/`. Complete both person
walk-throughs and browser playback/overlay checks before signing off.

## Development and status

- [Backend setup and APIs](backend/README.md)
- [Dashboard accounts, properties and incident actions](docs/runbooks/dashboard.md)
- [Reporter mobile app](mobile/reporter-app/README.md)
- [Mobile/backend integration and acceptance](docs/runbooks/mobile-backend-integration.md)
- [Private environment setup and phone host discovery](docs/runbooks/environment-setup.md)
- [Neon login/database with local images and videos](docs/runbooks/neon.md)
- [Neon live verification and changes](docs/status/neon-20261105.md)
- [Integration verification results](docs/status/mobile-backend-integration-20261104.md)
- [Completed work and pending host acceptance](docs/REMAINING_WORK.md)
- [Latest local verification](docs/status/main-host-readiness-20261104.md)
- [Database operations](docs/runbooks/backend-database.md)
- [Video event pipeline](docs/runbooks/video-event-pipeline.md)

Backend checks run with `python -m pytest -q` from `backend` after installing
`requirements-test.txt`. PostgreSQL acceptance requires its documented test
database and `RUN_POSTGRES_TESTS=1`. Dashboard checks are `npm test`,
`npm run build`, and `npm run lint` from `backend/dashboard` with Node 22.18+.
Reporter checks are `npm run typecheck` and `npm test` from `mobile/reporter-app`.
