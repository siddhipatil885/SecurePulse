# Backend and PostgreSQL Operations Runbook

## Nonproduction-first rule

Never run a migration, restore, destructive SQL, or seed operation against a
Neon target until its project, branch, database, and owner have been confirmed.
Use a disposable Neon branch or a dedicated local PostgreSQL database for the
first upgrade and restore rehearsal. Do not print `DATABASE_URL` or commit it.

## Local verification

For real database acceptance checks against a configured development target:

```powershell
cd backend
$env:RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest -q
```

The suite creates and migrates a unique `securepulse_test_<uuid>` schema. Its
search path excludes public; cleanup drops only that generated schema. A hard
process kill may leave the schema behind: inspect ownership and the exact name
before removing it. Ordinary runs without this flag explicitly skip database
acceptance tests. CI runs them against an ephemeral PostgreSQL 16 service.

Migration 0007 was corrected to accept both fresh 0001 objects and legacy Neon
objects. Already-upgraded databases do not rerun it. Prefer forward repair over
downgrades on shared targets. Migration 0007 explicitly refuses downgrade because
it cannot reconstruct the original legacy schema without risking evidence loss.
The reversal test exercises 0008 and 0009 only in isolated test data.
Migration 0009 aligns the event-to-camera foreign key with the model's cascade
behavior. It is prepared for review; it has not been applied to public Neon tables.

When running `python -m scripts.smoke_api` with authentication enabled, supply a
read-scoped bearer token through `SMOKE_API_TOKEN`. The script fails clearly if
the token is missing and never prints it. Do not disable production auth for a
smoke test.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -p no:cacheprovider -q
alembic heads
alembic history
```

Generate PostgreSQL migration SQL without connecting to a database:

```powershell
$env:DATABASE_URL='postgresql://offline:offline@localhost/securepulse_offline'
alembic upgrade head --sql
```

Run the non-destructive recovery rehearsal against the configured development
database. It creates dedicated test rows, captures them as a logical backup,
deletes and restores them, verifies ownership and content, and rolls back the
entire transaction:

```powershell
python -m scripts.smoke_backup_restore
```

The 2026-10-20 Neon rehearsal completed in 4.08 seconds with no residual rows.
This verifies application-level logical recovery; it does not replace a full
physical backup or disposable Neon branch restore before production.

## Approved development database procedure

After a team member identifies the safe target:

1. Confirm it is not the production branch/database.
2. Record the current application commit and `alembic current` output.
3. Create or verify a recoverable database branch/backup.
4. Run `alembic upgrade head` once against the disposable target.
5. Run the backend tests and smoke-test health, camera, incident, history, and
   evidence endpoints.
6. Check that legacy rows belong to `legacy-unassigned`; do not silently assign
   them to a real property.
7. Exercise an upgrade failure on another disposable target and verify that
   PostgreSQL transactional DDL leaves no partial migration.
8. Rehearse restore/branch reset using test data and record elapsed time.

## Failure behavior

- Database connection failure makes `/health/ready` return HTTP 503.
- Ingestion transaction failures roll back receipt, incident, history,
  evidence, alert, and outbox changes together.
- Realtime publishing occurs after commit; clients must refetch persisted state
  following a disconnect.
- A notification failure never deletes or rolls back the incident.

## Retention decisions

Retention durations are product/privacy decisions and are intentionally not
invented here. Approve and document separate periods for:

- raw snapshots and clips;
- source-event receipts and raw payload fields;
- incidents and immutable status/audit history;
- assignments and marshal availability/location;
- notification payloads and delivery attempts.

Until approved, do not add automatic deletion jobs. Store media references in
PostgreSQL, never video or image binaries.

## Production-change gate

Set `EVIDENCE_ROOT` to a dedicated archive directory and supply `JWT_SECRET`
before enabling file playback. Grant URLs contain a short-lived credential;
configure reverse proxies to omit query strings from access logs. Application
logs redact JWTs and database/RTSP URLs. Protect the archive from untrusted local
writers, and do not place configuration files or unrelated files in it.

A production migration requires peer review of the migration chain, a tested
backup/restore path, an approved maintenance/rollback plan, and confirmation
that all applications using the database understand mandatory `property_id`
fields. This repository does not automatically migrate Neon at startup.
