# EDI-SecurePulse: Database Layer

This directory contains the PostgreSQL database layer for the SecurePulse project. It is designed to connect to **Neon PostgreSQL** and relies on **SQLAlchemy 2.x**, **Psycopg 3**, and **Alembic** for schema migrations.

## Purpose
To provide a structured, robust, and asynchronous-ready foundation for storing CCTV surveillance data, security events (e.g. `PERSON_DETECTED`), and evidence paths.

## Architecture & Schema Overview

- **`cameras`**: Stores configured cameras, mapping internal IDs to `frigate_camera_name`.
- **`security_events`**: Stores detected threats/events with metadata and confidence scores. Linked to `cameras` via `camera_id`.
- **`evidence`**: Stores paths/URLs to media (snapshots, clips). Linked to `security_events` via `event_id`. **Does not store binary data.**

> [!WARNING]
> **No Video Binaries in Postgres**: Never store raw video or image bytes in the database. Use the `evidence` table to store references/paths to file storage.

### Indexes & Performance
Key indexes are configured for high performance:
- `(camera_id, timestamp)` composite index for querying recent camera events.
- `frigate_event_id` partial unique index (where NOT NULL) to handle Frigate duplicate event re-processing gracefully.

## Setup Instructions

### 1. Requirements
- Python 3.14.3
- Ensure you have installed the project requirements from the root directory:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Environment Variables
Create a `.env` file in the project root containing your Neon PostgreSQL connection string:

```
DATABASE_URL=postgresql://<user>:<password>@<host>/<database>?sslmode=require
```

> [!IMPORTANT]
> **Security Notice:** Do NOT commit your `.env` file. It is ignored in `.gitignore`. Never hardcode the `DATABASE_URL` in source files.

## Database Management Workflow

### Testing Connection
You can test connectivity to Neon safely (no secrets printed) using:
```bash
python -m database.scripts.test_connection
```

### Alembic Migrations
Migrations are the single source of truth for the database schema.
To apply all pending migrations to the database, run:
```bash
cd database
alembic upgrade head
```

### Seeding Data
For local development, you can seed dummy data (a Camera and a SecurityEvent):
```bash
python -m database.scripts.seed
```

### Running Tests
The database tests use transactional rollback (changes are isolated and discarded after the test run) ensuring the actual Neon database state remains untouched.

To run the tests:
```bash
pytest database/tests/ -v
```
