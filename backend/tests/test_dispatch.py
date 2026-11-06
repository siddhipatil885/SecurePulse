"""SQL-backed dispatch transaction and state-machine tests."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ApplicationError
from app.database.base import Base
from app.domain.events import DetectionEvent as IngestDetection
from app.domain.security import SecurityContext
from app.integrations.local_security_engine import LocalSecurityEngine
from app.models import (
    Assignment,
    AssignmentEvent,
    Camera,
    MarshalAvailability,
    MarshalProfile,
    NotificationAttempt,
    NotificationOutbox,
    Property,
    PropertyMembership,
    ReporterIncident,
    SecurityEvent,
    User,
)
from app.repositories.cameras import CameraRepository
from app.repositories.dispatch import OutboxRepository
from app.repositories.events import EventRepository
from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import Point, Zone
from app.services.dispatch_service import DispatchService
from app.services.dispatch_workers import (
    DeliveryResult,
    NotificationDispatcher,
    RecordingFakeProvider,
    TimeoutEscalator,
)
from app.services.event_processor import EventProcessor


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as session:
        session.add_all(
            [
                Property(id=1, slug="property", name="Property"),
                User(
                    id=1,
                    subject="marshal:1",
                    email="marshal@example.test",
                    display_name="Marshal",
                ),
                User(
                    id=2,
                    subject="marshal:2",
                    email="marshal2@example.test",
                    display_name="Marshal 2",
                ),
                Camera(
                    id=1,
                    property_id=1,
                    name="Camera",
                    frigate_camera_name="camera",
                    enabled=True,
                ),
            ]
        )
        await session.flush()

        profile = MarshalProfile(
            verification_status='APPROVED',
            id=1,
            user_id=1,
            property_id=1,
            service_area="North",
            capacity=1,
        )
        profile2 = MarshalProfile(
            verification_status='APPROVED',
            id=2,
            user_id=2,
            property_id=1,
            service_area="South",
            capacity=1,
        )

        session.add_all(
            [
                PropertyMembership(
                    user_id=1,
                    property_id=1,
                    role="marshal",
                ),
                PropertyMembership(
                    user_id=2,
                    property_id=1,
                    role="marshal",
                ),
                profile,
                profile2,
                MarshalAvailability(
                    marshal_profile_id=1,
                    on_duty=True,
                    available=True,
                    updated_at=datetime.now(timezone.utc),
                ),
                MarshalAvailability(
                    marshal_profile_id=2,
                    on_duty=True,
                    available=True,
                    updated_at=datetime.now(timezone.utc),
                ),
                SecurityEvent(
                    id=1,
                    property_id=1,
                    camera_id=1,
                    event_type="INTRUSION",
                    object_type="person",
                    confidence=0.9,
                    timestamp=datetime.now(timezone.utc),
                    severity="HIGH",
                    status="OPEN",
                    event_metadata={},
                ),
            ]
        )
        session.add(
            ReporterIncident(
                id=1,
                reporter_user_id=1,
                property_id=1,
                incident_type="THEFT",
                address="1 Test Street",
                status="RECEIVED",
                idempotency_key="reporter-incident-1",
            )
        )
        await session.commit()

    yield sessions
    await engine.dispose()


@pytest.mark.asyncio
async def test_offer_history_and_outbox_are_created_together(factory):
    async with factory() as session:
        offer = await DispatchService(session).create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="request-0001",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        assert offer.status == "OFFERED"
        assert await session.scalar(select(func.count(AssignmentEvent.id))) == 1

        outbox = await session.scalar(select(NotificationOutbox))
        assert outbox and outbox.kind == "ASSIGNMENT_OFFERED"


@pytest.mark.asyncio
async def test_offer_can_target_reporter_incident(factory):
    async with factory() as session:
        offer = await DispatchService(session).create_offer(
            reporter_incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="reporter-offer-1",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        assert offer.reporter_incident_id == 1
        assert offer.security_event_id is None


@pytest.mark.asyncio
async def test_idempotency_and_one_active_offer(factory):
    async with factory() as session:
        service = DispatchService(session)
        first = await service.create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="request-0001",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        same = await service.create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="request-0001",
            actor_subject="dispatcher:1",
        )
        assert same.id == first.id

        with pytest.raises(ApplicationError) as error:
            await service.create_offer(
                incident_id=1,
                property_id=1,
                marshal_profile_id=1,
                expires_in_seconds=60,
                idempotency_key="request-0002",
                actor_subject="dispatcher:1",
            )

        assert error.value.code == "ACTIVE_ASSIGNMENT_EXISTS"


@pytest.mark.asyncio
async def test_idempotency_key_reuse_for_different_incident_conflicts(factory):
    async with factory() as session:
        session.add(
            SecurityEvent(
                id=2,
                property_id=1,
                camera_id=1,
                event_type="INTRUSION",
                object_type="person",
                confidence=0.9,
                timestamp=datetime.now(timezone.utc),
                severity="HIGH",
                status="OPEN",
                event_metadata={},
            )
        )
        await session.commit()

        service = DispatchService(session)
        await service.create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="request-same-key",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        with pytest.raises(ApplicationError) as error:
            await service.create_offer(
                incident_id=2,
                property_id=1,
                marshal_profile_id=1,
                expires_in_seconds=60,
                idempotency_key="request-same-key",
                actor_subject="dispatcher:1",
            )
        assert error.value.code == "IDEMPOTENCY_CONFLICT"

        with pytest.raises(ApplicationError) as error:
            await service.create_offer(
                incident_id=1,
                property_id=1,
                marshal_profile_id=1,
                expires_in_seconds=90,
                idempotency_key="request-same-key",
                actor_subject="dispatcher:1",
            )
        assert error.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_compare_and_swap_accept_and_capacity(factory):
    async with factory() as session:
        service = DispatchService(session)
        offer = await service.create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="request-0001",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        accepted = await service.respond(
            offer_id=offer.id,
            user_id=1,
            accept=True,
            expected_version=1,
            actor_subject="marshal:1",
        )
        await session.commit()

        assert (accepted.status, accepted.version) == ("ACCEPTED", 2)

        with pytest.raises(ApplicationError) as error:
            await service.respond(
                offer_id=offer.id,
                user_id=1,
                accept=True,
                expected_version=1,
                actor_subject="marshal:1",
            )
        assert error.value.code == "OFFER_CONFLICT"


@pytest.mark.asyncio
async def test_marshal_progress_and_completion_resolve_incident(factory):
    async with factory() as session:
        service = DispatchService(session)
        offer = await service.create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="progress-0001",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        await service.respond(
            offer_id=offer.id,
            user_id=1,
            accept=True,
            expected_version=1,
            actor_subject="marshal:1",
        )
        await service.marshal_progress(
            offer_id=offer.id,
            user_id=1,
            status="EN_ROUTE",
            expected_version=2,
            actor_subject="marshal:1",
        )
        await service.marshal_progress(
            offer_id=offer.id,
            user_id=1,
            status="ON_SCENE",
            expected_version=3,
            actor_subject="marshal:1",
        )
        completed = await service.marshal_progress(
            offer_id=offer.id,
            user_id=1,
            status="COMPLETED",
            expected_version=4,
            actor_subject="marshal:1",
        )
        await session.commit()

        incident = await session.get(SecurityEvent, 1)
        history = list(
            (
                await session.scalars(
                    select(AssignmentEvent)
                    .where(AssignmentEvent.assignment_id == offer.id)
                    .order_by(AssignmentEvent.id)
                )
            ).all()
        )

        assert completed.status == "COMPLETED"
        assert incident.status == "RESOLVED"
        assert [event.new_status for event in history] == [
            "OFFERED",
            "ACCEPTED",
            "EN_ROUTE",
            "ON_SCENE",
            "COMPLETED",
        ]


@pytest.mark.asyncio
async def test_marshal_progress_rejects_wrong_user_and_transition(factory):
    async with factory() as session:
        service = DispatchService(session)
        offer = await service.create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="progress-0002",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        await service.respond(
            offer_id=offer.id,
            user_id=1,
            accept=True,
            expected_version=1,
            actor_subject="marshal:1",
        )

        with pytest.raises(ApplicationError) as error:
            await service.marshal_progress(
                offer_id=offer.id,
                user_id=999,
                status="EN_ROUTE",
                expected_version=2,
                actor_subject="marshal:999",
            )
        assert error.value.code == "NOT_FOUND"

        with pytest.raises(ApplicationError) as error:
            await service.marshal_progress(
                offer_id=offer.id,
                user_id=1,
                status="ON_SCENE",
                expected_version=2,
                actor_subject="marshal:1",
            )
        assert error.value.code == "OFFER_CONFLICT"


@pytest.mark.asyncio
async def test_dispatch_next_selects_least_loaded_and_reassigns_after_decline(factory):
    async with factory() as session:
        offer = await DispatchService(session).dispatch_next(
            incident_id=1,
            property_id=1,
            expires_in_seconds=60,
            actor_subject="dispatcher:1",
            correlation_id="dispatch-run-1",
        )
        await session.commit()

        assert offer is not None
        assert offer.marshal_profile_id == 1

        service = DispatchService(session)
        declined = await service.respond(
            offer_id=offer.id,
            user_id=1,
            accept=False,
            expected_version=1,
            actor_subject="marshal:1",
        )
        reassigned = await session.scalar(
            select(Assignment).where(
                Assignment.security_event_id == 1,
                Assignment.status == "OFFERED",
            )
        )
        await session.commit()

        assert declined.status == "DECLINED"
        assert reassigned is not None
        assert reassigned.marshal_profile_id == 2


@pytest.mark.asyncio
async def test_no_eligible_marshal_escalates_incident_and_queues_operator_intent(
    factory,
):
    async with factory() as session:
        for profile_id in (1, 2):
            availability = await session.get(MarshalAvailability, profile_id)
            availability.on_duty = False
        await session.commit()

        outcome = await DispatchService(session).dispatch_next(
            incident_id=1,
            property_id=1,
            expires_in_seconds=60,
            actor_subject="dispatcher:1",
            correlation_id="dispatch-no-marshal",
        )
        await session.commit()

        incident = await session.get(SecurityEvent, 1)
        intent = await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.kind == "DISPATCH_NO_ELIGIBLE_MARSHAL"
            )
        )

        assert outcome is None
        assert incident.status == "ESCALATED"
        assert intent is not None


@pytest.mark.asyncio
async def test_timeout_creates_history_and_escalation(factory):
    async with factory() as session:
        offer = Assignment(
            security_event_id=1,
            property_id=1,
            marshal_profile_id=1,
            status="OFFERED",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            idempotency_key="request-expired",
        )
        session.add(offer)
        await session.commit()

        expired = await DispatchService(session).expire(
            offer_id=offer.id,
            actor_subject="worker:timeout",
        )
        await session.commit()

        assert expired.status == "EXPIRED"
        next_offer = await session.scalar(
            select(Assignment).where(
                Assignment.security_event_id == 1,
                Assignment.status == "OFFERED",
            )
        )
        assert next_offer is not None
        assert next_offer.marshal_profile_id == 2


@pytest.mark.asyncio
async def test_timeout_worker_recovers_expired_offer_from_database(factory):
    async with factory() as session:
        session.add(
            Assignment(
                security_event_id=1,
                property_id=1,
                marshal_profile_id=1,
                status="OFFERED",
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=2),
                idempotency_key="restart-expired-1",
            )
        )
        await session.commit()

    worker = TimeoutEscalator(factory)
    assert await worker.run_once() == 1
    assert await TimeoutEscalator(factory).run_once() == 0

    async with factory() as session:
        expired = await session.scalar(
            select(Assignment).where(
                Assignment.idempotency_key == "restart-expired-1"
            )
        )
        next_offer = await session.scalar(
            select(Assignment).where(
                Assignment.security_event_id == 1,
                Assignment.status == "OFFERED",
            )
        )

        assert expired.status == "EXPIRED"
        assert next_offer is not None
        assert next_offer.marshal_profile_id == 2


@pytest.mark.asyncio
async def test_outbox_claim_and_attempt_receipt(factory):
    async with factory() as session:
        await DispatchService(session).create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="request-0001",
            actor_subject="dispatcher:1",
        )
        await session.commit()

        repository = OutboxRepository(session)
        claimed = await repository.claim_batch(
            "worker-1",
            datetime.now(timezone.utc),
        )
        assert len(claimed) == 1
        assert claimed[0].status == "PROCESSING"

        await repository.record_attempt(
            claimed[0].id,
            provider="test",
            result="DELIVERED",
            provider_reference="provider-1",
            now=datetime.now(timezone.utc),
        )
        await session.commit()

        receipt = await session.scalar(select(NotificationAttempt))
        assert receipt
        assert receipt.attempt_number == 1


class FailingProvider:
    name = "test-failure"

    async def deliver(self, destination, event_type, payload, idempotency_key):
        return DeliveryResult(
            delivered=False,
            error="temporary failure",
        )


@pytest.mark.asyncio
async def test_notification_failure_retries_then_exhausts(factory):
    worker = NotificationDispatcher(
        factory,
        FailingProvider(),
        worker_id="test-worker",
    )

    async with factory() as session:
        await DispatchService(session).create_offer(
            incident_id=1,
            property_id=1,
            marshal_profile_id=1,
            expires_in_seconds=60,
            idempotency_key="retry-00001",
            actor_subject="dispatcher:1",
        )
        await session.commit()

    for _attempt in range(5):
        async with factory() as session:
            outbox = await session.scalar(
                select(NotificationOutbox).order_by(NotificationOutbox.id)
            )
            outbox.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await session.commit()

        await worker.run_once()

    async with factory() as session:
        outbox = await session.scalar(
            select(NotificationOutbox).order_by(NotificationOutbox.id)
        )
        assert outbox.status == "EXHAUSTED"
        assert await session.scalar(
            select(func.count(NotificationAttempt.id))
        ) == 5


@pytest.mark.asyncio
async def test_detection_to_resolution_drill_with_fake_notification_provider(
    factory,
):
    zone = Zone(
        id="restricted",
        name="Restricted",
        camera_id="1",
        polygon=[
            Point(x=400, y=200),
            Point(x=800, y=200),
            Point(x=800, y=600),
            Point(x=400, y=600),
        ],
    )
    local_engine = LocalSecurityEngine(
        SecurityEngine(SecurityConfig(zones=[zone]))
    )
    decision = await local_engine.evaluate(
        SecurityContext(
            camera_id=1,
            object_type="person",
            confidence=0.95,
            timestamp=datetime.now(timezone.utc),
            track_id="track-event-1",
            bounding_box={"x": 0.35, "y": 0.2, "width": 0.3, "height": 0.6},
            frame_width=1280,
            frame_height=720,
            evidence_refs=["frigate:event-1:snapshot"],
        )
    )
    assert decision.event_type == "ZONE_ENTRY"

    class PilotDecisionAdapter:
        async def evaluate(self, _context):
            return decision

    async with factory() as session:
        processor = EventProcessor(
            session,
            CameraRepository(session),
            EventRepository(session),
            security_engine=PilotDecisionAdapter(),
        )
        processed = await processor.process(
            IngestDetection(
                source="frigate",
                source_event_id="event-1",
                camera="camera",
                object_type="person",
                confidence=0.95,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "lifecycle": "new",
                    "has_snapshot": True,
                },
            )
        )
        incident = processed.event
        assert incident.status == "OPEN"
        assert incident.zone == "restricted"
        assert incident.event_metadata["security_decision"]["metadata"][
            "evidence_refs"
        ] == ["frigate:event-1:snapshot"]

        service = DispatchService(session)
        offer = await service.dispatch_next(
            incident_id=incident.id,
            property_id=1,
            expires_in_seconds=60,
            actor_subject="dispatcher:1",
            correlation_id="pilot-drill-01",
        )
        assert offer is not None

        await service.respond(
            offer_id=offer.id,
            user_id=1,
            accept=True,
            expected_version=1,
            actor_subject="marshal:1",
        )
        await service.marshal_progress(
            offer_id=offer.id,
            user_id=1,
            status="EN_ROUTE",
            expected_version=2,
            actor_subject="marshal:1",
        )
        await service.marshal_progress(
            offer_id=offer.id,
            user_id=1,
            status="ON_SCENE",
            expected_version=3,
            actor_subject="marshal:1",
        )
        await service.marshal_progress(
            offer_id=offer.id,
            user_id=1,
            status="COMPLETED",
            expected_version=4,
            actor_subject="marshal:1",
        )
        await session.commit()

    fake_provider = RecordingFakeProvider()
    await NotificationDispatcher(
        factory,
        fake_provider,
        worker_id="pilot-drill",
    ).run_once()

    async with factory() as session:
        resolved = await session.get(SecurityEvent, incident.id)
        history = list(
            (
                await session.scalars(
                    select(AssignmentEvent)
                    .where(AssignmentEvent.assignment_id == offer.id)
                    .order_by(AssignmentEvent.id)
                )
            ).all()
        )
        attempts = list(
            (await session.scalars(select(NotificationAttempt))).all()
        )

        assert resolved.status == "RESOLVED"
        assert [row.new_status for row in history] == [
            "OFFERED",
            "ACCEPTED",
            "EN_ROUTE",
            "ON_SCENE",
            "COMPLETED",
        ]
        assert attempts
        assert all(row.status == "DELIVERED" for row in attempts)
        assert len(fake_provider.records) == len(attempts)
