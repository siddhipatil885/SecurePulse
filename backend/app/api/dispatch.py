"""Authenticated, property-scoped dispatch orchestration endpoints."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import get_reporter
from app.models import MarshalAvailability, MarshalProfile, PropertyMembership, User
from app.repositories.dispatch import DispatchRepository
from app.schemas.dispatch import AvailabilityUpdate, EligibleMarshal, OfferCreate, OfferResponse, OfferView
from app.services.dispatch_service import DispatchService

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


async def require_role(session: AsyncSession, user_id: int, property_id: int,
                       roles: set[str]) -> PropertyMembership:
    membership = await session.scalar(select(PropertyMembership).where(
        PropertyMembership.user_id == user_id, PropertyMembership.property_id == property_id,
        PropertyMembership.active.is_(True)))
    if membership is None or membership.role not in roles:
        raise ApplicationError("FORBIDDEN", "You cannot perform dispatch actions for this property.", 403)
    return membership


@router.get("/eligible-marshals", response_model=list[EligibleMarshal])
async def eligible_marshals(property_id: int = Query(ge=1), user: User = Depends(get_reporter),
                             session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, property_id, {"owner", "dispatcher"})
    return await DispatchRepository(session).eligible_marshals(
        property_id, datetime.now(timezone.utc) - timedelta(minutes=5))


@router.put("/marshal/availability", response_model=EligibleMarshal)
async def update_availability(body: AvailabilityUpdate, user: User = Depends(get_reporter),
                              session: AsyncSession = Depends(get_session)):
    await require_role(session, user.id, body.property_id, {"marshal"})
    profile = await session.scalar(select(MarshalProfile).where(MarshalProfile.user_id == user.id,
        MarshalProfile.property_id == body.property_id).with_for_update())
    if profile is None:
        raise ApplicationError("FORBIDDEN", "No marshal profile exists for this property.", 403)
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
        property_id=body.property_id, marshal_profile_id=body.marshal_profile_id,
        expires_in_seconds=body.expires_in_seconds, idempotency_key=body.idempotency_key,
        actor_subject=f"reporter:{user.id}")
    await session.commit()
    return offer


async def _respond(offer_id: int, body: OfferResponse, accept: bool,
                   user: User, session: AsyncSession):
    offer = await DispatchService(session).respond(offer_id=offer_id, user_id=user.id,
        accept=accept, expected_version=body.expected_version, actor_subject=f"marshal:{user.id}")
    await require_role(session, user.id, offer.property_id, {"marshal"})
    await session.commit()
    return offer


@router.post("/offers/{offer_id}/accept", response_model=OfferView)
async def accept_offer(offer_id: int, body: OfferResponse, user: User = Depends(get_reporter),
                       session: AsyncSession = Depends(get_session)):
    return await _respond(offer_id, body, True, user, session)


@router.post("/offers/{offer_id}/decline", response_model=OfferView)
async def decline_offer(offer_id: int, body: OfferResponse, user: User = Depends(get_reporter),
                        session: AsyncSession = Depends(get_session)):
    return await _respond(offer_id, body, False, user, session)


async def _dispatcher_offer(offer_id: int, property_id: int, user: User,
                            session: AsyncSession):
    await require_role(session, user.id, property_id, {"owner", "dispatcher"})
    offer = await DispatchRepository(session).lock_offer(offer_id)
    if offer is None or offer.property_id != property_id:
        raise ApplicationError("NOT_FOUND", "Assignment offer not found.", 404)
    return offer


@router.post("/offers/{offer_id}/expire", response_model=OfferView)
async def expire_offer(offer_id: int, property_id: int = Query(ge=1),
                       user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await _dispatcher_offer(offer_id, property_id, user, session)
    offer = await DispatchService(session).expire(offer_id=offer_id, actor_subject=f"reporter:{user.id}")
    await session.commit()
    return offer


@router.post("/offers/{offer_id}/cancel", response_model=OfferView)
async def cancel_offer(offer_id: int, property_id: int = Query(ge=1),
                       user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await _dispatcher_offer(offer_id, property_id, user, session)
    offer = await DispatchService(session).cancel(offer_id=offer_id, actor_subject=f"reporter:{user.id}")
    await session.commit()
    return offer
