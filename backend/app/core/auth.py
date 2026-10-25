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
    property_ids: frozenset[int] | None = frozenset()

    def can_access_property(self, property_id: int) -> bool:
        """Return whether this identity may access a property.

        ``None`` is reserved for the explicit auth-disabled local-development
        principal. Authenticated tokens must enumerate property IDs.
        """
        return self.property_ids is None or property_id in self.property_ids


def authenticate_token(token: str | None, settings: Settings | None = None) -> Principal:
    """Validate a bearer token or return the explicit local-development principal."""

    settings = settings or get_settings()
    if not settings.auth_enabled:
        return Principal(
            subject="local-development",
            scopes=frozenset({"read", "write"}),
            property_ids=None,
        )
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
    raw_property_ids = payload.get("property_ids", [])
    if not isinstance(raw_property_ids, list) or any(
        not isinstance(property_id, int) or isinstance(property_id, bool) or property_id < 1
        for property_id in raw_property_ids
    ):
        raise ApplicationError("UNAUTHORIZED", "The access token has invalid property access claims.", 401)
    return Principal(
        subject=subject,
        scopes=scopes,
        property_ids=frozenset(raw_property_ids),
    )


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


def websocket_token(websocket: WebSocket) -> str | None:
    """Browser subprotocol keeps credentials out of URL/access logs."""
    authorization = websocket.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    for protocol in websocket.headers.get("sec-websocket-protocol", "").split(","):
        protocol = protocol.strip()
        if protocol.startswith("bearer."):
            return protocol[7:]
    return websocket.query_params.get("access_token")  # legacy clients


async def get_websocket_principal(websocket: WebSocket) -> Principal:
    """Authenticate WebSocket clients using a bearer header or browser token query."""

    principal = authenticate_token(websocket_token(websocket))
    if "read" not in principal.scopes:
        raise ApplicationError("FORBIDDEN", "Read permission is required.", 403)
    return principal
