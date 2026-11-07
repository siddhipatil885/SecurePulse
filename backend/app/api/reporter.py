"""Reporter authentication, property-scoped reads, and manual incidents."""
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import jwt
from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_session, get_event_publisher
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import (get_reporter, hash_password, issue_token,
                                    require_reporter_auth_enabled, verify_password)
from app.models import (
    Alert, Assignment, Camera, Property, PropertyMembership, ReporterIncident,
    ReporterIncidentEvidence, ReporterIncidentTimeline, SecurityEvent, User,
)
from app.models.operations import AuditRecord
from app.schemas.reporter import (LoginRequest, PropertyAccess, ReporterCamera, ReporterEvent,
    ReporterDispatchResponse, ReporterEventPage, ReporterIncidentCreate,
    ReporterIncidentPage, ReporterIncidentResponse, ReporterProfile,
    ReporterSummary, TokenResponse, DeviceRegistration, NotificationPreferenceUpdate,
    NotificationPreferenceResponse, AlertReviewRequest, ReporterProfileUpdate,
    ReporterPasswordChange)
from app.models.operations import NotificationPreference, UserDeviceToken
from app.models import NotificationOutbox
from app.core.config import get_settings
from app.integrations.neon_auth import NeonAuth
from app.services.reporter_storage import ReporterStorage
from app.services.camera_health import camera_states
from app.core.rate_limit import SlidingWindowRateLimiter

push_test_limiter = SlidingWindowRateLimiter(3)

def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["reporter"], dependencies=[Depends(private_response)])
_dummy_hash = hash_password("unknown-account-timing-comparison")


@router.post("/auth/login", response_model=TokenResponse, dependencies=[Depends(require_reporter_auth_enabled)])
async def login(body: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    user = await session.scalar(select(User).where(
        User.email == body.email.strip().lower()).with_for_update())
    if get_settings().neon_auth_base_url and (user is None or user.subject.startswith("neon:")):
        if user is not None and not user.active:
            raise ApplicationError("INVALID_CREDENTIALS", "Unable to sign in.", 401)
        identity = await NeonAuth().signin(body.email.strip().lower(), body.password)
        subject = "neon:" + identity["id"]
        if user is None:
            if not get_settings().dashboard_registration_enabled:
                raise ApplicationError("REGISTRATION_DISABLED", "Contact your administrator for property access.", 403)
            # Match identity by provider ID, never automatically link by email.
            user = await session.scalar(select(User).where(User.subject == subject))
            if user is None:
                user = User(subject=subject, email=identity["email"].lower(), display_name=identity.get("name") or "")
                session.add(user)
                await session.flush()
        if user.subject != subject or not user.active:
            raise ApplicationError("INVALID_CREDENTIALS", "Unable to verify your identity.", 401)
        # Also recovers local revocation after a remote password reset succeeded
        # during a database outage. Do not issue a new session until both persist.
        user.token_version += 1
        await session.execute(update(UserDeviceToken).where(UserDeviceToken.user_id == user.id).values(active=False))
        token, expires = issue_token(user)
        await session.commit()
        return TokenResponse(access_token=token, expires_at=expires)
    valid = await run_in_threadpool(verify_password, body.password, (user.password_hash or _dummy_hash) if user else _dummy_hash)
    now = datetime.now(timezone.utc)
    locked = user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now
    if not user or not user.active or not user.password_hash or not valid or locked:
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
async def me(user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Property, PropertyMembership.role).join(
        PropertyMembership, PropertyMembership.property_id == Property.id
    ).where(PropertyMembership.user_id == user.id, PropertyMembership.active.is_(True), Property.active.is_(True)).order_by(Property.id))).all()
    return ReporterProfile(id=user.id, email=user.email, name=user.display_name or "",
        properties=[PropertyAccess(id=p.id, name=p.name, role=role) for p, role in rows])


@router.put("/auth/profile", response_model=ReporterProfile)
async def update_profile(
    body: ReporterProfileUpdate,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    user.display_name = body.name.strip()
    await session.commit()
    return await me(user, session)


@router.post("/auth/password", status_code=204)
async def change_password(
    body: ReporterPasswordChange,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    if user.subject.startswith("neon:"):
        if body.current_password == body.new_password:
            raise ApplicationError("PASSWORD_UNCHANGED", "Choose a new password.", 422)
        await NeonAuth().change_password(user, body.current_password, body.new_password)
        user.token_version += 1
        await session.execute(update(UserDeviceToken).where(UserDeviceToken.user_id == user.id).values(active=False))
        await session.commit()
        return Response(status_code=204)
    valid = await run_in_threadpool(verify_password, body.current_password, user.password_hash or "")
    if not valid:
        raise ApplicationError("INVALID_CURRENT_PASSWORD", "The current password is incorrect.", 400)
    if body.current_password == body.new_password:
        raise ApplicationError("PASSWORD_UNCHANGED", "Choose a new password.", 422)
    user.password_hash = await run_in_threadpool(hash_password, body.new_password)
    user.token_version += 1
    await session.execute(update(UserDeviceToken).where(UserDeviceToken.user_id == user.id).values(active=False))
    await session.commit()
    return Response(status_code=204)


@router.post("/auth/logout", status_code=204)
async def logout(user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    await session.execute(update(UserDeviceToken).where(UserDeviceToken.user_id == user.id).values(active=False))
    await session.execute(update(User).where(User.id == user.id).values(
        token_version=User.token_version + 1))
    await session.commit()
    return Response(status_code=204)


@router.post("/reporter/devices", status_code=204)
async def register_device(
    body: DeviceRegistration,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    from app.services.expo_push import TOKEN
    if body.provider == 'expo' and not TOKEN.fullmatch(body.push_token):
        raise ApplicationError('INVALID_PUSH_TOKEN', 'Register a valid Expo device token.', 422)
    # A client-supplied identifier/token is not proof of ownership of another
    # account's registration. Handover requires that account's logout/revocation.
    foreign = await session.scalar(select(UserDeviceToken.id).where(
        UserDeviceToken.user_id != user.id, UserDeviceToken.active.is_(True),
        or_(UserDeviceToken.device_id == body.device_id, UserDeviceToken.push_token == body.push_token)).limit(1))
    if foreign is not None:
        raise ApplicationError('DEVICE_IN_USE', 'Sign out of the previous account on this device before registering it.', 409)
    device = await session.scalar(select(UserDeviceToken).where(
        UserDeviceToken.user_id == user.id, UserDeviceToken.device_id == body.device_id
    ))
    if device is None:
        device = UserDeviceToken(user_id=user.id, device_id=body.device_id,
                                 push_token=body.push_token, provider=body.provider)
        session.add(device)
    else:
        device.push_token, device.provider, device.active = body.push_token, body.provider, True
        device.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=204)


@router.delete("/reporter/devices/{device_id}", status_code=204)
async def unregister_device(
    device_id: str,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(update(UserDeviceToken).where(
        UserDeviceToken.user_id == user.id, UserDeviceToken.device_id == device_id
    ).values(active=False))
    await session.commit()
    return Response(status_code=204)


@router.get("/reporter/notification-preferences", response_model=list[NotificationPreferenceResponse])
async def notification_preferences(
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    return list((await session.scalars(select(NotificationPreference).where(
        NotificationPreference.user_id == user.id
    ).order_by(NotificationPreference.category))).all())


@router.put("/reporter/notification-preferences", response_model=NotificationPreferenceResponse)
async def update_notification_preference(
    body: NotificationPreferenceUpdate,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    preference = await session.scalar(select(NotificationPreference).where(
        NotificationPreference.user_id == user.id,
        NotificationPreference.category == body.category,
    ))
    if preference is None:
        preference = NotificationPreference(user_id=user.id, category=body.category, enabled=body.enabled)
        session.add(preference)
    else:
        preference.enabled = body.enabled
        preference.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return preference


async def allowed_property(property_id: int = Query(ge=1), user: User = Depends(get_reporter),
                           session: AsyncSession = Depends(get_session)) -> int:
    membership = await session.scalar(select(PropertyMembership).join(Property).where(
        PropertyMembership.user_id == user.id,
        PropertyMembership.property_id == property_id,
        PropertyMembership.active.is_(True),
        Property.active.is_(True),
    ))
    if membership is None or membership.role not in {"owner", "reporter"}:
        raise ApplicationError("FORBIDDEN", "You do not have access to this property.", 403)
    return property_id


@router.post('/reporter/notifications/test', status_code=202)
async def test_push(property_id: int = Depends(allowed_property), user: User = Depends(get_reporter),
                    session: AsyncSession = Depends(get_session)):
    if get_settings().dispatch_notification_provider not in {'expo', 'routing'}:
        raise ApplicationError('PUSH_NOT_CONFIGURED', 'Expo delivery is not enabled on this host.', 503)
    retry = await push_test_limiter.check(str(user.id))
    if retry:
        raise ApplicationError('RATE_LIMITED', 'Wait before sending another test.', 429, {'Retry-After': str(retry)})
    preference = await session.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user.id,
        NotificationPreference.enabled.is_(True)).order_by(NotificationPreference.category).limit(1))
    device = await session.scalar(select(UserDeviceToken.id).where(UserDeviceToken.user_id == user.id,
        UserDeviceToken.active.is_(True), UserDeviceToken.provider == 'expo').limit(1))
    if not preference or not device:
        raise ApplicationError('PUSH_NOT_REGISTERED', 'Enable a notification category and register this device first.', 409)
    row = NotificationOutbox(property_id=property_id, kind='PUSH_SELF_TEST', destination=f'reporter:{user.id}',
        dedupe_key='self-test:' + str(uuid4()), payload={'category': preference.category, 'user_id': user.id})
    session.add(row); await session.commit()
    return {'id': row.id, 'status': row.status, 'message': 'Queued. Provider receipts and device receipt must still be checked.'}


@router.get('/reporter/notifications/test/{notification_id}')
async def test_push_status(notification_id: int, user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    row = await session.scalar(select(NotificationOutbox).where(NotificationOutbox.id == notification_id,
        NotificationOutbox.kind == 'PUSH_SELF_TEST', NotificationOutbox.destination == f'reporter:{user.id}'))
    if row is None:
        raise ApplicationError('NOT_FOUND', 'Notification test not found.', 404)
    await allowed_property(row.property_id, user, session)
    return {'id': row.id, 'status': row.status, 'sent_at': row.sent_at,
            'message': 'SENT means provider hand-off confirmed, not that the device displayed it.'}


def camera_ids(property_id: int):
    return select(Camera.id).where(Camera.property_id == property_id)


@router.get("/reporter/cameras", response_model=list[ReporterCamera])
async def cameras(property_id: int = Depends(allowed_property), session: AsyncSession = Depends(get_session)):
    records = (await session.scalars(select(Camera).where(Camera.id.in_(camera_ids(property_id))).order_by(Camera.id))).all()
    states = await camera_states(records, get_settings())
    return [ReporterCamera(id=c.id, name=c.name, location=c.location, enabled=c.enabled, connection_status=states[c.id]) for c in records]


@router.get("/reporter/cameras/{camera_id}", response_model=ReporterCamera)
async def camera(camera_id: int, property_id: int = Depends(allowed_property), session: AsyncSession = Depends(get_session)):
    result = await session.scalar(select(Camera).where(Camera.id == camera_id, Camera.id.in_(camera_ids(property_id))))
    if result is None:
        raise ApplicationError("NOT_FOUND", "Camera not found.", 404)
    states = await camera_states([result], get_settings())
    return ReporterCamera(id=result.id, name=result.name, location=result.location, enabled=result.enabled, connection_status=states[result.id])


@router.get("/reporter/events", response_model=ReporterEventPage)
async def events(property_id: int = Depends(allowed_property), page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100), session: AsyncSession = Depends(get_session)):
    permitted = SecurityEvent.camera_id.in_(camera_ids(property_id))
    total = await session.scalar(select(func.count()).select_from(SecurityEvent).where(permitted))
    rows = (await session.execute(select(SecurityEvent, Alert).outerjoin(
        Alert, Alert.security_event_id == SecurityEvent.id
    ).where(permitted).order_by(
        SecurityEvent.timestamp.desc(), SecurityEvent.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    items = [ReporterEvent.model_validate(event).model_copy(update={
        "alert_id": alert.id if alert else None,
        "alert_status": alert.status if alert else None,
    }) for event, alert in rows]
    return ReporterEventPage(items=items, total=total or 0, page=page, page_size=page_size)


@router.get("/reporter/events/{event_id}", response_model=ReporterEvent)
async def event(event_id: int, property_id: int = Depends(allowed_property), session: AsyncSession = Depends(get_session)):
    row = (await session.execute(select(SecurityEvent, Alert).outerjoin(
        Alert, Alert.security_event_id == SecurityEvent.id
    ).where(SecurityEvent.id == event_id, SecurityEvent.camera_id.in_(camera_ids(property_id))))).one_or_none()
    if row is None:
        raise ApplicationError("NOT_FOUND", "Alert not found.", 404)
    result, alert = row
    return ReporterEvent.model_validate(result).model_copy(update={
        "alert_id": alert.id if alert else None,
        "alert_status": alert.status if alert else None,
    })


@router.post("/reporter/events/{event_id}/review", response_model=ReporterEvent)
async def review_event(
    event_id: int,
    body: AlertReviewRequest,
    property_id: int = Query(ge=1),
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    membership = await session.scalar(select(PropertyMembership).where(
        PropertyMembership.user_id == user.id, PropertyMembership.property_id == property_id,
        PropertyMembership.active.is_(True), PropertyMembership.role.in_(("owner", "reporter")),
    ))
    if membership is None:
        raise ApplicationError("FORBIDDEN", "You do not have access to this property.", 403)
    row = (await session.execute(select(SecurityEvent, Alert).join(
        Alert, Alert.security_event_id == SecurityEvent.id
    ).where(SecurityEvent.id == event_id, SecurityEvent.camera_id.in_(camera_ids(property_id))).with_for_update())).one_or_none()
    if row is None:
        raise ApplicationError("NOT_FOUND", "Alert not found.", 404)
    event, alert = row
    if alert.status != "ACTIVE":
        raise ApplicationError("ALERT_ALREADY_REVIEWED", "This alert has already been reviewed.", 409)
    alert.status = body.decision
    alert.reviewed_by = f"reporter:{user.id}"
    alert.reviewed_at = datetime.now(timezone.utc)
    session.add(AuditRecord(
        property_id=property_id, actor_subject=f"reporter:{user.id}",
        action="ALERT_REVIEWED", resource_type="alert", resource_id=str(alert.id),
        correlation_id=f"alert-review:{alert.id}:{alert.reviewed_at.isoformat()}",
        details={"decision": body.decision, "event_id": event.id},
    ))
    await session.commit()
    return ReporterEvent.model_validate(event).model_copy(update={
        "alert_id": alert.id, "alert_status": alert.status,
    })


@router.get("/reporter/summary", response_model=ReporterSummary)
async def summary(property_id: int = Depends(allowed_property), user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    ids = camera_ids(property_id)
    cameras_count = await session.scalar(select(func.count()).select_from(Camera).where(Camera.id.in_(ids)))
    events_count = await session.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.camera_id.in_(ids)))
    active_alerts = await session.scalar(select(func.count()).select_from(Alert).where(Alert.camera_id.in_(ids), Alert.status == "ACTIVE"))
    records = (await session.scalars(select(Camera).where(Camera.id.in_(ids)))).all()
    states = await camera_states(records, get_settings())
    connected = None if any(s == 'unknown' for s in states.values()) else sum(s == 'online' for s in states.values())
    active_camera = await session.scalar(select(func.count()).select_from(SecurityEvent).where(
        SecurityEvent.camera_id.in_(ids), SecurityEvent.status.in_(['OPEN', 'ACKNOWLEDGED']),
        or_(and_(SecurityEvent.event_type != 'DETECTION', SecurityEvent.severity != 'INFO'),
            select(Alert.id).where(Alert.security_event_id == SecurityEvent.id, Alert.status == 'CONFIRMED').exists())))
    active_reports = await session.scalar(select(func.count()).select_from(ReporterIncident).where(
        ReporterIncident.property_id == property_id, ReporterIncident.reporter_user_id == user.id,
        ReporterIncident.status.in_(['RECEIVED', 'ACKNOWLEDGED'])))
    active = (active_camera or 0) + (active_reports or 0)
    status = 'attention_required' if active or active_alerts else 'camera_issue' if any(s in ('offline', 'disabled') for s in states.values()) else 'no_active_incidents' if records and connected is not None else 'unknown'
    return ReporterSummary(camera_count=cameras_count or 0, event_count=events_count or 0, active_alert_count=active_alerts or 0,
        connected_camera_count=connected, active_incident_count=active, security_status=status)


async def _owned_incident(
    incident_id: int, user_id: int, session: AsyncSession
) -> ReporterIncident:
    incident = await session.scalar(
        select(ReporterIncident)
        .options(selectinload(ReporterIncident.evidence), selectinload(ReporterIncident.timeline))
        .execution_options(populate_existing=True)
        .where(ReporterIncident.id == incident_id, ReporterIncident.reporter_user_id == user_id,
               ReporterIncident.property_id.in_(_report_properties(user_id)))
    )
    if incident is None:
        raise ApplicationError("INCIDENT_NOT_FOUND", "The requested incident does not exist.", 404)
    return incident


def _report_properties(user_id):
    return select(PropertyMembership.property_id).join(Property).where(
        PropertyMembership.user_id == user_id, PropertyMembership.active.is_(True),
        PropertyMembership.role.in_(("owner", "reporter")), Property.active.is_(True))


def _incident_response(
    incident: ReporterIncident,
    dispatch: Assignment | None = None,
    details: bool = True,
) -> ReporterIncidentResponse:
    if details:
        response = ReporterIncidentResponse.model_validate(incident)
    else:
        response = ReporterIncidentResponse(**{key: getattr(incident, key) for key in (
            "id", "property_id", "incident_type", "description", "address", "latitude", "longitude",
            "location_accuracy", "status", "created_at", "updated_at")}, details_included=False)
    if dispatch is not None:
        response.dispatch = ReporterDispatchResponse(
            assignment_id=dispatch.id,
            status=dispatch.status,
            marshal_profile_id=dispatch.marshal_profile_id,
            offered_at=dispatch.offered_at,
            expires_at=dispatch.expires_at,
            accepted_at=dispatch.accepted_at,
            closed_at=dispatch.closed_at,
            version=dispatch.version,
        )
    return response


async def _latest_dispatch(incident_id: int, session: AsyncSession) -> Assignment | None:
    return await session.scalar(select(Assignment).where(
        Assignment.reporter_incident_id == incident_id
    ).order_by(Assignment.offered_at.desc(), Assignment.id.desc()))


@router.post("/reporter/incidents", response_model=ReporterIncidentResponse, status_code=201)
async def create_reporter_incident(
    body: ReporterIncidentCreate,
    idempotency_key: str = Header(alias="X-Idempotency-Key", min_length=16, max_length=128),
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
) -> ReporterIncidentResponse:
    # Serialize retried creations for one account before looking up the receipt.
    # Concurrent PostgreSQL requests then replay the row instead of hitting the
    # unique key constraint and returning an ambiguous server error.
    await session.scalar(select(User.id).where(User.id == user.id).with_for_update())
    membership = await session.scalar(select(PropertyMembership).join(Property).where(
        PropertyMembership.user_id == user.id,
        PropertyMembership.property_id == body.property_id,
        PropertyMembership.active.is_(True),
        PropertyMembership.role.in_(("owner", "reporter")),
        Property.active.is_(True),
    ))
    if membership is None:
        raise ApplicationError("FORBIDDEN", "You do not have access to this property.", 403)
    existing = await session.scalar(select(ReporterIncident).options(
        selectinload(ReporterIncident.evidence), selectinload(ReporterIncident.timeline)
    ).execution_options(populate_existing=True).where(
        ReporterIncident.reporter_user_id == user.id,
        ReporterIncident.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        fields = ("property_id", "incident_type", "description", "address", "latitude", "longitude", "location_accuracy")
        if any(getattr(existing, field) != getattr(body, field) for field in fields):
            raise ApplicationError("IDEMPOTENCY_CONFLICT", "This request key was already used for a different report.", 409)
        return _incident_response(existing, await _latest_dispatch(existing.id, session))
    incident = ReporterIncident(
        reporter_user_id=user.id,
        property_id=body.property_id,
        incident_type=body.incident_type,
        description=body.description,
        address=body.address,
        latitude=body.latitude,
        longitude=body.longitude,
        location_accuracy=body.location_accuracy,
        status="RECEIVED",
        idempotency_key=idempotency_key,
    )
    session.add(incident)
    await session.flush()
    session.add(ReporterIncidentTimeline(
        incident_id=incident.id,
        status="RECEIVED",
        actor_subject=f"reporter:{user.id}",
        message="Report received by SecurePulse.",
    ))
    session.add(AuditRecord(
        property_id=body.property_id, actor_subject=f"reporter:{user.id}",
        action="REPORTER_INCIDENT_CREATED", resource_type="reporter_incident",
        resource_id=str(incident.id), correlation_id=idempotency_key, details={},
    ))
    session.add(NotificationOutbox(property_id=body.property_id, kind='REPORT_RECEIVED',
        destination=f'reporter:{user.id}', dedupe_key=f'report:{incident.id}:received',
        payload={'reporter_incident_id': incident.id, 'status': 'RECEIVED'}))
    await session.commit()
    owned = await _owned_incident(incident.id, user.id, session)
    await get_event_publisher().publish_case(owned.property_id, f"reporter:{owned.id}")
    return _incident_response(owned, await _latest_dispatch(owned.id, session))


@router.get("/reporter/incidents", response_model=ReporterIncidentPage)
async def list_reporter_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    status: str | None = Query(None, min_length=1, max_length=32),
    incident_type: str | None = Query(None, min_length=1, max_length=32),
    has_active_assignment: bool | None = None,
    include_details: bool = True,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
) -> ReporterIncidentPage:
    base = (ReporterIncident.reporter_user_id == user.id) & ReporterIncident.property_id.in_(_report_properties(user.id))
    filters = [base]
    if status:
        filters.append(ReporterIncident.status == status)
    if incident_type:
        filters.append(ReporterIncident.incident_type == incident_type)
    if has_active_assignment is not None:
        assigned = select(Assignment.id).where(Assignment.reporter_incident_id == ReporterIncident.id,
            Assignment.property_id == ReporterIncident.property_id,
            Assignment.status.in_(["OFFERED", "ACCEPTED", "EN_ROUTE", "ON_SCENE"])).exists()
        filters.append(assigned if has_active_assignment else ~assigned)
    total = await session.scalar(select(func.count()).select_from(ReporterIncident).where(*filters))
    relation_options = (selectinload(ReporterIncident.evidence), selectinload(ReporterIncident.timeline)) if include_details else (raiseload("*"),)
    incidents = list((await session.scalars(
        select(ReporterIncident).options(*relation_options).where(*filters).order_by(ReporterIncident.created_at.desc(), ReporterIncident.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all())
    latest = {}
    if incidents:
        ranked = select(Assignment.id.label("assignment_id"), func.row_number().over(
            partition_by=Assignment.reporter_incident_id,
            order_by=(Assignment.offered_at.desc(), Assignment.id.desc())).label("rank")).where(
                Assignment.reporter_incident_id.in_([item.id for item in incidents])).subquery()
        assignments = await session.scalars(select(Assignment).join(ranked,
            Assignment.id == ranked.c.assignment_id).where(ranked.c.rank == 1))
        for assignment in assignments:
            latest.setdefault(assignment.reporter_incident_id, assignment)
    return ReporterIncidentPage(
        items=[_incident_response(incident, latest.get(incident.id), details=include_details) for incident in incidents],
        page=page, page_size=page_size, total=total or 0,
    )


@router.get("/reporter/incidents/{incident_id}", response_model=ReporterIncidentResponse)
async def get_reporter_incident(
    incident_id: int,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
) -> ReporterIncidentResponse:
    incident = await _owned_incident(incident_id, user.id, session)
    return _incident_response(incident, await _latest_dispatch(incident.id, session))


@router.post("/reporter/incidents/{incident_id}/evidence/{evidence_id}/access")
async def grant_reporter_evidence_access(
    incident_id: int,
    evidence_id: int,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
) -> dict:
    incident = await _owned_incident(incident_id, user.id, session)
    evidence = await session.scalar(select(ReporterIncidentEvidence).where(
        ReporterIncidentEvidence.id == evidence_id,
        ReporterIncidentEvidence.incident_id == incident.id,
    ))
    if evidence is None:
        raise ApplicationError("EVIDENCE_NOT_FOUND", "The requested evidence does not exist.", 404)
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence signing is not configured.", 503)
    await ReporterStorage(settings).ensure(evidence.file_path)
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    grant = jwt.encode({
        "sub": f"reporter:{user.id}", "aud": "reporter-evidence", "exp": expires,
        "incident_id": incident.id, "evidence_id": evidence.id,
    }, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    session.add(AuditRecord(
        property_id=incident.property_id, actor_subject=f"reporter:{user.id}",
        action="REPORTER_EVIDENCE_ACCESS_GRANTED", resource_type="reporter_incident_evidence",
        resource_id=str(evidence.id), correlation_id=str(uuid4()), details={},
    ))
    await session.commit()
    return {
        "url": f"/api/v1/reporter/incidents/{incident.id}/evidence/{evidence.id}/content?grant={grant}",
        "expires_at": expires.isoformat(),
    }


@router.get("/reporter/incidents/{incident_id}/evidence/{evidence_id}/content")
async def reporter_evidence_content(
    incident_id: int,
    evidence_id: int,
    grant: str = Query(min_length=1, max_length=4096),
    range_header: str | None = Header(None, alias="Range"),
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence signing is not configured.", 503)
    try:
        claims = jwt.decode(
            grant, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            audience="reporter-evidence",
            options={"require": ["exp", "sub", "aud", "incident_id", "evidence_id"]},
        )
        if claims["sub"] != f"reporter:{user.id}" or claims["incident_id"] != incident_id or claims["evidence_id"] != evidence_id:
            raise ValueError("Grant binding mismatch")
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise ApplicationError("INVALID_MEDIA_GRANT", "The evidence grant is invalid or expired.", 401) from None
    incident = await _owned_incident(incident_id, user.id, session)
    evidence = await session.scalar(select(ReporterIncidentEvidence).where(
        ReporterIncidentEvidence.id == evidence_id, ReporterIncidentEvidence.incident_id == incident.id,
    ))
    if evidence is None:
        raise ApplicationError("EVIDENCE_NOT_FOUND", "The requested evidence does not exist.", 404)
    session.add(AuditRecord(
        property_id=incident.property_id, actor_subject=f"reporter:{user.id}",
        action="REPORTER_EVIDENCE_CONTENT_ACCESSED", resource_type="reporter_incident_evidence",
        resource_id=str(evidence.id), correlation_id=str(uuid4()), details={},
    ))
    await session.commit()
    return await ReporterStorage(settings).serve(evidence.file_path, evidence.media_type, range_header)


@router.post("/reporter/incidents/{incident_id}/evidence", response_model=ReporterIncidentResponse)
async def upload_reporter_evidence(
    incident_id: int,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(None, alias="X-Idempotency-Key", min_length=16, max_length=128),
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
) -> ReporterIncidentResponse:
    incident = await _owned_incident(incident_id, user.id, session)
    settings = get_settings()
    if settings.evidence_storage == "local" and not settings.evidence_root:
        raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence storage is not configured.", 503)
    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png", "video/mp4": ".mp4"}
    media_type = (file.content_type or "").lower()
    extension = allowed_types.get(media_type)
    if extension is None:
        raise ApplicationError("UNSUPPORTED_EVIDENCE", "Attach a JPG, PNG, or MP4 file.", 415)
    original_filename = Path(file.filename or "evidence").name[:255]
    content = await file.read(settings.reporter_evidence_max_bytes + 1)
    if len(content) > settings.reporter_evidence_max_bytes:
        raise ApplicationError("EVIDENCE_TOO_LARGE", "Evidence exceeds the configured size limit.", 413)
    if (media_type == "image/jpeg" and not content.startswith(b"\xff\xd8")) or (
        media_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise ApplicationError("INVALID_EVIDENCE", "The uploaded file is not a valid image.", 422)
    digest = hashlib.sha256(content).hexdigest()
    # Serialize property quota decisions before locking an individual report.
    await session.scalar(select(Property.id).where(Property.id == incident.property_id).with_for_update())
    await session.scalar(select(ReporterIncident.id).where(ReporterIncident.id == incident.id).with_for_update())
    if idempotency_key:
        previous = await session.scalar(select(ReporterIncidentEvidence).where(
            ReporterIncidentEvidence.incident_id == incident.id,
            ReporterIncidentEvidence.metadata_json["upload_key"].as_string() == idempotency_key))
        if previous is not None:
            if previous.metadata_json.get("sha256") != digest or previous.media_type != media_type:
                raise ApplicationError("IDEMPOTENCY_CONFLICT", "This upload key was already used for different evidence.", 409)
            owned = await _owned_incident(incident.id, user.id, session)
            return _incident_response(owned, await _latest_dispatch(owned.id, session))
    count, incident_bytes = (await session.execute(select(func.count(ReporterIncidentEvidence.id),
        func.coalesce(func.sum(ReporterIncidentEvidence.byte_size), 0)).where(
            ReporterIncidentEvidence.incident_id == incident.id))).one()
    if count >= settings.reporter_evidence_max_files or incident_bytes + len(content) > settings.reporter_evidence_max_incident_bytes:
        raise ApplicationError("INCIDENT_STORAGE_LIMIT", "This report has reached its attachment limit. Contact the property operator.", 413)
    property_bytes = await session.scalar(select(func.coalesce(func.sum(ReporterIncidentEvidence.byte_size), 0))
        .join(ReporterIncident, ReporterIncident.id == ReporterIncidentEvidence.incident_id)
        .where(ReporterIncident.property_id == incident.property_id))
    if property_bytes + len(content) > settings.reporter_evidence_max_property_bytes:
        raise ApplicationError("PROPERTY_STORAGE_LIMIT", "This property has reached its evidence storage limit. Contact the property operator.", 413)
    filename = secrets.token_hex(16) + extension
    storage = ReporterStorage(settings)
    relative_path = await storage.put(f"reporter-incidents/{incident.id}/{filename}", content, media_type)
    session.add(ReporterIncidentEvidence(
        incident_id=incident.id,
        media_type=media_type,
        file_path=relative_path,
        original_filename=original_filename,
        byte_size=len(content),
        metadata_json={"upload_key": idempotency_key, "sha256": digest},
    ))
    session.add(AuditRecord(
        property_id=incident.property_id, actor_subject=f"reporter:{user.id}",
        action="REPORTER_EVIDENCE_ATTACHED", resource_type="reporter_incident",
        resource_id=str(incident.id), correlation_id=str(uuid4()),
        details={"evidence_media_type": media_type, "byte_size": len(content)},
    ))
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        try:
            await storage.discard(relative_path)
        except Exception:
            pass  # Never delete other objects or hide the original DB failure.
        raise
    owned = await _owned_incident(incident.id, user.id, session)
    await get_event_publisher().publish_case(owned.property_id, f"reporter:{owned.id}")
    return _incident_response(owned, await _latest_dispatch(owned.id, session))
