import io
import json
from datetime import date

from cryptography.fernet import Fernet
from PIL import Image
import pytest
from sqlalchemy import select
from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.models import MarshalOnboarding, MarshalProfile, PropertyMembership
from app.review_marshal import review
from app.services.dispatch_service import DispatchService
from app.services.marshal_identity import IdentityDetails, IdentityVault
from tests.test_dispatch import factory
from tests.test_marshal import make_client


DETAILS = {'legal_name': 'Example Responder', 'date_of_birth': '1995-03-14', 'phone': '+919876543210',
    'address': '123 Example Lane, Test City', 'id_type': 'PASSPORT', 'id_number': 'X1234567',
    'emergency_name': 'Example Contact', 'emergency_phone': '+919876543211', 'emergency_relationship': 'spouse',
    'consent': True, 'emergency_contact_informed': True}


def photo():
    output = io.BytesIO(); Image.new('RGB', (600, 600), 'white').save(output, format='JPEG')
    return output.getvalue()


def files():
    return {'portrait': ('face.jpg', photo(), 'image/jpeg'), 'id_front': ('id.jpg', photo(), 'image/jpeg')}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    value = Settings(marshal_identity_key=Fernet.generate_key().decode(), marshal_identity_root=str(tmp_path / 'identity'), marshal_identity_insecure_test_mode=True)
    monkeypatch.setattr('app.api.marshal_onboarding.get_settings', lambda: value)
    monkeypatch.setattr('app.api.marshal_onboarding.limiter', SlidingWindowRateLimiter(100))
    return value


async def require_onboarding(factory):
    async with factory() as session:
        profile = await session.get(MarshalProfile, 1); profile.verification_status = 'REQUIRED'
        await session.commit()


@pytest.mark.asyncio
async def test_submission_encrypts_pii_documents_and_blocks_duty(factory, settings):
    await require_onboarding(factory)
    async with await make_client(factory, 1) as client:
        response = await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(DETAILS)}, files=files())
        assert response.status_code == 201, response.text
        summary = (await client.get('/api/v1/marshal/onboarding')).json()
        assert summary['status'] == 'PENDING' and summary['id_last_four'] == '4567'
        assert DETAILS['phone'] not in json.dumps(summary)
        assert (await client.put('/api/v1/dispatch/marshal/availability', json={'property_id': 1, 'on_duty': True, 'available': True})).status_code == 403
        assert (await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(DETAILS)}, files=files())).status_code == 409
        content = await client.get('/api/v1/marshal/onboarding/documents/portrait')
        assert content.status_code == 200 and content.headers['cache-control'] == 'no-store'
    async with factory() as session:
        record = await session.get(MarshalOnboarding, 1)
        assert DETAILS['id_number'].encode() not in record.encrypted_details
        assert IdentityVault(settings).details(record.encrypted_details)['phone'] == DETAILS['phone']
        for name in record.documents.values():
            raw = (IdentityVault(settings).root / name).read_bytes()
            assert not raw.startswith(b'\xff\xd8')
    # A different marshal cannot retrieve somebody else's portrait by ID or path.
    async with await make_client(factory, 2) as client:
        assert (await client.get('/api/v1/marshal/onboarding/documents/portrait')).status_code == 404


@pytest.mark.asyncio
async def test_incomplete_or_unsafe_submissions_are_rejected(factory, settings):
    await require_onboarding(factory)
    async with await make_client(factory, 1) as client:
        for invalid in [{**DETAILS, 'consent': False}, {**DETAILS, 'emergency_phone': DETAILS['phone']},
                        {**DETAILS, 'date_of_birth': date.today().isoformat()}, {**DETAILS, 'id_number': '123456789012'},
                        {**DETAILS, 'id_number': '1234-5678-9012'}]:
            result = await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(invalid)}, files=files())
            assert result.status_code == 422
            assert invalid['id_number'] not in result.text
        bad_files = {'portrait': ('face.jpg', b'not-an-image', 'image/jpeg'), 'id_front': files()['id_front']}
        assert (await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(DETAILS)}, files=bad_files)).status_code == 422
        assert (await client.get('/api/v1/marshal/onboarding')).json()['status'] == 'REQUIRED'


@pytest.mark.asyncio
async def test_review_requires_checks_and_withdrawal_removes_documents(factory, settings, monkeypatch):
    await require_onboarding(factory)
    async with await make_client(factory, 1) as client:
        assert (await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(DETAILS)}, files=files())).status_code == 201
    monkeypatch.setattr('app.review_marshal.get_session_factory', lambda: factory)
    with pytest.raises(ValueError):
        await review(1, 'APPROVED', 'test-reviewer', 'Checked documents')
    await review(1, 'APPROVED', 'test-reviewer', 'ID, portrait and emergency contact reviewed.', True)
    async with await make_client(factory, 1) as client:
        assert (await client.put('/api/v1/dispatch/marshal/availability', json={'property_id': 1, 'on_duty': True, 'available': True})).status_code == 200
        assert (await client.delete('/api/v1/marshal/onboarding')).status_code == 204
        assert (await client.get('/api/v1/marshal/onboarding')).json()['status'] == 'REQUIRED'
    assert list(IdentityVault(settings).root.iterdir()) == []
    async with factory() as session:
        assert await session.get(MarshalOnboarding, 1) is None


@pytest.mark.asyncio
async def test_pending_marshals_are_not_dispatchable_even_with_stale_duty_flags(factory):
    await require_onboarding(factory)
    async with factory() as session:
        from app.repositories.dispatch import DispatchRepository
        from datetime import datetime, timedelta, timezone
        eligible = await DispatchRepository(session).eligible_marshals(1, datetime.now(timezone.utc) - timedelta(minutes=5))
        assert [item.id for item in eligible] == [2]
        from app.core.exceptions import ApplicationError
        with pytest.raises(ApplicationError):
            await DispatchService(session).create_offer(incident_id=1, property_id=1, marshal_profile_id=1,
                expires_in_seconds=300, idempotency_key='unreviewed-dispatch-test', actor_subject='owner:3')


@pytest.mark.asyncio
async def test_identity_upload_requires_https_and_production_disallows_http_exception(factory, settings):
    await require_onboarding(factory)
    settings.marshal_identity_insecure_test_mode = False
    async with await make_client(factory, 1) as client:
        response = await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(DETAILS)}, files=files())
        assert response.status_code == 426
        assert (await client.get('/api/v1/marshal/onboarding/documents/portrait')).status_code == 426
        settings.app_env = 'production'; settings.marshal_identity_insecure_test_mode = True
        assert (await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(DETAILS)}, files=files())).status_code == 426
    assert not IdentityVault(settings).root.exists()


@pytest.mark.asyncio
async def test_admin_export_audits_before_writing_and_removes_partial_exports(factory, settings, monkeypatch, tmp_path):
    import os
    from pathlib import Path
    from types import SimpleNamespace
    from app.models import AuditRecord
    from app.review_marshal import run
    await require_onboarding(factory)
    async with await make_client(factory, 1) as client:
        assert (await client.post('/api/v1/marshal/onboarding', data={'details': json.dumps(DETAILS)}, files=files())).status_code == 201
    monkeypatch.setattr('app.review_marshal.get_session_factory', lambda: factory)
    monkeypatch.setattr('app.review_marshal.get_settings', lambda: settings)
    folder = tmp_path / 'export'
    args = SimpleNamespace(approve=None, reject=None, inspect=1, reviewer='test-reviewer', output_dir=str(folder))
    original = os.open
    def fail_photo(path, *args, **kwargs):
        if Path(path).name == 'portrait.jpg':
            assert (folder / 'details.json').exists()
            raise OSError('Injected write failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', fail_photo)
    with pytest.raises(OSError):
        await run(args)
    assert not folder.exists()
    async with factory() as session:
        attempt = await session.scalar(select(AuditRecord).where(AuditRecord.action == 'MARSHAL_IDENTITY_ADMIN_EXPORT'))
        assert attempt.details == {'status': 'STARTED'}
    monkeypatch.setattr(os, 'open', original)
    await run(args)
    assert (folder / 'portrait.jpg').exists()
    async with factory() as session:
        rows = (await session.scalars(select(AuditRecord).where(AuditRecord.action == 'MARSHAL_IDENTITY_ADMIN_EXPORT').order_by(AuditRecord.id))).all()
        assert [row.details['status'] for row in rows] == ['STARTED', 'COMPLETED']


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expired,expected', [('OFFERED', True, 204), ('OFFERED', False, 409), ('ACCEPTED', True, 409)])
async def test_withdrawal_uses_offer_deadlines_but_keeps_accepted_work_blocked(factory, settings, status, expired, expected):
    from datetime import datetime, timedelta, timezone
    from app.models import Assignment
    async with factory() as session:
        session.add(Assignment(property_id=1, security_event_id=1, marshal_profile_id=1, status=status,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 1), idempotency_key='withdrawal-offer'))
        await session.commit()
    async with await make_client(factory, 1) as client:
        assert (await client.delete('/api/v1/marshal/onboarding')).status_code == expected
