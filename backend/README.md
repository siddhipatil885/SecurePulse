# SecurePulse Backend

This directory contains the active FastAPI backend for SecurePulse.

For the full architecture, feature overview, and project setup, see the canonical project guide in [../README.md](../README.md).

## Backend-specific setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

## Backend responsibilities

- Frigate MQTT ingestion and normalization
- Async PostgreSQL persistence with SQLAlchemy
- Event deduplication and lifecycle handling
- Security rule evaluation and severity resolution
- Camera and event REST APIs
- WebSocket real-time event streaming
- JWT auth and scope validation

## Required environment

Use the values in [.env.example](.env.example) as the backend template. At minimum, configure:

- `DATABASE_URL`
- `FRIGATE_URL`
- `MQTT_HOST` and `MQTT_PORT`
- `FRIGATE_MQTT_TOPIC`
- `SECURITY_ENGINE_URL`
- `AUTH_ENABLED`
- `JWT_SECRET` when auth is enabled

## Tests

```powershell
pytest
```

## Database migrations

```powershell
alembic upgrade head
```

This backend is the authoritative runtime implementation for the project. Keep the root README as the single source of truth for high-level project documentation.
