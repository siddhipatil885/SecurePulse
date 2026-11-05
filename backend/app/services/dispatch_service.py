"""Property-authorized, race-safe assignment orchestration."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ApplicationError
from app.models import Assignment, MarshalAvailability, MarshalProfile, PropertyMembership, SecurityEvent, User
from app.repositories.dispatch import DispatchRepository


class DispatchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session, self.repository = session, DispatchRepository(session)

    @staticmethod
    def _same_request(existing: Assignment, *, property_id: int, incident_id: int,
                      marshal_profile_id: int, expires_in_seconds: int) -> bool:
        offered_at = existing.offered_at
        expires_at = existing.expires_at
        if offered_at.tzinfo is None and expires_at.tzinfo is not None:
            offered_at = offered_at.replace(tzinfo=expires_at.tzinfo)
        elif expires_at.tzinfo is None and offered_at.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=offered_at.tzinfo)
        duration_matches = abs((expires_at - offered_at).total_seconds() - expires_in_seconds) <= 1
        return (existing.property_id, existing.security_event_id, existing.marshal_profile_id) == (
            property_id, incident_id, marshal_profile_id
        ) and duration_matches

    async def create_offer(self, *, incident_id: int, property_id: int, marshal_profile_id: int,
                           expires_in_seconds: int, idempotency_key: str,
                           actor_subject: str) -> Assignment:
        existing = await self.repository.find_by_idempotency_key(idempotency_key)
        if existing:
            if not self._same_request(existing, property_id=property_id, incident_id=incident_id,
                                      marshal_profile_id=marshal_profile_id,
                                      expires_in_seconds=expires_in_seconds):
                raise ApplicationError("IDEMPOTENCY_CONFLICT", "Idempotency key belongs to another request.", 409)
            return existing
        incident = await self.session.scalar(select(SecurityEvent).where(SecurityEvent.id == incident_id,
            SecurityEvent.property_id == property_id).with_for_update())
        if incident is None:
            raise ApplicationError("NOT_FOUND", "Incident not found for this property.", 404)
        if incident.status not in {"OPEN", "ACKNOWLEDGED", "DISPATCHING", "ESCALATED"}:
            raise ApplicationError("INCIDENT_NOT_DISPATCHABLE", "Incident is not in a dispatchable state.", 409)
        existing = await self.repository.find_by_idempotency_key(idempotency_key)
        if existing:
            if not self._same_request(existing, property_id=property_id, incident_id=incident_id,
                                      marshal_profile_id=marshal_profile_id,
                                      expires_in_seconds=expires_in_seconds):
                raise ApplicationError("IDEMPOTENCY_CONFLICT", "Idempotency key belongs to another request.", 409)
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
            Assignment.status.in_(["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"])))
        if (count or 0) >= profile.capacity:
            raise ApplicationError("MARSHAL_AT_CAPACITY", "Marshal has reached assignment capacity.", 409)
        offer = Assignment(property_id=property_id, security_event_id=incident_id,
            marshal_profile_id=marshal_profile_id, status="OFFERED",
            expires_at=now + timedelta(seconds=expires_in_seconds), idempotency_key=idempotency_key)
        try:
            created = await self.repository.add_offer(offer, actor_subject=actor_subject,
                correlation_id=idempotency_key)
            await self.repository.set_incident_status(incident, status="DISPATCHING",
                actor_subject=actor_subject, reason="Marshal offer created",
                correlation_id=idempotency_key)
            return created
        except IntegrityError:
            # The unique idempotency key and one-active-offer index are the
            # final concurrency guard when simultaneous requests pass the reads.
            await self.session.rollback()
            existing = await self.repository.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if self._same_request(existing, property_id=property_id, incident_id=incident_id,
                                      marshal_profile_id=marshal_profile_id,
                                      expires_in_seconds=expires_in_seconds):
                    return existing
                raise ApplicationError("IDEMPOTENCY_CONFLICT", "Idempotency key belongs to another request.", 409)
            active = await self.session.scalar(select(Assignment).where(
                Assignment.security_event_id == incident_id,
                Assignment.status.in_(["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"])))
            if active is not None:
                raise ApplicationError("ACTIVE_ASSIGNMENT_EXISTS", "This incident already has an active assignment.", 409)
            raise

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
        transitioned = await self.repository.transition(offer, status="ACCEPTED" if accept else "DECLINED",
            now=now, actor_subject=actor_subject, correlation_id=f"response:{offer.id}:{expected_version}")
        if not accept:
            await self.dispatch_next(incident_id=offer.security_event_id, property_id=offer.property_id,
                expires_in_seconds=60,
                actor_subject="system:reassignment",
                correlation_id=f"declined:{offer.id}:{offer.version}")
        return transitioned

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
        await self.dispatch_next(incident_id=offer.security_event_id, property_id=offer.property_id,
            expires_in_seconds=60,
            actor_subject="system:reassignment",
            correlation_id=f"expired:{offer.id}:{offer.version}")
        return result

    async def dispatch_next(self, *, incident_id: int, property_id: int,
                            expires_in_seconds: int, actor_subject: str,
                            correlation_id: str) -> Assignment | None:
        """Offer to the least-loaded eligible marshal, or audit escalation.

        Provisional policy: at most three marshal offers per incident; among
        eligible marshals choose the fewest active offers/assignments, then ID.
        Previously declined or expired marshals are skipped for this incident.
        """
        incident = await self.session.scalar(select(SecurityEvent).where(
            SecurityEvent.id == incident_id, SecurityEvent.property_id == property_id
        ).with_for_update())
        if incident is None:
            raise ApplicationError("NOT_FOUND", "Incident not found for this property.", 404)
        if incident.status not in {"OPEN", "ACKNOWLEDGED", "DISPATCHING", "ESCALATED"}:
            raise ApplicationError("INCIDENT_NOT_DISPATCHABLE", "Incident is not in a dispatchable state.", 409)
        active = await self.session.scalar(select(Assignment).where(
            Assignment.security_event_id == incident_id,
            Assignment.status.in_(["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"])))
        if active is not None:
            return active

        attempt_count = await self.repository.assignment_attempt_count(incident_id)
        max_attempts = 3
        excluded = await self.repository.prior_attempt_profile_ids(incident_id)
        eligible = await self.repository.eligible_marshals(
            property_id, datetime.now(timezone.utc) - timedelta(minutes=5), excluded
        )
        if not eligible or attempt_count >= max_attempts:
            reason = "No eligible marshal is currently available"
            if attempt_count >= max_attempts:
                reason = "Maximum marshal offer attempts reached"
            await self.repository.add_no_marshal_escalation(incident, actor_subject=actor_subject,
                reason=reason, correlation_id=correlation_id)
            return None

        marshal = eligible[0]
        key = f"dispatch:{incident_id}:attempt:{attempt_count + 1}:marshal:{marshal.id}"
        return await self.create_offer(incident_id=incident_id, property_id=property_id,
            marshal_profile_id=marshal.id, expires_in_seconds=expires_in_seconds,
            idempotency_key=key, actor_subject=actor_subject)

    async def cancel(self, *, offer_id: int, actor_subject: str) -> Assignment:
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
        if offer.status not in {"OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"}:
            raise ApplicationError("OFFER_CONFLICT", "The assignment is already terminal.", 409)
        return await self.repository.transition(offer, status="CANCELLED", now=datetime.now(timezone.utc),
            actor_subject=actor_subject, correlation_id=f"cancel:{offer.id}:{offer.version}")

    async def marshal_progress(self, *, offer_id: int, user_id: int, status: str,
                               expected_version: int, actor_subject: str) -> Assignment:
        transitions = {"EN_ROUTE": ("ACCEPTED",), "ON_SCENE": ("EN_ROUTE",), "COMPLETED": ("ON_SCENE",)}
        if status not in transitions:
            raise ApplicationError("INVALID_ASSIGNMENT_TRANSITION", "Unsupported marshal progress state.", 409)
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
        profile = await self.session.get(MarshalProfile, offer.marshal_profile_id)
        if profile is None or profile.user_id != user_id:
            raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
        if offer.version != expected_version or offer.status not in transitions[status]:
            raise ApplicationError("OFFER_CONFLICT", f"Cannot move assignment from {offer.status} to {status}.", 409)
        now = datetime.now(timezone.utc)
        result = await self.repository.transition(offer, status=status, now=now,
            actor_subject=actor_subject, correlation_id=f"progress:{offer.id}:{expected_version}")
        if status == "COMPLETED":
            await self.repository.resolve_incident(offer.security_event_id,
                actor_subject=actor_subject, correlation_id=f"progress:{offer.id}:{result.version}")
        return result
