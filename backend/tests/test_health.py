"""Phase 1 health endpoint tests."""

import queue
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.health as health_module
import app.main as main_module
from app.main import app
from app.core.config import Settings


@pytest.mark.anyio
async def test_health_returns_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_readiness_does_not_claim_external_dependencies_are_ready() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["database"] in {"ok", "unavailable"}
    assert response.json()["checks"]["mqtt"] in {"ok", "unavailable"}


@pytest.mark.anyio
async def test_edge_health_reports_camera_fps_and_queue_depth(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "detection_fps": 2.5,
                "cameras": {
                    "front_door": {
                        "camera_fps": 5.0,
                        "process_fps": 4.8,
                        "detection_enabled": 1,
                    }
                },
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str, auth=None) -> FakeResponse:
            assert url.endswith("/api/stats")
            return FakeResponse()

    event_queue = queue.Queue(maxsize=4)
    event_queue.put(object())
    monkeypatch.setattr(main_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(main_module, "_frigate_listener", SimpleNamespace(client=SimpleNamespace(connected=True)))
    monkeypatch.setattr(main_module, "_mqtt_event_queue", event_queue)
    monkeypatch.setattr(health_module.httpx, "AsyncClient", FakeAsyncClient)

    result = await health_module.edge_health()

    assert result["status"] == "ok"
    assert result["detection_fps"] == 2.5
    assert result["queue_depth"] == 1
    assert result["cameras"]["front_door"]["status"] == "online"
    assert result["cameras"]["front_door"]["detection_enabled"] is True


@pytest.mark.anyio
async def test_edge_health_degrades_when_camera_detection_is_disabled(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "detection_fps": 0,
                "cameras": {
                    "front_door": {
                        "camera_fps": 4.5,
                        "process_fps": 4.5,
                        "detection_enabled": 0,
                    }
                },
            }

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str, auth=None) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(main_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(
        main_module,
        "_frigate_listener",
        SimpleNamespace(client=SimpleNamespace(connected=True)),
    )
    monkeypatch.setattr(main_module, "_mqtt_event_queue", queue.Queue(maxsize=4))
    monkeypatch.setattr(health_module.httpx, "AsyncClient", FakeAsyncClient)

    result = await health_module.edge_health()

    assert result["status"] == "degraded"
    assert result["detection_fps"] == 0
    assert result["cameras"]["front_door"]["status"] == "detection_disabled"
    assert result["cameras"]["front_door"]["detection_enabled"] is False
