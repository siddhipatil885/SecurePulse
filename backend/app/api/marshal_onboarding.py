from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.marshal import profile_for
from app.core.config import get_settings
from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.reporter_auth import get_reporter
from app.models import Assignment, AuditRecord, MarshalAvailability, MarshalOnboarding, User
from app.services.marshal_identity import CONSENT_VERSION, IdentityDetails, IdentityVault

router = APIRouter(prefix='/marshal/onboarding', tags=['marshal onboarding'])
limiter = SlidingWindowRateLimiter(5)


def secure_transport(request, settings):
    if request.url.scheme != 'https' and not (settings.app_env == 'development' and settings.marshal_identity_insecure_test_mode):
        raise ApplicationError('SECURE_CONNECTION_REQUIRED', 'Identity documents require a secure HTTPS connection.', 426)


def audit(session, profile, user, action):
    session.add(AuditRecord(property_id=profile.property_id, actor_subject=f'marshal:{user.id}', action=action,
        resource_type='marshal_onboarding', resource_id=str(profile.id), correlation_id=uuid4().hex, details={}))


@router.get('')
async def status(user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    profile = await profile_for(user, session)
    record = await session.get(MarshalOnboarding, profile.id)
    return {'status': profile.verification_status, 'review_note': record.review_note if record else None,
            'submitted_at': record.submitted_at if record else None,
            'id_type': record.id_type if record else None,
            'id_last_four': record.id_last_four if record else None,
            'documents': list(record.documents) if record else [], 'consent_version': CONSENT_VERSION}


@router.post('', status_code=201)
async def submit(request: Request, details: str = Form(max_length=10000), portrait: UploadFile = File(), id_front: UploadFile = File(),
                 id_back: UploadFile | None = File(None), user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    profile = await profile_for(user, session)
    settings = get_settings()
    secure_transport(request, settings)
    if await limiter.check(str(user.id)):
        raise ApplicationError('RATE_LIMITED', 'Wait before submitting again.', 429)
    # Serialize submissions and reviews for this marshal.
    await session.refresh(profile, with_for_update=True)
    if profile.verification_status in {'APPROVED', 'PENDING'}:
        raise ApplicationError('ONBOARDING_LOCKED', 'Your submission is approved or awaiting review. Contact your administrator for corrections.', 409)
    try:
        parsed = IdentityDetails.model_validate_json(details)
    except ValidationError:
        # Do not echo sensitive input values in validation errors or logs.
        raise ApplicationError('INVALID_ONBOARDING', 'Check your name, adult date of birth, government ID, address, different contact numbers and both consent boxes.', 422) from None
    vault = IdentityVault(settings)
    documents = {}
    previous = await session.get(MarshalOnboarding, profile.id)
    previous_documents = previous.documents.copy() if previous else {}
    try:
        for kind, upload in [('portrait', portrait), ('id_front', id_front), ('id_back', id_back)]:
            if upload is None:
                continue
            if upload.content_type not in {'image/jpeg', 'image/png'}:
                raise ApplicationError('INVALID_IDENTITY_PHOTO', 'Choose JPG or PNG images.', 422)
            raw = await upload.read(3_000_001)
            if len(raw) > 3_000_000:
                raise ApplicationError('IDENTITY_PHOTO_TOO_LARGE', 'Each photo must be smaller than 3 MB.', 413)
            documents[kind] = await run_in_threadpool(vault.save_photo, raw)
        record = previous or MarshalOnboarding(marshal_profile_id=profile.id)
        record.encrypted_details = vault.encrypt_details(parsed)
        record.documents = documents
        record.id_type = parsed.id_type
        record.id_last_four = parsed.id_number[-4:]
        record.consent_version = CONSENT_VERSION
        record.submitted_at = datetime.now(timezone.utc)
        record.reviewed_at = None; record.reviewed_by = None; record.review_note = None
        session.add(record)
        profile.verification_status = 'PENDING'
        availability = await session.get(MarshalAvailability, profile.id)
        if availability:
            availability.on_duty = False; availability.available = False
        audit(session, profile, user, 'MARSHAL_ONBOARDING_SUBMITTED')
        await session.commit()
    except BaseException:
        await session.rollback()
        await run_in_threadpool(vault.discard, documents)
        raise
    if previous_documents:
        await run_in_threadpool(vault.discard, previous_documents)
    return {'status': 'PENDING', 'message': 'Submitted for administrator review. You can go on duty after approval.'}


@router.get('/documents/{kind}')
async def document(kind: str, request: Request, user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    profile = await profile_for(user, session)
    secure_transport(request, get_settings())
    record = await session.get(MarshalOnboarding, profile.id)
    if not record or kind not in record.documents:
        raise ApplicationError('NOT_FOUND', 'Document not found.', 404)
    vault = IdentityVault(get_settings())
    content = await run_in_threadpool(vault.photo, record.documents[kind])
    audit(session, profile, user, 'MARSHAL_IDENTITY_DOCUMENT_ACCESSED'); await session.commit()
    return Response(content, media_type='image/jpeg', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})


@router.delete('', status_code=204)
async def withdraw(user: User = Depends(get_reporter), session: AsyncSession = Depends(get_session)):
    profile = await profile_for(user, session)
    await session.refresh(profile, with_for_update=True)
    active = await session.scalar(select(Assignment.id).where(Assignment.marshal_profile_id == profile.id,
        Assignment.status.in_(['OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE'])).limit(1))
    if active:
        raise ApplicationError('ACTIVE_ASSIGNMENT', 'Contact your dispatcher to close active assignments before withdrawing.', 409)
    record = await session.get(MarshalOnboarding, profile.id)
    documents = record.documents.copy() if record else {}
    vault = IdentityVault(get_settings())
    if documents:
        await run_in_threadpool(vault.discard, documents)
    if record:
        await session.delete(record)
    profile.verification_status = 'REQUIRED'
    availability = await session.get(MarshalAvailability, profile.id)
    if availability:
        availability.on_duty = False; availability.available = False
    audit(session, profile, user, 'MARSHAL_ONBOARDING_WITHDRAWN'); await session.commit()
    return Response(status_code=204)
