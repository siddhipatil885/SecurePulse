"""Authenticated, property-scoped dispatch orchestration endpoints."""
from datetime import datetime, timedelta, timezone
import hashlib
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_session, get_event_publisher
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import get_reporter
from app.models import Assignment, AssignmentMessage, AuditRecord, MarshalAvailability, MarshalLocationHistory, MarshalProfile, Property, PropertyMembership, ReporterIncident, SecurityEvent, User
from app.repositories.dispatch import DispatchRepository
from app.schemas.dispatch import (AssignmentProgress, AvailabilityUpdate, BroadcastOffer, DispatchOutcome,
    DispatchRequest, EligibleMarshal, OfferCreate, OfferResponse, OfferView, ReporterDispatchOutcome,
    ResponderLocation, SupervisorReview, TeamOfferCreate)
from app.services.dispatch_service import DispatchService
from app.services.location import MIN_MOVING_SPEED_MPS, distance_metres, estimate_eta_seconds

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


class AssignmentChatMessage(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    client_message_id: str = Field(min_length=8, max_length=80)


async def chat_assignment(offer_id: int, property_id: int, user: User, session: AsyncSession):
    item = await session.scalar(select(Assignment).where(Assignment.id == offer_id,
        Assignment.property_id == property_id))
    if item is None:
        raise ApplicationError("NOT_FOUND", "Assignment not found.", 404)
    profile = await session.scalar(select(MarshalProfile).where(MarshalProfile.user_id == user.id,
        MarshalProfile.id == item.marshal_profile_id))
    if profile is None:
        await require_role(session, user.id, property_id, {"owner", "dispatcher"})
    if item.status not in {"ACCEPTED", "EN_ROUTE", "ON_SCENE", "INVESTIGATING", "PENDING_REVIEW", "COMPLETED"}:
        raise ApplicationError("ASSIGNMENT_NOT_ACTIVE", "This assignment conversation is unavailable.", 409)
    return item


def assignment_thread(item: Assignment) -> str:
    return f"team:{item.team_key}" if item.team_key else f"assignment:{item.id}"


@router.get("/offers/{offer_id}/messages")
async def read_assignment_messages(offer_id: int, property_id: int = Query(ge=1),
        user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    item = await chat_assignment(offer_id, property_id, user, session)
    rows = (await session.execute(select(AssignmentMessage, User.display_name).join(
        User, User.id == AssignmentMessage.sender_user_id).where(
        AssignmentMessage.thread_key == assignment_thread(item)).order_by(AssignmentMessage.id.desc()).limit(100))).all()
    return {"items": [{"id": message.id, "sender": display_name, "body": message.body,
        "created_at": message.created_at, "mine": message.sender_user_id == user.id}
        for message, display_name in reversed(rows)]}


@router.post("/offers/{offer_id}/messages", status_code=201)
async def send_assignment_message(offer_id: int, body: AssignmentChatMessage,
        property_id: int = Query(ge=1), user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    item = await chat_assignment(offer_id, property_id, user, session)
    if item.status == "COMPLETED":
        raise ApplicationError("ASSIGNMENT_NOT_ACTIVE", "This assignment conversation is closed.", 409)
    text = body.body.strip()
    if not text:
        raise ApplicationError("INVALID_MESSAGE", "Enter a message.", 422)
    existing = await session.scalar(select(AssignmentMessage).where(
        AssignmentMessage.sender_user_id == user.id, AssignmentMessage.client_message_id == body.client_message_id))
    if existing is None:
        existing = AssignmentMessage(assignment_id=item.id, property_id=item.property_id,
            sender_user_id=user.id, thread_key=assignment_thread(item),
            client_message_id=body.client_message_id, body=text)
        session.add(existing)
        session.add(AuditRecord(property_id=item.property_id, actor_subject=f"reporter:{user.id}",
            action="ASSIGNMENT_MESSAGE_SENT", resource_type="assignment", resource_id=str(item.id),
            correlation_id=f"message:{body.client_message_id}", details={}))
    await session.commit()
    await publish_assignment_update(item)
    return {"id": existing.id, "body": existing.body}


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


async def can_view_assignment_location(principal, property_id, assignment_id, session):
    if not principal.can_access_property(property_id):
        return False
    assignment = await session.get(Assignment, assignment_id)
    if not assignment or assignment.property_id != property_id or assignment.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'}:
        return False
    if principal.subject.startswith('reporter:'):
        try:
            user = await session.get(User, int(principal.subject.removeprefix('reporter:')))
        except ValueError:
            return False
    else:
        user = await session.scalar(select(User).where(User.subject == principal.subject))
    if not user or not user.active:
        return False
    try:
        membership = await require_role(session, user.id, property_id, {'owner', 'dispatcher', 'marshal'})
    except ApplicationError:
        return False
    if membership.role in {'owner', 'dispatcher'}:
        return True
    profile = await session.get(MarshalProfile, assignment.marshal_profile_id)
    return bool(profile and profile.active and profile.user_id == user.id)


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
    assignment = await session.scalar(select(Assignment).where(Assignment.property_id == property_id, source_filter)
                                      .order_by(case((Assignment.status.in_(['ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW']), 0),
                                                     (Assignment.status == 'OFFERED', 1), else_=2),
                                                Assignment.offered_at.desc(), Assignment.id.desc()).limit(1))
    if assignment is None:
        return None
    response = OfferView.model_validate(assignment)
    if assignment.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'}:
        return response
    availability = await session.get(MarshalAvailability, assignment.marshal_profile_id)
    if not availability or availability.latitude is None or availability.longitude is None or not availability.location_updated_at:
        return response
    location_time = availability.location_updated_at
    if location_time.tzinfo is None:
        location_time = location_time.replace(tzinfo=timezone.utc)
    if location_time < datetime.now(timezone.utc) - timedelta(minutes=2):
        return response
    destination = await session.get(model, source_id)
    target_lat = getattr(destination, 'latitude', None)
    target_lon = getattr(destination, 'longitude', None)
    eta_fields = {}
    if target_lat is not None and target_lon is not None:
        distance = distance_metres(availability.latitude, availability.longitude, target_lat, target_lon)
        eta_fields = {
            'distance_m': round(distance, 1),
            'eta_seconds': estimate_eta_seconds(distance, availability.location_speed_mps),
            'eta_source': 'gps_speed' if availability.location_speed_mps is not None
                and availability.location_speed_mps >= MIN_MOVING_SPEED_MPS else 'urban_fallback',
        }
    response.responder_location = ResponderLocation(
        latitude=availability.latitude, longitude=availability.longitude,
        accuracy_m=availability.location_accuracy_m, heading=availability.location_heading,
        speed_mps=availability.location_speed_mps, updated_at=location_time, **eta_fields)
    return response


@router.get('/assignment/location-history')
async def assignment_location_history(property_id: int = Query(ge=1), assignment_id: int = Query(ge=1),
                                      user: User = Depends(get_reporter),
                                      session: AsyncSession = Depends(get_session)):
    """Return at most 500 recent GPS points for a property-authorized assignment."""
    await require_role(session, user.id, property_id, {'owner', 'dispatcher'})
    assignment = await session.scalar(select(Assignment).where(
        Assignment.id == assignment_id, Assignment.property_id == property_id))
    if assignment is None:
        raise ApplicationError('NOT_FOUND', 'Assignment not found for this property.', 404)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    await session.execute(delete(MarshalLocationHistory).where(
        MarshalLocationHistory.property_id == property_id,
        MarshalLocationHistory.recorded_at < cutoff,
    ))
    points = (await session.scalars(select(MarshalLocationHistory).where(
        MarshalLocationHistory.assignment_id == assignment_id,
        MarshalLocationHistory.recorded_at >= cutoff,
    ).order_by(MarshalLocationHistory.recorded_at.desc()).limit(500))).all()
    return {'assignment_id': assignment_id, 'retention_hours': 24, 'items': [
        {'latitude': item.latitude, 'longitude': item.longitude, 'accuracy_m': item.accuracy_m,
         'heading': item.heading, 'speed_mps': item.speed_mps, 'recorded_at': item.recorded_at}
        for item in reversed(points)
    ]}


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


@router.post('/offers/team', response_model=list[OfferView], status_code=201)
async def create_team_offers(body: TeamOfferCreate, user: User = Depends(get_reporter),
                             session: AsyncSession = Depends(get_session)):
    """Invite several responders into one incident team without first-accept cancellation."""
    await require_role(session, user.id, body.property_id, {'owner', 'dispatcher'})
    if session.bind.dialect.name == 'sqlite':
        await session.execute(text('BEGIN'))
    await session.scalar(select(Property).where(Property.id == body.property_id).with_for_update())
    request_key = hashlib.sha256(f'{user.id}:{body.property_id}:{body.idempotency_key}'.encode()).hexdigest()[:32]
    offers = await DispatchService(session).create_team_offers(
        incident_id=body.incident_id,
        reporter_incident_id=body.reporter_incident_id,
        property_id=body.property_id,
        marshal_profile_ids=body.marshal_profile_ids,
        expires_in_seconds=body.expires_in_seconds,
        idempotency_key=request_key,
        actor_subject=f'reporter:{user.id}',
    )
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


@router.post('/reporter-incidents/{reporter_incident_id}/dispatch', response_model=ReporterDispatchOutcome)
async def dispatch_reporter_incident(reporter_incident_id: int, body: DispatchRequest,
                                     user: User = Depends(get_reporter),
                                     session: AsyncSession = Depends(get_session)):
    """Automatically offer a located reporter incident to a nearby marshal."""
    await require_role(session, user.id, body.property_id, {'owner', 'dispatcher'})
    offer = await DispatchService(session).dispatch_next_reporter(
        reporter_incident_id=reporter_incident_id,
        property_id=body.property_id,
        expires_in_seconds=body.expires_in_seconds,
        actor_subject=f'reporter:{user.id}',
        correlation_id=body.correlation_id,
    )
    await session.commit()
    if offer is None:
        return ReporterDispatchOutcome(status="ESCALATED", reporter_incident_id=reporter_incident_id,
                                       reason="No eligible marshal is currently available")
    await publish_assignment_update(offer)
    return ReporterDispatchOutcome(status="OFFERED", reporter_incident_id=reporter_incident_id, assignment=offer)


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
        actor_subject=f"marshal:{user.id}", review_summary=body.review_summary)
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


@router.post('/offers/{offer_id}/review', response_model=OfferView)
async def review_assignment(offer_id: int, body: SupervisorReview, property_id: int = Query(ge=1),
                            user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await _dispatcher_offer(offer_id, property_id, user, session)
    offer = await DispatchService(session).supervisor_review(offer_id=offer_id,
        expected_version=body.expected_version, approved=body.approved, reason=body.reason,
        actor_subject=f'reporter:{user.id}')
    await session.commit()
    await publish_assignment_update(offer)
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
