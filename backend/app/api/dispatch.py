"""Authenticated, property-scoped dispatch orchestration endpoints."""
from datetime import datetime, timedelta, timezone
import hashlib
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_session, get_event_publisher
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import get_reporter
from app.models import Assignment, MarshalAvailability, MarshalProfile, Property, PropertyMembership, ReporterIncident, SecurityEvent, User
from app.repositories.dispatch import DispatchRepository
from app.schemas.dispatch import (AssignmentProgress, AvailabilityUpdate, BroadcastOffer, DispatchOutcome,
    DispatchRequest, EligibleMarshal, OfferCreate, OfferResponse, OfferView)
from app.services.dispatch_service import DispatchService

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


async def publish_assignment_update(offer):
    source, source_id = ("camera", offer.security_event_id) if offer.security_event_id is not None else ("reporter", offer.reporter_incident_id)
    await get_event_publisher().publish_case(offer.property_id, f"{source}:{source_id}")


async def require_role(session: AsyncSession, user_id: int, property_id: int,
                       roles: set[str]) -> PropertyMembership:
    membership = await session.scalar(select(PropertyMembership).join(Property).where(
        PropertyMembership.user_id == user_id, PropertyMembership.property_id == property_id,
        PropertyMembership.active.is_(True), Property.active.is_(True)))
    if membership is None or membership.role not in roles:
        raise ApplicationError("FORBIDDEN", "You cannot perform dispatch actions for this property.", 403)
    return membership


@router.get("/eligible-marshals", response_model=list[EligibleMarshal])
async def eligible_marshals(property_id: int = Query(ge=1), user: User = Depends(get_reporter),
                             session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, property_id, {"owner", "dispatcher"})
    profiles = await DispatchRepository(session).eligible_marshals(
        property_id, datetime.now(timezone.utc) - timedelta(minutes=5))
    users = {item.id: item for item in (await session.scalars(select(User).where(User.id.in_([p.user_id for p in profiles])))).all()}
    return [EligibleMarshal(id=p.id, user_id=p.user_id, service_area=p.service_area,
                            capacity=p.capacity, name=users[p.user_id].display_name) for p in profiles]


@router.get('/assignment', response_model=OfferView | None)
async def current_assignment(property_id: int = Query(ge=1), incident_id: int | None = Query(None, ge=1),
                             reporter_incident_id: int | None = Query(None, ge=1),
                             user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, property_id, {'owner', 'dispatcher'})
    if (incident_id is None) == (reporter_incident_id is None):
        raise ApplicationError('INVALID_INCIDENT_SOURCE', 'Provide exactly one incident source.', 422)
    model, source_id = (SecurityEvent, incident_id) if incident_id is not None else (ReporterIncident, reporter_incident_id)
    if await session.scalar(select(model.id).where(model.id == source_id, model.property_id == property_id)) is None:
        raise ApplicationError('NOT_FOUND', 'Incident not found.', 404)
    source_filter = Assignment.security_event_id == incident_id if incident_id is not None else Assignment.reporter_incident_id == reporter_incident_id
    return await session.scalar(select(Assignment).where(Assignment.property_id == property_id, source_filter)
                                .order_by(case((Assignment.status.in_(['ACCEPTED', 'EN_ROUTE', 'ON_SCENE']), 0),
                                               (Assignment.status == 'OFFERED', 1), else_=2),
                                          Assignment.offered_at.desc(), Assignment.id.desc()).limit(1))


@router.put("/marshal/availability", response_model=EligibleMarshal)
async def update_availability(body: AvailabilityUpdate, user: User = Depends(get_reporter),
                              session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, body.property_id, {"marshal"})
    profile = await session.scalar(select(MarshalProfile).where(MarshalProfile.user_id == user.id,
        MarshalProfile.property_id == body.property_id).with_for_update())
    if profile is None:
        raise ApplicationError("FORBIDDEN", "No marshal profile exists for this property.", 403)
    if (body.on_duty or body.available) and profile.verification_status != 'APPROVED':
        raise ApplicationError('ONBOARDING_REQUIRED', 'Complete onboarding and administrator review before going on duty.', 403)
    availability = await session.get(MarshalAvailability, profile.id, with_for_update=True)
    if availability is None:
        availability = MarshalAvailability(marshal_profile_id=profile.id)
        session.add(availability)
    availability.on_duty, availability.available = body.on_duty, body.available
    availability.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return profile


@router.post("/offers", response_model=OfferView, status_code=201)
async def create_offer(body: OfferCreate, user: User = Depends(get_reporter),
                       session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, body.property_id, {"owner", "dispatcher"})
    offer = await DispatchService(session).create_offer(incident_id=body.incident_id,
        reporter_incident_id=body.reporter_incident_id,
        property_id=body.property_id, marshal_profile_id=body.marshal_profile_id,
        expires_in_seconds=body.expires_in_seconds, idempotency_key=body.idempotency_key,
        actor_subject=f"reporter:{user.id}")
    await session.commit()
    await publish_assignment_update(offer)
    return offer


@router.post('/offers/broadcast', response_model=list[OfferView], status_code=201)
async def broadcast_offers(body: BroadcastOffer, user: User = Depends(get_reporter),
                           session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, body.property_id, {'owner', 'dispatcher'})
    if session.bind.dialect.name == 'sqlite':
        # sqlite3 legacy transaction mode otherwise lets the first SAVEPOINT
        # commit independently, breaking all-or-nothing batch creation.
        await session.execute(text('BEGIN'))
    await session.scalar(select(Property).where(Property.id == body.property_id).with_for_update())
    ids = sorted(set(body.marshal_profile_ids))
    if any(value <= 0 for value in ids):
        raise ApplicationError('INVALID_MARSHAL', 'Select valid responders.', 422)
    # Bind the entire selected set to the request key; all offers commit together.
    fingerprint = hashlib.sha256(f'{body.property_id}:{body.incident_id}:{body.reporter_incident_id}:{ids}:{body.expires_in_seconds}'.encode()).hexdigest()[:20]
    prefix = 'broadcast:' + hashlib.sha256(f'{user.id}:{body.property_id}:{body.idempotency_key}'.encode()).hexdigest()[:32]
    existing = (await session.scalars(select(Assignment).where(Assignment.idempotency_key.like(prefix + ':%')))).all()
    if existing and any(f':{fingerprint}:' not in item.idempotency_key for item in existing):
        raise ApplicationError('IDEMPOTENCY_CONFLICT', 'This request key belongs to another selection.', 409)
    service = DispatchService(session)
    offers = []
    for profile_id in ids:
        offers.append(await service.create_offer(incident_id=body.incident_id, reporter_incident_id=body.reporter_incident_id,
            property_id=body.property_id, marshal_profile_id=profile_id, expires_in_seconds=body.expires_in_seconds,
            idempotency_key=f'{prefix}:{fingerprint}:{profile_id}', actor_subject=f'reporter:{user.id}', broadcast=True))
    await session.commit()
    for offer in offers:
        await publish_assignment_update(offer)
    return offers


@router.post("/incidents/{incident_id}/dispatch", response_model=DispatchOutcome)
async def dispatch_next_marshal(incident_id: int, body: DispatchRequest,
                                user: User = Depends(get_reporter),
                                session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, body.property_id, {"owner", "dispatcher"})
    offer = await DispatchService(session).dispatch_next(incident_id=incident_id,
        property_id=body.property_id, expires_in_seconds=body.expires_in_seconds,
        actor_subject=f"reporter:{user.id}", correlation_id=body.correlation_id)
    await session.commit()
    if offer is None:
        return DispatchOutcome(status="ESCALATED", incident_id=incident_id,
            reason="No eligible marshal or the provisional offer-attempt limit was reached")
    return DispatchOutcome(status="OFFERED", incident_id=incident_id, assignment=offer)


async def _respond(offer_id: int, body: OfferResponse, accept: bool,
                   user: User, session: AsyncSession):
    offer = await DispatchService(session).respond(offer_id=offer_id, user_id=user.id,
        accept=accept, expected_version=body.expected_version, actor_subject=f"marshal:{user.id}")
    await require_role(session, user.id, offer.property_id, {"marshal"})
    await session.commit()
    await publish_assignment_update(offer)
    return offer


@router.post("/offers/{offer_id}/accept", response_model=OfferView)
async def accept_offer(offer_id: int, body: OfferResponse, user: User = Depends(get_reporter),
                       session: AsyncSession = Depends(get_session)):
    return await _respond(offer_id, body, True, user, session)


@router.post("/offers/{offer_id}/decline", response_model=OfferView)
async def decline_offer(offer_id: int, body: OfferResponse, user: User = Depends(get_reporter),
                        session: AsyncSession = Depends(get_session)):
    return await _respond(offer_id, body, False, user, session)


@router.post("/offers/{offer_id}/progress", response_model=OfferView)
async def update_progress(offer_id: int, body: AssignmentProgress,
                          user: User = Depends(get_reporter),
                          session: AsyncSession = Depends(get_session)):
    offer = await DispatchService(session).marshal_progress(offer_id=offer_id,
        user_id=user.id, status=body.status, expected_version=body.expected_version,
        actor_subject=f"marshal:{user.id}")
    await require_role(session, user.id, offer.property_id, {"marshal"})
    await session.commit()
    await publish_assignment_update(offer)
    return offer


async def _dispatcher_offer(offer_id: int, property_id: int, user: User,
                            session: AsyncSession):
    await require_role(session, user.id, property_id, {"owner", "dispatcher"})
    offer = await session.scalar(select(Assignment).where(Assignment.id == offer_id))
    if offer is None or offer.property_id != property_id:
        raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
    return offer


@router.post("/offers/{offer_id}/expire", response_model=OfferView)
async def expire_offer(offer_id: int, property_id: int = Query(ge=1),
                       user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await _dispatcher_offer(offer_id, property_id, user, session)
    offer = await DispatchService(session).expire(offer_id=offer_id, actor_subject=f"reporter:{user.id}")
    await session.commit()
    await publish_assignment_update(offer)
    return offer


@router.post("/offers/{offer_id}/cancel", response_model=OfferView)
async def cancel_offer(offer_id: int, property_id: int = Query(ge=1),
                       user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await _dispatcher_offer(offer_id, property_id, user, session)
    offer = await DispatchService(session).cancel(offer_id=offer_id, actor_subject=f"reporter:{user.id}")
    await session.commit()
    await publish_assignment_update(offer)
    return offer
