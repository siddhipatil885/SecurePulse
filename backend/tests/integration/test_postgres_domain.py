"""Real PostgreSQL acceptance tests in a disposable, randomly named schema.

Run with RUN_POSTGRES_TESTS=1 and DATABASE_URL (or the backend .env).
Only this suite's generated schema is dropped; public is never in search_path.
"""

import asyncio
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.database.database import _async_database_url
from app.domain.events import DetectionEvent
from app.domain.security import SecurityDecision
from app.models import Camera, Property, SecurityEvent, Evidence
from app.models.operations import IncidentStatusHistory, NotificationOutbox, SourceEventReceipt
from app.repositories.cameras import CameraRepository
from app.repositories.events import EventRepository
from app.services.event_processor import EventProcessor

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 to create a disposable PostgreSQL test schema",
)


@pytest.fixture(scope="module")
def postgres_schema():
    url = Settings().database_url
    schema = "securepulse_test_" + uuid4().hex
    assert re.fullmatch(r"securepulse_test_[0-9a-f]{32}", schema)
    engine = create_engine(make_url(url).set(drivername="postgresql+psycopg2"))
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0008_camera_zones_health"
        yield url, schema, engine
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture
async def database(postgres_schema):
    url, schema, _ = postgres_schema
    engine = create_async_engine(_async_database_url(url))

    @event.listens_for(engine.sync_engine, "begin")
    def isolate(connection):
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class FixedDecision:
    async def evaluate(self, context):
        return SecurityDecision(event_type="INTRUSION", score=90, severity="HIGH", reason="Test fixture")


async def seed(factory):
    marker = uuid4().hex
    async with factory() as session:
        property = Property(slug=marker, name="Acceptance test", active=True)
        session.add(property)
        await session.flush()
        camera = Camera(property_id=property.id, name="Test", frigate_camera_name=marker, enabled=True)
        session.add(camera)
        await session.commit()
        return camera


def detection(camera, phase="new"):
    return DetectionEvent(
        source="frigate", source_event_id=camera.frigate_camera_name,
        camera=camera.frigate_camera_name, object_type="person", confidence=0.9,
        timestamp=datetime(2026, 10, 20, tzinfo=timezone.utc),
        metadata={"lifecycle": phase, "revision": "1", "has_snapshot": True},
    )


async def ingest(factory, value, processor_type=EventProcessor):
    async with factory() as session:
        processor = processor_type(session, CameraRepository(session), EventRepository(session), FixedDecision())
        return await processor.process(value)


async def assert_incident_rows(factory, camera, count):
    async with factory() as session:
        for model in (SecurityEvent, SourceEventReceipt, NotificationOutbox):
            assert await session.scalar(
                select(func.count()).select_from(model).where(model.property_id == camera.property_id)
            ) == count


async def test_ten_replays_and_concurrent_ingesters(database):
    camera = await seed(database)
    value = detection(camera)
    # Separate sessions and connections exercise actual database contention.
    results = await asyncio.gather(*(ingest(database, value) for _ in range(6)))
    event_id = results[0].event.id
    assert {result.event.id for result in results} == {event_id}
    for _ in range(10):
        replay = await ingest(database, value)
        assert replay.duplicate and replay.event.id == event_id
    await assert_incident_rows(database, camera, 1)
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Evidence).where(Evidence.event_id == event_id)) == 1
        assert await session.scalar(select(func.count()).select_from(IncidentStatusHistory).where(IncidentStatusHistory.security_event_id == event_id)) == 1


async def test_failure_after_history_flush_rolls_back_everything(database):
    class FailingProcessor(EventProcessor):
        async def _add_initial_incident_records(self, *args):
            await super()._add_initial_incident_records(*args)
            await self.session.flush()
            raise RuntimeError("Injected failure after outbox/history flush")

    camera = await seed(database)
    with pytest.raises(RuntimeError, match="Injected failure"):
        await ingest(database, detection(camera), FailingProcessor)
    await assert_incident_rows(database, camera, 0)
    retry = await ingest(database, detection(camera))
    assert not retry.duplicate
    await assert_incident_rows(database, camera, 1)


async def test_concurrent_update_replays_return_the_exact_incident(database):
    camera = await seed(database)
    original = await ingest(database, detection(camera))
    value = detection(camera, "update")
    value.metadata["observed_at"] = "2026-10-20T00:00:01+00:00"
    updates = await asyncio.gather(*(ingest(database, value) for _ in range(4)))
    assert len({result.event.id for result in updates}) == 1
    assert updates[0].event.id != original.event.id
    replay = await ingest(database, value)
    assert replay.event.id == updates[0].event.id


def test_populated_forward_and_reverse_migration(postgres_schema):
    _, schema, engine = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        before = connection.scalar(text("SELECT count(*) FROM cameras"))
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0007_align_legacy")
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT count(*) FROM cameras")) == before


async def test_authenticated_api_isolation_pagination_and_evidence(database, monkeypatch, tmp_path):
    from datetime import timedelta
    import jwt
    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.core.dependencies import get_session
    from app.models.operations import AuditRecord

    secret = "integration-test-signing-secret-32-characters"
    settings = Settings(auth_enabled=True, jwt_secret=secret, evidence_root=str(tmp_path))
    monkeypatch.setattr("app.core.auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.evidence.get_settings", lambda: settings)
    camera = await seed(database)
    foreign = await seed(database)
    result = await ingest(database, detection(camera))
    foreign_result = await ingest(database, detection(foreign))
    async with database() as session:
        session.add(Camera(property_id=camera.property_id, name="Second camera", frigate_camera_name=uuid4().hex, enabled=True))
        evidence = await session.scalar(select(Evidence).where(Evidence.event_id == result.event.id))
        evidence.file_path = "snapshot.jpg"
        evidence_id = evidence.id
        await session.commit()
    (tmp_path / "snapshot.jpg").write_bytes(b"test-media-bytes")

    app = create_app()
    async def test_session():
        async with database() as session:
            yield session
    app.dependency_overrides[get_session] = test_session

    def headers(scope="read write", property_id=camera.property_id, expired=False):
        token = jwt.encode({"sub": "acceptance-operator", "scope": scope,
                            "property_ids": [property_id],
                            "exp": datetime.now(timezone.utc) + timedelta(seconds=-60 if expired else 600)}, secret, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/cameras")).status_code == 401
        assert (await client.get("/api/v1/cameras", headers=headers(expired=True))).status_code == 401
        assert (await client.get("/api/v1/cameras", headers=headers(scope="write"))).status_code == 403
        for path in [f"cameras/{foreign.id}", f"incidents/{foreign_result.event.id}",
                     f"incidents/{foreign_result.event.id}/history", f"incidents/{foreign_result.event.id}/evidence"]:
            assert (await client.get("/api/v1/" + path, headers=headers())).status_code == 404
        first = await client.get("/api/v1/cameras?page_size=1", headers=headers())
        second = await client.get("/api/v1/cameras?page_size=1&page=2", headers=headers())
        assert len(first.json()) == len(second.json()) == 1
        assert first.json()[0]["id"] != second.json()[0]["id"]
        assert (await client.get("/api/v1/cameras?page_size=101", headers=headers())).status_code == 422
        listed = await client.get("/api/v1/incidents?severity=HIGH", headers=headers())
        assert listed.json()["total"] == 1
        assert (await client.get("/api/v1/incidents?severity=LOW", headers=headers())).json()["total"] == 0
        catalog = await client.get(f"/api/v1/incidents/{result.event.id}/evidence", headers=headers())
        assert catalog.status_code == 200 and catalog.json()[0]["id"] == evidence_id
        command_body = {"command": "acknowledge", "reason": "reviewed", "correlation_id": "acceptance-command"}
        command_url = f"/api/v1/incidents/{result.event.id}/commands"
        assert (await client.post(command_url, json=command_body, headers=headers(scope="read"))).status_code == 403
        assert (await client.post(command_url, json=command_body, headers=headers())).status_code == 200
        assert (await client.post(command_url, json=command_body, headers=headers())).status_code == 409
        access_url = f"/api/v1/evidence/{evidence_id}/access"
        assert (await client.post(access_url, headers=headers(property_id=foreign.property_id))).status_code == 404
        access = await client.post(access_url, headers=headers())
        assert access.status_code == 200
        media = await client.get(access.json()["url"], headers=headers())
        assert media.status_code == 200 and media.content == b"test-media-bytes"
        assert (await client.get(access.json()["url"], headers=headers(property_id=foreign.property_id))).status_code == 404
        assert (await client.get(f"/api/v1/evidence/{evidence_id}/content?grant=invalid", headers=headers())).status_code == 401
        expired_grant = jwt.encode({"sub": "acceptance-operator", "aud": "evidence-playback", "exp": 1,
                                    "evidence_id": evidence_id, "property_id": camera.property_id}, secret, algorithm="HS256")
        assert (await client.get(f"/api/v1/evidence/{evidence_id}/content", params={"grant": expired_grant}, headers=headers())).status_code == 401
    async with database() as session:
        actions = set((await session.scalars(select(AuditRecord.action).where(AuditRecord.property_id == camera.property_id))).all())
        assert {"INCIDENT_STATUS_CHANGED", "INCIDENT_EVIDENCE_LISTED", "EVIDENCE_ACCESS_GRANTED", "EVIDENCE_CONTENT_ACCESSED"} <= actions


async def test_foreign_key_rejects_orphan_evidence(database):
    from sqlalchemy.exc import IntegrityError
    async with database() as session:
        session.add(Evidence(event_id=-1, type="SNAPSHOT", file_path="orphan.jpg",
                             timestamp=datetime.now(timezone.utc), evidence_metadata={}))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


def test_logical_restore_including_incidents_and_audits(postgres_schema):
    """Backup and restore every domain table, only inside the disposable schema."""
    import json
    from time import perf_counter
    from app.database.base import Base
    _, schema, engine = postgres_schema
    started = perf_counter()
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            tables = list(Base.metadata.sorted_tables)
            backup = {}
            for table in tables:
                backup[table.name] = connection.scalar(text(f'SELECT coalesce(json_agg(t), \'[]\'::json) FROM "{table.name}" t'))
            # The earlier API test persisted both incidents and audit records.
            assert backup["security_events"] and backup["audit_records"]
            for table in reversed(tables):
                connection.execute(text(f'DELETE FROM "{table.name}"'))
            for table in tables:
                connection.execute(text(f'INSERT INTO "{table.name}" SELECT * FROM json_populate_recordset(NULL::"{table.name}", CAST(:payload AS json))'),
                                   {"payload": json.dumps(backup[table.name])})
                restored = connection.scalar(text(f'SELECT coalesce(json_agg(t), \'[]\'::json) FROM "{table.name}" t'))
                canonical = lambda rows: sorted(json.dumps(row, sort_keys=True) for row in rows)
                assert canonical(restored) == canonical(backup[table.name])
        finally:
            transaction.rollback()
    print(f"full_domain_logical_restore_seconds={perf_counter() - started:.2f}")
