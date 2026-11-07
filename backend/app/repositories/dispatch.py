"""Transaction-neutral persistence for dispatch and notification workers."""

from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    AssignmentEvent,
    AuditRecord,
    IncidentStatusHistory,
    MarshalAvailability,
    MarshalProfile,
    NotificationAttempt,
    NotificationOutbox,
    PropertyMembership,
    ReporterIncident,
    ReporterIncidentTimeline,
    SecurityEvent,
    User,
)


class DispatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_offer(self, offer_id: int) -> Assignment | None:
        return await self.session.scalar(
            select(Assignment)
            .where(Assignment.id == offer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def find_by_idempotency_key(self, key: str) -> Assignment | None:
        return await self.session.scalar(
            select(Assignment).where(Assignment.idempotency_key == key)
        )

    async def add_offer(
        self,
        offer: Assignment,
        *,
        actor_subject: str,
        correlation_id: str,
    ) -> Assignment:
        self.session.add(offer)
        await self.session.flush()

        self.session.add(
            AssignmentEvent(
                assignment_id=offer.id,
                previous_status=None,
                new_status="OFFERED",
                actor_subject=actor_subject,
                correlation_id=correlation_id,
            )
        )
        self.session.add(
            NotificationOutbox(
                property_id=offer.property_id,
                security_event_id=offer.security_event_id,
                kind="ASSIGNMENT_OFFERED",
                destination=f"marshal:{offer.marshal_profile_id}",
                payload={
                    "assignment_id": offer.id,
                    "incident_id": offer.security_event_id,
                    "reporter_incident_id": offer.reporter_incident_id,
                    "expires_at": offer.expires_at.isoformat(),
                },
                dedupe_key=f"assignment:{offer.id}:offered",
                status="PENDING",
            )
        )
        await self.session.flush()
        return offer

    async def transition(
        self,
        offer: Assignment,
        *,
        status: str,
        now: datetime,
        actor_subject: str,
        correlation_id: str,
        reason: str | None = None,
        notify: bool = True,
    ) -> Assignment:
        previous = offer.status
        offer.status = status
        offer.version += 1

        if status == "ACCEPTED":
            offer.accepted_at = now
        if status in {"DECLINED", "EXPIRED", "CANCELLED", "COMPLETED"}:
            offer.closed_at = now

        self.session.add(
            AssignmentEvent(
                assignment_id=offer.id,
                previous_status=previous,
                new_status=status,
                actor_subject=actor_subject,
                correlation_id=correlation_id,
                reason=reason,
            )
        )

        if notify:
            self.session.add(
                NotificationOutbox(
                    property_id=offer.property_id,
                    security_event_id=offer.security_event_id,
                    kind=f"ASSIGNMENT_{status}",
                    destination=f"property:{offer.property_id}:dispatchers",
                    payload={
                        "assignment_id": offer.id,
                        "incident_id": offer.security_event_id,
                        "reporter_incident_id": offer.reporter_incident_id,
                        "status": status,
                        "version": offer.version,
                    },
                    dedupe_key=(
                        f"assignment:{offer.id}:{status.lower()}:{offer.version}"
                    ),
                    status="PENDING",
                )
            )

        await self.session.flush()
        return offer

    async def eligible_marshals(
        self,
        property_id: int,
        fresh_since: datetime,
        excluded_profile_ids: set[int] | None = None,
    ) -> list[MarshalProfile]:
        now = datetime.now(timezone.utc)

        active_load = (
            select(func.count(Assignment.id))
            .where(
                Assignment.marshal_profile_id == MarshalProfile.id,
                or_(
                    Assignment.status.in_(
                        ["ACCEPTED", "EN_ROUTE", "ON_SCENE"]
                    ),
                    and_(
                        Assignment.status == "OFFERED",
                        Assignment.expires_at > now,
                    ),
                ),
            )
            .correlate(MarshalProfile)
            .scalar_subquery()
        )

        statement = (
            select(MarshalProfile, active_load.label("active_load"))
            .join(User, User.id == MarshalProfile.user_id)
            .join(
                PropertyMembership,
                and_(
                    PropertyMembership.user_id == MarshalProfile.user_id,
                    PropertyMembership.property_id == MarshalProfile.property_id,
                ),
            )
            .join(
                MarshalAvailability,
                MarshalAvailability.marshal_profile_id == MarshalProfile.id,
            )
            .where(
                MarshalProfile.property_id == property_id,
                MarshalProfile.active.is_(True),
                MarshalProfile.verification_status == 'APPROVED',
                User.active.is_(True),
                PropertyMembership.active.is_(True),
                PropertyMembership.role == "marshal",
                MarshalAvailability.on_duty.is_(True),
                MarshalAvailability.available.is_(True),
                MarshalAvailability.updated_at >= fresh_since,
                active_load < MarshalProfile.capacity,
            )
            .order_by(active_load, MarshalProfile.id)
        )

        if excluded_profile_ids:
            statement = statement.where(
                MarshalProfile.id.not_in(excluded_profile_ids)
            )

        rows = (await self.session.execute(statement)).all()
        return [profile for profile, _load in rows]

    async def prior_attempt_profile_ids(self, incident_id: int) -> set[int]:
        statement = select(Assignment.marshal_profile_id).where(
            Assignment.security_event_id == incident_id,
            Assignment.status.in_(["DECLINED", "EXPIRED"]),
        )
        return set((await self.session.scalars(statement)).all())

    async def assignment_attempt_count(self, incident_id: int) -> int:
        count = await self.session.scalar(
            select(func.count(Assignment.id)).where(
                Assignment.security_event_id == incident_id
            )
        )
        return int(count or 0)

    async def due_offers(
        self,
        now: datetime,
        limit: int = 50,
    ) -> list[Assignment]:
        statement = (
            select(Assignment)
            .where(
                Assignment.status == "OFFERED",
                Assignment.expires_at <= now,
            )
            .order_by(Assignment.expires_at, Assignment.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(statement)).all())

    async def resolve_incident(
        self,
        incident_id: int | None,
        *,
        actor_subject: str,
        correlation_id: str,
        reporter_incident_id: int | None = None,
    ) -> None:
        if incident_id is not None:
            model = SecurityEvent
            source_id = incident_id
            resource_type = "security_event"
        else:
            model = ReporterIncident
            source_id = reporter_incident_id
            resource_type = "reporter_incident"

        if source_id is None:
            raise ValueError(
                "Either incident_id or reporter_incident_id must be provided"
            )

        incident = await self.session.scalar(
            select(model)
            .where(model.id == source_id)
            .with_for_update()
        )
        if incident is None or incident.status in {
            "RESOLVED",
            "CLOSED",
            "DISMISSED",
        }:
            return

        previous = incident.status
        incident.status = "RESOLVED"

        if incident_id is not None:
            self.session.add(
                IncidentStatusHistory(
                    security_event_id=incident.id,
                    previous_status=previous,
                    new_status="RESOLVED",
                    actor_subject=actor_subject,
                    reason="Marshal completed response",
                    correlation_id=correlation_id,
                )
            )
        else:
            self.session.add(
                ReporterIncidentTimeline(
                    incident_id=incident.id,
                    status="RESOLVED",
                    actor_subject=actor_subject,
                    message="Marshal completed response",
                )
            )

        self.session.add(
            AuditRecord(
                property_id=incident.property_id,
                actor_subject=actor_subject,
                action="INCIDENT_STATUS_CHANGED",
                resource_type=resource_type,
                resource_id=str(incident.id),
                correlation_id=correlation_id,
                details={
                    "previous_status": previous,
                    "new_status": "RESOLVED",
                    "reason": "Marshal completed response",
                },
            )
        )

    async def set_incident_status(
        self,
        incident: SecurityEvent,
        *,
        status: str,
        actor_subject: str,
        reason: str,
        correlation_id: str,
    ) -> None:
        previous = incident.status
        if previous == status:
            return

        incident.status = status
        self.session.add(
            IncidentStatusHistory(
                security_event_id=incident.id,
                previous_status=previous,
                new_status=status,
                actor_subject=actor_subject,
                reason=reason,
                correlation_id=correlation_id,
            )
        )
        self.session.add(
            AuditRecord(
                property_id=incident.property_id,
                actor_subject=actor_subject,
                action="INCIDENT_STATUS_CHANGED",
                resource_type="security_event",
                resource_id=str(incident.id),
                correlation_id=correlation_id,
                details={
                    "previous_status": previous,
                    "new_status": status,
                    "reason": reason,
                },
            )
        )

    async def add_no_marshal_escalation(
        self,
        incident: SecurityEvent,
        *,
        actor_subject: str,
        reason: str,
        correlation_id: str,
    ) -> None:
        await self.set_incident_status(
            incident,
            status="ESCALATED",
            actor_subject=actor_subject,
            reason=reason,
            correlation_id=correlation_id,
        )

        attempts = await self.assignment_attempt_count(incident.id)
        dedupe_key = (
            f"dispatch:{incident.id}:attempts:{attempts}:no-eligible-marshal"
        )
        existing = await self.session.scalar(
            select(NotificationOutbox.id).where(
                NotificationOutbox.dedupe_key == dedupe_key
            )
        )

        if existing is None:
            self.session.add(
                NotificationOutbox(
                    property_id=incident.property_id,
                    security_event_id=incident.id,
                    kind="DISPATCH_NO_ELIGIBLE_MARSHAL",
                    destination=f"property:{incident.property_id}:dispatchers",
                    payload={
                        "incident_id": incident.id,
                        "reason": reason,
                    },
                    dedupe_key=dedupe_key,
                    status="PENDING",
                )
            )


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim_batch(
        self,
        worker_id: str,
        now: datetime,
        limit: int = 50,
        destination_prefixes: tuple[str, ...] | None = None,
        exclude_destination_prefixes: tuple[str, ...] | None = None,
    ) -> list[NotificationOutbox]:
        destination_filter = None
        if destination_prefixes:
            destination_filter = or_(*[
                NotificationOutbox.destination.startswith(prefix)
                for prefix in destination_prefixes
            ])
        statement = select(NotificationOutbox).where(
            or_(
                NotificationOutbox.status.in_(["PENDING", "FAILED"]),
                and_(
                    NotificationOutbox.status == "PROCESSING",
                    NotificationOutbox.claimed_at < now - timedelta(minutes=5),
                ),
            ),
            NotificationOutbox.available_at <= now,
        )
        if destination_filter is not None:
            statement = statement.where(destination_filter)
        if exclude_destination_prefixes:
            statement = statement.where(or_(NotificationOutbox.destination.is_(None),
                ~or_(*[NotificationOutbox.destination.startswith(prefix) for prefix in exclude_destination_prefixes])))
        statement = statement.order_by(NotificationOutbox.id)
        statement = statement.limit(limit)
        statement = statement.with_for_update(skip_locked=True)
        rows = list((await self.session.scalars(statement)).all())

        for row in rows:
            row.status = "PROCESSING"
            row.claimed_by = worker_id
            row.claimed_at = now

        await self.session.flush()
        return rows

    async def record_attempt(
        self,
        outbox_id: int,
        *,
        provider: str,
        result: str,
        now: datetime,
        provider_reference: str | None = None,
        error: str | None = None,
        response_metadata: dict | None = None,
        max_attempts: int = 5,
        retry_base_seconds: int = 5,
    ) -> NotificationAttempt:
        row = await self.session.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .with_for_update()
        )
        if row is None:
            raise LookupError("outbox record not found")

        attempt_number = int(
            (
                await self.session.scalar(
                    select(func.count(NotificationAttempt.id)).where(
                        NotificationAttempt.outbox_id == outbox_id
                    )
                )
            )
            or 0
        ) + 1

        receipt = NotificationAttempt(
            outbox_id=row.id,
            attempt_number=attempt_number,
            provider=provider,
            provider_reference=provider_reference,
            status=result,
            error_code="DELIVERY_FAILED" if error else None,
            error_detail=error,
            response_metadata=response_metadata or {},
            attempted_at=now,
        )
        self.session.add(receipt)

        if result == "DELIVERED":
            row.status = "SENT"
            row.sent_at = now
        elif attempt_number >= max_attempts:
            row.status = "EXHAUSTED"
        else:
            row.status = "FAILED"
            delay = min(retry_base_seconds * (2 ** (attempt_number - 1)), 3600)
            row.available_at = now + timedelta(
                seconds=delay + random.uniform(0, delay * 0.2)
            )

        await self.session.flush()
        return receipt
