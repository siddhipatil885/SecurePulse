"""JWT authentication and scope-based authorization."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import jwt
from fastapi import Depends, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.core.config import Settings, get_settings
from app.core.exceptions import ApplicationError

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: frozenset[str]


def authenticate_token(token: str | None, settings: Settings | None = None) -> Principal:
    """Validate a bearer token or return the explicit local-development principal."""

    settings = settings or get_settings()
    if not settings.auth_enabled:
        return Principal(subject="local-development", scopes=frozenset({"read"}))
    if not settings.jwt_secret:
        raise ApplicationError(
            "AUTH_CONFIGURATION_ERROR",
            "Authentication is enabled but JWT_SECRET is not configured.",
            503,
        )
    if not token:
        raise ApplicationError(
            "UNAUTHORIZED",
            "Authentication is required.",
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    try:
        decode_kwargs: dict[str, object] = {
            "algorithms": [settings.jwt_algorithm],
            "options": {"require": ["sub", "exp"]},
        }
        if settings.jwt_issuer:
            decode_kwargs["issuer"] = settings.jwt_issuer
        payload = jwt.decode(token, settings.jwt_secret, **decode_kwargs)
    except (InvalidTokenError, ValueError, TypeError):
        raise ApplicationError(
            "UNAUTHORIZED",
            "The access token is invalid or expired.",
            401,
            {"WWW-Authenticate": "Bearer"},
        ) from None

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise ApplicationError(
            "UNAUTHORIZED",
            "The access token is invalid.",
            401,
            {"WWW-Authenticate": "Bearer"},
        )
    raw_scopes = payload.get("scope", [])
    if isinstance(raw_scopes, str):
        scopes = frozenset(raw_scopes.split())
    elif isinstance(raw_scopes, list) and all(isinstance(scope, str) for scope in raw_scopes):
        scopes = frozenset(raw_scopes)
    else:
        scopes = frozenset()
    return Principal(subject=subject, scopes=scopes)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    token = credentials.credentials if credentials else None
    return authenticate_token(token)


def require_scope(scope: str) -> Callable[..., Principal]:
    async def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if scope not in principal.scopes:
            raise ApplicationError(
                "FORBIDDEN",
                "The access token does not grant the required permission.",
                403,
            )
        return principal

    return dependency


async def get_websocket_principal(websocket: WebSocket) -> Principal:
    """Authenticate WebSocket clients using a bearer header or browser token query."""

    authorization = websocket.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    if not token:
        token = websocket.query_params.get("access_token")
    principal = authenticate_token(token)
    if "read" not in principal.scopes:
        raise ApplicationError("FORBIDDEN", "Read permission is required.", 403)
    return principal