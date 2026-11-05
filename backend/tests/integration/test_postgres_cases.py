"""Opt-in PostgreSQL locking tests in a generated disposable schema only."""
import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests.integration.test_postgres_domain import database, postgres_schema  # Reuse isolated-schema fixtures.
from app.core.exceptions import ApplicationError
from app.models import (Assignment, AssignmentEvent, MarshalAvailability, MarshalProfile,
    NotificationOutbox, Property, PropertyMembership, ReporterIncident,
    ReporterIncidentTimeline, User)
from app.schemas.case import CaseCommand
from app.services.case_service import CaseService
from app.services.dispatch_service import DispatchService

pytestmark = pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS") != "1",
                               reason="Requires PostgreSQL disposable-schema acceptance configuration")


async def seed(factory, capacity=2):
    marker = uuid4().hex
    async with factory() as session:
        property = Property(slug=marker, name="Case acceptance")
        user = User(subject=marker, email=f"{marker}@example.test", active=True)
        session.add_all([property, user])
        await session.flush()
        profile = MarshalProfile(user_id=user.id, property_id=property.id, capacity=capacity)
        session.add_all([profile, PropertyMembership(user_id=user.id, property_id=property.id, role="marshal")])
        await session.flush()
        session.add(MarshalAvailability(marshal_profile_id=profile.id, on_duty=True, available=True,
                                        updated_at=datetime.now(timezone.utc)))
        reports = [ReporterIncident(reporter_user_id=user.id, property_id=property.id, incident_type="THEFT",
            status="RECEIVED", address="Acceptance location", idempotency_key=uuid4().hex) for _ in range(2)]
        session.add_all(reports)
        await session.commit()
        return property.id, profile.id, [item.id for item in reports]


async def offer(factory, property_id, profile_id, report_id, key):
    async with factory() as session:
        try:
            item = await DispatchService(session).create_offer(property_id=property_id,
                marshal_profile_id=profile_id, reporter_incident_id=report_id,
                expires_in_seconds=60, idempotency_key=key, actor_subject="acceptance:dispatcher")
            await session.commit()
            return item.id
        except ApplicationError as error:
            await session.rollback()
            return error.code


async def test_same_key_concurrent_replay_writes_one_offer_history_and_outbox(database):
    property_id, profile_id, reports = await seed(database)
    key = uuid4().hex
    results = await asyncio.gather(*(offer(database, property_id, profile_id, reports[0], key) for _ in range(3)))
    assert all(isinstance(value, int) for value in results) and len(set(results)) == 1
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Assignment).where(Assignment.property_id == property_id)) == 1
        assert await session.scalar(select(func.count()).select_from(AssignmentEvent).where(AssignmentEvent.assignment_id == results[0])) == 1
        assert await session.scalar(select(func.count()).select_from(NotificationOutbox).where(NotificationOutbox.property_id == property_id)) == 1


async def test_different_keys_cannot_create_two_active_offers_for_one_report(database):
    property_id, profile_id, reports = await seed(database)
    results = await asyncio.gather(*(offer(database, property_id, profile_id, reports[0], uuid4().hex) for _ in range(2)))
    assert sum(isinstance(value, int) for value in results) == 1
    assert "ACTIVE_ASSIGNMENT_EXISTS" in results


async def test_pending_offers_reserve_capacity_across_concurrent_incidents(database):
    property_id, profile_id, reports = await seed(database, capacity=1)
    results = await asyncio.gather(*(offer(database, property_id, profile_id, report_id, uuid4().hex) for report_id in reports))
    assert sum(isinstance(value, int) for value in results) == 1
    assert "MARSHAL_AT_CAPACITY" in results


async def test_concurrent_manual_status_commands_have_one_winner(database):
    property_id, _, reports = await seed(database)
    async def acknowledge():
        async with database() as session:
            try:
                await CaseService(session).command(property_id, "reporter", reports[0],
                    CaseCommand(command="acknowledge", expected_status="OPEN", reason="Reviewed",
                                correlation_id=uuid4().hex), "acceptance:dispatcher")
                return "ok"
            except ApplicationError as error:
                await session.rollback()
                return error.code
    assert sorted(await asyncio.gather(acknowledge(), acknowledge())) == ["CASE_CONFLICT", "ok"]
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(ReporterIncidentTimeline)
                                    .where(ReporterIncidentTimeline.incident_id == reports[0])) == 1
