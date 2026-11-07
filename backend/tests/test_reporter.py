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
from app.models import Alert, AuditRecord, Camera, Property, PropertyMembership, ReporterIncident, SecurityEvent, User

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
        session.add_all([Property(id=1, slug="first", name="First property"), Property(id=2, slug="other", name="Other property")])
        session.add_all([User(id=1, subject="owner", email="owner@example.test", display_name="Owner", password_hash=hash_password(PASSWORD)),
                         User(id=2, subject="reporter", email="reporter@example.test", display_name="Reporter", password_hash=hash_password(PASSWORD))])
        await session.flush()
        session.add_all([PropertyMembership(user_id=1, property_id=1, role="owner"),
                         PropertyMembership(user_id=2, property_id=2, role="reporter")])
        for id in [1, 2, 3]:
            session.add(Camera(id=id, property_id=1 if id == 1 else 2, name=f"Camera {id}", frigate_camera_name=f"private_{id}", enabled=True))
        await session.flush()
        for id in [1, 2, 3]:
            session.add(SecurityEvent(id=id, property_id=1 if id == 1 else 2, camera_id=id, event_type="PERSON_DETECTED", object_type="person",
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
async def test_login_profile_scoped_reads_and_redaction(fixture, monkeypatch):
    from unittest.mock import AsyncMock
    async def unknown_states(cameras, settings):
        return {camera.id: 'unknown' for camera in cameras}
    monkeypatch.setattr('app.api.reporter.camera_states', AsyncMock(side_effect=unknown_states))
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
                       "connected_camera_count": None, "active_incident_count": 0, "security_status": "attention_required"}


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
        await session.execute(update(User).where(User.id == 1).values(active=False))
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
    spec = importlib.util.spec_from_file_location("reporter_migration", Path(__file__).parents[1] / "alembic/versions/0010_reporter_credentials.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, subject VARCHAR(255) NOT NULL UNIQUE, email VARCHAR(320), display_name VARCHAR(255), active BOOLEAN NOT NULL DEFAULT 1, created_at DATETIME, updated_at DATETIME)")
        connection.exec_driver_sql("CREATE TABLE properties (id INTEGER PRIMARY KEY)")
        Camera.__table__.create(connection)
        connection.execute(Camera.__table__.insert().values(id=1, property_id=1, name="Existing camera", frigate_camera_name="existing", enabled=True))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == {"cameras", "properties", "users"}
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
        assert await session.scalar(select(User).where(User.email == "new@example.test")) is None
    args.property_id = 2
    args.property_name = None
    args.camera_id = [3]
    await provision(args, PASSWORD)
    token = await sign_in(client, "new@example.test")
    headers = {"Authorization": "Bearer " + token}
    profile = (await client.get("/api/v1/auth/me", headers=headers)).json()
    property_id = profile["properties"][0]["id"]
    cameras = await client.get(f"/api/v1/reporter/cameras?property_id={property_id}", headers=headers)
    assert [camera["id"] for camera in cameras.json()] == [2, 3]
    with pytest.raises(ValueError, match="already exists"):
        await provision(args, PASSWORD)


@pytest.mark.asyncio
@pytest.mark.parametrize('revocation', ['membership', 'role', 'property'])
async def test_manual_reports_and_grants_require_current_property_access(fixture, monkeypatch, tmp_path, revocation):
    client, factory, settings = fixture
    settings.evidence_root = str(tmp_path)
    monkeypatch.setattr('app.api.reporter.get_settings', lambda: settings)
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    created = await client.post('/api/v1/reporter/incidents', headers=headers | {'X-Idempotency-Key': 'revocation-test-report'},
        json={'property_id': 1, 'incident_type': 'THEFT', 'address': 'Test address'})
    assert created.status_code == 201, created.text
    incident_id = created.json()['id']
    uploaded = await client.post(f'/api/v1/reporter/incidents/{incident_id}/evidence', headers=headers,
        files={'file': ('photo.jpg', b'\xff\xd8\xff\xe0test', 'image/jpeg')})
    evidence_id = uploaded.json()['evidence'][0]['id']
    grant = await client.post(f'/api/v1/reporter/incidents/{incident_id}/evidence/{evidence_id}/access', headers=headers)
    assert grant.status_code == 200
    async with factory() as session:
        if revocation == 'property':
            await session.execute(update(Property).where(Property.id == 1).values(active=False))
        else:
            values = {'active': False} if revocation == 'membership' else {'role': 'marshal'}
            await session.execute(update(PropertyMembership).where(PropertyMembership.user_id == 1).values(**values))
        await session.commit()
    assert (await client.get(f'/api/v1/reporter/incidents/{incident_id}', headers=headers)).status_code == 404
    assert (await client.get('/api/v1/reporter/incidents', headers=headers)).json()['total'] == 0
    assert (await client.get(grant.json()['url'], headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_reporter_can_create_idempotent_owned_incident_and_upload_image(fixture, monkeypatch, tmp_path):
    client, factory, settings = fixture
    settings.evidence_root = str(tmp_path)
    monkeypatch.setattr("app.api.reporter.get_settings", lambda: settings)
    headers = {"Authorization": "Bearer " + await sign_in(client)}
    payload = {
        "property_id": 1,
        "incident_type": "THEFT",
        "description": "A package was taken from the entrance.",
        "address": "1 Test Street",
    }
    first = await client.post(
        "/api/v1/reporter/incidents",
        json=payload,
        headers=headers | {"X-Idempotency-Key": "reporter-test-key-001"},
    )
    assert first.status_code == 201, first.text
    incident = first.json()
    duplicate = await client.post(
        "/api/v1/reporter/incidents",
        json=payload,
        headers=headers | {"X-Idempotency-Key": "reporter-test-key-001"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == incident["id"]
    upload = await client.post(
        f"/api/v1/reporter/incidents/{incident['id']}/evidence",
        files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0test", "image/jpeg")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["evidence"][0]["original_filename"] == "photo.jpg"
    detail = await client.get(f"/api/v1/reporter/incidents/{incident['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["timeline"][0]["status"] == "RECEIVED"
    async with factory() as session:
        stored = await session.scalar(select(ReporterIncident).where(ReporterIncident.id == incident["id"]))
        assert stored is not None
        assert stored.reporter_user_id == 1


@pytest.mark.asyncio
async def test_reporter_evidence_grant_is_owned_short_lived_and_audited(fixture, monkeypatch, tmp_path):
        client, factory, settings = fixture
        settings.evidence_root = str(tmp_path)
        monkeypatch.setattr("app.api.reporter.get_settings", lambda: settings)
        headers = {"Authorization": "Bearer " + await sign_in(client)}
        created = await client.post(
            "/api/v1/reporter/incidents",
            json={"property_id": 1, "incident_type": "THEFT", "address": "1 Test Street"},
            headers=headers | {"X-Idempotency-Key": "reporter-evidence-grant-01"},
        )
        incident_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/reporter/incidents/{incident_id}/evidence",
            files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0test", "image/jpeg")},
            headers=headers,
        )
        evidence_id = uploaded.json()["evidence"][0]["id"]
        grant = await client.post(
            f"/api/v1/reporter/incidents/{incident_id}/evidence/{evidence_id}/access",
            headers=headers,
        )
        assert grant.status_code == 200
        media = await client.get(grant.json()["url"], headers=headers)
        assert media.status_code == 200
        assert media.content.startswith(b"\xff\xd8")
        invalid = await client.get(
            f"/api/v1/reporter/incidents/{incident_id}/evidence/{evidence_id}/content?grant=invalid",
            headers=headers,
        )
        assert invalid.status_code == 401
        async with factory() as session:
            actions = set((await session.scalars(select(AuditRecord.action))).all())
            assert {"REPORTER_EVIDENCE_ACCESS_GRANTED", "REPORTER_EVIDENCE_CONTENT_ACCESSED"} <= actions


@pytest.mark.asyncio
async def test_reporter_incident_rejects_cross_property_and_missing_location(fixture):
    client, _, _ = fixture
    headers = {"Authorization": "Bearer " + await sign_in(client)}
    forbidden = await client.post(
        "/api/v1/reporter/incidents",
        json={"property_id": 2, "incident_type": "THEFT", "address": "Other property"},
        headers=headers | {"X-Idempotency-Key": "reporter-cross-property-001"},
    )
    assert forbidden.status_code == 403
    invalid = await client.post(
        "/api/v1/reporter/incidents",
        json={"property_id": 1, "incident_type": "THEFT"},
        headers=headers | {"X-Idempotency-Key": "reporter-missing-location-001"},
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_reporter_incident_history_supports_status_filter(fixture):
    client, _, _ = fixture
    headers = {"Authorization": "Bearer " + await sign_in(client)}
    response = await client.get(
        "/api/v1/reporter/incidents?status=RECEIVED",
        headers=headers,
    )
    assert response.status_code == 200
    assert all(item["status"] == "RECEIVED" for item in response.json()["items"])
    invalid_status = await client.get(
        "/api/v1/reporter/incidents?status=" + ("x" * 33),
        headers=headers,
    )
    assert invalid_status.status_code == 422


@pytest.mark.asyncio
async def test_reporter_device_registration_and_preferences_are_account_scoped(fixture):
    client, _, _ = fixture
    headers = {"Authorization": "Bearer " + await sign_in(client)}
    registered = await client.post(
        "/api/v1/reporter/devices",
        json={"device_id": "ios-test-device", "push_token": "ExponentPushToken[test]", "provider": "expo"},
        headers=headers,
    )
    assert registered.status_code == 204
    preference = await client.put(
        "/api/v1/reporter/notification-preferences",
        json={"category": "INCIDENT_UPDATES", "enabled": False},
        headers=headers,
    )
    assert preference.status_code == 200
    assert preference.json()["enabled"] is False
    preferences = await client.get("/api/v1/reporter/notification-preferences", headers=headers)
    assert preferences.json()[0]["category"] == "INCIDENT_UPDATES"
    assert (await client.delete("/api/v1/reporter/devices/ios-test-device", headers=headers)).status_code == 204


@pytest.mark.asyncio
async def test_reporter_can_update_profile_and_rotate_password(fixture):
    client, factory, _ = fixture
    headers = {"Authorization": "Bearer " + await sign_in(client)}
    updated = await client.put("/api/v1/auth/profile", json={"name": "Updated Reporter"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Reporter"
    changed = await client.post("/api/v1/auth/password", json={
        "current_password": PASSWORD, "new_password": "new-isolated-password",
    }, headers=headers)
    assert changed.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    login = await client.post("/api/v1/auth/login", json={"email": "owner@example.test", "password": "new-isolated-password"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_reporter_can_review_owned_active_alert_once(fixture):
    client, factory, _ = fixture
    headers = {"Authorization": "Bearer " + await sign_in(client)}
    before = await client.get("/api/v1/reporter/events/1?property_id=1", headers=headers)
    assert before.status_code == 200
    assert before.json()["alert_status"] == "ACTIVE"
    reviewed = await client.post(
        "/api/v1/reporter/events/1/review?property_id=1",
        json={"decision": "CONFIRMED"},
        headers=headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["alert_status"] == "CONFIRMED"
    conflict = await client.post(
        "/api/v1/reporter/events/1/review?property_id=1",
        json={"decision": "FALSE_ALARM"},
        headers=headers,
    )
    assert conflict.status_code == 409
    async with factory() as session:
        alert = await session.scalar(select(Alert).where(Alert.id == 1))
        assert alert and alert.reviewed_by == "reporter:1"
