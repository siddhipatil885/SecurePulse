"""Short-lived, audited access to evidence in a configured media directory."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, require_scope
from app.core.config import get_settings
from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.models import Evidence, SecurityEvent
from app.models.operations import AuditRecord

router = APIRouter(prefix="/evidence", tags=["evidence"])


def media_path(reference: str) -> Path:
    root = get_settings().evidence_root
    if not root:
        raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence storage is not configured.", 503)
    base = Path(root).resolve()
    path = (base / reference).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ApplicationError("MEDIA_NOT_FOUND", "Evidence media is unavailable.", 404)
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".mp4", ".webm"}:
        raise ApplicationError("MEDIA_NOT_FOUND", "Evidence media is unavailable.", 404)
    return path


async def lookup(session, evidence_id, property_ids):
    statement = select(Evidence, SecurityEvent).join(SecurityEvent, Evidence.event_id == SecurityEvent.id).where(Evidence.id == evidence_id)
    if property_ids is not None:
        statement = statement.where(SecurityEvent.property_id.in_(property_ids))
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise ApplicationError("EVIDENCE_NOT_FOUND", "The requested evidence does not exist.", 404)
    return row


async def audit(session, evidence, incident, actor, action):
    session.add(AuditRecord(
        property_id=incident.property_id, actor_subject=actor, action=action,
        resource_type="evidence", resource_id=str(evidence.id),
        correlation_id=str(uuid4()), details={},
    ))
    await session.commit()


@router.post("/{evidence_id}/access")
async def grant_access(
    evidence_id: int,
    principal: Principal = Depends(require_scope("read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    evidence, incident = await lookup(session, evidence_id, principal.property_ids)
    media_path(evidence.file_path)
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence signing is not configured.", 503)
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    token = jwt.encode({
        "sub": principal.subject, "aud": "evidence-playback", "exp": expires,
        "evidence_id": evidence.id, "property_id": incident.property_id,
    }, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    await audit(session, evidence, incident, principal.subject, "EVIDENCE_ACCESS_GRANTED")
    return {"url": f"/api/v1/evidence/{evidence_id}/content?grant={token}", "expires_at": expires.isoformat()}


@router.get("/{evidence_id}/content")
async def content(
    evidence_id: int,
    grant: str = Query(min_length=1, max_length=4096),
    principal: Principal = Depends(require_scope("read")),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ApplicationError("MEDIA_NOT_CONFIGURED", "Evidence signing is not configured.", 503)
    try:
        claims = jwt.decode(grant, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                            audience="evidence-playback", options={"require": ["exp", "sub", "aud", "evidence_id", "property_id"]})
        if claims["sub"] != principal.subject or claims["evidence_id"] != evidence_id:
            raise ValueError("Grant binding mismatch")
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise ApplicationError("INVALID_MEDIA_GRANT", "The evidence grant is invalid or expired.", 401) from None
    evidence, incident = await lookup(session, evidence_id, principal.property_ids)
    if claims["property_id"] != incident.property_id:
        raise ApplicationError("INVALID_MEDIA_GRANT", "The evidence grant is invalid.", 401)
    path = media_path(evidence.file_path)
    await audit(session, evidence, incident, principal.subject, "EVIDENCE_CONTENT_ACCESSED")
    return FileResponse(path, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})
