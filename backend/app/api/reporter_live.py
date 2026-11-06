"""Camera-scoped HLS proxy for native players. All media remains on the host."""
from datetime import datetime, timedelta, timezone
import hashlib
import re
from urllib.parse import urlencode, urljoin, urlsplit

import httpx
import jwt
from fastapi import APIRouter, Depends, Query, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.core.reporter_auth import get_reporter
from app.core.auth import bearer_scheme
from app.models import Camera, Property, PropertyMembership, User

router = APIRouter(prefix='/reporter/cameras', tags=['reporter-live'])
ALLOWED = {'/api/stream.m3u8', '/api/hls/playlist.m3u8', '/api/hls/segment.ts', '/api/hls/init.mp4', '/api/hls/segment.m4s'}


async def authorized_camera(camera_id, property_id, user, session):
    membership = await session.scalar(select(PropertyMembership.id).join(Property).where(
        PropertyMembership.user_id == user.id, PropertyMembership.property_id == property_id,
        PropertyMembership.active.is_(True), PropertyMembership.role.in_(('owner', 'reporter')),
        Property.active.is_(True)))
    camera = await session.scalar(select(Camera).where(Camera.id == camera_id, Camera.property_id == property_id))
    if membership is None or camera is None:
        raise ApplicationError('NOT_FOUND', 'Camera is not available to this account.', 404)
    if not camera.enabled:
        raise ApplicationError('CAMERA_DISABLED', 'This camera is disabled.', 409)
    return camera


def resource_hash(resource):
    return hashlib.sha256(resource.encode()).hexdigest()


def signed_url(camera_id, resource, claims, settings):
    claims = {**claims, 'resource': resource_hash(resource)}
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return f'/api/v1/reporter/cameras/{camera_id}/live?' + urlencode({'resource': resource, 'grant': token})


def rewrite_playlist(text, current_resource, camera_id, claims, settings):
    base = settings.go2rtc_url.rstrip('/')
    def replace(uri):
        target = urlsplit(urljoin(base + current_resource, uri))
        origin = urlsplit(base)
        if (target.scheme, target.netloc) != (origin.scheme, origin.netloc) or target.path not in ALLOWED:
            raise ApplicationError('INVALID_PLAYLIST', 'The camera returned an unsupported playlist.', 502)
        resource = target.path + ('?' + target.query if target.query else '')
        return signed_url(camera_id, resource, claims, settings)
    lines = []
    for line in text.splitlines():
        if line and not line.startswith('#'):
            line = replace(line.strip())
        elif 'URI="' in line:
            line = re.sub(r'URI="([^"]+)"', lambda match: 'URI="' + replace(match[1]) + '"', line)
        lines.append(line)
    return '\n'.join(lines) + '\n'


@router.post('/{camera_id}/live/access')
async def access(camera_id: int, property_id: int = Query(ge=1), user: User = Depends(get_reporter),
                 credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
                 session: AsyncSession = Depends(get_session)):
    camera = await authorized_camera(camera_id, property_id, user, session)
    settings = get_settings()
    # get_reporter already validated this exact bearer token. A playback grant
    # must not extend its parent's session lifetime.
    parent = jwt.decode(credentials.credentials, options={'verify_signature': False})
    deadline = min(int(parent['exp']), int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()))
    expires = datetime.fromtimestamp(deadline, timezone.utc)
    resource = '_root'
    claims = {'aud': 'reporter-live', 'sub': f'reporter:{user.id}', 'user_id': user.id,
              'ver': user.token_version, 'camera_id': camera.id, 'property_id': property_id, 'exp': int(expires.timestamp())}
    return {'url': signed_url(camera.id, resource, claims, settings), 'expires_at': expires.isoformat()}


@router.get('/{camera_id}/live')
async def live(camera_id: int, resource: str = Query(max_length=2048), grant: str = Query(max_length=4096),
               session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    try:
        claims = jwt.decode(grant, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience='reporter-live',
            options={'require': ['aud', 'sub', 'exp', 'user_id', 'ver', 'camera_id', 'property_id', 'resource']})
        if claims['camera_id'] != camera_id or claims['resource'] != resource_hash(resource):
            raise ValueError('Binding mismatch')
        if resource != '_root' and (urlsplit(resource).path not in ALLOWED or not resource.startswith('/api/') or resource.startswith('//')):
            raise ValueError('Invalid resource')
        user = await session.get(User, claims['user_id'])
        if not user or not user.active or user.token_version != claims['ver'] or claims['sub'] != f'reporter:{user.id}':
            raise ValueError('Revoked session')
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise ApplicationError('INVALID_MEDIA_GRANT', 'Live access has expired. Reopen the camera.', 401) from None
    camera = await authorized_camera(camera_id, claims['property_id'], user, session)
    if resource == '_root':
        resource = '/api/stream.m3u8?' + urlencode({'src': camera.frigate_camera_name, 'mp4': ''})
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
            async with client.stream('GET', settings.go2rtc_url.rstrip('/') + resource) as response:
                response.raise_for_status()
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 16_000_000:
                        raise ApplicationError('INVALID_STREAM', 'The camera returned an oversized segment.', 502)
                    chunks.append(chunk)
                content = b''.join(chunks)
    except httpx.HTTPError:
        raise ApplicationError('LIVE_UNAVAILABLE', 'Live video is unavailable. Check the camera host and retry.', 502) from None
    if urlsplit(resource).path.endswith('.m3u8'):
        text = content.decode('utf-8', errors='replace')
        if not text.lstrip().startswith('#EXTM3U'):
            raise ApplicationError('INVALID_PLAYLIST', 'The camera did not return a live playlist.', 502)
        return Response(rewrite_playlist(text, resource, camera_id, claims, settings),
            media_type='application/vnd.apple.mpegurl', headers={'Cache-Control': 'no-store'})
    media_type = 'video/mp2t' if urlsplit(resource).path.endswith('.ts') else 'video/mp4'
    return Response(content, media_type=media_type,
        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
