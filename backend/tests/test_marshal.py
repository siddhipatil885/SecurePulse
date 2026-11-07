import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.marshal import router
from app.api.marshal_onboarding import router as onboarding_router
from app.api.dispatch import router as dispatch_router
from app.core.dependencies import get_session
from app.core.exceptions import register_exception_handlers
from app.core.reporter_auth import get_reporter
from app.models import Assignment, AssignmentEvent, MarshalProfile, PropertyMembership, User
from app.services.dispatch_service import DispatchService
from tests.test_dispatch import factory


async def make_client(factory, user_id):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix='/api/v1')
    app.include_router(onboarding_router, prefix='/api/v1')
    app.include_router(dispatch_router, prefix='/api/v1')
    async def session_dependency():
        async with factory() as session:
            yield session
    async def user_dependency():
        async with factory() as session:
            return await session.get(User, user_id)
    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[get_reporter] = user_dependency
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


async def offer(factory):
    async with factory() as session:
        item = await DispatchService(session).create_offer(incident_id=1,
            property_id=1, marshal_profile_id=1, expires_in_seconds=60,
            idempotency_key='marshal-workspace-test', actor_subject='dispatcher:1')
        await session.commit()
        return item.id


@pytest.mark.asyncio
async def test_workspace_and_assignment_isolation(factory):
    assignment_id = await offer(factory)
    async with await make_client(factory, 1) as client:
        assert (await client.get('/api/v1/marshal/workspace')).json()['on_duty'] is True
        items = (await client.get('/api/v1/marshal/assignments')).json()['items']
        assert [item['id'] for item in items] == [assignment_id]
        assert items[0]['incident_type'] == 'INTRUSION'
        assert (await client.get(f'/api/v1/marshal/assignments/{assignment_id}')).status_code == 200
    async with await make_client(factory, 2) as client:
        assert (await client.get('/api/v1/marshal/assignments')).json()['items'] == []
        assert (await client.get(f'/api/v1/marshal/assignments/{assignment_id}')).status_code == 404
        assert (await client.post(f'/api/v1/marshal/assignments/{assignment_id}/notes', json={'text': 'Other marshal', 'expected_version': 1})).status_code == 404


@pytest.mark.asyncio
async def test_revoked_or_non_marshal_membership_blocks_workspace(factory):
    async with factory() as session:
        membership = await session.scalar(select(PropertyMembership).where(PropertyMembership.user_id == 1))
        membership.role = 'owner'
        await session.commit()
    async with await make_client(factory, 1) as client:
        assert (await client.get('/api/v1/marshal/workspace')).status_code == 403
        assert (await client.get('/api/v1/marshal/assignments')).status_code == 403
    async with factory() as session:
        membership = await session.scalar(select(PropertyMembership).where(PropertyMembership.user_id == 1))
        membership.role = 'marshal'
        membership.active = False
        await session.commit()
    async with await make_client(factory, 1) as client:
        assert (await client.get('/api/v1/marshal/workspace')).status_code == 403


@pytest.mark.asyncio
async def test_progress_notes_conflicts_and_history(factory):
    assignment_id = await offer(factory)
    async with await make_client(factory, 1) as client:
        path = f'/api/v1/marshal/assignments/{assignment_id}'
        assert (await client.post(path + '/notes', json={'text': 'Before accepting', 'expected_version': 1})).status_code == 409
        version = 1
        for action, status in [('accept', None), ('progress', 'EN_ROUTE'), ('progress', 'ON_SCENE')]:
            response = await client.post(f'/api/v1/dispatch/offers/{assignment_id}/{action}', json={'expected_version': version, **({'status': status} if status else {})})
            assert response.status_code == 200, response.text
            version = response.json()['version']
        assert (await client.post(path + '/notes', json={'text': '  ', 'expected_version': version})).status_code == 422
        assert (await client.post(path + '/notes', json={'text': 'Stale', 'expected_version': 1})).status_code == 409
        assert (await client.post(path + '/notes', json={'text': 'Investigated entrance. No ongoing threat.', 'expected_version': version})).status_code == 201
        detail = (await client.get(path)).json()
        assert detail['timeline'][-1]['note'] == 'Investigated entrance. No ongoing threat.'
        assert (await client.post(f'/api/v1/dispatch/offers/{assignment_id}/progress', json={'expected_version': version, 'status': 'COMPLETED'})).status_code == 200
        assert (await client.get('/api/v1/marshal/assignments')).json()['items'] == []
        assert (await client.get('/api/v1/marshal/assignments?history=true')).json()['items'][0]['status'] == 'COMPLETED'
        assert (await client.post(path + '/notes', json={'text': 'After completion', 'expected_version': version + 1})).status_code == 409
