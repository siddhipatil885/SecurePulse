"""Security event read endpoints."""

from datetime import datetime
from pydantic import AwareDatetime

from fastapi import APIRouter, Depends, Query

from app.core.auth import Principal, require_scope
from app.core.dependencies import get_event_service
from app.schemas.event import EventPage, EventResponse
from app.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventPage, summary="List security events")
async def list_events(
    camera_id: int | None = Query(default=None, ge=1),
    event_type: str | None = Query(default=None, min_length=1),
    severity: str | None = Query(default=None, min_length=1),
    start_time: AwareDatetime | None = Query(default=None),
    end_time: AwareDatetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_scope("read")),
    service: EventService = Depends(get_event_service),
) -> EventPage:
    events, total = await service.list(
        camera_id=camera_id,
        event_type=event_type,
        severity=severity,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
        property_ids=principal.property_ids,
    )
    return EventPage(items=events, page=page, page_size=page_size, total=total)


@router.get("/{event_id}", response_model=EventResponse, summary="Get a security event")
async def get_event(
    event_id: int,
    principal: Principal = Depends(require_scope("read")),
    service: EventService = Depends(get_event_service),
) -> EventResponse:
    return await service.get(event_id, property_ids=principal.property_ids)
