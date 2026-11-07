"""Unified operator cases without replacing mobile or camera incident endpoints."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import browser_request, property_access
from app.api import evidence as evidence_api
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.dependencies import get_session, get_event_publisher, get_mutation_rate_limiter
from app.core.exceptions import ApplicationError
from app.models import Assignment, AuditRecord, NotificationAttempt, NotificationOutbox, User
from app.repositories.dispatch import DispatchRepository
from app.schemas.case import (AssignmentCancel, CaseAssignmentPage, CaseCommand, CaseDetail,
    CaseEvidencePage, CaseOffer, CasePage, CaseSeverity, CaseSource, CaseStatus, CaseTimelinePage, OperatorMarshal)
from app.schemas.dispatch import OfferView
from app.schemas.report import IncidentReport, NotificationReport
from app.services.case_service import CaseService, assignment_filter
from app.services.dispatch_service import DispatchService
from app.services.reporter_storage import ReporterStorage

router = APIRouter(prefix="/dashboard/properties/{property_id}/cases", tags=["operator-cases"],
                   dependencies=[Depends(browser_request)])


async def operator(principal: Principal = Depends(property_access)) -> Principal:
    # Property-wide manual reports contain private descriptions/evidence. Existing
    # reporter users keep their original own-report API, not this operator queue.
    if "write" not in principal.scopes:
        raise ApplicationError("FORBIDDEN", "Owner or dispatcher access is required.", 403)
    return principal


async def mutation(principal: Principal = Depends(operator)) -> Principal:
    retry = await get_mutation_rate_limiter().check(principal.subject)
    if retry is not None:
        raise ApplicationError("RATE_LIMITED", "Too many changes. Try again shortly.", 429, {"Retry-After": str(retry)})
    return principal


@router.get("", response_model=CasePage)
async def list_cases(property_id: int, source: CaseSource | None = None, status: CaseStatus | None = None,
                     severity: CaseSeverity | None = None,
                     page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                     principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    return await CaseService(session).list(property_id, source=source, status=status, severity=severity,
                                          page=page, page_size=page_size)


@router.get("/overview")
async def overview(property_id: int, principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    return await CaseService(session).overview(property_id)


@router.get("/eligible-marshals", response_model=list[OperatorMarshal])
async def eligible_marshals(property_id: int, principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    items = await DispatchRepository(session).eligible_marshals(property_id, datetime.now(timezone.utc) - timedelta(minutes=5))
    users = {user.id: user for user in (await session.scalars(select(User).where(User.id.in_([item.user_id for item in items])))).all()} if items else {}
    return [OperatorMarshal(id=item.id, name=users[item.user_id].display_name,
        service_area=item.service_area, capacity=item.capacity) for item in items]


@router.get("/{source}/{source_id}", response_model=CaseDetail)
async def detail(property_id: int, source: CaseSource, source_id: int,
                 principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    return await CaseService(session).detail(property_id, source, source_id)


@router.get("/{source}/{source_id}/timeline", response_model=CaseTimelinePage)
async def timeline(property_id: int, source: CaseSource, source_id: int,
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                   principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    return await CaseService(session).timeline(property_id, source, source_id, page, page_size)


@router.get("/{source}/{source_id}/evidence", response_model=CaseEvidencePage)
async def evidence(property_id: int, source: CaseSource, source_id: int,
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                   principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    result = await CaseService(session).evidence(property_id, source, source_id, page, page_size)
    await audit(session, property_id, source, source_id, principal.subject, "CASE_EVIDENCE_LISTED")
    return result


@router.get("/{source}/{source_id}/report", response_model=IncidentReport)
async def report(property_id: int, source: CaseSource, source_id: int,
                 principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    """Build an audited report for an authorized property's incident.

    Include every timeline and evidence-metadata page, assignment history and
    matching notification attempts. Media bytes and historical GPS are excluded.
    Request a retry if pagination can no longer supply the expected records.
    """
    service = CaseService(session)
    incident = await service.detail(property_id, source, source_id)
    timeline_page = await service.timeline(property_id, source, source_id, 1, 100)
    timeline = list(timeline_page.items)
    page = 1
    while len(timeline) < timeline_page.total:
        page += 1
        next_page = await service.timeline(property_id, source, source_id, page, 100)
        if not next_page.items:
            raise ApplicationError('REPORT_CHANGED', 'Incident history changed while generating the report. Retry.', 409)
        timeline.extend(next_page.items)
    evidence_page = await service.evidence(property_id, source, source_id, 1, 100)
    evidence = list(evidence_page.items)
    page = 1
    while len(evidence) < evidence_page.total:
        page += 1
        next_page = await service.evidence(property_id, source, source_id, page, 100)
        if not next_page.items:
            raise ApplicationError('REPORT_CHANGED', 'Incident evidence changed while generating the report. Retry.', 409)
        evidence.extend(next_page.items)
    assignments = list((await session.scalars(
        select(Assignment).where(
            Assignment.property_id == property_id,
            assignment_filter(source, source_id),
        ).order_by(Assignment.offered_at, Assignment.id)
    )).all())
    outboxes = list((await session.scalars(
        select(NotificationOutbox).where(
            NotificationOutbox.property_id == property_id,
            NotificationOutbox.security_event_id == source_id if source == 'camera'
            else NotificationOutbox.payload['reporter_incident_id'].as_integer() == source_id,
        ).order_by(NotificationOutbox.created_at, NotificationOutbox.id)
    )).all())
    notification_rows = []
    for row in outboxes:
        attempts = list((await session.scalars(
            select(NotificationAttempt).where(NotificationAttempt.outbox_id == row.id)
            .order_by(NotificationAttempt.attempt_number)
        )).all())
        notification_rows.append(NotificationReport(
            kind=row.kind,
            destination=row.destination,
            status=row.status,
            attempts=len(attempts),
            last_attempt_at=attempts[-1].attempted_at if attempts else None,
        ))
    occurred_at = incident.occurred_at
    resolved_at = next(
        (item.occurred_at for item in reversed(timeline)
         if item.status in {"RESOLVED", "CLOSED", "COMPLETED"}),
        None,
    )
    duration = (resolved_at - occurred_at).total_seconds() if resolved_at else None
    await audit(session, property_id, source, source_id, principal.subject, "CASE_REPORT_GENERATED")
    return IncidentReport(
        generated_at=datetime.now(timezone.utc),
        incident=incident,
        timeline=timeline,
        evidence=evidence,
        assignments=[OfferView.model_validate(item) for item in assignments],
        notifications=notification_rows,
        metrics={
            "response_duration_seconds": duration,
            "dispatch_count": len(assignments),
            "notification_count": len(notification_rows),
        },
        tracking={
            "location_history_included": False,
            "latest_location_included": bool(
                incident.latest_assignment and incident.latest_assignment.responder_location
            ),
            "note": "Historical GPS points are not retained in this deployment.",
        },
    )


async def audit(session, property_id, source, source_id, actor, action, details=None):
    session.add(AuditRecord(property_id=property_id, actor_subject=actor, action=action,
        resource_type=f"{source}_incident", resource_id=str(source_id), correlation_id=str(uuid4()), details=details or {}))
    await session.commit()


@router.post("/{source}/{source_id}/commands", response_model=CaseDetail)
async def command(property_id: int, source: CaseSource, source_id: int, body: CaseCommand,
                  principal: Principal = Depends(mutation), session: AsyncSession = Depends(get_session)):
    result = await CaseService(session).command(property_id, source, source_id, body, principal.subject)
    await publish(property_id, source, source_id)
    return result


async def publish(property_id, source, source_id):
    await get_event_publisher().publish_case(property_id, f"{source}:{source_id}")


@router.get("/{source}/{source_id}/assignments", response_model=CaseAssignmentPage)
async def assignments(property_id: int, source: CaseSource, source_id: int,
                      page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                      principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    await CaseService(session).get(property_id, source, source_id)
    statement = select(Assignment).where(Assignment.property_id == property_id, assignment_filter(source, source_id))
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    items = list((await session.scalars(statement.order_by(Assignment.offered_at.desc(), Assignment.id.desc())
                                      .offset((page - 1) * page_size).limit(page_size))).all())
    return CaseAssignmentPage(items=items, total=total, page=page, page_size=page_size)


@router.post("/{source}/{source_id}/offers", response_model=OfferView, status_code=201)
async def offer(property_id: int, source: CaseSource, source_id: int, body: CaseOffer,
                principal: Principal = Depends(mutation), session: AsyncSession = Depends(get_session)):
    # Verify even a replay against this path, not just the submitted key.
    await CaseService(session).get(property_id, source, source_id)
    item = await DispatchService(session).create_offer(property_id=property_id,
        incident_id=source_id if source == "camera" else None,
        reporter_incident_id=source_id if source == "reporter" else None,
        marshal_profile_id=body.marshal_profile_id, expires_in_seconds=body.expires_in_seconds,
        idempotency_key=body.idempotency_key, actor_subject=principal.subject)
    await session.commit()
    await publish(property_id, source, source_id)
    return item


@router.post("/{source}/{source_id}/assignments/{assignment_id}/cancel", response_model=OfferView)
async def cancel(property_id: int, source: CaseSource, source_id: int, assignment_id: int, body: AssignmentCancel,
                 principal: Principal = Depends(mutation), session: AsyncSession = Depends(get_session)):
    await CaseService(session).get(property_id, source, source_id, lock=True)
    item = await session.scalar(select(Assignment).where(Assignment.id == assignment_id,
        Assignment.property_id == property_id, assignment_filter(source, source_id)).with_for_update())
    if item is None:
        raise ApplicationError("ASSIGNMENT_NOT_FOUND", "The assignment does not exist for this incident.", 404)
    if item.version != body.expected_version:
        raise ApplicationError("OFFER_CONFLICT", "The assignment has changed. Reload before cancelling.", 409)
    result = await DispatchService(session).cancel(offer_id=item.id, actor_subject=principal.subject)
    await session.commit()
    await publish(property_id, source, source_id)
    return result


@router.post("/{source}/{source_id}/evidence/{evidence_id}/access")
async def grant(property_id: int, source: CaseSource, source_id: int, evidence_id: int,
                principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    incident, item = await CaseService(session).evidence_record(property_id, source, source_id, evidence_id)
    if source == "reporter":
        await ReporterStorage(get_settings()).ensure(item.file_path)
    elif not evidence_api.frigate_snapshot(item, incident):
        evidence_api.media_path(item.file_path)
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    token = jwt.encode({"aud": "operator-case-evidence", "sub": principal.subject, "exp": expires,
        "source": source, "source_id": source_id, "property_id": property_id, "evidence_id": evidence_id},
        settings.jwt_secret, algorithm=settings.jwt_algorithm)
    await audit(session, property_id, source, source_id, principal.subject, "CASE_EVIDENCE_ACCESS_GRANTED", {"evidence_id": evidence_id})
    return {"url": f"/api/v1/dashboard/properties/{property_id}/cases/{source}/{source_id}/evidence/{evidence_id}/content?grant={token}",
            "expires_at": expires.isoformat()}


@router.get("/{source}/{source_id}/evidence/{evidence_id}/content")
async def content(property_id: int, source: CaseSource, source_id: int, evidence_id: int,
                  grant: str = Query(min_length=1, max_length=4096),
                  range_header: str | None = Header(None, alias="Range"),
                  principal: Principal = Depends(operator), session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    try:
        claims = jwt.decode(grant, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience="operator-case-evidence",
            options={"require": ["aud", "exp", "sub", "source", "source_id", "property_id", "evidence_id"]})
        if (claims["sub"], claims["source"], claims["source_id"], claims["property_id"], claims["evidence_id"]) != (
                principal.subject, source, source_id, property_id, evidence_id):
            raise ValueError("Grant binding mismatch")
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise ApplicationError("INVALID_MEDIA_GRANT", "The evidence grant is invalid or expired.", 401) from None
    incident, item = await CaseService(session).evidence_record(property_id, source, source_id, evidence_id)
    if source == "camera":
        return await evidence_api.serve_evidence(item, incident, principal, session)
    if item.media_type not in {"image/jpeg", "image/png", "video/mp4"}:
        raise ApplicationError("UNSUPPORTED_MEDIA", "This evidence format cannot be viewed.", 415)
    await audit(session, property_id, source, source_id, principal.subject, "CASE_EVIDENCE_CONTENT_ACCESSED", {"evidence_id": evidence_id})
    return await ReporterStorage(settings).serve(item.file_path, item.media_type, range_header)
