from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from sqlalchemy import update

from app.core.exceptions import ApplicationError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.models import PropertyMembership, User
from app.models.operations import UserDeviceToken
from tests.test_reporter import fixture, sign_in


def upstream(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.asyncio
async def test_password_reset_retries_local_revocation_after_provider_success(fixture, monkeypatch):
    from app.api.account_recovery import reset_password, RecoveryPassword
    from sqlalchemy.exc import SQLAlchemyError
    client, factory, settings = fixture
    provider = SimpleNamespace(public_operation=AsyncMock(return_value={}))
    monkeypatch.setattr('app.api.account_recovery.NeonAuth', lambda: provider)
    async with factory() as session:
        session.add(User(id=3, subject='neon:managed', email='managed@example.test'))
        await session.flush()
        session.add(UserDeviceToken(user_id=3, device_id='reset-device', push_token='ExpoPushToken[reset]', provider='expo'))
        await session.commit()
        commit = session.commit
        calls = 0
        async def flaky_commit():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise SQLAlchemyError('temporary database failure')
            await commit()
        monkeypatch.setattr(session, 'commit', flaky_commit)
        await reset_password(RecoveryPassword(email='managed@example.test', code='123456', new_password='Replacement-password123'), session)
    provider.public_operation.assert_awaited_once()
    async with factory() as session:
        assert (await session.get(User, 3)).token_version == 1
        from sqlalchemy import select
        assert not (await session.scalar(select(UserDeviceToken).where(UserDeviceToken.user_id == 3))).active


@pytest.mark.asyncio
async def test_managed_signin_completes_reset_revocation_after_persistent_database_failure(fixture, monkeypatch):
    from app.api.account_recovery import reset_password, RecoveryPassword
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy import select
    client, factory, settings = fixture
    settings.neon_auth_base_url = 'https://auth.example.test/auth'
    monkeypatch.setattr('app.api.reporter.get_settings', lambda: settings)
    provider = SimpleNamespace(public_operation=AsyncMock(return_value={}),
        signin=AsyncMock(return_value={'id': 'managed', 'email': 'managed@example.test'}))
    monkeypatch.setattr('app.api.account_recovery.NeonAuth', lambda: provider)
    monkeypatch.setattr('app.api.reporter.NeonAuth', lambda: provider)
    async with factory() as session:
        session.add(User(id=3, subject='neon:managed', email='managed@example.test'))
        await session.flush()
        session.add(UserDeviceToken(user_id=3, device_id='reset-device', push_token='ExpoPushToken[reset]', provider='expo'))
        await session.commit()
        monkeypatch.setattr(session, 'execute', AsyncMock(side_effect=SQLAlchemyError('database unavailable')))
        with pytest.raises(ApplicationError) as error:
            await reset_password(RecoveryPassword(email='managed@example.test', code='123456', new_password='Replacement-password123'), session)
        assert error.value.status_code == 503
    result = await client.post('/api/v1/auth/login', json={'email': 'managed@example.test', 'password': 'Replacement-password123'})
    assert result.status_code == 200
    async with factory() as session:
        assert (await session.get(User, 3)).token_version == 1
        assert not (await session.scalar(select(UserDeviceToken).where(UserDeviceToken.user_id == 3))).active


@pytest.mark.asyncio
async def test_device_registration_cannot_deactivate_another_accounts_device(fixture):
    client, factory, _ = fixture
    owner = {'Authorization': 'Bearer ' + await sign_in(client)}
    other = {'Authorization': 'Bearer ' + await sign_in(client, 'reporter@example.test')}
    original = {'device_id': 'owner-device', 'push_token': 'ExpoPushToken[owner]', 'provider': 'expo'}
    assert (await client.post('/api/v1/reporter/devices', json=original, headers=owner)).status_code == 204
    for body in [{**original, 'device_id': 'attacker-device'}, {**original, 'push_token': 'ExpoPushToken[attacker]'}]:
        assert (await client.post('/api/v1/reporter/devices', json=body, headers=other)).status_code == 409
    assert (await client.post('/api/v1/auth/logout', headers=owner)).status_code == 204
    assert (await client.post('/api/v1/reporter/devices', json=original, headers=other)).status_code == 204


@pytest.mark.asyncio
async def test_prefixed_go2rtc_playlists_normalize_resources_and_keep_origin_checks(fixture, monkeypatch):
    from app.api.reporter_live import rewrite_playlist
    _, _, settings = fixture
    settings.go2rtc_url = 'https://camera.example/proxy/go2rtc'
    claims = {'aud': 'reporter-live', 'exp': 9999999999}
    for uri in ['hls/playlist.m3u8?id=a', '/proxy/go2rtc/api/hls/playlist.m3u8?id=a', '/api/hls/playlist.m3u8?id=a']:
        result = rewrite_playlist('#EXTM3U\n' + uri, '/api/stream.m3u8', 1, claims, settings)
        resource = parse_qs(urlsplit(result.splitlines()[1]).query)['resource'][0]
        assert resource == '/api/hls/playlist.m3u8?id=a'
    with pytest.raises(ApplicationError):
        rewrite_playlist('#EXTM3U\nhttps://evil.example/api/hls/playlist.m3u8', '/api/stream.m3u8', 1, claims, settings)


@pytest.mark.asyncio
async def test_native_hls_rewrites_segments_and_rejects_tampering_and_revocation(fixture, monkeypatch):
    client, factory, settings = fixture
    settings.go2rtc_url = 'http://go2rtc.test'
    monkeypatch.setattr('app.api.reporter_live.get_settings', lambda: settings)
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/api/stream.m3u8':
            return httpx.Response(200, text='#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000\nhls/playlist.m3u8?id=opaque\n')
        if request.url.path.endswith('playlist.m3u8'):
            return httpx.Response(200, text='#EXTM3U\n#EXT-X-MAP:URI="init.mp4?id=opaque"\nsegment.m4s?id=opaque&n=1\n')
        return httpx.Response(200, content=b'local-media-bytes')
    upstream(monkeypatch, handler)
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    grant = await client.post('/api/v1/reporter/cameras/1/live/access?property_id=1', headers=headers)
    assert grant.status_code == 200
    assert 'private_1' not in grant.text and 'go2rtc' not in grant.text
    playlist = await client.get(grant.json()['url'])
    assert playlist.status_code == 200
    child = next(line for line in playlist.text.splitlines() if line.startswith('/api/'))
    content = await client.get(child)
    assert content.status_code == 200 and 'go2rtc.test' not in content.text
    segment = next(line for line in content.text.splitlines() if line.startswith('/api/'))
    assert (await client.get(segment)).content == b'local-media-bytes'
    parts = urlsplit(segment); query = parse_qs(parts.query)
    query['resource'] = ['/api/hls/segment.m4s?id=another-camera']
    assert (await client.get(parts.path + '?' + urlencode(query, doseq=True))).status_code == 401
    assert (await client.get(segment.replace('/cameras/1/', '/cameras/2/'))).status_code == 401
    async with factory() as session:
        await session.execute(update(PropertyMembership).where(PropertyMembership.user_id == 1).values(active=False))
        await session.commit()
    assert (await client.get(segment)).status_code == 404


@pytest.mark.asyncio
async def test_live_access_is_property_scoped_and_logout_revokes_playlist(fixture, monkeypatch):
    client, _, settings = fixture
    monkeypatch.setattr('app.api.reporter_live.get_settings', lambda: settings)
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    assert (await client.post('/api/v1/reporter/cameras/2/live/access?property_id=2', headers=headers)).status_code == 404
    assert (await client.post('/api/v1/reporter/cameras/1/live/access?property_id=1')).status_code == 401
    grant = (await client.post('/api/v1/reporter/cameras/1/live/access?property_id=1', headers=headers)).json()
    assert (await client.post('/api/v1/auth/logout', headers=headers)).status_code == 204
    assert (await client.get(grant['url'])).status_code == 401


@pytest.mark.asyncio
async def test_hls_cannot_proxy_external_playlist_uri(fixture, monkeypatch):
    client, _, settings = fixture
    monkeypatch.setattr('app.api.reporter_live.get_settings', lambda: settings)
    upstream(monkeypatch, lambda request: httpx.Response(200, text='#EXTM3U\nhttps://external.example/steal\n'))
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    grant = (await client.post('/api/v1/reporter/cameras/1/live/access?property_id=1', headers=headers)).json()
    assert (await client.get(grant['url'])).status_code == 502


@pytest.mark.asyncio
async def test_camera_health_and_real_incident_counts(fixture, monkeypatch):
    from app.services.camera_health import _cache
    _cache.clear()
    client, _, settings = fixture
    monkeypatch.setattr('app.api.reporter.get_settings', lambda: settings)
    upstream(monkeypatch, lambda request: httpx.Response(200, json={'cameras': {'private_1': {'camera_fps': 5}}}))
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    cameras = (await client.get('/api/v1/reporter/cameras?property_id=1', headers=headers)).json()
    assert cameras[0]['connection_status'] == 'online'
    summary = (await client.get('/api/v1/reporter/summary?property_id=1', headers=headers)).json()
    assert summary['connected_camera_count'] == 1 and summary['active_incident_count'] == 0
    assert summary['security_status'] == 'attention_required'
    _cache.clear()


@pytest.mark.asyncio
async def test_recovery_is_generic_and_reset_revokes_only_managed_sessions(fixture, monkeypatch):
    client, factory, settings = fixture
    settings.neon_auth_base_url = 'https://auth.example.test/auth'
    monkeypatch.setattr('app.api.account_recovery.get_settings', lambda: settings)
    monkeypatch.setattr('app.api.account_recovery.limiter', SlidingWindowRateLimiter(100))
    service = SimpleNamespace(public_operation=AsyncMock(return_value={'success': True}))
    monkeypatch.setattr('app.api.account_recovery.NeonAuth', lambda: service)
    async with factory() as session:
        session.add(User(id=3, subject='neon:managed', email='managed@example.test', display_name='Managed'))
        await session.flush()
        session.add(UserDeviceToken(user_id=3, device_id='test', push_token='ExpoPushToken[test]', provider='expo'))
        await session.commit()
    request = await client.post('/api/v1/auth/recovery/request', json={'email': 'managed@example.test'})
    assert request.status_code == 202
    service.public_operation.side_effect = ApplicationError('INVALID_CREDENTIALS', 'Not found', 401)
    missing = await client.post('/api/v1/auth/recovery/request', json={'email': 'unknown@example.test'})
    assert missing.status_code == 202 and missing.json() == request.json()
    invalid = await client.post('/api/v1/auth/recovery/verify', json={'email': 'managed@example.test', 'code': '123456'})
    assert invalid.status_code == 400
    service.public_operation.side_effect = None
    reset = await client.post('/api/v1/auth/recovery/reset', json={'email': 'managed@example.test', 'code': '123456', 'new_password': 'Replacement-test-pass123'})
    assert reset.status_code == 200
    async with factory() as session:
        assert (await session.get(User, 3)).token_version == 1
        assert (await session.get(User, 1)).token_version == 0
        from sqlalchemy import select
        assert not (await session.scalar(select(UserDeviceToken).where(UserDeviceToken.user_id == 3))).active


@pytest.mark.asyncio
async def test_recovery_rate_limit(fixture, monkeypatch):
    client, _, settings = fixture
    settings.neon_auth_base_url = 'https://auth.example.test/auth'
    monkeypatch.setattr('app.api.account_recovery.get_settings', lambda: settings)
    monkeypatch.setattr('app.api.account_recovery.limiter', SlidingWindowRateLimiter(1))
    monkeypatch.setattr('app.api.account_recovery.NeonAuth', lambda: SimpleNamespace(public_operation=AsyncMock(return_value={})))
    assert (await client.post('/api/v1/auth/recovery/request', json={'email': 'test@example.test'})).status_code == 202
    assert (await client.post('/api/v1/auth/recovery/request', json={'email': 'test@example.test'})).status_code == 429


@pytest.mark.asyncio
async def test_push_self_test_requires_configuration_registration_and_ownership(fixture, monkeypatch):
    from app.models import NotificationOutbox
    from app.models.operations import NotificationPreference
    client, factory, settings = fixture
    monkeypatch.setattr('app.api.reporter.get_settings', lambda: settings)
    monkeypatch.setattr('app.api.reporter.push_test_limiter', SlidingWindowRateLimiter(100))
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    assert (await client.post('/api/v1/reporter/notifications/test?property_id=1', headers=headers)).status_code == 503
    settings.dispatch_notification_provider = 'expo'
    assert (await client.post('/api/v1/reporter/notifications/test?property_id=1', headers=headers)).status_code == 409
    async with factory() as session:
        session.add(NotificationPreference(user_id=1, category='INCIDENT_UPDATES', enabled=True))
        session.add(UserDeviceToken(user_id=1, device_id='self-test', provider='expo', push_token='ExpoPushToken[test-device]'))
        await session.commit()
    queued = await client.post('/api/v1/reporter/notifications/test?property_id=1', headers=headers)
    assert queued.status_code == 202
    path = f"/api/v1/reporter/notifications/test/{queued.json()['id']}"
    assert (await client.get(path, headers=headers)).json()['status'] == 'PENDING'
    other = {'Authorization': 'Bearer ' + await sign_in(client, 'reporter@example.test')}
    assert (await client.get(path, headers=other)).status_code == 404


@pytest.mark.asyncio
async def test_hls_grant_cannot_outlive_parent_session(fixture, monkeypatch):
    import jwt
    from datetime import datetime, timedelta, timezone
    client, _, settings = fixture
    monkeypatch.setattr('app.api.reporter_live.get_settings', lambda: settings)
    expires = int((datetime.now(timezone.utc) + timedelta(seconds=30)).timestamp())
    token = jwt.encode({'sub': 'reporter:1', 'scope': 'reporter:read', 'ver': 0, 'exp': expires,
        'iss': settings.jwt_issuer}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    grant = await client.post('/api/v1/reporter/cameras/1/live/access?property_id=1', headers={'Authorization': 'Bearer ' + token})
    assert grant.status_code == 200
    query = parse_qs(urlsplit(grant.json()['url']).query)
    claims = jwt.decode(query['grant'][0], settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience='reporter-live')
    assert claims['exp'] <= expires
