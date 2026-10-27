"""Property-authorized, race-safe assignment orchestration."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ApplicationError
from app.models import (Assignment, MarshalAvailability, MarshalProfile,
    NotificationOutbox, PropertyMembership, SecurityEvent, User)
from app.repositories.dispatch import DispatchRepository


class DispatchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session, self.repository = session, DispatchRepository(session)

    async def create_offer(self, *, incident_id: int, property_id: int, marshal_profile_id: int,
                           expires_in_seconds: int, idempotency_key: str,
                           actor_subject: str) -> Assignment:
        existing = await self.repository.find_by_idempotency_key(idempotency_key)
        if existing:
            if existing.property_id != property_id:
                raise ApplicationError("IDEMPOTENCY_CONFLICT", "Idempotency key belongs to another request.", 409)
            return existing
        incident = await self.session.scalar(select(SecurityEvent).where(SecurityEvent.id == incident_id,
            SecurityEvent.property_id == property_id).with_for_update())
        if incident is None:
            raise ApplicationError("NOT_FOUND", "Incident not found for this property.", 404)
        existing = await self.repository.find_by_idempotency_key(idempotency_key)
        if existing:
            return existing
        active = await self.session.scalar(select(Assignment).where(Assignment.security_event_id == incident_id,
            Assignment.status.in_(["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"])))
        if active:
            raise ApplicationError("ACTIVE_ASSIGNMENT_EXISTS", "This incident already has an active assignment.", 409)
        row = await self.session.execute(select(MarshalProfile, MarshalAvailability).join(
            MarshalAvailability, MarshalAvailability.marshal_profile_id == MarshalProfile.id).join(
            User, User.id == MarshalProfile.user_id).join(PropertyMembership,
            (PropertyMembership.user_id == MarshalProfile.user_id) &
            (PropertyMembership.property_id == MarshalProfile.property_id)).where(
            MarshalProfile.id == marshal_profile_id, MarshalProfile.property_id == property_id,
            MarshalProfile.active.is_(True), User.active.is_(True), PropertyMembership.active.is_(True),
            PropertyMembership.role == "marshal").with_for_update())
        eligibility = row.first()
        now = datetime.now(timezone.utc)
        if eligibility is None:
            raise ApplicationError("MARSHAL_UNAVAILABLE", "Marshal is not eligible for this property.", 409)
        profile, availability = eligibility
        updated = availability.updated_at if availability.updated_at.tzinfo else availability.updated_at.replace(tzinfo=timezone.utc)
        if not availability.on_duty or not availability.available or updated < now - timedelta(minutes=5):
            raise ApplicationError("MARSHAL_UNAVAILABLE", "Marshal availability is absent or stale.", 409)
        count = await self.session.scalar(select(func.count(Assignment.id)).where(
            Assignment.marshal_profile_id == profile.id,
            Assignment.status.in_(["ACCEPTED", "EN_ROUTE", "ON_SCENE"])))
        if (count or 0) >= profile.capacity:
            raise ApplicationError("MARSHAL_AT_CAPACITY", "Marshal has reached assignment capacity.", 409)
        offer = Assignment(property_id=property_id, security_event_id=incident_id,
            marshal_profile_id=marshal_profile_id, status="OFFERED",
            expires_at=now + timedelta(seconds=expires_in_seconds), idempotency_key=idempotency_key)
        return await self.repository.add_offer(offer, actor_subject=actor_subject,
            correlation_id=idempotency_key)

    async def respond(self, *, offer_id: int, user_id: int, accept: bool,
                      expected_version: int, actor_subject: str) -> Assignment:
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
        profile = await self.session.get(MarshalProfile, offer.marshal_profile_id)
        if profile is None or profile.user_id != user_id:
            raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
        now = datetime.now(timezone.utc)
        expires = offer.expires_at if offer.expires_at.tzinfo else offer.expires_at.replace(tzinfo=timezone.utc)
        if offer.status != "OFFERED" or offer.version != expected_version:
            raise ApplicationError("OFFER_CONFLICT", "The offer has already changed.", 409)
        if expires <= now:
            raise ApplicationError("OFFER_EXPIRED", "The assignment offer has expired.", 409)
        return await self.repository.transition(offer, status="ACCEPTED" if accept else "DECLINED",
            now=now, actor_subject=actor_subject, correlation_id=f"response:{offer.id}:{expected_version}")

    async def expire(self, *, offer_id: int, actor_subject: str) -> Assignment:
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
        now = datetime.now(timezone.utc)
        expires = offer.expires_at if offer.expires_at.tzinfo else offer.expires_at.replace(tzinfo=timezone.utc)
        if offer.status != "OFFERED":
            raise ApplicationError("OFFER_CONFLICT", "The offer has already changed.", 409)
        if expires > now:
            raise ApplicationError("OFFER_NOT_EXPIRED", "The offer deadline has not elapsed.", 409)
        result = await self.repository.transition(offer, status="EXPIRED", now=now,
            actor_subject=actor_subject, correlation_id=f"timeout:{offer.id}:{offer.version}",
            reason="deadline elapsed")
        self.session.add(NotificationOutbox(property_id=offer.property_id,
            security_event_id=offer.security_event_id, kind="DISPATCH_ESCALATION_REQUIRED",
            destination=f"property:{offer.property_id}:dispatchers",
            payload={"assignment_id": offer.id, "incident_id": offer.security_event_id,
                     "reason": "offer_expired"},
            dedupe_key=f"assignment:{offer.id}:escalation:{offer.version}", status="PENDING"))
        await self.session.flush()
        return result

    async def cancel(self, *, offer_id: int, actor_subject: str) -> Assignment:
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
        if offer.status not in {"OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"}:
            raise ApplicationError("OFFER_CONFLICT", "The assignment is already terminal.", 409)
        return await self.repository.transition(offer, status="CANCELLED", now=datetime.now(timezone.utc),
            actor_subject=actor_subject, correlation_id=f"cancel:{offer.id}:{offer.version}")
