"""Security-engine interface and HTTP adapter."""

from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.domain.security import SecurityContext, SecurityDecision


class SecurityEngineError(RuntimeError):
    """Raised when the security engine is unavailable or returns invalid data."""


class SecurityEngine(Protocol):
    async def evaluate(self, context: SecurityContext) -> SecurityDecision: ...


class HttpSecurityEngine:
    """Call the configured security engine over HTTP with a strict timeout."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def evaluate(self, context: SecurityContext) -> SecurityDecision:
        url = (
            self.settings.security_engine_url.rstrip("/")
            + "/"
            + self.settings.security_engine_decision_path.lstrip("/")
        )
        try:
            async with httpx.AsyncClient(timeout=self.settings.security_engine_timeout_seconds) as client:
                response = await client.post(url, json=context.model_dump(mode="json"))
                response.raise_for_status()
                return SecurityDecision.model_validate(response.json())
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise SecurityEngineError("Security engine request failed") from error