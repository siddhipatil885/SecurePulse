"""Incident commands with explicit legal transitions."""

from app.core.exceptions import ApplicationError
from app.models.evidence import Evidence
from app.models.operations import IncidentStatusHistory
from app.models.security_event import SecurityEvent
from app.repositories.incidents import IncidentRepository


class IncidentService:
    _commands = {
        "acknowledge": ({"OPEN"}, "ACKNOWLEDGED"),
        "resolve": ({"OPEN", "ACKNOWLEDGED"}, "RESOLVED"),
        "dismiss": ({"OPEN", "ACKNOWLEDGED", "UNCLASSIFIED"}, "DISMISSED"),
        "reopen": ({"RESOLVED", "DISMISSED", "CLOSED"}, "OPEN"),
    }

    def __init__(self, repository: IncidentRepository) -> None:
        self.repository = repository

    async def history(self, incident_id: int, property_ids: frozenset[int] | None) -> list[IncidentStatusHistory]:
        history = await self.repository.list_history(incident_id, property_ids)
        if history is None:
            raise ApplicationError("INCIDENT_NOT_FOUND", "The requested incident does not exist.", 404)
        return history

    async def evidence(
        self,
        incident_id: int,
        property_ids: frozenset[int] | None,
        *,
        actor_subject: str,
        correlation_id: str,
    ) -> list[Evidence]:
        evidence = await self.repository.list_evidence(incident_id, property_ids)
        if evidence is None:
            raise ApplicationError("INCIDENT_NOT_FOUND", "The requested incident does not exist.", 404)
        incident = await self.repository.get(incident_id, property_ids)
        if incident is None:
            raise ApplicationError("INCIDENT_NOT_FOUND", "The requested incident does not exist.", 404)
        await self.repository.audit_evidence_access(
            incident,
            actor_subject=actor_subject,
            correlation_id=correlation_id,
        )
        return evidence

    async def command(
        self,
        incident_id: int,
        command: str,
        *,
        actor_subject: str,
        property_ids: frozenset[int] | None,
        reason: str,
        correlation_id: str,
    ) -> SecurityEvent:
        incident = await self.repository.get_for_update(incident_id, property_ids)
        if incident is None:
            raise ApplicationError("INCIDENT_NOT_FOUND", "The requested incident does not exist.", 404)
        allowed, new_status = self._commands[command]
        if incident.status not in allowed:
            raise ApplicationError(
                "INVALID_INCIDENT_TRANSITION",
                f"Cannot {command} an incident in state {incident.status}.",
                409,
            )
        await self.repository.record_transition(
            incident,
            new_status=new_status,
            actor_subject=actor_subject,
            reason=reason,
            correlation_id=correlation_id,
        )
        return incident
