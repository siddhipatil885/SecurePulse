from app.services.location import distance_metres, estimate_eta_seconds
import pytest
from tests.test_dispatch import factory


def test_distance_and_eta_are_bounded_and_deterministic():
    distance = distance_metres(18.5204, 73.8567, 18.5304, 73.8567)
    assert 1000 < distance < 1200
    assert estimate_eta_seconds(distance, 10) == round(distance / 10)


def test_eta_uses_safe_fallback_when_speed_is_missing_or_stationary():
    assert estimate_eta_seconds(800, None) == 100
    assert estimate_eta_seconds(800, 0) == 100


@pytest.mark.asyncio
async def test_pending_offer_never_projects_old_availability_location(factory):
    from datetime import datetime, timezone
    from app.models import MarshalAvailability, Assignment
    from app.services.case_service import CaseService
    from tests.test_marshal import offer
    assignment_id = await offer(factory)
    async with factory() as session:
        availability = await session.get(MarshalAvailability, 1)
        availability.latitude = 18; availability.longitude = 73
        availability.location_updated_at = datetime.now(timezone.utc)
        await session.commit()
        detail = await CaseService(session).detail(1, 'camera', 1)
        assert detail.latest_assignment.responder_location is None
        assignment = await session.get(Assignment, assignment_id)
        assignment.status = 'ACCEPTED'
        await session.commit()
        detail = await CaseService(session).detail(1, 'camera', 1)
        assert detail.latest_assignment.responder_location.latitude == 18


@pytest.mark.asyncio
async def test_location_publisher_checks_assignment_access_and_rechecks_revocation(factory):
    from app.api.dispatch import can_view_assignment_location
    from app.core.auth import Principal
    from app.models import Assignment
    from app.realtime.publisher import InMemoryEventPublisher
    from tests.test_marshal import offer
    assignment_id = await offer(factory)
    async with factory() as session:
        assignment = await session.get(Assignment, assignment_id); assignment.status = 'ACCEPTED'
        await session.commit()
    publisher = InMemoryEventPublisher()
    async def allowed(property_id, item_id):
        async with factory() as session:
            return await can_view_assignment_location(Principal('reporter:1', frozenset({'reporter:read'}), frozenset({1})), property_id, item_id, session)
    async def other(property_id, item_id):
        async with factory() as session:
            return await can_view_assignment_location(Principal('reporter:2', frozenset({'reporter:read'}), frozenset({1})), property_id, item_id, session)
    own = await publisher.subscribe(frozenset({1}), location_access=allowed)
    unrelated = await publisher.subscribe(frozenset({1}), location_access=other)
    default = await publisher.subscribe(frozenset({1}))
    await publisher.publish_marshal_location(1, assignment_id, {'latitude': 18})
    assert (await own.get())['type'] == 'marshal_location'
    assert unrelated.empty() and default.empty()
    async with factory() as session:
        assignment = await session.get(Assignment, assignment_id); assignment.status = 'COMPLETED'
        await session.commit()
    await publisher.publish_marshal_location(1, assignment_id, {'latitude': 18})
    assert own.empty()
