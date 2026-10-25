"""Proxy Frigate camera media and WebRTC signaling."""

import httpx
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.auth import Principal, require_scope
from app.core.config import get_settings
from app.core.dependencies import get_camera_service
from app.services.camera_service import CameraService

router = APIRouter(prefix="/frigate", tags=["frigate"])

_frigate_token: str | None = None


@router.post("/cameras/{camera_id}/playback-access")
async def playback_access(
    camera_id: int,
    response: Response,
    principal: Principal = Depends(require_scope("read")),
    service: CameraService = Depends(get_camera_service),
) -> dict:
    """Authorize a one-minute signaling grant; no source credentials leave the API."""
    camera = await service.get(camera_id, property_ids=principal.property_ids)
    if not camera.enabled:
        raise HTTPException(409, "Camera is disabled")
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise HTTPException(503, "Playback signing is not configured")
    expires = datetime.now(timezone.utc) + timedelta(seconds=60)
    grant = jwt.encode({"sub": principal.subject, "aud": "camera-playback", "exp": expires,
        "camera_id": camera.id, "property_id": camera.property_id}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    response.headers["Cache-Control"] = "no-store"
    return {"grant": grant, "expires_at": expires.isoformat()}


@router.get("/cameras/{camera_name}/snapshot", summary="Get the latest Frigate snapshot")
async def latest_snapshot(
    camera_name: str,
    principal: Principal = Depends(require_scope("read")),
    service: CameraService = Depends(get_camera_service),
) -> Response:
    """Return the latest JPEG without exposing Frigate directly to the browser."""

    camera = await service.get_by_frigate_name(camera_name, principal.property_ids)
    settings = get_settings()
    base_url = settings.frigate_url.rstrip("/")
    try:
        async with httpx.AsyncClient(
            timeout=5, verify=settings.frigate_verify_ssl
        ) as client:
            global _frigate_token
            if _frigate_token:
                client.cookies.set("frigate_token", _frigate_token)
            elif settings.frigate_username and settings.frigate_password:
                login = await client.post(
                    f"{base_url}/api/login",
                    json={
                        "user": settings.frigate_username,
                        "password": settings.frigate_password,
                    },
                )
                login.raise_for_status()
                _frigate_token = client.cookies.get("frigate_token")

            url = f"{base_url}/api/{camera.frigate_camera_name}/latest.jpg"
            response = await client.get(url)
            if response.status_code == 401 and settings.frigate_username and settings.frigate_password:
                _frigate_token = None
                login = await client.post(
                    f"{base_url}/api/login",
                    json={
                        "user": settings.frigate_username,
                        "password": settings.frigate_password,
                    },
                )
                login.raise_for_status()
                _frigate_token = client.cookies.get("frigate_token")
                response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Frigate snapshot unavailable") from error

    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/cameras/{camera_id}/webrtc",
    summary="Negotiate a WebRTC stream for a camera",
    response_class=Response,
)
async def negotiate_webrtc(
    camera_id: int,
    request: Request,
    principal: Principal = Depends(require_scope("read")),
    service: CameraService = Depends(get_camera_service),
) -> Response:
    """Proxy SDP negotiation to Frigate after validating camera access."""
    camera = await service.get(camera_id, property_ids=principal.property_ids)
    if not camera.enabled:
        raise HTTPException(status_code=409, detail="Camera is disabled")

    offer = await request.body()
    if not offer or len(offer) > 256_000:
        raise HTTPException(status_code=400, detail="A valid SDP offer is required")

    settings = get_settings()
    base_url = settings.go2rtc_url.rstrip("/")
    if settings.auth_enabled or request.headers.get("x-playback-grant"):
        try:
            claims = jwt.decode(request.headers.get("x-playback-grant", ""), settings.jwt_secret,
                algorithms=[settings.jwt_algorithm], audience="camera-playback",
                options={"require": ["sub", "exp", "camera_id", "property_id", "aud"]})
            if claims["sub"] != principal.subject or claims["camera_id"] != camera.id or claims["property_id"] != camera.property_id:
                raise ValueError("Grant binding mismatch")
        except (jwt.InvalidTokenError, ValueError, TypeError):
            raise HTTPException(401, "Playback grant expired or invalid") from None
    url = f"{base_url}/api/webrtc"
    content_type = request.headers.get("content-type", "application/sdp")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                params={"src": camera.frigate_camera_name},
                content=offer,
                headers={"Content-Type": content_type},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail="Frigate WebRTC negotiation failed") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Frigate WebRTC negotiation unavailable") from error

    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/sdp"),
        headers={"Cache-Control": "no-store"},
    )
