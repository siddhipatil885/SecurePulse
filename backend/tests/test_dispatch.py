"""SQL-backed dispatch transaction and state-machine tests."""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ApplicationError
from app.database.base import Base
from app.models import (Assignment, AssignmentEvent, Camera, MarshalAvailability, MarshalProfile,
    NotificationAttempt, NotificationOutbox, Property, PropertyMembership, SecurityEvent, User)
from app.repositories.dispatch import OutboxRepository
from app.services.dispatch_service import DispatchService


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add_all([
            Property(id=1, slug="property", name="Property"),
            User(id=1, subject="marshal:1", email="marshal@example.test", display_name="Marshal"),
            Camera(id=1, property_id=1, name="Camera", frigate_camera_name="camera", enabled=True),
        ])
        await session.flush()
        profile = MarshalProfile(id=1, user_id=1, property_id=1, service_area="North", capacity=1)
        session.add_all([PropertyMembership(user_id=1, property_id=1, role="marshal"), profile,
            MarshalAvailability(marshal_profile_id=1, on_duty=True, available=True,
                updated_at=datetime.now(timezone.utc)),
            SecurityEvent(id=1, property_id=1, camera_id=1, event_type="INTRUSION", object_type="person",
                confidence=.9, timestamp=datetime.now(timezone.utc), severity="HIGH", status="OPEN",
                event_metadata={})])
        await session.commit()
    yield sessions
    await engine.dispose()


@pytest.mark.asyncio
async def test_offer_history_and_outbox_are_created_together(factory):
    async with factory() as session:
        offer = await DispatchService(session).create_offer(incident_id=1, property_id=1, marshal_profile_id=1,
            expires_in_seconds=60, idempotency_key="request-0001", actor_subject="dispatcher:1")
        await session.commit()
        assert offer.status == "OFFERED"
        assert await session.scalar(select(func.count(AssignmentEvent.id))) == 1
        outbox = await session.scalar(select(NotificationOutbox))
        assert outbox and outbox.kind == "ASSIGNMENT_OFFERED"


@pytest.mark.asyncio
async def test_idempotency_and_one_active_offer(factory):
    async with factory() as session:
        service = DispatchService(session)
        first = await service.create_offer(incident_id=1, property_id=1, marshal_profile_id=1,
            expires_in_seconds=60, idempotency_key="request-0001", actor_subject="dispatcher:1")
        await session.commit()
        same = await service.create_offer(incident_id=1, property_id=1, marshal_profile_id=1,
            expires_in_seconds=60, idempotency_key="request-0001", actor_subject="dispatcher:1")
        assert same.id == first.id
        with pytest.raises(ApplicationError) as error:
            await service.create_offer(incident_id=1, property_id=1, marshal_profile_id=1,
                expires_in_seconds=60, idempotency_key="request-0002", actor_subject="dispatcher:1")
        assert error.value.code == "ACTIVE_ASSIGNMENT_EXISTS"


@pytest.mark.asyncio
async def test_compare_and_swap_accept_and_capacity(factory):
    async with factory() as session:
        service = DispatchService(session)
        offer = await service.create_offer(incident_id=1, property_id=1, marshal_profile_id=1,
            expires_in_seconds=60, idempotency_key="request-0001", actor_subject="dispatcher:1")
        await session.commit()
        accepted = await service.respond(offer_id=offer.id, user_id=1, accept=True,
            expected_version=1, actor_subject="marshal:1")
        await session.commit()
        assert (accepted.status, accepted.version) == ("ACCEPTED", 2)
        with pytest.raises(ApplicationError) as error:
            await service.respond(offer_id=offer.id, user_id=1, accept=True,
                expected_version=1, actor_subject="marshal:1")
        assert error.value.code == "OFFER_CONFLICT"


@pytest.mark.asyncio
async def test_timeout_creates_history_and_escalation(factory):
    async with factory() as session:
        offer = Assignment(security_event_id=1, property_id=1, marshal_profile_id=1, status="OFFERED",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1), idempotency_key="request-expired")
        session.add(offer)
        await session.commit()
        expired = await DispatchService(session).expire(offer_id=offer.id, actor_subject="worker:timeout")
        await session.commit()
        assert expired.status == "EXPIRED"
        events = set((await session.scalars(select(NotificationOutbox.kind))).all())
        assert "DISPATCH_ESCALATION_REQUIRED" in events


@pytest.mark.asyncio
async def test_outbox_claim_and_attempt_receipt(factory):
    async with factory() as session:
        offer = await DispatchService(session).create_offer(incident_id=1, property_id=1, marshal_profile_id=1,
            expires_in_seconds=60, idempotency_key="request-0001", actor_subject="dispatcher:1")
        await session.commit()
        repository = OutboxRepository(session)
        claimed = await repository.claim_batch("worker-1", datetime.now(timezone.utc))
        assert len(claimed) == 1 and claimed[0].status == "PROCESSING"
        await repository.record_attempt(claimed[0].id, provider="test", result="DELIVERED",
            provider_reference="provider-1", now=datetime.now(timezone.utc))
        await session.commit()
        receipt = await session.scalar(select(NotificationAttempt))
        assert receipt and receipt.attempt_number == 1
