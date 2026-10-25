"""Dashboard delivery regression tests without camera/network services."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal
from app.core.exceptions import ApplicationError
from app.main import app
from app.models.security_event import SecurityEvent
from app.realtime.publisher import InMemoryEventPublisher


def event():
    return SecurityEvent(id=42, property_id=1, camera_id=1, event_type="INTRUSION",
        object_type="person", confidence=.9, timestamp=datetime.now(timezone.utc),
        severity="HIGH", status="OPEN", event_metadata={})


async def test_overflow_requires_resync_and_connection_limit_is_bounded():
    publisher = InMemoryEventPublisher(queue_size=1)
    queue = await publisher.subscribe(frozenset({1}))
    await publisher.publish(event())
    await publisher.publish(event())
    assert await queue.get() == {"version": 1, "type": "resync_required"}
    publisher.max_subscribers = 1
    with pytest.raises(OverflowError):
        await publisher.subscribe()
    await publisher.unsubscribe(queue)
    await publisher.subscribe()


async def test_repeated_states_have_distinct_transport_ids_and_unknown_tracks_fail_closed():
    publisher = InMemoryEventPublisher()
    queue = await publisher.subscribe(frozenset({1}))
    await publisher.publish_tracks("999", [])
    assert queue.empty()
    value = event()
    await publisher.publish(value)
    first = await queue.get()
    value.status = "RESOLVED"
    await publisher.publish(value)
    await queue.get()
    value.status = "OPEN"
    await publisher.publish(value)
    reopened = await queue.get()
    assert first["event_id"] != reopened["event_id"]
    assert reopened["sequence"] > first["sequence"]
    assert reopened["property_id"] == 1


def test_websocket_subprotocol_auth_resync_expiry_and_unsubscribe(monkeypatch):
    from app.core.auth import get_websocket_principal
    publisher = InMemoryEventPublisher()
    monkeypatch.setattr("app.api.realtime.get_event_publisher", lambda: publisher)
    app.dependency_overrides[get_websocket_principal] = lambda: Principal("test", frozenset({"read"}), frozenset({1}))
    def expired(_):
        raise ApplicationError("UNAUTHORIZED", "Expired", 401)
    monkeypatch.setattr("app.api.realtime.authenticate_token", expired)
    # Seed an invalidation as soon as the connection subscribes, without sleeping.
    original = publisher.subscribe
    async def subscribe(properties):
        queue = await original(properties)
        queue.put_nowait({"type": "heartbeat", "version": 1})
        return queue
    monkeypatch.setattr(publisher, "subscribe", subscribe)
    try:
        with TestClient(app).websocket_connect('/api/v1/events/stream', subprotocols=['securepulse.v1', 'bearer.test']) as socket:
            assert socket.accepted_subprotocol == 'securepulse.v1'
            assert socket.receive_json()["type"] == 'resync_required'
            assert socket.receive()["code"] == 4401
        assert not publisher._subscribers
    finally:
        app.dependency_overrides.clear()


async def test_browser_subprotocol_reuses_existing_authenticator(monkeypatch):
    from starlette.websockets import WebSocket
    from app.core.auth import get_websocket_principal
    from tests.test_auth import auth_settings, make_token
    monkeypatch.setattr("app.core.auth.get_settings", auth_settings)
    token = make_token()
    socket = WebSocket({"type": "websocket", "path": "/", "query_string": b"",
        "headers": [(b"sec-websocket-protocol", f"securepulse.v1, bearer.{token}".encode())]}, AsyncMock(), AsyncMock())
    principal = await get_websocket_principal(socket)
    assert principal.property_ids == frozenset({1})


async def test_command_failure_emits_no_realtime(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from app.core.dependencies import get_incident_service
    service = AsyncMock()
    service.command.side_effect = ApplicationError("INVALID_INCIDENT_TRANSITION", "Conflict", 409)
    publisher = InMemoryEventPublisher()
    queue = await publisher.subscribe()
    monkeypatch.setattr("app.api.incidents.get_event_publisher", lambda: publisher)
    app.dependency_overrides[get_incident_service] = lambda: service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post('/api/v1/incidents/42/commands', json={"command": "resolve", "reason": "Reviewed", "correlation_id": "fixture"})
        assert response.status_code == 409 and queue.empty()
    finally:
        app.dependency_overrides.clear()


async def test_playback_grants_bind_camera_property_actor_and_expire(monkeypatch):
    import jwt
    from types import SimpleNamespace
    from fastapi import HTTPException, Response
    from starlette.requests import Request
    from app.api.frigate import playback_access, negotiate_webrtc
    from tests.test_auth import auth_settings, SECRET
    settings = auth_settings()
    monkeypatch.setattr("app.api.frigate.get_settings", lambda: settings)
    principal = Principal("test", frozenset({"read"}), frozenset({1}))
    camera = SimpleNamespace(id=1, property_id=1, enabled=True)
    service = AsyncMock()
    service.get.return_value = camera
    response = Response()
    access = await playback_access(1, response, principal, service)
    assert response.headers['cache-control'] == 'no-store'
    claims = jwt.decode(access['grant'], SECRET, algorithms=['HS256'], audience='camera-playback')
    assert claims['camera_id'] == 1 and claims['property_id'] == 1 and claims['sub'] == 'test'
    assert 0 < claims['exp'] - datetime.now(timezone.utc).timestamp() <= 60
    for changed in [{'exp': 1}, {'camera_id': 2}, {'property_id': 2}, {'sub': 'other'}]:
        grant = jwt.encode(claims | changed, SECRET, algorithm='HS256')
        request = Request({'type': 'http', 'headers': [(b'x-playback-grant', grant.encode())]})
        request._body = b'v=0'
        with pytest.raises(HTTPException) as caught:
            await negotiate_webrtc(1, request, principal, service)
        assert caught.value.status_code == 401


def test_two_dashboard_sessions_and_foreign_property_receive_only_authorized_events(monkeypatch):
    from fastapi import FastAPI
    from app.api.realtime import router
    from tests.test_auth import auth_settings, make_token
    publisher = InMemoryEventPublisher()
    monkeypatch.setattr('app.api.realtime.get_event_publisher', lambda: publisher)
    monkeypatch.setattr('app.core.auth.get_settings', auth_settings)
    isolated = FastAPI()
    isolated.include_router(router)
    with TestClient(isolated) as client:
        protocols = ['securepulse.v1', 'bearer.' + make_token()]
        foreign_protocols = ['securepulse.v1', 'bearer.' + make_token(property_ids=[2])]
        with client.websocket_connect('/events/stream', subprotocols=protocols) as first, client.websocket_connect('/events/stream', subprotocols=protocols) as second, client.websocket_connect('/events/stream', subprotocols=foreign_protocols) as foreign:
            assert first.receive_json()['type'] == second.receive_json()['type'] == 'resync_required'
            assert foreign.receive_json()['type'] == 'resync_required'
            client.portal.call(publisher.publish, event())
            one, two = first.receive_json(), second.receive_json()
            assert one['event_id'] == two['event_id']
            assert one['data']['id'] == two['data']['id'] == 42
            sentinel = event()
            sentinel.property_id = 2
            client.portal.call(publisher.publish, sentinel)
            # A foreign leak would have queued property 1 before this sentinel.
            assert foreign.receive_json()['property_id'] == 2
    assert not publisher._subscribers


def test_invalid_websocket_token_cannot_open_subscription(monkeypatch):
    from tests.test_auth import auth_settings
    from starlette.websockets import WebSocketDisconnect
    monkeypatch.setattr('app.core.auth.get_settings', auth_settings)
    publisher = InMemoryEventPublisher()
    monkeypatch.setattr('app.api.realtime.get_event_publisher', lambda: publisher)
    with pytest.raises((WebSocketDisconnect,)):
        with TestClient(app).websocket_connect('/api/v1/events/stream', subprotocols=['securepulse.v1', 'bearer.invalid']):
            pytest.fail('Unauthenticated socket was accepted')
    assert not publisher._subscribers
