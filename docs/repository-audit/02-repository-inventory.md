# Repository Inventory

## Audit boundary and method

The audit enumerated tracked files with `git ls-files`, searched all non-generated files with `rg`, inspected every substantive tracked file line-by-line, and reviewed local Git status, branches, and history. Generated/dependency directories were excluded; none were present. The worktree was clean before report generation.

## Important tree

```text
SecurePulse/
├── README.md                              # Product vision; explicitly planned/prototype
├── ai-cctv/
│   ├── backend/
│   │   ├── requirements.txt               # Unpinned Python dependency ranges
│   │   └── app/
│   │       ├── alerts/.gitkeep            # Empty placeholders only
│   │       ├── cameras/.gitkeep
│   │       ├── config/.gitkeep
│   │       ├── database/.gitkeep
│   │       ├── detection/.gitkeep
│   │       ├── events/.gitkeep
│   │       ├── health/.gitkeep
│   │       ├── incidents/.gitkeep
│   │       ├── mqtt/.gitkeep
│   │       └── zones/.gitkeep
│   ├── dashboard/
│   │   └── src/
│   │       ├── components/.gitkeep         # Empty placeholders only
│   │       ├── pages/.gitkeep
│   │       ├── services/.gitkeep
│   │       └── types/.gitkeep
│   ├── deployment/
│   │   ├── .env.example                   # Four development environment keys
│   │   ├── docker-compose.yml             # MQTT, Frigate, MediaMTX
│   │   └── mosquitto/config/mosquitto.conf
│   ├── docs/phase1_setup.md                # Phase 1 operator notes
│   ├── frigate/
│   │   ├── config/frigate.yml             # Single-camera detection config
│   │   └── media/.gitkeep                 # Intended local media mount
│   ├── shared/.gitkeep                    # Empty placeholder
│   └── tests/test_mqtt_subscriber.py       # Manual subscriber, not a pytest test
└── docs/repository-audit/                 # Audit output only
```

Evidence: Git tree and placeholder intent are corroborated by `ai-cctv/docs/phase1_setup.md:17-35`, though that document omits the empty future directories.

## Repository size and boundaries

Before this audit, the repository had 24 tracked files: seven substantive content/config files, sixteen one-line placeholders, and the root README. `ai-cctv` is a proposed monorepo boundary but does not yet contain separately buildable backend or dashboard applications.

| Directory | Actual purpose | State |
|---|---|---|
| `ai-cctv/deployment` | Local Compose topology and MQTT broker configuration | Configured, unverified |
| `ai-cctv/frigate` | Frigate configuration and host media directory | Configured, unverified |
| `ai-cctv/tests` | Manual MQTT observation script | Executable utility; zero automated tests |
| `ai-cctv/backend` | Dependency wish list and module placeholders | No application code |
| `ai-cctv/dashboard` | React-like folder placeholders only | No manifest or code |
| `ai-cctv/shared` | Empty placeholder | No contracts/assets |
| `ai-cctv/docs` | Phase 1 setup document | Present, contains unverified claims |

## Languages, frameworks, and services

| Technology | Repository evidence | Actual use |
|---|---|---|
| Python | `test_mqtt_subscriber.py`; `requirements.txt` | One manual MQTT client |
| Paho MQTT | Requirements `:3`; subscriber import `:9` | Used by manual subscriber |
| FastAPI/Uvicorn/Pydantic | `ai-cctv/backend/requirements.txt:1-4` | Declared only; no imports/app |
| SQLAlchemy/asyncpg/psycopg2 | Requirements `:5-7` | Declared only; no DB URL/model/migration |
| pytest | Requirements `:9` | Declared; zero tests collected |
| Docker Compose | `ai-cctv/deployment/docker-compose.yml:1-53` | Local prototype topology |
| Frigate 0.13.2 | Compose `:15-41` | Image/config only |
| Mosquitto 2.0 | Compose `:4-13` | Image/config only |
| MediaMTX | Compose `:43-49` | `latest` image only; no stream publisher |
| React/Vite/Tailwind | `README.md:197-200` | Planned only; no `package.json` |
| PostgreSQL | Python drivers in requirements | Intended by prompt, absent from source/infrastructure |
| Firebase | `README.md:206-208` | Planned documentation only; no config/code |

## Entrypoints

- Manual Python entrypoint: `main()` in `ai-cctv/tests/test_mqtt_subscriber.py:44-64`.
- Container entrypoints are inherited from upstream images; the repository supplies no Dockerfiles (`ai-cctv/deployment/docker-compose.yml:4-49`).
- No ASGI/FastAPI entrypoint exists.
- No frontend or mobile entrypoint exists.
- No security engine or event-adapter entrypoint exists.

## Configuration and dependency manifests

- `.env.example` defines `RTSP_STREAM_URL`, `MQTT_PORT`, `FRIGATE_PORT`, and `TZ` (`ai-cctv/deployment/.env.example:1-15`). It does not define database, auth, notification, or backend settings.
- Python dependencies use open-ended minimum constraints and have no lock or hash file (`ai-cctv/backend/requirements.txt:1-9`).
- Frigate is pinned to `0.13.2`; Mosquitto is only pinned to major/minor `2.0`; MediaMTX uses mutable `latest` (`ai-cctv/deployment/docker-compose.yml:5`, `:16`, `:45`).
- No `pyproject.toml`, `setup.cfg`, `tox.ini`, pytest config, Alembic config, Node manifest/lockfile, mobile manifest, Dockerfile, Kubernetes/Terraform/Ansible, or CI workflow exists.
- No repository `.gitignore` exists; the tracked media directory only contains `.gitkeep` (`ai-cctv/frigate/media/.gitkeep:1`).

## Documentation consistency

The root README accurately warns that capabilities are planned and the repository is in an early prototype state (`README.md:15`, `:33-52`, `:284-315`). It is stale when it says the repository contains only `README.md` (`README.md:215-232`) because the later initial-import commit added Phase 1 configuration. `phase1_setup.md` describes services and expected results (`ai-cctv/docs/phase1_setup.md:55-103`) but provides no captured evidence that they ran.

## Git history and visibility

Visible history contains two commits:

1. `60bdb23` — 2026-09-12 — initial README based on PRD.
2. `0e039d6` — 2026-09-12 — initial project-file import.

Only local `main`, `origin/main`, and `origin/HEAD -> origin/main` were visible; both main refs pointed to `0e039d6`. No unmerged/divergent local branch or later commit was visible. No TODO/FIXME marker was found; incompleteness is represented by placeholders and roadmap prose. Unpushed work, inaccessible remote branches, and external systems remain outside the audit.

