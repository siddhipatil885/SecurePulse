"""Marshal workspace: only currently authorized, personally assigned work."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
import jwt
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
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
from app.models import (Assignment, AssignmentEvent, AssignmentMessage, AuditRecord, MarshalAvailability,
                        MarshalEvidence, MarshalLocationHistory, MarshalProfile, Property,
                        ReporterIncident, SecurityEvent, User)
from app.repositories.dispatch import DispatchRepository
from app.services.dispatch_service import DispatchService

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
    if item.status in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'} and availability and availability.location_updated_at:
        responder_location = {
            'latitude': availability.latitude,
            'longitude': availability.longitude,
            'accuracy_m': availability.location_accuracy_m,
            'heading': availability.location_heading,
            'speed_mps': availability.location_speed_mps,
            'updated_at': availability.location_updated_at,
        }
    team = []
    if item.team_key:
        members = (await session.execute(select(Assignment, User.display_name).join(
            MarshalProfile, MarshalProfile.id == Assignment.marshal_profile_id
        ).join(User, User.id == MarshalProfile.user_id).where(
            Assignment.team_key == item.team_key
        ).order_by(Assignment.id))).all()
        team = [{'assignment_id': member.id, 'marshal_profile_id': member.marshal_profile_id,
                 'name': display_name, 'status': member.status, 'role': member.team_role}
                for member, display_name in members]
    uploaded = (await session.scalars(select(MarshalEvidence).where(
        MarshalEvidence.assignment_id == item.id).order_by(MarshalEvidence.created_at, MarshalEvidence.id))).all()
    evidence = [{'id': row.id, 'name': row.original_filename, 'media_type': row.media_type, 'source': 'marshal'}
                for row in uploaded]
    return {'id': item.id, 'property_id': item.property_id, 'property_name': property_record.name,
            'status': item.status, 'version': item.version, 'expires_at': item.expires_at,
            'offered_at': item.offered_at, 'closed_at': item.closed_at,
            'team_key': item.team_key, 'team_role': item.team_role, 'team': team,
            'incident_type': getattr(incident, 'event_type', getattr(incident, 'incident_type', 'Incident')),
            'severity': getattr(incident, 'severity', None),
            'description': getattr(incident, 'description', getattr(incident, 'reason', None)),
            'address': getattr(incident, 'address', None) or property_record.address,
            'latitude': getattr(incident, 'latitude', None),
            'longitude': getattr(incident, 'longitude', None),
            'responder_location': responder_location, 'evidence': evidence}


@router.get('/assignments')
async def assignments(history: bool = False, page: int = Query(1, ge=1),
                      user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    profile = await profile_for(user, session)
    active = ['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW']
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
                               'media_type': 'image/jpeg' if row.type.upper() == 'SNAPSHOT' else 'video/mp4', 'source': 'incident'} for row in records] + result['evidence']
    else:
        records = (await session.scalars(select(ReporterIncidentEvidence).where(ReporterIncidentEvidence.incident_id == item.reporter_incident_id))).all()
        result['evidence'] = [{'id': row.id, 'name': row.original_filename, 'media_type': row.media_type, 'source': 'incident'} for row in records] + result['evidence']
    return result


def assignment_thread(item: Assignment) -> str:
    return f'team:{item.team_key}' if item.team_key else f'assignment:{item.id}'


async def thread_access(assignment_id: int, user: User, session: AsyncSession, *, write=False):
    item = await assigned(assignment_id, user, session)
    allowed = {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW'}
    if item.status not in (allowed if write else allowed | {'COMPLETED'}):
        raise ApplicationError('ASSIGNMENT_NOT_ACTIVE', 'This assignment conversation is unavailable.', 409)
    return item


@router.get('/assignments/{assignment_id}/messages')
async def read_messages(assignment_id: int, after_id: int = Query(0, ge=0),
                        user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    item = await thread_access(assignment_id, user, session)
    rows = (await session.execute(select(AssignmentMessage, User.display_name).join(
        User, User.id == AssignmentMessage.sender_user_id).where(
        AssignmentMessage.thread_key == assignment_thread(item), AssignmentMessage.id > after_id
    ).order_by(AssignmentMessage.id).limit(100))).all()
    return {'items': [{'id': message.id, 'sender': display_name, 'body': message.body,
                       'created_at': message.created_at, 'mine': message.sender_user_id == user.id}
                      for message, display_name in rows]}


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    client_message_id: str = Field(min_length=8, max_length=80)


@router.post('/assignments/{assignment_id}/messages', status_code=201)
async def send_message(assignment_id: int, body: MessageCreate, user: User = Depends(get_reporter),
                       session: AsyncSession = Depends(get_session)):
    item = await thread_access(assignment_id, user, session, write=True)
    text = body.body.strip()
    if not text:
        raise ApplicationError('INVALID_MESSAGE', 'Enter a message.', 422)
    existing = await session.scalar(select(AssignmentMessage).where(
        AssignmentMessage.sender_user_id == user.id,
        AssignmentMessage.client_message_id == body.client_message_id))
    if existing is None:
        existing = AssignmentMessage(assignment_id=item.id, property_id=item.property_id,
            sender_user_id=user.id, thread_key=assignment_thread(item),
            client_message_id=body.client_message_id, body=text)
        session.add(existing)
        session.add(AuditRecord(property_id=item.property_id, actor_subject=f'marshal:{user.id}',
            action='ASSIGNMENT_MESSAGE_SENT', resource_type='assignment', resource_id=str(item.id),
            correlation_id=f'message:{body.client_message_id}', details={}))
    await session.commit()
    await get_event_publisher().publish_case(item.property_id,
        f"{'camera' if item.security_event_id is not None else 'reporter'}:{item.security_event_id or item.reporter_incident_id}")
    return {'id': existing.id, 'body': existing.body}


@router.get('/assignments/{assignment_id}/nearby')
async def nearby_marshals(assignment_id: int, user: User = Depends(get_reporter),
                          session: AsyncSession = Depends(get_session)):
    """List fresh, eligible responders nearest to the requesting marshal."""
    item = await assigned(assignment_id, user, session)
    if item.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}:
        raise ApplicationError('TEAM_NOT_ACTIVE', 'Request backup after accepting the assignment.', 409)
    profile = await profile_for(user, session)
    own_location = await session.get(MarshalAvailability, profile.id)
    now = datetime.now(timezone.utc)
    location_time = own_location.location_updated_at if own_location else None
    if location_time and location_time.tzinfo is None:
        location_time = location_time.replace(tzinfo=timezone.utc)
    destination = None
    if (own_location and own_location.latitude is not None and own_location.longitude is not None
            and location_time and location_time >= now - timedelta(minutes=2)):
        destination = (own_location.latitude, own_location.longitude)
    if destination is None:
        return {'items': [], 'location_required': True}
    active_team_ids = set()
    if item.team_key:
        active_team_ids = set((await session.scalars(select(Assignment.marshal_profile_id).where(
            Assignment.team_key == item.team_key,
            Assignment.status.in_(['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW']),
        ))).all())
    profiles = await DispatchRepository(session).eligible_marshals(
        profile.property_id, now - timedelta(minutes=5), active_team_ids | {profile.id}, destination
    )
    result = []
    for candidate in profiles:
        availability = await session.get(MarshalAvailability, candidate.id)
        person = await session.get(User, candidate.user_id)
        distance_m = None
        if destination and availability and availability.latitude is not None and availability.longitude is not None:
            from app.services.location import distance_metres
            distance_m = round(distance_metres(availability.latitude, availability.longitude, *destination))
        result.append({'marshal_profile_id': candidate.id, 'name': person.display_name if person else None,
                       'distance_m': distance_m})
    return {'items': result}


class BackupRequest(BaseModel):
    marshal_profile_ids: list[int] = Field(min_length=1, max_length=10)
    idempotency_key: str = Field(min_length=8, max_length=128)


@router.post('/assignments/{assignment_id}/backup')
async def request_backup(assignment_id: int, body: BackupRequest, user: User = Depends(get_reporter),
                         session: AsyncSession = Depends(get_session)):
    """Create same-incident team offers for selected nearby responders."""
    item = await assigned(assignment_id, user, session, lock=True)
    if item.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}:
        raise ApplicationError('TEAM_NOT_ACTIVE', 'Only an active responder can request backup.', 409)
    offers = await DispatchService(session).create_team_offers(
        incident_id=item.security_event_id,
        reporter_incident_id=item.reporter_incident_id,
        property_id=item.property_id,
        marshal_profile_ids=body.marshal_profile_ids,
        expires_in_seconds=300,
        idempotency_key=hashlib.sha256(f'marshal:{user.id}:{body.idempotency_key}'.encode()).hexdigest()[:40],
        actor_subject=f'marshal:{user.id}',
    )
    await session.commit()
    for offer in offers:
        await get_event_publisher().publish_case(offer.property_id,
            f"{'camera' if offer.security_event_id is not None else 'reporter'}:{offer.security_event_id or offer.reporter_incident_id}")
    return {'offers': [{'assignment_id': offer.id, 'status': offer.status} for offer in offers]}


class TeamRoleUpdate(BaseModel):
    role: str = Field(min_length=2, max_length=80)


@router.put('/assignments/{assignment_id}/team/{member_assignment_id}/role')
async def assign_team_role(assignment_id: int, member_assignment_id: int, body: TeamRoleUpdate,
                           user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    """Let an active team member split work by setting a teammate's task label."""
    lead = await assigned(assignment_id, user, session)
    target = await session.scalar(select(Assignment).where(Assignment.id == member_assignment_id).with_for_update())
    if (not lead.team_key or target is None or target.team_key != lead.team_key
            or target.status not in {'OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}
            or lead.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}):
        raise ApplicationError('TEAM_MEMBER_NOT_FOUND', 'This responder is not an active member of your team.', 404)
    target.team_role = body.role.strip()
    if not target.team_role:
        raise ApplicationError('INVALID_TEAM_ROLE', 'Enter a task for this responder.', 422)
    session.add(AssignmentEvent(
        assignment_id=target.id,
        previous_status=target.status,
        new_status=target.status,
        actor_subject=f'marshal:{user.id}',
        reason=f'Team task assigned: {target.team_role}',
        correlation_id='team-role:' + uuid4().hex,
        occurred_at=datetime.now(timezone.utc),
    ))
    await session.commit()
    await get_event_publisher().publish_case(target.property_id,
        f"{'camera' if target.security_event_id is not None else 'reporter'}:{target.security_event_id or target.reporter_incident_id}")
    return {'assignment_id': target.id, 'role': target.team_role}


@router.post('/assignments/{assignment_id}/evidence', status_code=201)
async def upload_assignment_evidence(assignment_id: int, file: UploadFile = File(...),
        idempotency_key: str | None = Header(None, alias='X-Idempotency-Key', min_length=16, max_length=128),
        user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    item = await assigned(assignment_id, user, session, lock=True)
    if item.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}:
        raise ApplicationError('EVIDENCE_NOT_ALLOWED', 'Evidence can be added while investigating this response.', 409)
    settings = get_settings()
    media_type = (file.content_type or '').lower()
    extensions = {'image/jpeg': '.jpg', 'image/png': '.png', 'video/mp4': '.mp4', 'video/quicktime': '.mp4'}
    extension = extensions.get(media_type)
    if not extension:
        raise ApplicationError('UNSUPPORTED_EVIDENCE', 'Attach a JPG, PNG, MP4, or phone video.', 415)
    content = await file.read(settings.reporter_evidence_max_bytes + 1)
    if len(content) > settings.reporter_evidence_max_bytes:
        raise ApplicationError('EVIDENCE_TOO_LARGE', 'This file exceeds the evidence size limit.', 413)
    if ((media_type == 'image/jpeg' and not content.startswith(b'\xff\xd8'))
        or (media_type == 'image/png' and not content.startswith(b'\x89PNG\r\n\x1a\n'))
        or (media_type.startswith('video/') and (len(content) < 12 or content[4:8] != b'ftyp'))):
        raise ApplicationError('INVALID_EVIDENCE', 'The selected file is not valid media.', 422)
    digest = hashlib.sha256(content).hexdigest()
    await session.scalar(select(Property.id).where(Property.id == item.property_id).with_for_update())
    if idempotency_key:
        previous = await session.scalar(select(MarshalEvidence).where(
            MarshalEvidence.assignment_id == item.id, MarshalEvidence.idempotency_key == idempotency_key))
        if previous:
            if previous.sha256 != digest or previous.media_type != media_type:
                raise ApplicationError('IDEMPOTENCY_CONFLICT', 'This upload key was already used for different media.', 409)
            return {'id': previous.id, 'name': previous.original_filename, 'media_type': previous.media_type, 'source': 'marshal'}
    count, total = (await session.execute(select(func.count(MarshalEvidence.id),
        func.coalesce(func.sum(MarshalEvidence.byte_size), 0)).where(MarshalEvidence.assignment_id == item.id))).one()
    if count >= settings.reporter_evidence_max_files or total + len(content) > settings.reporter_evidence_max_incident_bytes:
        raise ApplicationError('INCIDENT_STORAGE_LIMIT', 'This response has reached its attachment limit.', 413)
    name = Path(file.filename or 'field-evidence').name[:255]
    correlation = uuid4().hex
    storage = ReporterStorage(settings)
    path = await storage.put(f'marshal-assignments/{item.id}/{secrets.token_hex(16)}{extension}', content, media_type)
    evidence = MarshalEvidence(assignment_id=item.id, property_id=item.property_id, uploader_user_id=user.id,
        media_type=media_type, file_path=path, original_filename=name, byte_size=len(content),
        idempotency_key=idempotency_key or correlation, sha256=digest)
    session.add(evidence)
    session.add(AuditRecord(property_id=item.property_id, actor_subject=f'marshal:{user.id}',
        action='MARSHAL_EVIDENCE_ATTACHED', resource_type='assignment', resource_id=str(item.id),
        correlation_id=correlation, details={'media_type': media_type, 'byte_size': len(content)}))
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        try:
            await storage.discard(path)
        except Exception:
            pass
        raise
    await get_event_publisher().publish_case(item.property_id,
        f"{'camera' if item.security_event_id is not None else 'reporter'}:{item.security_event_id or item.reporter_incident_id}")
    return {'id': evidence.id, 'name': name, 'media_type': media_type, 'source': 'marshal'}


async def assignment_evidence(assignment_id, evidence_id, user, session, source='incident'):
    item = await assigned(assignment_id, user, session)
    if item.status not in {'OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW', 'COMPLETED'}:
        raise ApplicationError('NOT_FOUND', 'Evidence is no longer available for this assignment.', 404)
    deadline = item.expires_at.replace(tzinfo=timezone.utc) if item.expires_at.tzinfo is None else item.expires_at
    if item.status == 'OFFERED' and deadline <= datetime.now(timezone.utc):
        raise ApplicationError('NOT_FOUND', 'This offer has expired.', 404)
    if source == 'marshal':
        evidence = await session.scalar(select(MarshalEvidence).where(
            MarshalEvidence.id == evidence_id, MarshalEvidence.assignment_id == item.id,
            MarshalEvidence.property_id == item.property_id))
        if evidence is None:
            raise ApplicationError('EVIDENCE_NOT_FOUND', 'The requested evidence does not exist.', 404)
        return item, source, None, evidence
    case_source, source_id = ('camera', item.security_event_id) if item.security_event_id is not None else ('reporter', item.reporter_incident_id)
    incident, evidence = await CaseService(session).evidence_record(item.property_id, case_source, source_id, evidence_id)
    return item, case_source, incident, evidence


@router.post('/assignments/{assignment_id}/evidence/{evidence_id}/access')
async def evidence_access(assignment_id: int, evidence_id: int, source: str = Query('incident', pattern='^(incident|marshal)$'), user: User = Depends(get_reporter),
                          session: AsyncSession = Depends(get_session)):
    item, source, incident, evidence = await assignment_evidence(assignment_id, evidence_id, user, session, source)
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ApplicationError('MEDIA_NOT_CONFIGURED', 'Evidence signing is not configured.', 503)
    if source in {'reporter', 'marshal'}:
        await ReporterStorage(settings).ensure(evidence.file_path)
    elif not evidence_api.frigate_snapshot(evidence, incident):
        evidence_api.media_path(evidence.file_path)
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    token = jwt.encode({'aud': 'marshal-evidence', 'sub': str(user.id), 'exp': expires, 'source': source,
                        'assignment_id': item.id, 'evidence_id': evidence.id}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    if source == 'marshal':
        session.add(AuditRecord(property_id=item.property_id, actor_subject=f'marshal:{user.id}', action='MARSHAL_EVIDENCE_ACCESS_GRANTED', resource_type='marshal_evidence', resource_id=str(evidence.id), correlation_id=uuid4().hex, details={}))
        await session.commit()
    else:
        await evidence_api.audit(session, evidence, incident, f'marshal:{user.id}', 'MARSHAL_EVIDENCE_ACCESS_GRANTED')
    return {'url': f'/api/v1/marshal/assignments/{item.id}/evidence/{evidence.id}/content?source={source}&grant={token}', 'expires_at': expires}


@router.get('/assignments/{assignment_id}/evidence/{evidence_id}/content')
async def evidence_content(assignment_id: int, evidence_id: int, source: str = Query('incident', pattern='^(incident|marshal)$'), grant: str = Query(min_length=1, max_length=4096),
                           range_header: str | None = Header(None, alias='Range'), user: User = Depends(get_reporter),
                           session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    try:
        claims = jwt.decode(grant, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience='marshal-evidence',
                            options={'require': ['aud', 'exp', 'sub', 'assignment_id', 'evidence_id', 'source']})
        if (claims['sub'], claims['assignment_id'], claims['evidence_id'], claims['source']) != (str(user.id), assignment_id, evidence_id, source):
            raise ValueError('Grant mismatch')
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise ApplicationError('INVALID_MEDIA_GRANT', 'The evidence link is invalid or expired.', 401) from None
    item, source, incident, evidence = await assignment_evidence(assignment_id, evidence_id, user, session, source)
    if source == 'marshal':
        session.add(AuditRecord(property_id=item.property_id, actor_subject=f'marshal:{user.id}', action='MARSHAL_EVIDENCE_CONTENT_ACCESSED', resource_type='marshal_evidence', resource_id=str(evidence.id), correlation_id=uuid4().hex, details={}))
        await session.commit()
        return await ReporterStorage(settings).serve(evidence.file_path, evidence.media_type, range_header)
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
    if item.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}:
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
    active_assignments = (await session.scalars(select(Assignment).where(
        Assignment.marshal_profile_id == profile.id,
        Assignment.status.in_({'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}),
    ))).all()
    for active_assignment in active_assignments:
        session.add(MarshalLocationHistory(
            assignment_id=active_assignment.id, property_id=active_assignment.property_id,
            marshal_profile_id=profile.id, latitude=body.latitude, longitude=body.longitude,
            accuracy_m=body.accuracy_m, heading=body.heading, speed_mps=body.speed_mps, recorded_at=now,
        ))
    await session.execute(delete(MarshalLocationHistory).where(
        MarshalLocationHistory.marshal_profile_id == profile.id,
        MarshalLocationHistory.recorded_at < now - timedelta(hours=24),
    ))
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
    if item.version != body.expected_version or item.status not in {'ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING'}:
        raise ApplicationError('OFFER_CONFLICT', 'Refresh this assignment before adding a note.', 409)
    session.add(AssignmentEvent(assignment_id=item.id, previous_status=item.status,
        new_status=item.status, actor_subject=f'marshal:{user.id}', reason=text,
        correlation_id='note:' + uuid4().hex, occurred_at=datetime.now(timezone.utc)))
    await session.commit()
    return {'saved': True}
