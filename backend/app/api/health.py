"""Health and readiness endpoints."""

from datetime import datetime, timezone
from importlib import import_module
import logging
import math

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database.database import check_database_connection

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("", summary="Check application health")
async def health() -> dict[str, str]:
    """Return a liveness response when the process is running."""

    return {"status": "ok"}


@router.get("/ready", summary="Check application readiness")
async def readiness() -> JSONResponse:
    """Report readiness with checks for key dependencies."""

    main_module = import_module("app.main")
    database_ready = await check_database_connection()
    listener = main_module._frigate_listener
    mqtt_connected = listener is not None and listener.client.connected
    
    all_ready = database_ready and mqtt_connected
    
    return JSONResponse(
        status_code=200 if all_ready else 503,
        content={
            "status": "ok" if all_ready else "not_ready",
            "checks": {
                "database": "ok" if database_ready else "unavailable",
                "mqtt": "ok" if mqtt_connected else "unavailable",
            },
        },
    )


@router.get("/edge", summary="Report edge pipeline and camera health")
async def edge_health() -> dict[str, object]:
    """Expose Frigate camera signals and adapter queue health for operators."""
    main_module = import_module("app.main")
    settings = main_module.get_settings()
    listener = main_module._frigate_listener
    mqtt_connected = bool(listener and listener.client.connected)
    queue = main_module._mqtt_event_queue
    adapter = listener.client if listener is not None else None
    cameras: dict[str, dict[str, object]] = {}
    frigate_reachable = False
    detection_fps: float | None = None
    try:
        auth = None
        if settings.frigate_username and settings.frigate_password:
            auth = (settings.frigate_username, settings.frigate_password)
        async with httpx.AsyncClient(timeout=2.0, verify=settings.frigate_verify_ssl) as client:
            response = await client.get(
                f"{settings.frigate_url.rstrip('/')}/api/stats", auth=auth
            )
            response.raise_for_status()
            stats = response.json()
        if not isinstance(stats, dict):
            raise ValueError("Frigate stats response is not an object")
        frigate_reachable = True
        raw_detection_fps = stats.get("detection_fps")
        if (
            isinstance(raw_detection_fps, (int, float))
            and not isinstance(raw_detection_fps, bool)
            and math.isfinite(raw_detection_fps)
        ):
            detection_fps = float(raw_detection_fps)
        raw_cameras = stats.get("cameras")
        if not isinstance(raw_cameras, dict):
            raw_cameras = {}
        for name, values in raw_cameras.items():
            if not isinstance(values, dict):
                cameras[str(name)] = {
                    "status": "unknown",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
                continue
            camera_fps = values.get("camera_fps")
            process_fps = values.get("process_fps")
            raw_detection_enabled = values.get("detection_enabled")
            if isinstance(raw_detection_enabled, bool):
                detection_enabled: bool | None = raw_detection_enabled
            elif (
                isinstance(raw_detection_enabled, (int, float))
                and not isinstance(raw_detection_enabled, bool)
                and math.isfinite(raw_detection_enabled)
            ):
                detection_enabled = raw_detection_enabled > 0
            else:
                detection_enabled = None
            if (
                isinstance(camera_fps, bool)
                or not isinstance(camera_fps, (int, float))
                or not math.isfinite(camera_fps)
            ):
                status = "unknown"
            elif camera_fps <= 0:
                status = "offline"
            elif detection_enabled is False:
                status = "detection_disabled"
            elif (
                isinstance(process_fps, (int, float))
                and not isinstance(process_fps, bool)
                and math.isfinite(process_fps)
                and process_fps <= 0
            ):
                status = "degraded"
            else:
                status = "online"
            cameras[name] = {
                "status": status,
                "camera_fps": camera_fps,
                "process_fps": process_fps,
                "detection_enabled": detection_enabled,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
    except (httpx.HTTPError, ValueError, TypeError) as error:
        logger.warning(
            "Frigate edge stats are unavailable",
            extra={"reason": type(error).__name__},
        )
    edge_ok = (
        frigate_reachable
        and mqtt_connected
        and bool(cameras)
        and all(camera["status"] == "online" for camera in cameras.values())
    )
    return {
        "status": "ok" if edge_ok else "degraded",
        "mqtt": "connected" if mqtt_connected else "disconnected",
        "frigate": "reachable" if frigate_reachable else "unavailable",
        "detection_fps": detection_fps,
        "queue_depth": queue.qsize() if queue is not None else 0,
        "queue_capacity": queue.maxsize if queue is not None else settings.mqtt_event_queue_size,
        "queue_rejections": main_module._mqtt_queue_rejections,
        "processing_failures": main_module._mqtt_processing_failures,
        "last_event_at": getattr(adapter, "last_event_at", None).isoformat()
        if getattr(adapter, "last_event_at", None)
        else None,
        "invalid_event_count": getattr(adapter, "invalid_message_count", 0),
        "adapter_delivery_failures": getattr(adapter, "delivery_failure_count", 0),
        "cameras": cameras,
    }
