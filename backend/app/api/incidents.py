"""Authorized incident history, evidence, and command endpoints."""

from uuid import uuid4
from pydantic import AwareDatetime

from fastapi import APIRouter, Depends, Header, Query

from app.core.auth import Principal, require_scope
from app.core.dependencies import (
    get_event_service,
    get_incident_service,
    get_mutation_rate_limiter,
    get_event_publisher,
)
from app.core.exceptions import ApplicationError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.schemas.event import EventPage, EventResponse
from app.schemas.incident import EvidenceResponse, IncidentCommand, IncidentHistoryResponse
from app.services.incident_service import IncidentService
from app.services.event_service import EventService

router = APIRouter(prefix="/incidents", tags=["incidents"])


async def mutation_principal(
    principal: Principal = Depends(require_scope("write")),
    limiter: SlidingWindowRateLimiter = Depends(get_mutation_rate_limiter),
) -> Principal:
    retry_after = await limiter.check(principal.subject)
    if retry_after is not None:
        raise ApplicationError(
            "RATE_LIMITED",
            "Too many incident mutation requests.",
            429,
            {"Retry-After": str(retry_after)},
        )
    return principal


@router.get("", response_model=EventPage)
async def list_incidents(
    camera_id: int | None = Query(default=None, ge=1),
    event_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    start_time: AwareDatetime | None = Query(default=None),
    end_time: AwareDatetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_scope("read")),
    service: EventService = Depends(get_event_service),
) -> EventPage:
    incidents, total = await service.list(
        camera_id=camera_id, event_type=event_type, severity=severity,
        start_time=start_time, end_time=end_time,
        page=page,
        page_size=page_size,
        property_ids=principal.property_ids,
    )
    return EventPage(items=incidents, page=page, page_size=page_size, total=total)


@router.get("/{incident_id}", response_model=EventResponse)
async def get_incident(
    incident_id: int,
    principal: Principal = Depends(require_scope("read")),
    service: EventService = Depends(get_event_service),
) -> EventResponse:
    return await service.get(incident_id, property_ids=principal.property_ids)


@router.get("/{incident_id}/history", response_model=list[IncidentHistoryResponse])
async def incident_history(
    incident_id: int,
    principal: Principal = Depends(require_scope("read")),
    service: IncidentService = Depends(get_incident_service),
) -> list[IncidentHistoryResponse]:
    return await service.history(incident_id, principal.property_ids)


@router.get("/{incident_id}/evidence", response_model=list[EvidenceResponse])
async def incident_evidence(
    incident_id: int,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    principal: Principal = Depends(require_scope("read")),
    service: IncidentService = Depends(get_incident_service),
) -> list[EvidenceResponse]:
    return await service.evidence(
        incident_id,
        principal.property_ids,
        actor_subject=principal.subject,
        correlation_id=correlation_id or str(uuid4()),
    )


@router.post("/{incident_id}/commands", response_model=EventResponse)
async def incident_command(
    incident_id: int,
    command: IncidentCommand,
    principal: Principal = Depends(mutation_principal),
    service: IncidentService = Depends(get_incident_service),
) -> EventResponse:
    incident = await service.command(
        incident_id,
        command.command,
        actor_subject=principal.subject,
        property_ids=principal.property_ids,
        reason=command.reason,
        correlation_id=command.correlation_id,
    )
    # Service returns only after the transition/history transaction commits.
    await get_event_publisher().publish(incident)
    return incident
