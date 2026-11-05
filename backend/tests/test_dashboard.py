"""Dashboard auth, onboarding, tenant isolation, incident actions and evidence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api import dashboard
from app.core.config import Settings
from app.core.dependencies import get_session
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.reporter_auth import hash_password
from app.database.base import Base
from app.main import app
from app.models import Camera, Evidence, Property, PropertyMembership, SecurityEvent, User
from app.models.operations import IncidentStatusHistory, AuditRecord

PASSWORD = "Dashboard-test-pass123"
SECRET = "dashboard-test-only-secret-at-least-32-characters"
ROOT = "/api/v1/dashboard"


@pytest_asyncio.fixture
async def site(monkeypatch, tmp_path):
    settings = Settings(auth_enabled=True, jwt_secret=SECRET, evidence_root=str(tmp_path))
    for module in ("app.core.auth", "app.core.reporter_auth", "app.api.dashboard", "app.api.evidence"):
        monkeypatch.setattr(module + ".get_settings", lambda: settings)
    monkeypatch.setattr(dashboard, "auth_limiter", SlidingWindowRateLimiter(limit=1000))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(dashboard, "get_session_factory", lambda: factory)
    async with factory() as session:
        session.add_all([Property(id=id, slug=f"p{id}", name=f"Property {id}", address=f"Address {id}") for id in (1, 2, 3)])
        session.add_all([User(id=1, subject="owner", email="owner@example.test", display_name="Owner", password_hash=hash_password(PASSWORD)),
                         User(id=2, subject="reader", email="reader@example.test", display_name="Reader", password_hash=hash_password(PASSWORD))])
        await session.flush()
        session.add_all([PropertyMembership(user_id=1, property_id=id, role="owner") for id in (1, 2)])
        session.add(PropertyMembership(user_id=2, property_id=1, role="reporter"))
        for id in (1, 2, 3):
            session.add(Camera(id=id, property_id=id, name=f"Camera {id}", frigate_camera_name=f"camera{id}", enabled=True))
            session.add(SecurityEvent(id=id, property_id=id, camera_id=id, event_type="INTRUSION", object_type="person",
                confidence=.9, timestamp=datetime.now(timezone.utc), severity="HIGH", status="OPEN", frigate_event_id=f"event-{id}", event_metadata={}))
        await session.flush()
        (tmp_path / "snapshot.jpg").write_bytes(b"\xff\xd8test-image")
        session.add_all([Evidence(id=id, event_id=id, type="SNAPSHOT", file_path="snapshot.jpg", timestamp=datetime.now(timezone.utc)) for id in (1, 2, 3)])
        await session.commit()
    async def session_override():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Dashboard-Request": "1"}) as client:
        yield client, factory, settings
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client, email="owner@example.test"):
    response = await client.post(ROOT + "/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response


def registration(**changes):
    return {"email": "new@example.test", "password": PASSWORD, "full_name": "New Owner",
            "name": "New property", "address": "12 Example Street", **changes}


async def test_registration_creates_only_own_property_and_cookie_session(site):
    client, factory, _ = site
    response = await client.post(ROOT + "/auth/register", json=registration(email=" NEW@example.test "))
    assert response.status_code == 201, response.text
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and f"Path={ROOT}" in cookie
    data = response.json()
    assert "access_token" not in data
    assert data["email"] == "new@example.test"
    assert len(data["properties"]) == 1
    property_id = data["properties"][0]["id"]
    assert property_id not in (1, 2, 3)
    assert data["properties"][0]["address"] == "12 Example Street"
    assert (await client.get(ROOT + "/auth/session")).json() == data
    assert (await client.get(ROOT + "/properties/1/cameras")).status_code == 403
    async with factory() as session:
        user = await session.scalar(select(User).where(User.email == "new@example.test"))
        assert user.password_hash != PASSWORD
        assert await session.scalar(select(func.count()).select_from(PropertyMembership).where(PropertyMembership.user_id == user.id)) == 1


@pytest.mark.parametrize("changes", [{"password": "short123"}, {"password": "nonumericpassword"},
                                     {"full_name": "  "}, {"name": "  "}, {"address": " "}, {"email": "invalid"}])
async def test_registration_validates_required_details_without_echoing_password(site, changes):
    client, factory, _ = site
    body = registration(**changes)
    response = await client.post(ROOT + "/auth/register", json=body)
    assert response.status_code == 422
    assert body["password"] not in response.text
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 2


async def test_duplicate_registration_and_registration_disabled(site):
    client, _, settings = site
    response = await client.post(ROOT + "/auth/register", json=registration(email="OWNER@example.test"))
    assert response.status_code == 409
    settings.dashboard_registration_enabled = False
    assert (await client.post(ROOT + "/auth/register", json=registration())).status_code == 403


async def test_login_logout_revocation_expiry_and_forgery(site):
    client, _, _ = site
    assert (await client.get(ROOT + "/auth/session")).status_code == 401
    response = await login(client, " OWNER@example.test ")
    assert len(response.json()["properties"]) == 2
    token = client.cookies.get(dashboard.COOKIE)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    for invalid in ("invalid", jwt.encode(claims | {"exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, SECRET, algorithm="HS256"),
                    jwt.encode(claims, "different-secret-with-at-least-32-characters", algorithm="HS256")):
        client.cookies.set(dashboard.COOKIE, invalid, domain="test.local", path=ROOT)
        assert (await client.get(ROOT + "/auth/session")).status_code == 401
    client.cookies.set(dashboard.COOKIE, token, domain="test.local", path=ROOT)
    assert (await client.post(ROOT + "/auth/logout")).status_code == 204
    client.cookies.set(dashboard.COOKIE, token, domain="test.local", path=ROOT)
    assert (await client.get(ROOT + "/auth/session")).status_code == 401


async def test_failed_logins_lock_account_and_requests_are_limited(site):
    client, _, _ = site
    for _ in range(5):
        assert (await client.post(ROOT + "/auth/login", json={"email": "owner@example.test", "password": "wrong"})).status_code == 401
    assert (await client.post(ROOT + "/auth/login", json={"email": "owner@example.test", "password": PASSWORD})).status_code == 401
    dashboard.auth_limiter = SlidingWindowRateLimiter(limit=1)
    await client.post(ROOT + "/auth/login", json={"email": "unknown@example.test", "password": "wrong"})
    assert (await client.post(ROOT + "/auth/login", json={"email": "unknown@example.test", "password": "wrong"})).status_code == 429


async def test_cross_origin_and_missing_csrf_header_are_rejected(site):
    client, _, _ = site
    assert (await client.post(ROOT + "/auth/register", json=registration(), headers={"Origin": "https://attacker.example"})).status_code == 403
    del client.headers["X-Dashboard-Request"]
    assert (await client.post(ROOT + "/auth/login", json={"email": "owner@example.test", "password": PASSWORD})).status_code == 403


async def test_switching_properties_scopes_every_resource_and_revocation(site):
    client, factory, _ = site
    await login(client)
    for id in (1, 2):
        base = ROOT + f"/properties/{id}"
        assert [item["id"] for item in (await client.get(base + "/cameras")).json()] == [id]
        assert [item["id"] for item in (await client.get(base + "/incidents")).json()["items"]] == [id]
        assert (await client.get(base + "/overview")).json()["active_incidents"] == 1
        for suffix in ("", "/history", "/evidence"):
            assert (await client.get(base + f"/incidents/{3-id}{suffix}")).status_code == 404
        assert (await client.post(base + f"/evidence/{3-id}/access")).status_code == 404
        assert (await client.post(base + f"/cameras/{3-id}/webrtc", content="sdp", headers={"Content-Type": "application/sdp"})).status_code == 404
    assert (await client.get(ROOT + "/properties/3/incidents")).status_code == 403
    async with factory() as session:
        await session.execute(update(PropertyMembership).where(PropertyMembership.property_id == 1).values(active=False))
        await session.commit()
    assert (await client.get(ROOT + "/properties/1/incidents")).status_code == 403


async def test_incident_actions_persist_history_refresh_counts_and_deny_reader(site):
    client, factory, _ = site
    await login(client)
    base = ROOT + "/properties/1"
    for action, status in (("acknowledge", "ACKNOWLEDGED"), ("resolve", "RESOLVED"), ("reopen", "OPEN"), ("dismiss", "DISMISSED")):
        response = await client.post(base + "/incidents/1/commands", json={"command": action, "reason": " Reviewed evidence ", "correlation_id": action})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == status
    history = (await client.get(base + "/incidents/1/history")).json()
    assert [item["new_status"] for item in history] == ["ACKNOWLEDGED", "RESOLVED", "OPEN", "DISMISSED"]
    assert all(item["reason"] == "Reviewed evidence" for item in history)
    assert (await client.get(base + "/overview")).json()["active_incidents"] == 0
    assert (await client.get(base + "/incidents?status=OPEN")).json()["total"] == 0
    assert (await client.get(base + "/incidents?page=2&page_size=1")).json()["items"] == []
    body = {"command": "acknowledge", "reason": "Checked", "correlation_id": "invalid-transition"}
    assert (await client.post(base + "/incidents/1/commands", json=body)).status_code == 409
    assert (await client.post(ROOT + "/properties/2/incidents/1/commands", json=body)).status_code == 404
    await client.post(ROOT + "/auth/logout")
    await login(client, "reader@example.test")
    assert (await client.get(base + "/incidents/1")).status_code == 200
    assert (await client.post(base + "/incidents/1/commands", json=body)).status_code == 403
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(IncidentStatusHistory)) == 4
        assert await session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action == "INCIDENT_STATUS_CHANGED")) == 4


async def test_property_onboarding_and_update_do_not_reassign_existing_data(site):
    client, factory, _ = site
    await login(client)
    response = await client.post(ROOT + "/properties", json={"name": "Second home", "address": "22 Test Road"})
    assert response.status_code == 201
    new_id = response.json()["properties"][-1]["id"]
    assert (await client.get(ROOT + f"/properties/{new_id}/incidents")).json()["total"] == 0
    response = await client.patch(ROOT + "/properties/1", json={"name": "Updated home", "address": "New location"})
    assert response.status_code == 200
    assert response.json()["properties"][0]["name"] == "Updated home"
    async with factory() as session:
        assert (await session.get(SecurityEvent, 1)).property_id == 1
    await client.post(ROOT + "/auth/logout")
    await login(client, "reader@example.test")
    assert (await client.patch(ROOT + "/properties/1", json={"name": "Wrong", "address": "Not allowed"})).status_code == 403


async def test_evidence_grants_bound_to_user_property_and_expiry(site):
    client, _, _ = site
    await login(client)
    base = ROOT + "/properties/1/evidence/1"
    response = await client.post(base + "/access")
    assert response.status_code == 200, response.text
    url = response.json()["url"]
    image = await client.get(url)
    assert image.status_code == 200 and image.content.startswith(b"\xff\xd8")
    assert image.headers["cache-control"] == "no-store"
    assert (await client.get(url.replace("properties/1", "properties/2"))).status_code == 404
    expired = jwt.encode({"sub": "reporter:1", "aud": "evidence-playback", "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
                          "evidence_id": 1, "property_id": 1}, SECRET, algorithm="HS256")
    assert (await client.get(base + "/content", params={"grant": expired})).status_code == 401
    await client.post(ROOT + "/auth/logout")
    await login(client, "reader@example.test")
    assert (await client.get(url)).status_code == 401


async def test_frigate_evidence_uses_the_incident_event_not_latest_camera(site, monkeypatch):
    client, factory, _ = site
    await login(client)
    async with factory() as session:
        evidence = await session.get(Evidence, 1)
        evidence.file_path = "/api/v1/frigate/cameras/camera1/snapshot"
        await session.commit()
    calls = []
    class FrigateClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url):
            calls.append(url)
            return SimpleNamespace(status_code=200, content=b"\xff\xd8snapshot", raise_for_status=lambda: None)
    monkeypatch.setattr("app.api.evidence.httpx.AsyncClient", FrigateClient)
    grant = await client.post(ROOT + "/properties/1/evidence/1/access")
    assert grant.status_code == 200, grant.text
    response = await client.get(grant.json()["url"])
    assert response.status_code == 200
    assert calls == ["http://localhost:5000/api/events/event-1/snapshot.jpg"]
