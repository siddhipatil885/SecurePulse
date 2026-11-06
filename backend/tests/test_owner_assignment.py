from datetime import datetime, timezone

import pytest
from app.models import MarshalAvailability, MarshalProfile, PropertyMembership, User
from tests.test_reporter import fixture, sign_in


@pytest.mark.asyncio
async def test_owner_can_find_named_marshal_offer_and_read_status(fixture):
    client, factory, _ = fixture
    async with factory() as session:
        session.add(User(id=3, subject='marshal-test', display_name='Marshal Test', active=True))
        await session.flush()
        session.add(PropertyMembership(user_id=3, property_id=1, role='marshal'))
        session.add(MarshalProfile(id=1, user_id=3, property_id=1, capacity=1, verification_status='APPROVED'))
        await session.flush()
        session.add(MarshalAvailability(marshal_profile_id=1, on_duty=True, available=True, updated_at=datetime.now(timezone.utc)))
        await session.commit()
    headers = {'Authorization': 'Bearer ' + await sign_in(client)}
    candidates = await client.get('/api/v1/dispatch/eligible-marshals?property_id=1', headers=headers)
    assert candidates.status_code == 200
    assert candidates.json()[0]['name'] == 'Marshal Test'
    assert (await client.get('/api/v1/dispatch/assignment?property_id=1&incident_id=1', headers=headers)).json() is None
    result = await client.post('/api/v1/dispatch/offers', headers=headers, json={'property_id': 1, 'incident_id': 1, 'marshal_profile_id': 1, 'expires_in_seconds': 300, 'idempotency_key': 'owner-app-offer-test'})
    assert result.status_code == 201, result.text
    current = await client.get('/api/v1/dispatch/assignment?property_id=1&incident_id=1', headers=headers)
    assert current.json()['id'] == result.json()['id']
    assert current.json()['status'] == 'OFFERED'
    assert (await client.get('/api/v1/dispatch/assignment?property_id=1&incident_id=2', headers=headers)).status_code == 404
    assert (await client.get('/api/v1/dispatch/assignment?property_id=2&incident_id=2', headers=headers)).status_code == 403
    assert (await client.get('/api/v1/dispatch/assignment?property_id=1', headers=headers)).status_code == 422
    reporter = {'Authorization': 'Bearer ' + await sign_in(client, 'reporter@example.test')}
    assert (await client.get('/api/v1/dispatch/assignment?property_id=2&incident_id=2', headers=reporter)).status_code == 403
