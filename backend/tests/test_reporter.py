"""Real SQL-backed auth/authorization tests; isolated in-memory DB, no MQTT."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update
from sqlalchemy import create_engine, inspect, select
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import get_websocket_principal
from app.core.config import Settings
from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import hash_password
from app.database.base import Base
from app.main import app
from app.models import Alert, Camera, SecurityEvent
from app.models.reporter import Property, PropertyCamera, PropertyMembership, ReporterUser

SECRET = "reporter-test-only-secret-with-32-characters"
PASSWORD = "isolated-test-password"


@pytest_asyncio.fixture
async def fixture(monkeypatch):
    settings = Settings(auth_enabled=True, jwt_secret=SECRET, jwt_issuer="securepulse-tests")
    monkeypatch.setattr("app.core.auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.core.reporter_auth.get_settings", lambda: settings)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([Property(id=1, name="First property"), Property(id=2, name="Other property")])
        session.add_all([ReporterUser(id=1, email="owner@example.test", name="Owner", password_hash=hash_password(PASSWORD)),
                         ReporterUser(id=2, email="reporter@example.test", name="Reporter", password_hash=hash_password(PASSWORD))])
        await session.flush()
        session.add_all([PropertyMembership(user_id=1, property_id=1, role="owner"),
                         PropertyMembership(user_id=2, property_id=2, role="reporter")])
        for id in [1, 2, 3]:
            session.add(Camera(id=id, name=f"Camera {id}", frigate_camera_name=f"private_{id}", enabled=True))
        await session.flush()
        session.add_all([PropertyCamera(camera_id=1, property_id=1), PropertyCamera(camera_id=2, property_id=2)])
        for id in [1, 2, 3]:
            session.add(SecurityEvent(id=id, camera_id=id, event_type="PERSON_DETECTED", object_type="person",
                confidence=.9, timestamp=datetime.now(timezone.utc), severity="INFO", status="OPEN", event_metadata={"internal": "hidden"}))
        await session.flush()
        session.add_all([Alert(camera_id=1, security_event_id=1, severity="INFO", status="ACTIVE"),
                         Alert(camera_id=2, security_event_id=2, severity="INFO", status="ACTIVE")])
        await session.commit()
    async def override_session():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, settings
    app.dependency_overrides.clear()
    await engine.dispose()


async def sign_in(client, email="owner@example.test"):
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_login_profile_scoped_reads_and_redaction(fixture):
    client, _, _ = fixture
    token = await sign_in(client)
    headers = {"Authorization": f"Bearer {token}"}
    profile = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert profile == {"id": 1, "email": "owner@example.test", "name": "Owner",
                       "properties": [{"id": 1, "name": "First property", "role": "owner"}]}
    cameras = await client.get("/api/v1/reporter/cameras?property_id=1", headers=headers)
    assert cameras.status_code == 200
    assert [item["id"] for item in cameras.json()] == [1]
    assert cameras.json()[0]["connection_status"] == "unknown"
    assert "frigate_camera_name" not in cameras.json()[0]
    events = await client.get("/api/v1/reporter/events?property_id=1&page_size=1", headers=headers)
    assert events.json()["total"] == 1
    assert [item["id"] for item in events.json()["items"]] == [1]
    assert "metadata" not in events.json()["items"][0]
    assert (await client.get("/api/v1/reporter/events?property_id=1&page=2", headers=headers)).json()["items"] == []
    summary = (await client.get("/api/v1/reporter/summary?property_id=1", headers=headers)).json()
    assert summary == {"camera_count": 1, "event_count": 1, "active_alert_count": 1,
                       "connected_camera_count": None, "active_incident_count": None, "security_status": "unknown"}


@pytest.mark.asyncio
async def test_ownership_enforced_for_lists_and_direct_ids(fixture):
    client, _, _ = fixture
    headers = {"Authorization": "Bearer " + await sign_in(client)}
    for resource in ["cameras", "events", "summary", "cameras/2", "events/2"]:
        assert (await client.get(f"/api/v1/reporter/{resource}?property_id=2", headers=headers)).status_code == 403
    for resource in ["cameras/2", "events/2", "cameras/3", "events/3", "events/999"]:
        assert (await client.get(f"/api/v1/reporter/{resource}?property_id=1", headers=headers)).status_code == 404
    for resource in ["cameras/1", "events/1"]:
        assert (await client.get(f"/api/v1/reporter/{resource}?property_id=1", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/reporter/events", headers=headers)).status_code == 422
    assert (await client.get("/api/v1/reporter/events?property_id=1&page_size=101", headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_reporter_role_and_unassigned_user(fixture):
    client, factory, _ = fixture
    headers = {"Authorization": "Bearer " + await sign_in(client, "reporter@example.test")}
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["properties"][0]["role"] == "reporter"
    assert (await client.get("/api/v1/reporter/cameras?property_id=2", headers=headers)).status_code == 200
    async with factory() as session:
        await session.execute(delete(PropertyMembership).where(PropertyMembership.user_id == 2))
        await session.commit()
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["properties"] == []
    assert (await client.get("/api/v1/reporter/cameras?property_id=2", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_reporter_cannot_access_global_legacy_or_media_endpoints(fixture):
    client, _, _ = fixture
    token = await sign_in(client)
    headers = {"Authorization": "Bearer " + token}
    for path in ["cameras", "cameras/1", "events", "events/1", "tracks", "frigate/cameras/private_1/snapshot"]:
        assert (await client.get("/api/v1/" + path, headers=headers)).status_code == 403
    assert (await client.post("/api/v1/frigate/cameras/1/webrtc", headers=headers)).status_code == 403
    with pytest.raises(ApplicationError) as caught:
        await get_websocket_principal(SimpleNamespace(headers=headers | {"authorization": "Bearer " + token}, query_params={}))
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_forged_expired_and_revoked_tokens(fixture):
    client, factory, _ = fixture
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    token = await sign_in(client)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="securepulse-tests")
    expired = jwt.encode(claims | {"exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, SECRET, algorithm="HS256")
    forged = jwt.encode(claims, "wrong-secret-with-at-least-thirty-two-characters", algorithm="HS256")
    for invalid in ["bad", expired, forged]:
        assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + invalid})).status_code == 401
    headers = {"Authorization": "Bearer " + token}
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    token2 = await sign_in(client)
    async with factory() as session:
        await session.execute(update(ReporterUser).where(ReporterUser.id == 1).values(enabled=False))
        await session.commit()
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token2})).status_code == 401


@pytest.mark.asyncio
async def test_credentials_lockout_and_disabled_auth(fixture):
    client, _, settings = fixture
    for _ in range(5):
        response = await client.post("/api/v1/auth/login", json={"email": "owner@example.test", "password": "incorrect"})
        assert response.status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": "owner@example.test", "password": PASSWORD})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": "unknown@example.test", "password": PASSWORD})).status_code == 401
    settings.auth_enabled = False
    assert (await client.post("/api/v1/auth/login", json={"email": "reporter@example.test", "password": PASSWORD})).status_code == 503
    assert (await client.get("/api/v1/auth/me")).status_code == 503


def test_additive_migration_preserves_existing_camera():
    engine = create_engine("sqlite:///:memory:")
    spec = importlib.util.spec_from_file_location("reporter_migration", Path(__file__).parents[1] / "alembic/versions/0005_reporter_access.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        Camera.__table__.create(connection)
        connection.execute(Camera.__table__.insert().values(id=1, name="Existing camera", frigate_camera_name="existing", enabled=True))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == {"cameras", "reporter_users", "properties", "property_memberships", "property_cameras"}
        assert connection.scalar(select(Camera.name)) == "Existing camera"
    engine.dispose()


@pytest.mark.asyncio
async def test_provisioning_is_atomic_and_does_not_reassign_cameras(fixture, monkeypatch):
    from app.provision_reporter import provision
    client, factory, _ = fixture
    monkeypatch.setattr("app.provision_reporter.get_session_factory", lambda: factory)
    args = SimpleNamespace(email="new@example.test", name="New owner", role="owner", property_id=None,
                           property_name="New property", camera_id=[1])
    with pytest.raises(ValueError, match="already belongs"):
        await provision(args, PASSWORD)
    async with factory() as session:
        assert await session.scalar(select(Property).where(Property.name == "New property")) is None
        assert await session.scalar(select(ReporterUser).where(ReporterUser.email == "new@example.test")) is None
    args.camera_id = [3]
    await provision(args, PASSWORD)
    token = await sign_in(client, "new@example.test")
    headers = {"Authorization": "Bearer " + token}
    profile = (await client.get("/api/v1/auth/me", headers=headers)).json()
    property_id = profile["properties"][0]["id"]
    cameras = await client.get(f"/api/v1/reporter/cameras?property_id={property_id}", headers=headers)
    assert [camera["id"] for camera in cameras.json()] == [3]
    with pytest.raises(ValueError, match="already exists"):
        await provision(args, PASSWORD)
