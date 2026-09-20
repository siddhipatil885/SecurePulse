"""Phase 6 API tests with service-level dependency overrides."""

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_camera_service, get_event_service
from app.main import app
from app.models.camera import Camera
from app.models.security_event import SecurityEvent


class FakeCameraService:
    async def list(self, enabled: bool | None = None) -> list[Camera]:
        return [
            Camera(
                id=1,
                name="Front Door",
                frigate_camera_name="front_door",
                location="Main Gate",
                enabled=True,
            )
        ]

    async def get(self, camera_id: int) -> Camera:
        if camera_id != 1:
            from app.core.exceptions import ApplicationError

            raise ApplicationError("CAMERA_NOT_FOUND", "The requested camera does not exist.", 404)
        cameras = await self.list()
        return cameras[0]


class FakeEventService:
    async def list(self, **kwargs: object) -> tuple[list[SecurityEvent], int]:
        return [
            SecurityEvent(
                id=42,
                camera_id=1,
                event_type="PERSON_DETECTED",
                object_type="person",
                confidence=0.94,
                timestamp=datetime(2026, 9, 19, tzinfo=timezone.utc),
                severity="INFO",
                status="OPEN",
                score=15,
                zone=None,
                frigate_event_id="frigate-42",
                reason="Person detected",
                event_metadata={},
            )
        ], 1

    async def get(self, event_id: int) -> SecurityEvent:
        events, _ = await self.list()
        if event_id != 42:
            from app.core.exceptions import ApplicationError

            raise ApplicationError("EVENT_NOT_FOUND", "The requested event does not exist.", 404)
        return events[0]


@pytest.fixture(autouse=True)
def override_services() -> None:
    app.dependency_overrides[get_camera_service] = lambda: FakeCameraService()
    app.dependency_overrides[get_event_service] = lambda: FakeEventService()
    yield
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_camera_and_event_endpoints() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cameras = await client.get("/api/v1/cameras")
        events = await client.get("/api/v1/events?page=1&page_size=10&severity=INFO")
        event = await client.get("/api/v1/events/42")

    assert cameras.status_code == 200
    assert cameras.json()[0]["frigate_camera_name"] == "front_door"
    assert events.status_code == 200
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["metadata"] == {}
    assert event.status_code == 200
    assert event.json()["id"] == 42


@pytest.mark.anyio
async def test_missing_resources_use_structured_errors() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        camera = await client.get("/api/v1/cameras/404")
        event = await client.get("/api/v1/events/404")

    assert camera.status_code == 404
    assert camera.json() == {
        "error": {"code": "CAMERA_NOT_FOUND", "message": "The requested camera does not exist."}
    }
    assert event.status_code == 404
    assert event.json()["error"]["code"] == "EVENT_NOT_FOUND"