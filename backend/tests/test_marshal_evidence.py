from datetime import datetime, timezone

import pytest
from app.core.config import Settings
from app.models import Assignment, Evidence, ReporterIncidentEvidence
from app.services.dispatch_service import DispatchService
from tests.test_dispatch import factory
from tests.test_marshal import make_client


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['camera', 'reporter'])
async def test_assignment_evidence_binding_and_revocation(factory, tmp_path, monkeypatch, source):
    photo = tmp_path / 'incident.jpg'
    photo.write_bytes(b'\xff\xd8isolated-test-photo')
    settings = Settings(jwt_secret='marshal-evidence-test-secret-with-32-characters', evidence_root=str(tmp_path))
    monkeypatch.setattr('app.api.marshal.get_settings', lambda: settings)
    monkeypatch.setattr('app.api.evidence.get_settings', lambda: settings)
    async with factory() as session:
        if source == 'camera':
            record = Evidence(event_id=1, type='SNAPSHOT', file_path='incident.jpg', timestamp=datetime.now(timezone.utc))
        else:
            record = ReporterIncidentEvidence(incident_id=1, media_type='image/jpeg', file_path='incident.jpg', original_filename='incident.jpg', byte_size=photo.stat().st_size)
        session.add(record); await session.flush()
        offer = await DispatchService(session).create_offer(property_id=1, marshal_profile_id=1,
                    incident_id=1 if source == 'camera' else None,
                    reporter_incident_id=1 if source == 'reporter' else None,
                    expires_in_seconds=300, idempotency_key='photo-test-assignment', actor_subject='owner:3')
        await session.commit()
        offer_id, evidence_id = offer.id, record.id
    path = f'/api/v1/marshal/assignments/{offer_id}/evidence/{evidence_id}'
    async with await make_client(factory, 1) as client:
        detail = (await client.get(f'/api/v1/marshal/assignments/{offer_id}')).json()
        assert detail['evidence'][0]['id'] == evidence_id
        assert 'file_path' not in detail['evidence'][0]
        grant = await client.post(path + '/access')
        assert grant.status_code == 200, grant.text
        url = grant.json()['url']
        content = await client.get(url)
        assert content.status_code == 200 and content.content == photo.read_bytes()
        assert content.headers['cache-control'] == 'no-store'
        assert (await client.post(path.replace(f'/evidence/{evidence_id}', '/evidence/999') + '/access')).status_code == 404
    async with await make_client(factory, 2) as client:
        assert (await client.post(path + '/access')).status_code == 404
        assert (await client.get(url)).status_code == 401
    async with factory() as session:
        offer = await session.get(Assignment, offer_id); offer.status = 'CANCELLED'
        await session.commit()
    async with await make_client(factory, 1) as client:
        assert (await client.get(url)).status_code == 404
        assert (await client.post(path + '/access')).status_code == 404
