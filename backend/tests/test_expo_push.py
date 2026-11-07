from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from sqlalchemy import select

from app.models import NotificationAttempt, NotificationOutbox, PropertyMembership
from app.models.operations import NotificationPreference, UserDeviceToken
from app.services.expo_push import ExpoPushWorker
from tests.test_dispatch import factory


async def seed(factory, enabled=True):
    async with factory() as session:
        session.add(UserDeviceToken(id=1, user_id=1, device_id='test-device', provider='expo', push_token='ExpoPushToken[test-device]'))
        session.add(NotificationPreference(user_id=1, category='INCIDENT_UPDATES', enabled=enabled))
        row = NotificationOutbox(property_id=1, kind='CASE_STATUS_CHANGED', destination='reporter:1',
            payload={'reporter_incident_id': 1}, dedupe_key='test-notification')
        session.add(row); await session.commit()
        return row.id


async def due(factory, row_id):
    async with factory() as session:
        row = await session.get(NotificationOutbox, row_id)
        row.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()


@pytest.mark.asyncio
async def test_ticket_waits_for_receipt_without_duplicate_send(factory):
    row_id = await seed(factory)
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/send'):
            data = json.loads(request.content)
            assert data[0]['data']['user_id'] == 1 and data[0]['data']['kind'] == 'reporter_incident'
            assert 'address' not in request.content.decode()
            return httpx.Response(200, json={'data': [{'status': 'ok', 'id': 'ticket-1'}]})
        return httpx.Response(200, json={'data': {'ticket-1': {'status': 'ok'}}})
    worker = ExpoPushWorker(factory, transport=httpx.MockTransport(handler))
    await worker.run_once()
    async with factory() as session:
        row = await session.get(NotificationOutbox, row_id)
        assert row.status == 'PENDING' and row.sent_at is None
    await due(factory, row_id); await worker.run_once()
    async with factory() as session:
        assert (await session.get(NotificationOutbox, row_id)).status == 'SENT'
        receipt = await session.scalar(select(NotificationAttempt))
        assert 'ExpoPushToken' not in str(receipt.response_metadata)
    assert sum(p.endswith('/send') for p in calls) == 1


@pytest.mark.asyncio
async def test_opt_out_and_revoked_membership_prevent_delivery(factory):
    row_id = await seed(factory, enabled=False)
    worker = ExpoPushWorker(factory, transport=httpx.MockTransport(lambda request: pytest.fail('Unexpected push')))
    await worker.run_once()
    async with factory() as session:
        assert (await session.get(NotificationOutbox, row_id)).status == 'SKIPPED'


@pytest.mark.asyncio
async def test_revocation_after_ticket_prevents_more_provider_requests(factory):
    row_id = await seed(factory)
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={'data': [{'status': 'ok', 'id': 'ticket-1'}]})
    worker = ExpoPushWorker(factory, transport=httpx.MockTransport(handler))
    await worker.run_once()
    async with factory() as session:
        membership = await session.scalar(select(PropertyMembership).where(PropertyMembership.user_id == 1))
        membership.active = False
        await session.commit()
    await due(factory, row_id); await worker.run_once()
    async with factory() as session:
        assert (await session.get(NotificationOutbox, row_id)).status == 'SKIPPED'
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_unregistered_device_is_disabled(factory):
    row_id = await seed(factory)
    worker = ExpoPushWorker(factory, transport=httpx.MockTransport(lambda request: httpx.Response(200,
        json={'data': [{'status': 'error', 'details': {'error': 'DeviceNotRegistered'}}]})))
    await worker.run_once()
    async with factory() as session:
        assert not (await session.get(UserDeviceToken, 1)).active
        assert (await session.get(NotificationOutbox, row_id)).status == 'SKIPPED'


@pytest.mark.asyncio
async def test_transient_push_failure_is_bounded(factory):
    row_id = await seed(factory)
    worker = ExpoPushWorker(factory, transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    for attempt in range(6):
        await due(factory, row_id); await worker.run_once()
    async with factory() as session:
        assert (await session.get(NotificationOutbox, row_id)).status == 'EXHAUSTED'
        from sqlalchemy import func
        assert await session.scalar(select(func.count()).select_from(NotificationAttempt)) == 5


@pytest.mark.asyncio
async def test_large_delivery_batches_preserve_successful_tickets_on_partial_failure(factory):
    row_id = await seed(factory)
    async with factory() as session:
        session.add_all([UserDeviceToken(user_id=1, device_id=f'device-{i}', provider='expo',
            push_token=f'ExpoPushToken[device-{i}]') for i in range(204)])
        await session.commit()
    sends = []
    fail_once = True
    def handler(request):
        nonlocal fail_once
        body = json.loads(request.content)
        if request.url.path.endswith('/getReceipts'):
            return httpx.Response(200, json={'data': {key: {'status': 'ok'} for key in body['ids']}})
        sends.append([item['to'] for item in body])
        assert len(body) <= 100
        if len(sends) == 2 and fail_once:
            fail_once = False
            return httpx.Response(503)
        return httpx.Response(200, json={'data': [{'status': 'ok', 'id': item['to']} for item in body]})
    worker = ExpoPushWorker(factory, transport=httpx.MockTransport(handler))
    await worker.run_once()
    await due(factory, row_id); await worker.run_once()
    assert [len(batch) for batch in sends] == [100, 100, 100, 5]
    assert set(sends[0]).isdisjoint(set(sends[2] + sends[3]))
    await due(factory, row_id); await worker.run_once()
    async with factory() as session:
        assert (await session.get(NotificationOutbox, row_id)).status == 'SENT'


@pytest.mark.asyncio
async def test_expo_and_external_workers_claim_disjoint_destinations(factory):
    from app.services.dispatch_workers import ExternalAlertDispatcher, RecordingFakeProvider
    row_id = await seed(factory)
    async with factory() as session:
        external = NotificationOutbox(property_id=1, kind='INCIDENT_EXTERNAL_ALERT',
            destination='sms:+15550010', dedupe_key='external-only')
        session.add(external); await session.commit(); external_id = external.id
    worker = ExpoPushWorker(factory, transport=httpx.MockTransport(lambda request: httpx.Response(200,
        json={'data': [{'status': 'ok', 'id': 'ticket'}]})))
    assert await worker.run_once() == 1
    assert await ExternalAlertDispatcher(factory, RecordingFakeProvider()).run_once() == 1
    async with factory() as session:
        assert (await session.get(NotificationOutbox, row_id)).status == 'PENDING'
        assert (await session.get(NotificationOutbox, external_id)).status == 'SENT'
