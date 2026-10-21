"""Transactional incident history, evidence, and audit persistence."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence
from app.models.operations import AuditRecord, IncidentStatusHistory
from app.models.security_event import SecurityEvent


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_update(
        self, incident_id: int, property_ids: frozenset[int] | None
    ) -> SecurityEvent | None:
        statement = select(SecurityEvent).where(SecurityEvent.id == incident_id).with_for_update()
        if property_ids is not None:
            statement = statement.where(SecurityEvent.property_id.in_(property_ids))
        return await self.session.scalar(statement)

    async def list_history(
        self, incident_id: int, property_ids: frozenset[int] | None
    ) -> list[IncidentStatusHistory] | None:
        incident = await self.get_for_update(incident_id, property_ids)
        if incident is None:
            return None
        statement = (
            select(IncidentStatusHistory)
            .where(IncidentStatusHistory.security_event_id == incident_id)
            .order_by(IncidentStatusHistory.occurred_at, IncidentStatusHistory.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_evidence(
        self, incident_id: int, property_ids: frozenset[int] | None
    ) -> list[Evidence] | None:
        incident = await self.get_for_update(incident_id, property_ids)
        if incident is None:
            return None
        statement = select(Evidence).where(Evidence.event_id == incident_id).order_by(Evidence.timestamp)
        return list((await self.session.scalars(statement)).all())

    async def audit_evidence_access(
        self,
        incident: SecurityEvent,
        *,
        actor_subject: str,
        correlation_id: str,
    ) -> None:
        self.session.add(
            AuditRecord(
                property_id=incident.property_id,
                actor_subject=actor_subject,
                action="INCIDENT_EVIDENCE_LISTED",
                resource_type="security_event",
                resource_id=str(incident.id),
                correlation_id=correlation_id,
                details={},
            )
        )
        await self.session.commit()

    async def record_transition(
        self,
        incident: SecurityEvent,
        *,
        new_status: str,
        actor_subject: str,
        reason: str,
        correlation_id: str,
    ) -> None:
        previous_status = incident.status
        incident.status = new_status
        self.session.add(
            IncidentStatusHistory(
                security_event_id=incident.id,
                previous_status=previous_status,
                new_status=new_status,
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
                details={"previous_status": previous_status, "new_status": new_status, "reason": reason},
            )
        )
        await self.session.commit()
