"""Two simultaneous acceptances must produce one winner on actual PostgreSQL."""
import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from app.core.exceptions import ApplicationError
from app.models import Assignment, MarshalAvailability, MarshalProfile, Property, PropertyMembership, ReporterIncident, User
from app.services.dispatch_service import DispatchService
from tests.integration.test_postgres_domain import database, postgres_schema

pytestmark = pytest.mark.skipif(os.getenv('RUN_POSTGRES_TESTS') != '1', reason='Requires disposable PostgreSQL schema')


async def test_concurrent_broadcast_acceptance_has_exactly_one_winner(database):
    marker = uuid4().hex
    async with database() as session:
        property_record = Property(slug=marker, name='Broadcast race test')
        users = [User(subject=f'{marker}:{i}', active=True) for i in range(2)]
        session.add_all([property_record, *users]); await session.flush()
        profiles = [MarshalProfile(user_id=u.id, property_id=property_record.id, capacity=1, verification_status='APPROVED') for u in users]
        session.add_all(profiles); await session.flush()
        for user, profile in zip(users, profiles):
            session.add(PropertyMembership(user_id=user.id, property_id=property_record.id, role='marshal'))
            session.add(MarshalAvailability(marshal_profile_id=profile.id, on_duty=True, available=True, updated_at=datetime.now(timezone.utc)))
        incident = ReporterIncident(property_id=property_record.id, reporter_user_id=users[0].id, incident_type='TEST', status='RECEIVED', idempotency_key=marker)
        session.add(incident); await session.flush()
        service = DispatchService(session)
        offers = [await service.create_offer(property_id=property_record.id, reporter_incident_id=incident.id,
                  marshal_profile_id=p.id, expires_in_seconds=300, idempotency_key=f'{marker}:{p.id}', actor_subject='test', broadcast=True) for p in profiles]
        await session.commit()
        ids = [item.id for item in offers]; user_ids = [item.id for item in users]
    async def accept(offer_id, user_id):
        async with database() as session:
            try:
                await DispatchService(session).respond(offer_id=offer_id, user_id=user_id, accept=True, expected_version=1, actor_subject=f'marshal:{user_id}')
                await session.commit(); return 'ACCEPTED'
            except ApplicationError as error:
                await session.rollback(); return error.code
    results = await asyncio.gather(*(accept(id, user) for id, user in zip(ids, user_ids)))
    assert sorted(results) == ['ACCEPTED', 'OFFER_CONFLICT']
    async with database() as session:
        states = (await session.scalars(select(Assignment.status).where(Assignment.id.in_(ids)))).all()
        assert sorted(states) == ['ACCEPTED', 'CANCELLED']
