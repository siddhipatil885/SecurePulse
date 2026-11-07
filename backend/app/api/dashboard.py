"""Cookie-authenticated dashboard with live database-backed property permissions."""
import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket, WebSocketDisconnect
from typing import Literal
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection

from app.api import evidence as evidence_api, frigate as frigate_api, reporter as reporter_api
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.dependencies import (get_session, get_camera_service, get_event_service,
    get_incident_service, get_person_tracker, get_event_publisher, get_mutation_rate_limiter)
from app.core.exceptions import ApplicationError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.reporter_auth import get_reporter, hash_password, issue_token, require_reporter_auth_enabled
from app.database.database import get_session_factory
from app.models import Property, PropertyMembership, User, SecurityEvent
from app.schemas.camera import CameraResponse
from app.schemas.event import EventPage, EventResponse
from app.schemas.incident import IncidentCommand, IncidentHistoryResponse, EvidenceResponse
from app.schemas.reporter import LoginRequest
from app.services.camera_service import CameraService
from app.services.event_service import EventService
from app.services.incident_service import IncidentService
from app.integrations.neon_auth import NeonAuth

COOKIE = "securepulse_dashboard"
COOKIE_PATH = "/api/v1/dashboard"
auth_limiter = SlidingWindowRateLimiter(limit=15)


def allowed_origin(origin: str, base_url: str) -> bool:
    return origin.rstrip("/") in {*get_settings().parsed_cors_origins, base_url.rstrip("/")}


async def browser_request(request: HTTPConnection, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if request.scope.get("method", "GET") not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("x-dashboard-request") != "1":
            raise ApplicationError("INVALID_REQUEST", "Reload the dashboard and try again.", 403)
        origin = request.headers.get("origin")
        if origin and not allowed_origin(origin, str(request.base_url)):
            raise ApplicationError("FORBIDDEN", "This origin cannot change dashboard data.", 403)


router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(browser_request)])


class PropertyInput(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    address: str = Field(min_length=5, max_length=1000)

    @field_validator("name", "address", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class Registration(PropertyInput):
    full_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=128)

    @field_validator("full_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def password_strength(cls, value):
        if not any(letter.isalpha() for letter in value) or not any(letter.isdigit() for letter in value):
            raise ValueError("Use at least 12 characters, including a letter and a number")
        return value


async def throttle(request: Request):
    retry = await auth_limiter.check(request.client.host if request.client else "unknown")
    if retry is not None:
        raise ApplicationError("RATE_LIMITED", "Too many attempts. Please try again shortly.", 429,
                               {"Retry-After": str(retry)})


def set_cookie(response: Response, token: str, expires: datetime):
    response.set_cookie(COOKIE, token, httponly=True, secure=get_settings().app_env == "production",
                        samesite="strict", path=COOKIE_PATH, expires=expires)


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token) if token else None
    return await get_reporter(credentials=credentials, session=session)


async def property_access(property_id: int, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)) -> Principal:
    membership = await session.scalar(select(PropertyMembership).join(Property).where(
        PropertyMembership.user_id == user.id, PropertyMembership.property_id == property_id,
        PropertyMembership.active.is_(True), Property.active.is_(True)))
    if membership is None or membership.role not in {"owner", "dispatcher", "reporter"}:
        raise ApplicationError("FORBIDDEN", "You do not have dashboard access to this property.", 403)
    scopes = {"read", "write"} if membership.role in {"owner", "dispatcher"} else {"read"}
    return Principal(f"reporter:{user.id}", frozenset(scopes), frozenset({property_id}))


async def profile(user: User, session: AsyncSession):
    rows = (await session.execute(select(Property, PropertyMembership.role).join(PropertyMembership).where(
        PropertyMembership.user_id == user.id, PropertyMembership.active.is_(True), Property.active.is_(True),
        PropertyMembership.role.in_(["owner", "dispatcher", "reporter"])).order_by(Property.id))).all()
    return {"id": user.id, "name": user.display_name, "email": user.email,
            "properties": [{"id": item.id, "name": item.name, "address": item.address, "role": role}
                           for item, role in rows]}


@router.get("/config")
async def config():
    settings = get_settings()
    return {"auth_enabled": settings.auth_enabled, "registration_enabled": settings.dashboard_registration_enabled}


@router.post("/auth/register", status_code=201)
async def register(body: Registration, request: Request, response: Response,
                   session: AsyncSession = Depends(get_session)):
    require_reporter_auth_enabled()
    if not get_settings().dashboard_registration_enabled:
        raise ApplicationError("REGISTRATION_DISABLED", "Registration is disabled. Contact your administrator.", 403)
    await throttle(request)
    if await session.scalar(select(User.id).where(User.email == body.email)):
        raise ApplicationError("REGISTRATION_CONFLICT", "Unable to register with those details. Try signing in.", 409)
    if get_settings().neon_auth_base_url:
        identity = await NeonAuth().signup(body.email, body.password, body.full_name)
        user = User(subject="neon:" + identity["id"], email=body.email, display_name=body.full_name)
    else:
        user = User(subject=f"dashboard:{uuid4().hex}", email=body.email, display_name=body.full_name,
                    password_hash=await run_in_threadpool(hash_password, body.password))
    # A new account may create a new property, never claim an existing property.
    item = Property(slug=uuid4().hex, name=body.name, address=body.address)
    try:
        session.add_all([user, item])
        await session.flush()
        session.add(PropertyMembership(user_id=user.id, property_id=item.id, role="owner"))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ApplicationError("REGISTRATION_CONFLICT", "Unable to register with those details. Try signing in.", 409) from None
    token, expires = issue_token(user)
    set_cookie(response, token, expires)
    return await profile(user, session)


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    require_reporter_auth_enabled()
    await throttle(request)
    result = await reporter_api.login(body, response, session)
    set_cookie(response, result.access_token, result.expires_at)
    user = await session.scalar(select(User).where(User.email == body.email.strip().lower()))
    return await profile(user, session)


@router.get("/auth/session")
async def session_profile(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return await profile(user, session)


@router.post("/auth/logout", status_code=204)
async def logout(response: Response, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await reporter_api.logout(user, session)
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="strict",
                           secure=get_settings().app_env == "production")


@router.post("/properties", status_code=201)
async def create_property(body: PropertyInput, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    item = Property(slug=uuid4().hex, name=body.name, address=body.address)
    session.add(item)
    await session.flush()
    session.add(PropertyMembership(user_id=user.id, property_id=item.id, role="owner"))
    await session.commit()
    return await profile(user, session)


@router.patch("/properties/{property_id}")
async def update_property(property_id: int, body: PropertyInput, user: User = Depends(current_user),
                          principal: Principal = Depends(property_access), session: AsyncSession = Depends(get_session)):
    membership = await session.scalar(select(PropertyMembership).where(
        PropertyMembership.user_id == user.id, PropertyMembership.property_id == property_id))
    if membership.role != "owner":
        raise ApplicationError("FORBIDDEN", "Only the property owner may edit these details.", 403)
    item = await session.get(Property, property_id)
    item.name, item.address = body.name, body.address
    await session.commit()
    return await profile(user, session)


@router.get("/properties/{property_id}/cameras", response_model=list[CameraResponse])
async def cameras(principal: Principal = Depends(property_access), service: CameraService = Depends(get_camera_service)):
    return await service.list(property_ids=principal.property_ids)


@router.get("/properties/{property_id}/incidents", response_model=EventPage)
async def incidents(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=100),
                    status: Literal["OPEN", "ACKNOWLEDGED", "UNCLASSIFIED", "RESOLVED", "DISMISSED", "CLOSED"] | None = None,
                    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None,
                    principal: Principal = Depends(property_access), session: AsyncSession = Depends(get_session)):
    statement = select(SecurityEvent).where(SecurityEvent.property_id.in_(principal.property_ids))
    if status is not None:
        statement = statement.where(SecurityEvent.status == status)
    if severity is not None:
        statement = statement.where(SecurityEvent.severity == severity)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    items = list((await session.scalars(statement.order_by(SecurityEvent.timestamp.desc(), SecurityEvent.id.desc())
                       .offset((page - 1) * page_size).limit(page_size))).all())
    return EventPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/properties/{property_id}/overview")
async def overview(property_id: int, principal: Principal = Depends(property_access), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(SecurityEvent.status, SecurityEvent.severity, func.count()).where(
        SecurityEvent.property_id == property_id).group_by(SecurityEvent.status, SecurityEvent.severity))).all()
    return {"total_incidents": sum(count for _, _, count in rows),
            "active_incidents": sum(count for status, _, count in rows if status in {"OPEN", "ACKNOWLEDGED"}),
            "critical_incidents": sum(count for status, severity, count in rows
                                      if status in {"OPEN", "ACKNOWLEDGED"} and severity.upper() == "CRITICAL")}


@router.get("/properties/{property_id}/tracks")
async def tracks(principal: Principal = Depends(property_access), service: CameraService = Depends(get_camera_service)):
    ids = {str(item.id) for item in await service.list(property_ids=principal.property_ids)}
    return {key: value for key, value in get_person_tracker().snapshot().items() if key in ids}


@router.get("/properties/{property_id}/incidents/{incident_id}", response_model=EventResponse)
async def incident(incident_id: int, principal: Principal = Depends(property_access), service: EventService = Depends(get_event_service)):
    return await service.get(incident_id, property_ids=principal.property_ids)


@router.get("/properties/{property_id}/incidents/{incident_id}/history", response_model=list[IncidentHistoryResponse])
async def history(incident_id: int, principal: Principal = Depends(property_access), service: IncidentService = Depends(get_incident_service)):
    return await service.history(incident_id, principal.property_ids)


@router.get("/properties/{property_id}/incidents/{incident_id}/evidence", response_model=list[EvidenceResponse])
async def evidence(incident_id: int, principal: Principal = Depends(property_access), service: IncidentService = Depends(get_incident_service)):
    return await service.evidence(incident_id, principal.property_ids, actor_subject=principal.subject, correlation_id=str(uuid4()))


@router.post("/properties/{property_id}/incidents/{incident_id}/commands", response_model=EventResponse)
async def command(incident_id: int, body: IncidentCommand, principal: Principal = Depends(property_access),
                  service: IncidentService = Depends(get_incident_service)):
    if "write" not in principal.scopes:
        raise ApplicationError("FORBIDDEN", "Only owners and dispatchers may change incidents.", 403)
    if await get_mutation_rate_limiter().check(principal.subject) is not None:
        raise ApplicationError("RATE_LIMITED", "Too many changes. Try again shortly.", 429)
    body.reason = body.reason.strip()
    if not body.reason:
        raise ApplicationError("INVALID_REASON", "Provide a reason for this action.", 422)
    result = await service.command(incident_id, body.command, actor_subject=principal.subject,
        property_ids=principal.property_ids, reason=body.reason, correlation_id=body.correlation_id)
    await get_event_publisher().publish(result)
    return result


@router.post("/properties/{property_id}/evidence/{evidence_id}/access")
async def evidence_access(property_id: int, evidence_id: int, principal: Principal = Depends(property_access), session: AsyncSession = Depends(get_session)):
    result = await evidence_api.grant_access(evidence_id, principal, session)
    result["url"] = result["url"].replace(f"/api/v1/evidence/{evidence_id}", f"{COOKIE_PATH}/properties/{property_id}/evidence/{evidence_id}")
    return result


@router.get("/properties/{property_id}/evidence/{evidence_id}/content")
async def evidence_content(evidence_id: int, grant: str = Query(min_length=1, max_length=4096), principal: Principal = Depends(property_access), session: AsyncSession = Depends(get_session)):
    return await evidence_api.content(evidence_id, grant, principal, session)


@router.post("/properties/{property_id}/cameras/{camera_id}/webrtc")
async def webrtc(camera_id: int, request: Request, principal: Principal = Depends(property_access), service: CameraService = Depends(get_camera_service)):
    return await frigate_api.negotiate_webrtc(camera_id, request, principal, service)


@router.websocket("/properties/{property_id}/stream")
async def stream(websocket: WebSocket, property_id: int):
    origin = websocket.headers.get("origin")
    if not origin or not allowed_origin(origin, str(websocket.base_url).replace("ws://", "http://").replace("wss://", "https://")):
        await websocket.close(code=1008)
        return
    token = websocket.cookies.get(COOKIE)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token) if token else None

    async def authorize():
        async with get_session_factory()() as session:
            user = await get_reporter(credentials=credentials, session=session)
            return await property_access(property_id, user, session)

    async def authorize_location(target_property, assignment_id):
        from app.api.dispatch import can_view_assignment_location
        async with get_session_factory()() as session:
            user = await get_reporter(credentials=credentials, session=session)
            principal = await property_access(property_id, user, session)
            return await can_view_assignment_location(principal, target_property, assignment_id, session)

    queue = None
    disconnect_task = None
    message_task = None
    publisher = get_event_publisher()
    try:
        await authorize()
        await websocket.accept()
        queue = await publisher.subscribe(frozenset({property_id}), location_access=authorize_location)
        async def wait_for_disconnect():
            while True:
                if (await websocket.receive())["type"] == "websocket.disconnect":
                    return
        disconnect_task = asyncio.create_task(wait_for_disconnect())
        while True:
            message_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({message_task, disconnect_task}, timeout=15, return_when=asyncio.FIRST_COMPLETED)
            if disconnect_task in done:
                break
            if message_task not in done:
                message_task.cancel()
                await asyncio.gather(message_task, return_exceptions=True)
                await authorize()
                await websocket.send_json({"type": "heartbeat"})
                continue
            await authorize()
            message = message_task.result()
            if message.get('type') == 'marshal_location' and not await authorize_location(message['property_id'], message['data']['assignment_id']):
                continue
            await websocket.send_json(message)
    except ApplicationError:
        try:
            await websocket.close(code=1008)
        except (WebSocketDisconnect, RuntimeError):
            pass
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        tasks = [task for task in (message_task, disconnect_task) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if queue is not None:
            await publisher.unsubscribe(queue)
