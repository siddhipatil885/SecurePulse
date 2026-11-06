"""Property-authorized, race-safe assignment orchestration."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.models import (
    Assignment,
    MarshalAvailability,
    MarshalProfile,
    NotificationOutbox,
    PropertyMembership,
    ReporterIncident,
    SecurityEvent,
    User,
)
from app.repositories.dispatch import DispatchRepository


class DispatchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DispatchRepository(session)

    @staticmethod
    def _same_source(offer):
        return (Assignment.security_event_id == offer.security_event_id if offer.security_event_id is not None
                else Assignment.reporter_incident_id == offer.reporter_incident_id)

    async def _lock_offer_source(self, offer_id):
        snapshot = await self.session.get(Assignment, offer_id)
        if snapshot is None:
            raise ApplicationError('NOT_FOUND', 'Assignment offer not found.', 404)
        model, source_id = (SecurityEvent, snapshot.security_event_id) if snapshot.security_event_id is not None else (ReporterIncident, snapshot.reporter_incident_id)
        await self.session.scalar(select(model).where(model.id == source_id).with_for_update())

    async def _other_pending(self, offer):
        now = datetime.now(timezone.utc)
        return await self.session.scalar(select(Assignment.id).where(self._same_source(offer),
            Assignment.id != offer.id, self._capacity_filter(now)).limit(1)) is not None

    @staticmethod
    def _same_offer(
        existing: Assignment,
        *,
        property_id: int,
        incident_id: int | None,
        reporter_incident_id: int | None,
        marshal_profile_id: int,
        expires_in_seconds: int,
    ) -> Assignment:
        offered_at = existing.offered_at
        expires_at = existing.expires_at

        if offered_at.tzinfo is None and expires_at.tzinfo is not None:
            offered_at = offered_at.replace(tzinfo=expires_at.tzinfo)
        elif expires_at.tzinfo is None and offered_at.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=offered_at.tzinfo)

        duration_matches = (
            abs((expires_at - offered_at).total_seconds() - expires_in_seconds) <= 1
        )
        request_matches = (
            existing.property_id,
            existing.security_event_id,
            existing.reporter_incident_id,
            existing.marshal_profile_id,
        ) == (
            property_id,
            incident_id,
            reporter_incident_id,
            marshal_profile_id,
        )

        if not duration_matches or not request_matches:
            raise ApplicationError(
                "IDEMPOTENCY_CONFLICT",
                "Idempotency key belongs to another request.",
                409,
            )

        return existing

    @staticmethod
    def _capacity_filter(now: datetime):
        """Count active assignments and offers whose deadlines have not elapsed."""
        return or_(
            Assignment.status.in_(["ACCEPTED", "EN_ROUTE", "ON_SCENE"]),
            and_(
                Assignment.status == "OFFERED",
                Assignment.expires_at > now,
            ),
        )

    async def _queue_reporter_escalation(
        self,
        offer: Assignment,
        *,
        reason: str,
    ) -> None:
        """Notify dispatchers when a reporter-incident offer needs reassignment."""
        dedupe_key = f"assignment:{offer.id}:escalation:{offer.version}"
        existing = await self.session.scalar(
            select(NotificationOutbox.id).where(
                NotificationOutbox.dedupe_key == dedupe_key
            )
        )
        if existing is not None:
            return

        self.session.add(
            NotificationOutbox(
                property_id=offer.property_id,
                security_event_id=offer.security_event_id,
                kind="DISPATCH_ESCALATION_REQUIRED",
                destination=f"property:{offer.property_id}:dispatchers",
                payload={
                    "assignment_id": offer.id,
                    "incident_id": offer.security_event_id,
                    "reporter_incident_id": offer.reporter_incident_id,
                    "reason": reason,
                },
                dedupe_key=dedupe_key,
                status="PENDING",
            )
        )
        await self.session.flush()

    async def create_offer(
        self,
        *,
        incident_id: int | None = None,
        reporter_incident_id: int | None = None,
        property_id: int,
        marshal_profile_id: int,
        expires_in_seconds: int,
        idempotency_key: str,
        actor_subject: str,
        broadcast: bool = False,
    ) -> Assignment:
        if (incident_id is None) == (reporter_incident_id is None):
            raise ApplicationError(
                "INVALID_INCIDENT_SOURCE",
                "Exactly one incident source is required.",
                422,
            )

        existing = await self.repository.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._same_offer(
                existing,
                property_id=property_id,
                incident_id=incident_id,
                reporter_incident_id=reporter_incident_id,
                marshal_profile_id=marshal_profile_id,
                expires_in_seconds=expires_in_seconds,
            )

        if incident_id is not None:
            incident = await self.session.scalar(
                select(SecurityEvent)
                .where(
                    SecurityEvent.id == incident_id,
                    SecurityEvent.property_id == property_id,
                )
                .with_for_update()
            )
            allowed_statuses = {
                "OPEN",
                "ACKNOWLEDGED",
                "DISPATCHING",
                "ESCALATED",
            }
            error_code = "INCIDENT_NOT_DISPATCHABLE"
            error_message = "Incident is not in a dispatchable state."
        else:
            incident = await self.session.scalar(
                select(ReporterIncident)
                .where(
                    ReporterIncident.id == reporter_incident_id,
                    ReporterIncident.property_id == property_id,
                )
                .with_for_update()
            )
            allowed_statuses = {"OPEN", "ACKNOWLEDGED", "RECEIVED"}
            error_code = "INCIDENT_CLOSED"
            error_message = "Only open or acknowledged incidents can be dispatched."

        if incident is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Incident not found for this property.",
                404,
            )

        if incident.status not in allowed_statuses:
            raise ApplicationError(error_code, error_message, 409)

        # Recheck after locking the incident, so concurrent requests cannot
        # both proceed based only on the initial idempotency lookup.
        existing = await self.repository.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._same_offer(
                existing,
                property_id=property_id,
                incident_id=incident_id,
                reporter_incident_id=reporter_incident_id,
                marshal_profile_id=marshal_profile_id,
                expires_in_seconds=expires_in_seconds,
            )

        if incident_id is not None:
            source_filter = Assignment.security_event_id == incident_id
        else:
            source_filter = (
                Assignment.reporter_incident_id == reporter_incident_id
            )

        active_offer = await self.session.scalar(
            select(Assignment)
            .where(
                source_filter,
                Assignment.status.in_(
                    ["ACCEPTED", "EN_ROUTE", "ON_SCENE"] if broadcast else ["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"]
                ),
            )
            .with_for_update()
        )
        if active_offer is not None:
            raise ApplicationError(
                "ACTIVE_ASSIGNMENT_EXISTS",
                "This incident already has an active assignment.",
                409,
            )

        eligibility_result = await self.session.execute(
            select(MarshalProfile, MarshalAvailability)
            .join(
                MarshalAvailability,
                MarshalAvailability.marshal_profile_id == MarshalProfile.id,
            )
            .join(User, User.id == MarshalProfile.user_id)
            .join(
                PropertyMembership,
                and_(
                    PropertyMembership.user_id == MarshalProfile.user_id,
                    PropertyMembership.property_id == MarshalProfile.property_id,
                ),
            )
            .where(
                MarshalProfile.id == marshal_profile_id,
                MarshalProfile.property_id == property_id,
                MarshalProfile.active.is_(True),
                MarshalProfile.verification_status == 'APPROVED',
                User.active.is_(True),
                PropertyMembership.active.is_(True),
                PropertyMembership.role == "marshal",
            )
            .with_for_update()
        )
        eligibility = eligibility_result.first()
        now = datetime.now(timezone.utc)

        if eligibility is None:
            raise ApplicationError(
                "MARSHAL_UNAVAILABLE",
                "Marshal is not eligible for this property.",
                409,
            )

        profile, availability = eligibility
        updated_at = availability.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        if (
            not availability.on_duty
            or not availability.available
            or updated_at < now - timedelta(minutes=5)
        ):
            raise ApplicationError(
                "MARSHAL_UNAVAILABLE",
                "Marshal availability is absent or stale.",
                409,
            )

        active_assignment_count = await self.session.scalar(
            select(func.count(Assignment.id)).where(
                Assignment.marshal_profile_id == profile.id,
                self._capacity_filter(now),
            )
        )
        if (active_assignment_count or 0) >= profile.capacity:
            raise ApplicationError(
                "MARSHAL_AT_CAPACITY",
                "Marshal has reached assignment capacity.",
                409,
            )

        offer = Assignment(
            property_id=property_id,
            security_event_id=incident_id,
            reporter_incident_id=reporter_incident_id,
            marshal_profile_id=marshal_profile_id,
            status="OFFERED",
            offered_at=now,
            expires_at=now + timedelta(seconds=expires_in_seconds),
            idempotency_key=idempotency_key,
        )

        try:
            async with self.session.begin_nested():
                created = await self.repository.add_offer(
                    offer,
                    actor_subject=actor_subject,
                    correlation_id=idempotency_key,
                )
                if incident_id is not None:
                    await self.repository.set_incident_status(
                        incident,
                        status="DISPATCHING",
                        actor_subject=actor_subject,
                        reason="Marshal offer created",
                        correlation_id=idempotency_key,
                    )
            return created

        except IntegrityError:
            existing = await self.repository.find_by_idempotency_key(
                idempotency_key
            )
            if existing is not None:
                return self._same_offer(
                    existing,
                    property_id=property_id,
                    incident_id=incident_id,
                    reporter_incident_id=reporter_incident_id,
                    marshal_profile_id=marshal_profile_id,
                    expires_in_seconds=expires_in_seconds,
                )

            active_id = await self.session.scalar(
                select(Assignment.id)
                .where(
                    source_filter,
                    Assignment.status.in_(
                        ["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"]
                    ),
                )
                .limit(1)
            )
            if active_id is not None:
                raise ApplicationError(
                    "ACTIVE_ASSIGNMENT_EXISTS",
                    "This incident already has an active assignment.",
                    409,
                )

            raise ApplicationError(
                "DISPATCH_CONFLICT",
                "Another assignment changed this incident. Reload before retrying.",
                409,
            ) from None

    async def respond(
        self,
        *,
        offer_id: int,
        user_id: int,
        accept: bool,
        expected_version: int,
        actor_subject: str,
    ) -> Assignment:
        await self._lock_offer_source(offer_id)
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Assignment offer not found.",
                404,
            )

        profile = await self.session.scalar(
            select(MarshalProfile)
            .where(MarshalProfile.id == offer.marshal_profile_id)
            .with_for_update()
        )
        if profile is None or profile.user_id != user_id:
            raise ApplicationError(
                "NOT_FOUND",
                "Assignment offer not found.",
                404,
            )

        now = datetime.now(timezone.utc)
        expires_at = offer.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if offer.status != "OFFERED" or offer.version != expected_version:
            raise ApplicationError(
                "OFFER_CONFLICT",
                "The offer has already changed.",
                409,
            )
        if expires_at <= now:
            raise ApplicationError(
                "OFFER_EXPIRED",
                "The assignment offer has expired.",
                409,
            )

        if accept:
            if profile.verification_status != 'APPROVED':
                raise ApplicationError('ONBOARDING_REQUIRED', 'Complete marshal onboarding and administrator review first.', 403)
            if not profile.active:
                raise ApplicationError(
                    "MARSHAL_UNAVAILABLE",
                    "Marshal profile is disabled.",
                    409,
                )

            other_active_count = await self.session.scalar(
                select(func.count(Assignment.id)).where(
                    Assignment.marshal_profile_id == profile.id,
                    Assignment.id != offer.id,
                    self._capacity_filter(now),
                )
            )
            if (other_active_count or 0) >= profile.capacity:
                raise ApplicationError(
                    "MARSHAL_AT_CAPACITY",
                    "Marshal has reached assignment capacity.",
                    409,
                )

        if accept:
            siblings = (await self.session.scalars(select(Assignment).where(
                self._same_source(offer), Assignment.id != offer.id,
                Assignment.status.in_(['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE'])
            ).order_by(Assignment.id).with_for_update())).all()
            if any(item.status != 'OFFERED' for item in siblings):
                raise ApplicationError('OFFER_CONFLICT', 'Another marshal has already accepted this incident.', 409)
            for sibling in siblings:
                await self.repository.transition(sibling, status='CANCELLED', now=now,
                    actor_subject='system:first-accept', correlation_id=f'winner:{offer.id}:{sibling.id}',
                    reason='Another marshal accepted the incident')

        transitioned = await self.repository.transition(
            offer,
            status="ACCEPTED" if accept else "DECLINED",
            now=now,
            actor_subject=actor_subject,
            correlation_id=f"response:{offer.id}:{expected_version}",
        )

        if not accept and not await self._other_pending(offer):
            if offer.security_event_id is not None:
                await self.dispatch_next(
                    incident_id=offer.security_event_id,
                    property_id=offer.property_id,
                    expires_in_seconds=300,
                    actor_subject="system:reassignment",
                    correlation_id=f"declined:{offer.id}:{offer.version}",
                )
            else:
                await self._queue_reporter_escalation(
                    offer,
                    reason="offer_declined",
                )

        return transitioned

    async def expire(
        self,
        *,
        offer_id: int,
        actor_subject: str,
    ) -> Assignment:
        await self._lock_offer_source(offer_id)
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Assignment offer not found.",
                404,
            )

        now = datetime.now(timezone.utc)
        expires_at = offer.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if offer.status != "OFFERED":
            raise ApplicationError(
                "OFFER_CONFLICT",
                "The offer has already changed.",
                409,
            )
        if expires_at > now:
            raise ApplicationError(
                "OFFER_NOT_EXPIRED",
                "The offer deadline has not elapsed.",
                409,
            )

        result = await self.repository.transition(
            offer,
            status="EXPIRED",
            now=now,
            actor_subject=actor_subject,
            correlation_id=f"timeout:{offer.id}:{offer.version}",
            reason="deadline elapsed",
        )

        if await self._other_pending(offer):
            return result
        if offer.security_event_id is not None:
            await self.dispatch_next(
                incident_id=offer.security_event_id,
                property_id=offer.property_id,
                expires_in_seconds=300,
                actor_subject="system:reassignment",
                correlation_id=f"expired:{offer.id}:{offer.version}",
            )
        else:
            await self._queue_reporter_escalation(
                offer,
                reason="offer_expired",
            )

        return result

    async def dispatch_next(
        self,
        *,
        incident_id: int,
        property_id: int,
        expires_in_seconds: int,
        actor_subject: str,
        correlation_id: str,
    ) -> Assignment | None:
        """Offer to the least-loaded eligible marshal, or audit escalation.

        Provisional policy: at most three marshal offers per incident. Among
        eligible marshals, choose the fewest active assignments, then the
        lowest profile ID. Previously declined or expired marshals are skipped.
        """
        incident = await self.session.scalar(
            select(SecurityEvent)
            .where(
                SecurityEvent.id == incident_id,
                SecurityEvent.property_id == property_id,
            )
            .with_for_update()
        )
        if incident is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Incident not found for this property.",
                404,
            )
        if incident.status not in {
            "OPEN",
            "ACKNOWLEDGED",
            "DISPATCHING",
            "ESCALATED",
        }:
            raise ApplicationError(
                "INCIDENT_NOT_DISPATCHABLE",
                "Incident is not in a dispatchable state.",
                409,
            )

        active = await self.session.scalar(
            select(Assignment).where(
                Assignment.security_event_id == incident_id,
                Assignment.status.in_(
                    ["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"]
                ),
            )
        )
        if active is not None:
            return active

        attempt_count = await self.repository.assignment_attempt_count(incident_id)
        max_attempts = 3
        excluded_profile_ids = (
            await self.repository.prior_attempt_profile_ids(incident_id)
        )
        eligible = await self.repository.eligible_marshals(
            property_id,
            datetime.now(timezone.utc) - timedelta(minutes=5),
            excluded_profile_ids,
        )

        if not eligible or attempt_count >= max_attempts:
            reason = "No eligible marshal is currently available"
            if attempt_count >= max_attempts:
                reason = "Maximum marshal offer attempts reached"

            await self.repository.add_no_marshal_escalation(
                incident,
                actor_subject=actor_subject,
                reason=reason,
                correlation_id=correlation_id,
            )
            return None

        marshal = eligible[0]
        idempotency_key = (
            f"dispatch:{incident_id}:attempt:{attempt_count + 1}:"
            f"marshal:{marshal.id}"
        )
        return await self.create_offer(
            incident_id=incident_id,
            property_id=property_id,
            marshal_profile_id=marshal.id,
            expires_in_seconds=expires_in_seconds,
            idempotency_key=idempotency_key,
            actor_subject=actor_subject,
        )

    async def cancel(
        self,
        *,
        offer_id: int,
        actor_subject: str,
    ) -> Assignment:
        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Assignment offer not found.",
                404,
            )
        if offer.status not in {"OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"}:
            raise ApplicationError(
                "OFFER_CONFLICT",
                "The assignment is already terminal.",
                409,
            )

        return await self.repository.transition(
            offer,
            status="CANCELLED",
            now=datetime.now(timezone.utc),
            actor_subject=actor_subject,
            correlation_id=f"cancel:{offer.id}:{offer.version}",
        )

    async def marshal_progress(
        self,
        *,
        offer_id: int,
        user_id: int,
        status: str,
        expected_version: int,
        actor_subject: str,
    ) -> Assignment:
        transitions = {
            "EN_ROUTE": ("ACCEPTED",),
            "ON_SCENE": ("EN_ROUTE",),
            "COMPLETED": ("ON_SCENE",),
        }
        if status not in transitions:
            raise ApplicationError(
                "INVALID_ASSIGNMENT_TRANSITION",
                "Unsupported marshal progress state.",
                409,
            )

        # Read the assignment to determine which incident row to lock first.
        # Progress updates use source-incident -> assignment lock order.
        snapshot = await self.session.get(Assignment, offer_id)
        if snapshot is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Assignment offer not found.",
                404,
            )

        profile = await self.session.get(
            MarshalProfile,
            snapshot.marshal_profile_id,
        )
        if profile is None or profile.user_id != user_id:
            raise ApplicationError(
                "NOT_FOUND",
                "Assignment offer not found.",
                404,
            )

        if snapshot.security_event_id is not None:
            source_model = SecurityEvent
            source_id = snapshot.security_event_id
        else:
            source_model = ReporterIncident
            source_id = snapshot.reporter_incident_id

        if source_id is None:
            raise ApplicationError(
                "INVALID_INCIDENT_SOURCE",
                "Assignment has no incident source.",
                409,
            )

        source = await self.session.scalar(
            select(source_model)
            .where(source_model.id == source_id)
            .with_for_update()
        )
        if source is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Incident not found.",
                404,
            )

        offer = await self.repository.lock_offer(offer_id)
        if offer is None:
            raise ApplicationError(
                "NOT_FOUND",
                "Assignment offer not found.",
                404,
            )

        if offer.version != expected_version or offer.status not in transitions[status]:
            raise ApplicationError(
                "OFFER_CONFLICT",
                f"Cannot move assignment from {offer.status} to {status}.",
                409,
            )

        now = datetime.now(timezone.utc)
        result = await self.repository.transition(
            offer,
            status=status,
            now=now,
            actor_subject=actor_subject,
            correlation_id=f"progress:{offer.id}:{expected_version}",
        )

        if status == "COMPLETED":
            await self.repository.resolve_incident(
                offer.security_event_id,
                reporter_incident_id=offer.reporter_incident_id,
                actor_subject=actor_subject,
                correlation_id=f"progress:{offer.id}:{result.version}",
            )

        return result
