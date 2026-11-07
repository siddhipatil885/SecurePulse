"""Marshal workspace: only currently authorized, personally assigned work."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query
import jwt
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dispatch import require_role
from app.core.dependencies import get_session
from app.core.dependencies import get_event_publisher
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import get_reporter
from app.core.config import get_settings
from app.core.auth import Principal
from app.api import evidence as evidence_api
from app.services.case_service import CaseService
from app.services.reporter_storage import ReporterStorage
from app.models import (Assignment, AssignmentEvent, MarshalAvailability, MarshalProfile,
                        Property, ReporterIncident, SecurityEvent, User)

router = APIRouter(prefix='/marshal', tags=['marshal'])


async def profile_for(user: User, session: AsyncSession):
    profile = await session.scalar(select(MarshalProfile).where(
        MarshalProfile.user_id == user.id, MarshalProfile.active.is_(True)))
    if profile is None:
        raise ApplicationError('FORBIDDEN', 'A marshal account is required.', 403)
    await require_role(session, user.id, profile.property_id, {'marshal'})
    return profile


async def assigned(assignment_id: int, user: User, session: AsyncSession, *, lock=False):
    profile = await profile_for(user, session)
    statement = select(Assignment).where(Assignment.id == assignment_id,
        Assignment.marshal_profile_id == profile.id, Assignment.property_id == profile.property_id)
    if lock:
        statement = statement.with_for_update()
    item = await session.scalar(statement)
    if item is None:
        raise ApplicationError('NOT_FOUND', 'Assignment not found.', 404)
    return item


@router.get('/workspace')
async def workspace(user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    profile = await profile_for(user, session)
    availability = await session.get(MarshalAvailability, profile.id)
    property_record = await session.get(Property, profile.property_id)
    updated = availability.updated_at if availability else None
    if updated and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    fresh = bool(updated and updated >= datetime.now(timezone.utc) - timedelta(minutes=5))
    return {'property_id': profile.property_id, 'property_name': property_record.name,
            'verification_status': profile.verification_status,
            'service_area': profile.service_area, 'capacity': profile.capacity,
            'on_duty': bool(fresh and availability.on_duty),
            'available': bool(fresh and availability.available)}


async def describe(item: Assignment, session: AsyncSession):
    property_record = await session.get(Property, item.property_id)
    incident = await session.get(SecurityEvent, item.security_event_id) if item.security_event_id else await session.get(ReporterIncident, item.reporter_incident_id)
    availability = await session.get(MarshalAvailability, item.marshal_profile_id)
    responder_location = None
    if item.status in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE'} and availability and availability.location_updated_at:
        responder_location = {
            'latitude': availability.latitude,
            'longitude': availability.longitude,
            'accuracy_m': availability.location_accuracy_m,
            'heading': availability.location_heading,
            'speed_mps': availability.location_speed_mps,
            'updated_at': availability.location_updated_at,
        }
    return {'id': item.id, 'property_id': item.property_id, 'property_name': property_record.name,
            'status': item.status, 'version': item.version, 'expires_at': item.expires_at,
            'offered_at': item.offered_at, 'closed_at': item.closed_at,
            'incident_type': getattr(incident, 'event_type', getattr(incident, 'incident_type', 'Incident')),
            'severity': getattr(incident, 'severity', None),
            'description': getattr(incident, 'description', getattr(incident, 'reason', None)),
            'address': getattr(incident, 'address', None) or property_record.address,
            'latitude': getattr(incident, 'latitude', None),
            'longitude': getattr(incident, 'longitude', None),
            'responder_location': responder_location}


@router.get('/assignments')
async def assignments(history: bool = False, page: int = Query(1, ge=1),
                      user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    profile = await profile_for(user, session)
    active = ['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE']
    statement = select(Assignment).where(Assignment.marshal_profile_id == profile.id,
        Assignment.property_id == profile.property_id)
    statement = statement.where(Assignment.status.not_in(active) if history else Assignment.status.in_(active))
    rows = (await session.scalars(statement.order_by(Assignment.offered_at.desc(), Assignment.id.desc())
                                   .offset((page - 1) * 20).limit(20))).all()
    return {'items': [await describe(item, session) for item in rows], 'page': page}


@router.get('/assignments/{assignment_id}')
async def detail(assignment_id: int, user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    item = await assigned(assignment_id, user, session)
    result = await describe(item, session)
    events = (await session.scalars(select(AssignmentEvent).where(AssignmentEvent.assignment_id == item.id)
                                   .order_by(AssignmentEvent.occurred_at, AssignmentEvent.id))).all()
    result['timeline'] = [{'id': event.id, 'status': event.new_status, 'note': event.reason,
                           'at': event.occurred_at} for event in events]
    from app.models import Evidence, ReporterIncidentEvidence
    if item.security_event_id is not None:
        records = (await session.scalars(select(Evidence).where(Evidence.event_id == item.security_event_id))).all()
        result['evidence'] = [{'id': row.id, 'name': 'Incident ' + row.type.lower(),
                               'media_type': 'image/jpeg' if row.type.upper() == 'SNAPSHOT' else 'video/mp4'} for row in records]
    else:
        records = (await session.scalars(select(ReporterIncidentEvidence).where(ReporterIncidentEvidence.incident_id == item.reporter_incident_id))).all()
        result['evidence'] = [{'id': row.id, 'name': row.original_filename, 'media_type': row.media_type} for row in records]
    return result


async def assignment_evidence(assignment_id, evidence_id, user, session):
    item = await assigned(assignment_id, user, session)
    if item.status not in {'OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'COMPLETED'}:
        raise ApplicationError('NOT_FOUND', 'Evidence is no longer available for this assignment.', 404)
    deadline = item.expires_at.replace(tzinfo=timezone.utc) if item.expires_at.tzinfo is None else item.expires_at
    if item.status == 'OFFERED' and deadline <= datetime.now(timezone.utc):
        raise ApplicationError('NOT_FOUND', 'This offer has expired.', 404)
    source, source_id = ('camera', item.security_event_id) if item.security_event_id is not None else ('reporter', item.reporter_incident_id)
    incident, evidence = await CaseService(session).evidence_record(item.property_id, source, source_id, evidence_id)
    return item, source, incident, evidence


@router.post('/assignments/{assignment_id}/evidence/{evidence_id}/access')
async def evidence_access(assignment_id: int, evidence_id: int, user: User = Depends(get_reporter),
                          session: AsyncSession = Depends(get_session)):
    item, source, incident, evidence = await assignment_evidence(assignment_id, evidence_id, user, session)
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ApplicationError('MEDIA_NOT_CONFIGURED', 'Evidence signing is not configured.', 503)
    if source == 'reporter':
        await ReporterStorage(settings).ensure(evidence.file_path)
    elif not evidence_api.frigate_snapshot(evidence, incident):
        evidence_api.media_path(evidence.file_path)
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    token = jwt.encode({'aud': 'marshal-evidence', 'sub': str(user.id), 'exp': expires,
                        'assignment_id': item.id, 'evidence_id': evidence.id}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    await evidence_api.audit(session, evidence, incident, f'marshal:{user.id}', 'MARSHAL_EVIDENCE_ACCESS_GRANTED')
    return {'url': f'/api/v1/marshal/assignments/{item.id}/evidence/{evidence.id}/content?grant={token}', 'expires_at': expires}


@router.get('/assignments/{assignment_id}/evidence/{evidence_id}/content')
async def evidence_content(assignment_id: int, evidence_id: int, grant: str = Query(min_length=1, max_length=4096),
                           range_header: str | None = Header(None, alias='Range'), user: User = Depends(get_reporter),
                           session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    try:
        claims = jwt.decode(grant, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience='marshal-evidence',
                            options={'require': ['aud', 'exp', 'sub', 'assignment_id', 'evidence_id']})
        if (claims['sub'], claims['assignment_id'], claims['evidence_id']) != (str(user.id), assignment_id, evidence_id):
            raise ValueError('Grant mismatch')
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise ApplicationError('INVALID_MEDIA_GRANT', 'The evidence link is invalid or expired.', 401) from None
    item, source, incident, evidence = await assignment_evidence(assignment_id, evidence_id, user, session)
    if source == 'camera':
        return await evidence_api.serve_evidence(evidence, incident, Principal(subject=f'marshal:{user.id}', scopes=frozenset({'read'}), property_ids=frozenset({item.property_id})), session)
    await evidence_api.audit(session, evidence, incident, f'marshal:{user.id}', 'MARSHAL_EVIDENCE_CONTENT_ACCESSED')
    return await ReporterStorage(settings).serve(evidence.file_path, evidence.media_type, range_header)


class Note(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(gt=0)


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000)
    heading: float | None = Field(default=None, ge=0, lt=360)
    speed_mps: float | None = Field(default=None, ge=0, le=1000)


@router.post('/assignments/{assignment_id}/location')
async def update_location(
    assignment_id: int,
    body: LocationUpdate,
    user: User = Depends(get_reporter),
    session: AsyncSession = Depends(get_session),
):
    item = await assigned(assignment_id, user, session, lock=True)
    if item.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE'}:
        raise ApplicationError('LOCATION_NOT_ALLOWED', 'Location updates require an active assignment.', 409)
    profile = await profile_for(user, session)
    availability = await session.get(MarshalAvailability, profile.id)
    if availability is None:
        availability = MarshalAvailability(marshal_profile_id=profile.id)
        session.add(availability)
    now = datetime.now(timezone.utc)
    last_location = availability.location_updated_at
    if last_location and last_location.tzinfo is None:
        last_location = last_location.replace(tzinfo=timezone.utc)
    if last_location and (
        now - last_location
    ).total_seconds() < 4:
        raise ApplicationError('LOCATION_RATE_LIMITED', 'Location updates must be at least four seconds apart.', 429)
    availability.latitude = body.latitude
    availability.longitude = body.longitude
    availability.location_accuracy_m = body.accuracy_m
    availability.location_heading = body.heading
    availability.location_speed_mps = body.speed_mps
    availability.location_updated_at = now
    await session.commit()
    await get_event_publisher().publish_marshal_location(
        item.property_id,
        item.id,
        {
            'latitude': body.latitude,
            'longitude': body.longitude,
            'accuracy_m': body.accuracy_m,
            'heading': body.heading,
            'speed_mps': body.speed_mps,
            'updated_at': now.isoformat(),
        },
    )
    return {'assignment_id': assignment_id, 'updated_at': now}


@router.post('/assignments/{assignment_id}/notes', status_code=201)
async def add_note(assignment_id: int, body: Note, user: User = Depends(get_reporter),
                   session: AsyncSession = Depends(get_session)):
    item = await assigned(assignment_id, user, session, lock=True)
    text = body.text.strip()
    if not text:
        raise ApplicationError('INVALID_NOTE', 'Enter an incident note.', 422)
    if item.version != body.expected_version or item.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE'}:
        raise ApplicationError('OFFER_CONFLICT', 'Refresh this assignment before adding a note.', 409)
    session.add(AssignmentEvent(assignment_id=item.id, previous_status=item.status,
        new_status=item.status, actor_subject=f'marshal:{user.id}', reason=text,
        correlation_id='note:' + uuid4().hex, occurred_at=datetime.now(timezone.utc)))
    await session.commit()
    return {'saved': True}
