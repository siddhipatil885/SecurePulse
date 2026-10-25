"""Real broker -> adapter -> PostgreSQL -> authorized HTTP/WebSocket acceptance.

Only runs in the disposable compose stack. Fake rule provider is explicit;
dispatch/notification worker is NOT simulated into an acceptance PASS.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pytest
from paho.mqtt.publish import single
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from websockets.asyncio.client import connect

from app.models import Camera, Property, SecurityEvent
from app.models.operations import SourceEventReceipt, IncidentStatusHistory
from app.database.database import _async_database_url

pytestmark = pytest.mark.skipif(os.getenv('RUN_STACK_TESTS') != '1', reason='Requires disposable Docker integration stack')


async def test_mqtt_database_rest_realtime_and_resolution():
    # Refuse accidental invocation against a developer or hosted database.
    assert os.environ['DATABASE_URL'] == 'postgresql://securepulse:test-only-password@postgres:5432/securepulse_test'
    engine = create_async_engine(_async_database_url(os.environ['DATABASE_URL']))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    marker = uuid4().hex
    async with factory() as session:
        north = Property(name='P4 North fixture', slug='north-' + marker)
        south = Property(name='P4 South fixture', slug='south-' + marker)
        session.add_all([north, south]); await session.flush()
        camera = Camera(property_id=north.id, name='North test pattern', frigate_camera_name='p4_' + marker, enabled=True)
        session.add(camera); await session.commit()
        property_id, foreign_id, camera_id, camera_name = north.id, south.id, camera.id, camera.frigate_camera_name
    token = jwt.encode({'sub': 'p4-test-operator', 'scope': 'read write', 'property_ids': [property_id],
        'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, os.environ['JWT_SECRET'], algorithm='HS256')
    foreign_token = jwt.encode({'sub': 'p4-foreign-operator', 'scope': 'read', 'property_ids': [foreign_id],
        'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, os.environ['JWT_SECRET'], algorithm='HS256')
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/person-in-zone.json').read_text())
    fixture['after'].update(id='p4-person-zone-001-' + marker, camera=camera_name)
    try:
        async with httpx.AsyncClient(base_url='http://backend:8000', headers={'Authorization': 'Bearer ' + token}) as client:
            for _ in range(60):
                try:
                    if (await client.get('/health/ready')).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
            else:
                pytest.fail('Backend/MQTT did not become ready')
            async with connect('ws://backend:8000/api/v1/events/stream', subprotocols=['securepulse.v1', 'bearer.' + token]) as socket:
                assert json.loads(await socket.recv())['type'] == 'resync_required'
                await asyncio.to_thread(single, 'frigate/events', json.dumps(fixture), hostname='mqtt', qos=1)
                while True:
                    message = json.loads(await asyncio.wait_for(socket.recv(), 20))
                    if message.get('type') == 'security_event' and message['data']['frigate_event_id'] == fixture['after']['id']:
                        break
                incident_id = message['data']['id']
                assert message['property_id'] == property_id and message['version'] == 1
                assert message['data']['severity'] == 'HIGH'
                result = await client.get('/api/v1/incidents')
                assert result.status_code == 200 and result.json()['total'] == 1
                foreign = await client.get('/api/v1/incidents', headers={'Authorization': 'Bearer ' + foreign_token})
                assert foreign.json()['total'] == 0
                assert (await client.get(f'/api/v1/incidents/{incident_id}', headers={'Authorization': 'Bearer ' + foreign_token})).status_code == 404
                for _ in range(3):
                    await asyncio.to_thread(single, 'frigate/events', json.dumps(fixture), hostname='mqtt', qos=1)
                await asyncio.sleep(1)
                async with factory() as session:
                    for model in (SecurityEvent, SourceEventReceipt):
                        assert await session.scalar(select(func.count()).select_from(model).where(model.property_id == property_id)) == 1
                for command in ('acknowledge', 'resolve'):
                    response = await client.post(f'/api/v1/incidents/{incident_id}/commands', json={
                        'command': command, 'reason': 'P4 Docker acceptance', 'correlation_id': marker + command})
                    assert response.status_code == 200
                history = (await client.get(f'/api/v1/incidents/{incident_id}/history')).json()
                assert [h['new_status'] for h in history] == ['OPEN', 'ACKNOWLEDGED', 'RESOLVED']
                assert (await client.get(f'/api/v1/incidents/{incident_id}')).json()['status'] == 'RESOLVED'
                async with factory() as session:
                    assert await session.scalar(select(func.count()).select_from(IncidentStatusHistory).where(IncidentStatusHistory.security_event_id == incident_id)) == 3
    finally:
        await engine.dispose()
