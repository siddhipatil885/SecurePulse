"""Reporter credentials reuse the existing JWT signature and scope validator."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import authenticate_token, bearer_scheme
from app.core.config import get_settings
from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.models import User


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def require_reporter_auth_enabled() -> None:
    if not get_settings().auth_enabled:
        raise ApplicationError("AUTH_DISABLED", "Reporter sign-in requires server authentication to be enabled.", 503)


def issue_token(user: User) -> tuple[str, datetime]:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    claims = {"sub": f"reporter:{user.id}", "scope": "reporter:read", "exp": expires,
              "iat": datetime.now(timezone.utc), "ver": user.token_version}
    if settings.jwt_issuer:
        claims["iss"] = settings.jwt_issuer
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires


async def get_reporter(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    require_reporter_auth_enabled()
    token = credentials.credentials if credentials else None
    principal = authenticate_token(token)
    if "reporter:read" not in principal.scopes or not principal.subject.startswith("reporter:"):
        raise ApplicationError("FORBIDDEN", "A reporter account is required.", 403)
    try:
        user_id = int(principal.subject.removeprefix("reporter:"))
    except ValueError:
        raise ApplicationError("UNAUTHORIZED", "Invalid session.", 401) from None
    # The existing validator has already checked signature, expiration and issuer.
    claims = jwt.decode(token, options={"verify_signature": False})
    user = await session.get(User, user_id)
    if user is None or not user.active or not user.password_hash or claims.get("ver") != user.token_version:
        raise ApplicationError("UNAUTHORIZED", "Your session has ended. Please sign in again.", 401)
    return user
