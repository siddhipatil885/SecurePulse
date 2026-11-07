"""Server-side Managed Better Auth REST bridge, using its published OpenAPI.

Neon verifies credentials. SecurePulse continues to own property permissions and
its revocable application JWT/cookie sessions. Provider sessions are short lived
and signed out after the exchange; they are never persisted or sent to clients.
"""
from contextlib import asynccontextmanager

import httpx

from app.core.config import get_settings
from app.core.exceptions import ApplicationError


class NeonAuth:
    def __init__(self):
        self.base_url = get_settings().neon_auth_base_url.rstrip("/")
        self.client = None

    async def _request(self, path, body=None, token=None, method="POST"):
        if not self.base_url:
            raise ApplicationError("AUTH_NOT_CONFIGURED", "Managed authentication is not configured.", 503)
        try:
            # Managed Auth's signed session cookie is required for get-session;
            # the raw response token alone is not a bearer session credential.
            response = await self.client.request(method, self.base_url + path, json=body)
        except httpx.HTTPError:
            raise ApplicationError("AUTH_UNAVAILABLE", "Authentication is temporarily unavailable. Please retry.", 503) from None
        if response.status_code >= 500:
            raise ApplicationError("AUTH_UNAVAILABLE", "Authentication is temporarily unavailable. Please retry.", 503)
        if response.status_code == 429:
            raise ApplicationError("AUTH_RATE_LIMITED", "Too many sign-in attempts. Please try again later.", 429)
        if not response.is_success:
            try:
                code = response.json().get('code', '')
            except (ValueError, AttributeError):
                code = ''
            if code in ('MISSING_ORIGIN', 'INVALID_ORIGIN', 'INVALID_CALLBACK_URL'):
                raise ApplicationError('AUTH_CONFIGURATION_ERROR', 'The account service origin is not configured correctly. Contact your administrator.', 503)
            if code in ('FAILED_TO_SEND_EMAIL', 'FAILED_TO_SEND_VERIFICATION_EMAIL', 'FAILED_TO_SEND_VERIFICATION_OTP', 'FAILED_TO_SEND_OTP'):
                raise ApplicationError('AUTH_DELIVERY_UNAVAILABLE', 'The account service could not send email. Contact your administrator.', 503)
            raise ApplicationError("INVALID_CREDENTIALS", "Unable to sign in. Check your credentials or verify your email.", 401)
        try:
            return response.json()
        except ValueError:
            raise ApplicationError("AUTH_UNAVAILABLE", "Authentication returned an unexpected response.", 503) from None

    @asynccontextmanager
    async def session(self, email, password, name=None):
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
                headers={"Origin": get_settings().parsed_cors_origins[0]}) as client:
            self.client = client
            try:
                async with self._session(email, password, name) as identity:
                    yield identity
            finally:
                self.client = None

    @asynccontextmanager
    async def _session(self, email, password, name=None):
        body = {"email": email, "password": password}
        if name is not None:
            body["name"] = name
        result = await self._request("/sign-up/email" if name is not None else "/sign-in/email", body)
        token = result.get("token") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise ApplicationError("EMAIL_VERIFICATION_REQUIRED", "Verify your email before signing in.", 401)
        try:
            session = await self._request("/get-session", token=token, method="GET")
            user = session.get("user") if isinstance(session, dict) else None
            if (not isinstance(user, dict) or not isinstance(user.get("id"), str)
                    or not user["id"] or not isinstance(user.get("email"), str)
                    or user["email"].lower() != email.lower()):
                raise ApplicationError("INVALID_CREDENTIALS", "Unable to verify your identity.", 401)
            yield user, token
        finally:
            # Never report logout failure as credential rejection after a change
            # has succeeded. The app JWT still has its own revocation version.
            try:
                await self._request("/sign-out", {}, token=token)
            except ApplicationError:
                pass

    async def signup(self, email, password, name):
        async with self.session(email, password, name=name) as (user, _):
            return user

    async def signin(self, email, password):
        async with self.session(email, password) as (user, _):
            return user

    async def change_password(self, user, current, new):
        try:
            async with self.session(user.email, current) as (identity, token):
                if user.subject != "neon:" + identity["id"]:
                    raise ApplicationError("INVALID_CREDENTIALS", "Unable to verify your identity.", 401)
                await self._request("/change-password", {"currentPassword": current,
                    "newPassword": new, "revokeOtherSessions": True}, token=token)
        except ApplicationError as error:
            if error.status_code == 401:
                raise ApplicationError("INVALID_CURRENT_PASSWORD", "The current password is incorrect.", 400) from None
            raise

    async def public_operation(self, path, body):
        """OTP endpoints use the same trusted Origin and ephemeral cookie jar."""
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
                headers={"Origin": get_settings().parsed_cors_origins[0]}) as client:
            self.client = client
            try:
                return await self._request(path, body)
            finally:
                if client.cookies:
                    try:
                        await self._request('/sign-out', {})
                    except ApplicationError:
                        pass
                self.client = None
