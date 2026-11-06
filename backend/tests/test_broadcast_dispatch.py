from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from app.core.exceptions import ApplicationError
from app.models import Assignment, PropertyMembership, User
from app.services.dispatch_service import DispatchService
from tests.test_dispatch import factory
from tests.test_marshal import make_client


@pytest.mark.asyncio
async def test_broadcast_first_accept_wins_and_replay_is_idempotent(factory):
    async with factory() as session:
        session.add(User(id=3, subject='owner-test', active=True))
        await session.flush()
        session.add(PropertyMembership(user_id=3, property_id=1, role='owner'))
        await session.commit()
    body = {'property_id': 1, 'incident_id': 1, 'marshal_profile_ids': [1, 2], 'idempotency_key': 'broadcast-test-request'}
    async with await make_client(factory, 3) as client:
        response = await client.post('/api/v1/dispatch/offers/broadcast', json=body)
        assert response.status_code == 201, response.text
        offers = response.json()
        assert len(offers) == 2
        assert all((datetime.fromisoformat(item['expires_at']) - datetime.fromisoformat(item['offered_at'])).total_seconds() == 300 for item in offers)
        replay = await client.post('/api/v1/dispatch/offers/broadcast', json=body)
        assert [item['id'] for item in replay.json()] == [item['id'] for item in offers]
        assert (await client.post('/api/v1/dispatch/offers/broadcast', json={**body, 'marshal_profile_ids': [1]})).status_code == 409
        assert (await client.post('/api/v1/dispatch/offers/broadcast', json={**body, 'expires_in_seconds': 3600})).status_code == 422
    async with await make_client(factory, 2) as client:
        assert (await client.post(f"/api/v1/dispatch/offers/{offers[1]['id']}/accept", json={'expected_version': 1})).status_code == 200
    async with await make_client(factory, 1) as client:
        assert (await client.post(f"/api/v1/dispatch/offers/{offers[0]['id']}/accept", json={'expected_version': 1})).status_code == 409
    async with factory() as session:
        states = (await session.scalars(select(Assignment).order_by(Assignment.id))).all()
        assert [item.status for item in states] == ['CANCELLED', 'ACCEPTED']
    async with await make_client(factory, 3) as client:
        current = (await client.get('/api/v1/dispatch/assignment?property_id=1&incident_id=1')).json()
        assert current['id'] == offers[1]['id']


@pytest.mark.asyncio
async def test_decline_one_offer_preserves_other_offer(factory):
    async with factory() as session:
        service = DispatchService(session)
        offers = [await service.create_offer(incident_id=1, property_id=1, marshal_profile_id=id,
                    expires_in_seconds=300, idempotency_key=f'broadcast-decline-{id}', actor_subject='owner:3', broadcast=True) for id in [1, 2]]
        await session.commit()
        await service.respond(offer_id=offers[0].id, user_id=1, accept=False, expected_version=1, actor_subject='marshal:1')
        await session.commit()
        await session.refresh(offers[1])
        assert offers[1].status == 'OFFERED'
        assert await session.scalar(select(Assignment.id).where(Assignment.status == 'ACCEPTED')) is None


@pytest.mark.asyncio
async def test_batch_rolls_back_if_any_marshal_is_ineligible(factory):
    async with factory() as session:
        session.add(User(id=3, subject='owner-test', active=True))
        await session.flush()
        session.add(PropertyMembership(user_id=3, property_id=1, role='owner'))
        await session.commit()
    async with await make_client(factory, 3) as client:
        response = await client.post('/api/v1/dispatch/offers/broadcast', json={'property_id': 1, 'reporter_incident_id': 1, 'marshal_profile_ids': [1, 999], 'idempotency_key': 'broadcast-atomic-test'})
        assert response.status_code == 409
    async with factory() as session:
        assert (await session.scalars(select(Assignment))).all() == []
