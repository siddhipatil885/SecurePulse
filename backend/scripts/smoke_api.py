"""Read-only FastAPI smoke checks against the configured database."""

from __future__ import annotations

import asyncio
import os

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.config import get_settings


async def main() -> None:
    """Check reads using an explicitly supplied token when auth is enabled."""
    headers = {}
    if get_settings().auth_enabled:
        token = os.getenv("SMOKE_API_TOKEN")
        if not token:
            raise SystemExit("AUTH_ENABLED=true requires SMOKE_API_TOKEN with read access")
        headers["Authorization"] = f"Bearer {token}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        responses = {
            "liveness": await client.get("/health"),
            "readiness": await client.get("/health/ready"),
            "cameras": await client.get("/api/v1/cameras"),
            "properties": await client.get("/api/v1/properties"),
            "events": await client.get("/api/v1/events"),
            "incidents": await client.get("/api/v1/incidents"),
        }

    assert responses["liveness"].status_code == 200
    # MQTT may intentionally be absent in a backend/database-only smoke run.
    assert responses["readiness"].status_code in {200, 503}
    for name in ("cameras", "properties", "events", "incidents"):
        assert responses[name].status_code == 200, f"{name}: HTTP {responses[name].status_code}"
    print(
        "api_smoke=passed "
        f"cameras={len(responses['cameras'].json())} "
        f"properties={len(responses['properties'].json())} "
        f"events={responses['events'].json()['total']} "
        f"incidents={responses['incidents'].json()['total']} "
        f"readiness={responses['readiness'].status_code}"
    )


if __name__ == "__main__":
    asyncio.run(main())
