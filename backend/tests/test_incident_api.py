"""Property-scoped incident HTTP contract tests."""

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_incident_service
from app.main import app
from app.models.operations import IncidentStatusHistory
from app.models.security_event import SecurityEvent


class FakeIncidentService:
    async def history(self, incident_id: int, property_ids: frozenset[int] | None):
        return [
            IncidentStatusHistory(
                id=1,
                security_event_id=incident_id,
                previous_status=None,
                new_status="OPEN",
                actor_subject="system:ingestion",
                reason="Detection ingested",
                correlation_id="frigate:event-1:new:0",
                occurred_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
            )
        ]

    async def evidence(self, incident_id: int, property_ids: frozenset[int] | None):
        return []

    async def command(self, incident_id: int, command: str, **kwargs: object):
        return SecurityEvent(
            id=incident_id,
            property_id=1,
            camera_id=1,
            event_type="INTRUSION",
            object_type="person",
            confidence=0.9,
            timestamp=datetime(2026, 10, 16, tzinfo=timezone.utc),
            severity="HIGH",
            status="ACKNOWLEDGED",
            event_metadata={},
        )


@pytest.fixture(autouse=True)
def override_incident_service():
    app.dependency_overrides[get_incident_service] = lambda: FakeIncidentService()
    yield
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_incident_history_and_command_contracts() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        history = await client.get("/api/v1/incidents/42/history")
        command = await client.post(
            "/api/v1/incidents/42/commands",
            json={
                "command": "acknowledge",
                "reason": "Reviewed evidence",
                "correlation_id": "request-42",
            },
        )

    assert history.status_code == 200
    assert history.json()[0]["new_status"] == "OPEN"
    assert command.status_code == 200
    assert command.json()["status"] == "ACKNOWLEDGED"
