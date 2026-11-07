"""Real SQL operator flows over both incident sources; no deployment DB or MQTT."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import dashboard, operator_cases
from app.core.config import Settings
from app.core.dependencies import get_event_publisher, get_session
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.reporter_auth import hash_password
from app.database.base import Base
from app.main import app
from app.models import (Assignment, AssignmentEvent, AuditRecord, Camera, Evidence,
    IncidentStatusHistory, MarshalAvailability, MarshalProfile, NotificationOutbox,
    Property, PropertyMembership, ReporterIncident, ReporterIncidentEvidence,
    ReporterIncidentTimeline, SecurityEvent, User)

ROOT = "/api/v1/dashboard"
CASES = ROOT + "/properties/1/cases"
PASSWORD = "Operator-test-password123"
SECRET = "operator-test-secret-at-least-32-characters"


@pytest_asyncio.fixture
async def site(monkeypatch, tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    (root / "camera.jpg").write_bytes(b"\xff\xd8camera")
    (root / "manual.png").write_bytes(b"\x89PNG\r\n\x1a\nmanual")
    (tmp_path / "outside.png").write_bytes(b"private")
    settings = Settings(auth_enabled=True, jwt_secret=SECRET, evidence_root=str(root))
    for name in ("app.core.auth", "app.core.reporter_auth", "app.api.dashboard", "app.api.evidence", "app.api.operator_cases"):
        monkeypatch.setattr(name + ".get_settings", lambda: settings)
    monkeypatch.setattr(dashboard, "auth_limiter", SlidingWindowRateLimiter(limit=1000))
    limiter = SlidingWindowRateLimiter(limit=1000)
    monkeypatch.setattr(operator_cases, "get_mutation_rate_limiter", lambda: limiter)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/database.sqlite")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add_all([Property(id=id, slug=f"property-{id}", name=f"Property {id}", address=f"Address {id}") for id in (1, 2)])
        for id, role in [(1, "owner"), (2, "reporter"), (3, "dispatcher"), (4, "marshal"), (5, "foreign-marshal")]:
            session.add(User(id=id, subject=role, email=f"{role}@example.test", display_name=role.title(), password_hash=hash_password(PASSWORD)))
        await session.flush()
        session.add_all([PropertyMembership(user_id=1, property_id=id, role="owner") for id in (1, 2)])
        session.add_all([PropertyMembership(user_id=id, property_id=1 if id < 5 else 2, role=role)
                         for id, role in [(2, "reporter"), (3, "dispatcher"), (4, "marshal"), (5, "marshal")]])
        for id in (1, 2):
            session.add(Camera(id=id, property_id=id, name=f"Camera {id}", frigate_camera_name=f"camera-{id}", enabled=True, location=f"Gate {id}"))
            session.add(SecurityEvent(id=id, property_id=id, camera_id=id, event_type="INTRUSION", object_type="person",
                confidence=.91, timestamp=now, status="OPEN", severity="HIGH", reason=f"Camera incident {id}", event_metadata={}))
            session.add(ReporterIncident(id=id, reporter_user_id=2 if id == 1 else 1, property_id=id,
                incident_type="THEFT", description=f"Manual report {id}", address=f"Street {id}", latitude=19.0,
                longitude=72.0, location_accuracy=5.0, status="RECEIVED", idempotency_key=f"manual-report-{id}", created_at=now))
            session.add(MarshalProfile(id=id, user_id=4 if id == 1 else 5, property_id=id, capacity=1, service_area=f"Area {id}", verification_status='APPROVED'))
        await session.flush()
        for id in (1, 2):
            session.add(MarshalAvailability(marshal_profile_id=id, on_duty=True, available=True, updated_at=now))
            session.add(IncidentStatusHistory(security_event_id=id, new_status="OPEN", actor_subject="system:ingestion",
                reason="Detected", correlation_id=f"detection-{id}", occurred_at=now))
            session.add(ReporterIncidentTimeline(incident_id=id, status="RECEIVED", actor_subject=f"reporter:{id}", message="Report received", occurred_at=now))
            session.add(Evidence(id=id, event_id=id, type="SNAPSHOT", file_path="camera.jpg", timestamp=now))
            session.add(ReporterIncidentEvidence(id=id, incident_id=id, media_type="image/png", file_path="manual.png",
                original_filename="attachment.png", byte_size=14))
        await session.commit()
    async def sessions():
        async with factory() as session:
            yield session
    app.dependency_overrides[get_session] = sessions
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-Dashboard-Request": "1"}) as client:
        yield client, factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client, role="owner"):
    response = await client.post(ROOT + "/auth/login", json={"email": f"{role}@example.test", "password": PASSWORD})
    assert response.status_code == 200, response.text


def offer(key="operator-offer-0001", marshal=1):
    return {"marshal_profile_id": marshal, "expires_in_seconds": 60, "idempotency_key": key}


def command(action="acknowledge", status="OPEN", reason="Reviewed evidence"):
    return {"command": action, "expected_status": status, "reason": reason, "correlation_id": uuid4().hex}


async def test_one_paginated_queue_disambiguates_sources_without_inventing_severity(site):
    client, _ = site
    await login(client)
    response = await client.get(CASES)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows["total"] == 2
    assert [item["key"] for item in rows["items"]] == ["camera:1", "reporter:1"]
    assert rows["items"][1]["status"] == "OPEN" and rows["items"][1]["source_status"] == "RECEIVED"
    assert rows["items"][1]["severity"] is None
    assert (await client.get(CASES + "?page=2&page_size=1")).json()["items"][0]["key"] == "reporter:1"
    assert (await client.get(CASES + "?page=3&page_size=1")).json()["items"] == []
    assert (await client.get(CASES + "?source=reporter&status=OPEN")).json()["total"] == 1
    assert (await client.get(CASES + "?severity=HIGH")).json()["items"][0]["key"] == "camera:1"
    assert (await client.get(CASES + "/overview")).json() == {"total": 2, "active": 2, "by_source": {"camera": 1, "reporter": 1}}
    assert response.headers["cache-control"] == "no-store"
    for suffix in ("?source=other", "?page=0", "?page_size=101", "?severity=invalid"):
        assert (await client.get(CASES + suffix)).status_code == 422


async def test_property_scoped_details_include_report_location_without_private_paths(site):
    client, _ = site
    await login(client)
    camera = (await client.get(CASES + "/camera/1")).json()
    report = (await client.get(CASES + "/reporter/1")).json()
    assert camera["location"]["address"] == "Gate 1"
    assert report["location"] == {"address": "Street 1", "latitude": 19.0, "longitude": 72.0, "accuracy_metres": 5.0}
    assert report["confidence"] is None and report["camera_id"] is None
    for source in ("camera", "reporter"):
        for suffix in ("", "/timeline", "/evidence", "/assignments"):
            assert (await client.get(CASES + f"/{source}/2{suffix}")).status_code == 404
        evidence = (await client.get(CASES + f"/{source}/1/evidence")).json()
        assert evidence["total"] == 1 and "file_path" not in str(evidence)
    assert (await client.get(ROOT + "/properties/999/cases")).status_code == 403


@pytest.mark.parametrize("role,expected", [("reporter", 403), ("marshal", 403), ("dispatcher", 200)])
async def test_private_operator_queue_and_mutations_are_role_restricted(site, role, expected):
    client, _ = site
    await login(client, role)
    for path in ("", "/overview", "/reporter/1", "/reporter/1/evidence", "/eligible-marshals"):
        assert (await client.get(CASES + path)).status_code == expected
    response = await client.post(CASES + "/reporter/1/commands", json=command())
    assert response.status_code == expected


@pytest.mark.parametrize("source", ["camera", "reporter"])
async def test_status_commands_are_audited_version_checked_and_keep_source_contract(site, source):
    client, factory = site
    await login(client)
    base = CASES + f"/{source}/1"
    assert (await client.post(base + "/commands", json=command(reason=" "))).status_code == 422
    for action, before, after in [("acknowledge", "OPEN", "ACKNOWLEDGED"), ("resolve", "ACKNOWLEDGED", "RESOLVED"),
                                  ("reopen", "RESOLVED", "OPEN"), ("dismiss", "OPEN", "DISMISSED")]:
        response = await client.post(base + "/commands", json=command(action, before))
        assert response.status_code == 200, response.text
        assert response.json()["status"] == after
        assert (await client.post(base + "/commands", json=command(action, before))).status_code == 409
    events = (await client.get(base + "/timeline")).json()
    assert events["total"] == 5
    assert len({item["key"] for item in events["items"]}) == 5
    assert (await client.get(base + "/timeline?page=2&page_size=2")).json()["items"]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action == "CASE_STATUS_CHANGED")) == 4
        assert await session.scalar(select(func.count()).select_from(NotificationOutbox).where(NotificationOutbox.kind == "CASE_STATUS_CHANGED")) == 4
    assert (await client.get(CASES + "/overview")).json()["active"] == 1


@pytest.mark.parametrize("source", ["camera", "reporter"])
async def test_offer_replay_cancel_reoffer_and_timeline(site, source):
    client, _ = site
    await login(client)
    base = CASES + f"/{source}/1"
    assert [item["id"] for item in (await client.get(CASES + "/eligible-marshals")).json()] == [1]
    first = await client.post(base + "/offers", json=offer())
    assert first.status_code == 201, first.text
    item = first.json()
    replay = await client.post(base + "/offers", json=offer())
    assert replay.status_code == 201 and replay.json()["id"] == item["id"]
    assert (await client.post(base + "/offers", json=offer("different-request"))).status_code == 409
    other = "camera" if source == "reporter" else "reporter"
    assert (await client.post(CASES + f"/{other}/1/offers", json=offer())).status_code == 409
    assert (await client.get(CASES + "/eligible-marshals")).json() == []
    detail = (await client.get(base)).json()
    assert detail["latest_assignment"]["status"] == "OFFERED" and not detail["dispatch_allowed"]
    assert "resolve" not in detail["allowed_actions"]
    assert (await client.post(base + "/commands", json=command("resolve"))).status_code == 409
    cancel = base + f"/assignments/{item['id']}/cancel"
    assert (await client.post(cancel, json={"expected_version": 2})).status_code == 409
    assert (await client.post(cancel, json={"expected_version": 1})).json()["status"] == "CANCELLED"
    assert (await client.post(base + "/offers", json=offer("reoffer-request-0002"))).status_code == 201
    assignments = (await client.get(base + "/assignments?page_size=1")).json()
    assert assignments["total"] == 2 and assignments["items"][0]["status"] == "OFFERED"
    timeline = (await client.get(base + "/timeline")).json()["items"]
    assert [item["status"] for item in timeline if item["kind"] == "assignment_status"] == ["OFFERED", "CANCELLED", "OFFERED"]


async def test_eligibility_foreign_marshal_and_terminal_incident_guards(site):
    client, factory = site
    await login(client)
    assert (await client.post(CASES + "/reporter/1/offers", json=offer(marshal=2))).status_code == 409
    async with factory() as session:
        await session.execute(update(MarshalAvailability).where(MarshalAvailability.marshal_profile_id == 1)
                              .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=6)))
        await session.commit()
    assert (await client.get(CASES + "/eligible-marshals")).json() == []
    assert (await client.post(CASES + "/reporter/1/offers", json=offer())).status_code == 409
    response = await client.post(CASES + "/reporter/1/commands", json=command("resolve"))
    assert response.status_code == 200
    assert (await client.post(CASES + "/reporter/1/offers", json=offer())).json()["error"]["code"] == "INCIDENT_CLOSED"


async def test_reporter_can_still_read_own_report_and_real_assignment_status(site):
    client, _ = site
    await login(client)
    created = await client.post(CASES + "/reporter/1/offers", json=offer())
    assert created.status_code == 201, created.text
    item = created.json()
    auth = (await client.post("/api/v1/auth/login", json={"email": "marshal@example.test", "password": PASSWORD})).json()
    accepted = await client.post(f"/api/v1/dispatch/offers/{item['id']}/accept", json={"expected_version": 1},
                                 headers={"Authorization": "Bearer " + auth["access_token"]})
    assert accepted.status_code == 200, accepted.text
    assert (await client.get(CASES + "/reporter/1")).json()["latest_assignment"]["status"] == "ACCEPTED"
    auth = (await client.post("/api/v1/auth/login", json={"email": "reporter@example.test", "password": PASSWORD})).json()
    report = await client.get("/api/v1/reporter/incidents/1", headers={"Authorization": "Bearer " + auth["access_token"]})
    assert report.status_code == 200 and report.json()["status"] == "RECEIVED"
    assert report.json()["dispatch"]["status"] == "ACCEPTED"


@pytest.mark.parametrize("source", ["camera", "reporter"])
async def test_evidence_grants_bound_to_source_case_property_actor_and_expiration(site, source):
    client, _ = site
    await login(client)
    base = CASES + f"/{source}/1/evidence"
    assert (await client.post(base + "/2/access")).status_code == 404
    response = await client.post(base + "/1/access")
    assert response.status_code == 200, response.text
    url = response.json()["url"]
    image = await client.get(url)
    assert image.status_code == 200 and image.headers["cache-control"] == "no-store"
    other = "reporter" if source == "camera" else "camera"
    assert (await client.get(url.replace(f"/{source}/1", f"/{other}/1"))).status_code == 401
    assert (await client.get(url.replace("properties/1", "properties/2"))).status_code == 401
    expired = jwt.encode({"aud": "operator-case-evidence", "sub": "reporter:1", "exp": 1,
        "source": source, "source_id": 1, "property_id": 1, "evidence_id": 1}, SECRET, algorithm="HS256")
    assert (await client.get(base + "/1/content", params={"grant": expired})).status_code == 401
    await login(client, "dispatcher")
    assert (await client.get(url)).status_code == 401


async def test_private_file_paths_are_never_exposed_or_allowed_to_escape_storage(site):
    client, factory = site
    await login(client)
    async with factory() as session:
        await session.execute(update(ReporterIncidentEvidence).where(ReporterIncidentEvidence.id == 1).values(file_path="../outside.png"))
        await session.commit()
    evidence = await client.get(CASES + "/reporter/1/evidence")
    assert "outside" not in evidence.text
    assert (await client.post(CASES + "/reporter/1/evidence/1/access")).status_code == 404


async def test_database_prevents_duplicate_active_manual_offers_and_invalid_sources(site):
    _, factory = site
    async with factory() as session:
        first = Assignment(property_id=1, reporter_incident_id=1, marshal_profile_id=1, status="ACCEPTED",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60), idempotency_key="database-first-offer")
        session.add(first)
        await session.commit()
    async with factory() as session:
        session.add(Assignment(property_id=1, reporter_incident_id=1, marshal_profile_id=1, status="ACCEPTED",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60), idempotency_key="database-second-offer"))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
        session.add(Assignment(property_id=1, security_event_id=1, reporter_incident_id=1, marshal_profile_id=1,
            status="OFFERED", expires_at=datetime.now(timezone.utc), idempotency_key="database-invalid-source"))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.parametrize('source', ['camera', 'reporter'])
async def test_duplicate_pending_offers_for_same_marshal_are_rejected(site, source):
    _, factory = site
    async with factory() as session:
        for key in ['pending-first', 'pending-duplicate']:
            session.add(Assignment(property_id=1, marshal_profile_id=1, status='OFFERED',
                security_event_id=1 if source == 'camera' else None,
                reporter_incident_id=1 if source == 'reporter' else None,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), idempotency_key=key))
            if key == 'pending-first':
                await session.flush()
            else:
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()


@pytest.mark.parametrize('source', ['camera', 'reporter'])
async def test_case_report_uses_complete_history_and_only_incident_notifications(site, source):
    client, factory = site
    await login(client)
    async with factory() as session:
        item = await session.get(SecurityEvent if source == 'camera' else ReporterIncident, 1)
        started = item.timestamp if source == 'camera' else item.created_at
        for index in range(1, 126):
            status = 'RESOLVED' if index == 125 else 'ACKNOWLEDGED'
            when = started + timedelta(seconds=index)
            row = IncidentStatusHistory(security_event_id=1, new_status=status, actor_subject='test',
                reason='Test history', correlation_id=f'full-history-{index}', occurred_at=when) if source == 'camera' else ReporterIncidentTimeline(
                    incident_id=1, status=status, actor_subject='test', message='Test history', occurred_at=when)
            session.add(row)
        for id in [1, 2]:
            for kind in ['CAMERA', 'REPORTER']:
                session.add(NotificationOutbox(property_id=1, security_event_id=id if kind == 'CAMERA' else None,
                    kind=kind, dedupe_key=f'report-{kind}-{id}', payload={} if kind == 'CAMERA' else {'reporter_incident_id': id}))
        await session.commit()
    result = await client.get(CASES + f'/{source}/1/report')
    assert result.status_code == 200, result.text
    report = result.json()
    assert len(report['timeline']) == 126
    assert report['metrics']['response_duration_seconds'] == 125
    assert [row['kind'] for row in report['notifications']] == [source.upper()]


@pytest.mark.parametrize('source', ['camera', 'reporter'])
async def test_download_report_includes_evidence_beyond_the_first_page(site, source):
    """Verify both incident sources export every evidence reference without private paths."""
    client, factory = site
    await login(client)
    async with factory() as session:
        for index in range(105):
            session.add(Evidence(event_id=1, type='SNAPSHOT', file_path=f'private-{index}.jpg', timestamp=datetime.now(timezone.utc))
                if source == 'camera' else ReporterIncidentEvidence(incident_id=1, media_type='image/jpeg',
                    file_path=f'private-{index}.jpg', original_filename=f'photo-{index}.jpg', byte_size=100))
        await session.commit()
    result = await client.get(CASES + f'/{source}/1/report')
    assert result.status_code == 200, result.text
    assert len(result.json()['evidence']) == 106
    assert len({row['id'] for row in result.json()['evidence']}) == 106
    assert 'file_path' not in result.text and 'private-' not in result.text


async def test_case_updates_are_published_only_to_the_authorized_property(site):
    client, _ = site
    await login(client)
    publisher = get_event_publisher()
    own, foreign = await publisher.subscribe(frozenset({1})), await publisher.subscribe(frozenset({2}))
    try:
        response = await client.post(CASES + "/reporter/1/commands", json=command())
        assert response.status_code == 200, response.text
        assert (await own.get()) == {"type": "case_updated", "property_id": 1, "data": {"key": "reporter:1"}}
        assert foreign.empty()
    finally:
        await publisher.unsubscribe(own)
        await publisher.unsubscribe(foreign)


async def test_mobile_report_creation_notifies_operator_queue_without_changing_response(site):
    client, _ = site
    auth = (await client.post("/api/v1/auth/login", json={"email": "reporter@example.test", "password": PASSWORD})).json()
    publisher = get_event_publisher()
    queue = await publisher.subscribe(frozenset({1}))
    try:
        response = await client.post("/api/v1/reporter/incidents", json={
            "property_id": 1, "incident_type": "THEFT", "address": "New report location"},
            headers={"Authorization": "Bearer " + auth["access_token"], "X-Idempotency-Key": "operator-new-mobile-report-1"})
        assert response.status_code == 201, response.text
        report = response.json()
        assert report["status"] == "RECEIVED" and report["timeline"][0]["status"] == "RECEIVED"
        assert await queue.get() == {"type": "case_updated", "property_id": 1, "data": {"key": f"reporter:{report['id']}"}}
        await login(client)
        assert (await client.get(CASES + f"/reporter/{report['id']}")).json()["source_status"] == "RECEIVED"
    finally:
        await publisher.unsubscribe(queue)


async def test_revoked_permissions_and_csrf_checks_apply_to_unified_endpoints(site):
    client, factory = site
    await login(client)
    del client.headers["X-Dashboard-Request"]
    assert (await client.post(CASES + "/reporter/1/offers", json=offer())).status_code == 403
    client.headers["X-Dashboard-Request"] = "1"
    assert (await client.post(CASES + "/reporter/1/commands", json=command(), headers={"Origin": "https://foreign.test"})).status_code == 403
    async with factory() as session:
        await session.execute(update(PropertyMembership).where(PropertyMembership.user_id == 1,
            PropertyMembership.property_id == 1).values(active=False))
        await session.commit()
    assert (await client.get(CASES)).status_code == 403
    assert (await client.post(CASES + "/camera/1/offers", json=offer())).status_code == 403


async def test_failed_outbox_write_rolls_back_offer_and_assignment_history(site):
    client, factory = site
    await login(client)
    async with factory() as session:
        await session.execute(text("""CREATE TRIGGER reject_test_outbox BEFORE INSERT ON notification_outbox
            BEGIN SELECT RAISE(ABORT, 'injected outbox failure'); END"""))
        await session.commit()
    response = await client.post(CASES + "/reporter/1/offers", json=offer())
    assert response.status_code == 409
    async with factory() as session:
        for model in (Assignment, AssignmentEvent, NotificationOutbox):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_command_retry_after_reopen_does_not_apply_the_old_action_again(site):
    client, factory = site
    await login(client)
    base = CASES + "/reporter/1"
    original = command()
    assert (await client.post(base + "/commands", json=original)).status_code == 200
    assert (await client.post(base + "/commands", json=command("resolve", "ACKNOWLEDGED"))).status_code == 200
    assert (await client.post(base + "/commands", json=command("reopen", "RESOLVED"))).status_code == 200
    replay = await client.post(base + "/commands", json=original)
    assert replay.status_code == 200 and replay.json()["status"] == "OPEN"
    assert (await client.post(base + "/commands", json={**original, "reason": "Changed intent"})).status_code == 409
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action == "CASE_STATUS_CHANGED")) == 3
