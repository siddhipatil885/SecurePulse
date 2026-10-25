"""Property-scoped reads over existing cameras, events and alerts. No dispatch."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import (get_reporter, hash_password, issue_token,
                                    require_reporter_auth_enabled, verify_password)
from app.models import Alert, Camera, SecurityEvent
from app.models.reporter import Property, PropertyCamera, PropertyMembership, ReporterUser
from app.schemas.reporter import (LoginRequest, PropertyAccess, ReporterCamera, ReporterEvent,
    ReporterEventPage, ReporterProfile, ReporterSummary, TokenResponse)

def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["reporter"], dependencies=[Depends(private_response)])
_dummy_hash = hash_password("unknown-account-timing-comparison")


@router.post("/auth/login", response_model=TokenResponse, dependencies=[Depends(require_reporter_auth_enabled)])
async def login(body: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    user = await session.scalar(select(ReporterUser).where(
        ReporterUser.email == body.email.strip().lower()).with_for_update())
    valid = await run_in_threadpool(verify_password, body.password, user.password_hash if user else _dummy_hash)
    now = datetime.now(timezone.utc)
    locked = user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now
    if not user or not user.enabled or not valid or locked:
        if user and not locked:
            user.failed_attempts += 1
            if user.failed_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
                user.failed_attempts = 0
            await session.commit()
        raise ApplicationError("INVALID_CREDENTIALS", "Unable to sign in. Check your credentials or try again later.", 401)
    user.failed_attempts = 0
    user.locked_until = None
    token, expires = issue_token(user)
    await session.commit()
    return TokenResponse(access_token=token, expires_at=expires)


@router.get("/auth/me", response_model=ReporterProfile)
async def me(user: ReporterUser = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Property, PropertyMembership.role).join(
        PropertyMembership, PropertyMembership.property_id == Property.id
    ).where(PropertyMembership.user_id == user.id).order_by(Property.id))).all()
    return ReporterProfile(id=user.id, email=user.email, name=user.name,
        properties=[PropertyAccess(id=p.id, name=p.name, role=role) for p, role in rows])


@router.post("/auth/logout", status_code=204)
async def logout(user: ReporterUser = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await session.execute(update(ReporterUser).where(ReporterUser.id == user.id).values(
        token_version=ReporterUser.token_version + 1))
    await session.commit()
    return Response(status_code=204)


async def allowed_property(property_id: int = Query(ge=1), user: ReporterUser = Depends(get_reporter),
                           session: AsyncSession = Depends(get_session)) -> int:
    membership = await session.get(PropertyMembership, (user.id, property_id))
    if membership is None or membership.role not in {"owner", "reporter"}:
        raise ApplicationError("FORBIDDEN", "You do not have access to this property.", 403)
    return property_id


def camera_ids(property_id: int):
    return select(PropertyCamera.camera_id).where(PropertyCamera.property_id == property_id)


@router.get("/reporter/cameras", response_model=list[ReporterCamera])
async def cameras(property_id: int = Depends(allowed_property), session: AsyncSession = Depends(get_session)):
    return (await session.scalars(select(Camera).where(Camera.id.in_(camera_ids(property_id))).order_by(Camera.id))).all()


@router.get("/reporter/cameras/{camera_id}", response_model=ReporterCamera)
async def camera(camera_id: int, property_id: int = Depends(allowed_property), session: AsyncSession = Depends(get_session)):
    result = await session.scalar(select(Camera).where(Camera.id == camera_id, Camera.id.in_(camera_ids(property_id))))
    if result is None:
        raise ApplicationError("NOT_FOUND", "Camera not found.", 404)
    return result


@router.get("/reporter/events", response_model=ReporterEventPage)
async def events(property_id: int = Depends(allowed_property), page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100), session: AsyncSession = Depends(get_session)):
    permitted = SecurityEvent.camera_id.in_(camera_ids(property_id))
    total = await session.scalar(select(func.count()).select_from(SecurityEvent).where(permitted))
    items = (await session.scalars(select(SecurityEvent).where(permitted).order_by(
        SecurityEvent.timestamp.desc(), SecurityEvent.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return ReporterEventPage(items=items, total=total or 0, page=page, page_size=page_size)


@router.get("/reporter/events/{event_id}", response_model=ReporterEvent)
async def event(event_id: int, property_id: int = Depends(allowed_property), session: AsyncSession = Depends(get_session)):
    result = await session.scalar(select(SecurityEvent).where(SecurityEvent.id == event_id,
        SecurityEvent.camera_id.in_(camera_ids(property_id))))
    if result is None:
        raise ApplicationError("NOT_FOUND", "Alert not found.", 404)
    return result


@router.get("/reporter/summary", response_model=ReporterSummary)
async def summary(property_id: int = Depends(allowed_property), session: AsyncSession = Depends(get_session)):
    ids = camera_ids(property_id)
    cameras_count = await session.scalar(select(func.count()).select_from(Camera).where(Camera.id.in_(ids)))
    events_count = await session.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.camera_id.in_(ids)))
    active_alerts = await session.scalar(select(func.count()).select_from(Alert).where(Alert.camera_id.in_(ids), Alert.status == "ACTIVE"))
    return ReporterSummary(camera_count=cameras_count or 0, event_count=events_count or 0, active_alert_count=active_alerts or 0)
