"""Read-only FastAPI smoke checks against the configured database."""

from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app


async def main() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
    assert responses["cameras"].status_code == 200
    assert responses["properties"].status_code == 200
    assert responses["events"].status_code == 200
    assert responses["incidents"].status_code == 200
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
