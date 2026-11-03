"""Transaction-neutral persistence for dispatch and notification workers."""
from datetime import datetime, timedelta
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (Assignment, AssignmentEvent, MarshalAvailability, MarshalProfile,
    NotificationAttempt, NotificationOutbox, PropertyMembership, User)


class DispatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_offer(self, offer_id: int) -> Assignment | None:
        return await self.session.scalar(select(Assignment).where(Assignment.id == offer_id).with_for_update())

    async def find_by_idempotency_key(self, key: str) -> Assignment | None:
        return await self.session.scalar(select(Assignment).where(Assignment.idempotency_key == key))

    async def add_offer(self, offer: Assignment, *, actor_subject: str, correlation_id: str) -> Assignment:
        self.session.add(offer)
        await self.session.flush()
        self.session.add(AssignmentEvent(assignment_id=offer.id, previous_status=None,
            new_status="OFFERED", actor_subject=actor_subject, correlation_id=correlation_id))
        self.session.add(NotificationOutbox(property_id=offer.property_id,
            security_event_id=offer.security_event_id, kind="ASSIGNMENT_OFFERED",
            destination=f"marshal:{offer.marshal_profile_id}",
            payload={"assignment_id": offer.id, "incident_id": offer.security_event_id,
                     "expires_at": offer.expires_at.isoformat()},
            dedupe_key=f"assignment:{offer.id}:offered", status="PENDING"))
        await self.session.flush()
        return offer

    async def transition(self, offer: Assignment, *, status: str, now: datetime,
                         actor_subject: str, correlation_id: str,
                         reason: str | None = None, notify: bool = True) -> Assignment:
        previous = offer.status
        offer.status, offer.version = status, offer.version + 1
        if status == "ACCEPTED":
            offer.accepted_at = now
        if status in {"DECLINED", "EXPIRED", "CANCELLED", "COMPLETED"}:
            offer.closed_at = now
        self.session.add(AssignmentEvent(assignment_id=offer.id, previous_status=previous,
            new_status=status, actor_subject=actor_subject, correlation_id=correlation_id, reason=reason))
        if notify:
            self.session.add(NotificationOutbox(property_id=offer.property_id,
                security_event_id=offer.security_event_id, kind=f"ASSIGNMENT_{status}",
                destination=f"property:{offer.property_id}:dispatchers",
                payload={"assignment_id": offer.id, "incident_id": offer.security_event_id,
                         "status": status, "version": offer.version},
                dedupe_key=f"assignment:{offer.id}:{status.lower()}:{offer.version}", status="PENDING"))
        await self.session.flush()
        return offer

    async def eligible_marshals(self, property_id: int, fresh_since: datetime) -> list[MarshalProfile]:
        active = select(func.count(Assignment.id)).where(
            Assignment.marshal_profile_id == MarshalProfile.id,
            Assignment.status.in_(["ACCEPTED", "EN_ROUTE", "ON_SCENE"])).scalar_subquery()
        statement = (select(MarshalProfile).join(User, User.id == MarshalProfile.user_id)
            .join(PropertyMembership, (PropertyMembership.user_id == MarshalProfile.user_id) &
                  (PropertyMembership.property_id == MarshalProfile.property_id))
            .join(MarshalAvailability, MarshalAvailability.marshal_profile_id == MarshalProfile.id)
            .where(MarshalProfile.property_id == property_id, MarshalProfile.active.is_(True),
                User.active.is_(True), PropertyMembership.active.is_(True),
                PropertyMembership.role == "marshal", MarshalAvailability.on_duty.is_(True),
                MarshalAvailability.available.is_(True), MarshalAvailability.updated_at >= fresh_since,
                active < MarshalProfile.capacity).order_by(MarshalProfile.id))
        return list((await self.session.scalars(statement)).all())

    async def due_offers(self, now: datetime, limit: int = 50) -> list[Assignment]:
        return list((await self.session.scalars(select(Assignment).where(
            Assignment.status == "OFFERED", Assignment.expires_at <= now)
            .order_by(Assignment.expires_at, Assignment.id).limit(limit)
            .with_for_update(skip_locked=True))).all())


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim_batch(self, worker_id: str, now: datetime, limit: int = 50) -> list[NotificationOutbox]:
        rows = list((await self.session.scalars(select(NotificationOutbox).where(
            or_(NotificationOutbox.status.in_(["PENDING", "FAILED"]),
                (NotificationOutbox.status == "PROCESSING") &
                (NotificationOutbox.claimed_at < now - timedelta(minutes=5))),
            NotificationOutbox.available_at <= now).order_by(NotificationOutbox.id).limit(limit)
            .with_for_update(skip_locked=True))).all())
        for row in rows:
            row.status, row.claimed_by, row.claimed_at = "PROCESSING", worker_id, now
        await self.session.flush()
        return rows

    async def record_attempt(self, outbox_id: int, *, provider: str, result: str, now: datetime,
                             provider_reference: str | None = None, error: str | None = None,
                             response_metadata: dict | None = None) -> NotificationAttempt:
        row = await self.session.scalar(select(NotificationOutbox).where(
            NotificationOutbox.id == outbox_id).with_for_update())
        if row is None:
            raise LookupError("outbox record not found")
        attempt_number = int((await self.session.scalar(select(func.count(NotificationAttempt.id)).where(
            NotificationAttempt.outbox_id == outbox_id))) or 0) + 1
        receipt = NotificationAttempt(outbox_id=row.id, attempt_number=attempt_number,
            provider=provider, provider_reference=provider_reference, status=result,
            error_code="DELIVERY_FAILED" if error else None, error_detail=error,
            response_metadata=response_metadata or {}, attempted_at=now)
        self.session.add(receipt)
        if result == "DELIVERED":
            row.status, row.sent_at = "SENT", now
        else:
            row.status = "FAILED"
        await self.session.flush()
        return receipt
