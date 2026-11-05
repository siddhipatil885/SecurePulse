"""Neon identity/session regressions and bounded local attachment behavior."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.integrations.neon_auth import NeonAuth
from app.models import User
from app.services.reporter_storage import ReporterStorage
from tests.test_reporter import fixture, sign_in


@pytest.mark.asyncio
async def test_managed_auth_keeps_signed_cookie_origin_and_clears_session(monkeypatch):
    calls = []
    original = httpx.AsyncClient
    def handler(request):
        calls.append(request)
        assert request.headers['origin'] == 'http://localhost:5173'
        if request.url.path.endswith('/sign-in/email'):
            return httpx.Response(200, json={'token': 'opaque-token'},
                headers={'set-cookie': '__Secure-neon-auth.session_token=signed-test-cookie; Path=/; Secure; HttpOnly'})
        assert '__Secure-neon-auth.session_token=signed-test-cookie' in request.headers.get('cookie', '')
        if request.url.path.endswith('/get-session'):
            return httpx.Response(200, json={'user': {'id': 'provider-id', 'email': 'test@example.test'}})
        return httpx.Response(200, json={'success': True})
    settings = Settings(_env_file=None, neon_auth_base_url='https://auth.example.test/neondb/auth',
                        cors_origins='http://localhost:5173')
    monkeypatch.setattr('app.integrations.neon_auth.get_settings', lambda: settings)
    monkeypatch.setattr('app.integrations.neon_auth.httpx.AsyncClient',
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    auth = NeonAuth()
    assert (await auth.signin('test@example.test', 'private-password'))['id'] == 'provider-id'
    assert [r.url.path.rsplit('/', 1)[-1] for r in calls] == ['email', 'get-session', 'sign-out']
    assert auth.client is None


@pytest.mark.asyncio
async def test_neon_identity_does_not_reassign_existing_account(fixture, monkeypatch):
    client, factory, settings = fixture
    async with factory() as session:
        session.add(User(id=5, subject='neon:expected-provider-id', email='neon@example.test', display_name='Neon'))
        await session.commit()
    settings.neon_auth_base_url = 'https://auth.example.test/auth'
    monkeypatch.setattr('app.api.reporter.get_settings', lambda: settings)
    neon = SimpleNamespace(signin=AsyncMock(return_value={'id': 'different-provider-id', 'email': 'neon@example.test'}))
    monkeypatch.setattr('app.api.reporter.NeonAuth', lambda: neon)
    response = await client.post('/api/v1/auth/login', json={'email': 'neon@example.test', 'password': 'password'})
    assert response.status_code == 401
    async with factory() as session:
        assert (await session.get(User, 5)).subject == 'neon:expected-provider-id'


@pytest.mark.asyncio
async def test_attachment_count_limit_preserves_idempotent_retry_and_light_history(fixture, monkeypatch, tmp_path):
    client, _, settings = fixture
    settings.evidence_root = str(tmp_path)
    settings.reporter_evidence_max_files = 1
    monkeypatch.setattr('app.api.reporter.get_settings', lambda: settings)
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    report = await client.post('/api/v1/reporter/incidents', headers=headers | {'X-Idempotency-Key': 'bounded-media-test-key'},
        json={'property_id': 1, 'incident_type': 'THEFT', 'address': 'Test location'})
    assert report.status_code == 201
    path = f"/api/v1/reporter/incidents/{report.json()['id']}/evidence"
    files = {'file': ('photo.jpg', b'\xff\xd8local-photo', 'image/jpeg')}
    upload_headers = headers | {'X-Idempotency-Key': 'bounded-upload-test-key'}
    first = await client.post(path, headers=upload_headers, files=files)
    assert first.status_code == 200
    assert (await client.post(path, headers=upload_headers, files=files)).status_code == 200
    rejected = await client.post(path, headers=headers, files=files)
    assert rejected.status_code == 413
    assert rejected.json()['error']['code'] == 'INCIDENT_STORAGE_LIMIT'
    assert len(list(tmp_path.rglob('*.jpg'))) == 1
    summary = await client.get('/api/v1/reporter/incidents?include_details=false', headers=headers)
    assert summary.status_code == 200
    item = summary.json()['items'][0]
    assert item['details_included'] is False and item['timeline'] == [] and item['evidence'] == []
    full_history = await client.get('/api/v1/reporter/incidents?include_details=true', headers=headers)
    assert len(summary.content) < len(full_history.content)
    detail = await client.get(path.rsplit('/evidence', 1)[0], headers=headers)
    assert len(detail.json()['evidence']) == 1 and len(detail.json()['timeline']) == 1


@pytest.mark.asyncio
async def test_local_upload_reserves_host_disk_space(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, evidence_storage='local', evidence_root=str(tmp_path))
    monkeypatch.setattr('app.services.reporter_storage.shutil.disk_usage', lambda path: SimpleNamespace(free=100))
    with pytest.raises(ApplicationError) as error:
        await ReporterStorage(settings).put('reporter-incidents/1/' + 'a' * 32 + '.jpg', b'photo', 'image/jpeg')
    assert error.value.status_code == 507
    assert not list(tmp_path.rglob('*.jpg'))


@pytest.mark.asyncio
async def test_large_uploads_rejected_before_reading_and_chunked_body_is_bounded(monkeypatch):
    from fastapi import FastAPI, Request
    from app.core.upload_limit import EvidenceUploadLimitMiddleware
    monkeypatch.setattr('app.core.upload_limit.get_settings', lambda: SimpleNamespace(reporter_evidence_max_bytes=10))
    app = FastAPI()
    app.add_middleware(EvidenceUploadLimitMiddleware)
    called = []
    @app.post('/api/v1/reporter/incidents/1/evidence')
    async def upload(request: Request):
        called.append(True)
        await request.body()
        return {'ok': True}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/reporter/incidents/1/evidence', headers={'Content-Length': '1000000000'}, content=b'')
        assert response.status_code == 413 and not called
        async def chunks():
            yield b'x' * 40_000
            yield b'x' * 40_000
        response = await client.post('/api/v1/reporter/incidents/1/evidence', content=chunks())
        assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize('scope', ['incident', 'property'])
async def test_attachment_byte_quotas_reject_before_writing(fixture, monkeypatch, tmp_path, scope):
    client, _, settings = fixture
    settings.evidence_root = str(tmp_path)
    if scope == 'incident':
        settings.reporter_evidence_max_incident_bytes = 1_000_000
    else:
        settings.reporter_evidence_max_property_bytes = 1_000_000
    monkeypatch.setattr('app.api.reporter.get_settings', lambda: settings)
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    paths = []
    for index in range(2 if scope == 'property' else 1):
        response = await client.post('/api/v1/reporter/incidents', headers=headers | {'X-Idempotency-Key': f'byte-quota-test-key-{index}'},
            json={'property_id': 1, 'incident_type': 'THEFT', 'address': 'Test location'})
        paths.append(f"/api/v1/reporter/incidents/{response.json()['id']}/evidence")
    files = {'file': ('photo.jpg', b'\xff\xd8' + b'x' * 600_000, 'image/jpeg')}
    assert (await client.post(paths[0], headers=headers, files=files)).status_code == 200
    rejected = await client.post(paths[-1], headers=headers, files=files)
    assert rejected.status_code == 413
    assert rejected.json()['error']['code'] == ('INCIDENT_STORAGE_LIMIT' if scope == 'incident' else 'PROPERTY_STORAGE_LIMIT')
    assert len(list(tmp_path.rglob('*.jpg'))) == 1
