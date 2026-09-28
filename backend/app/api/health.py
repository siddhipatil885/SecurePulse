"""Health and readiness endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database.database import check_database_connection
import app.main as main_module

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Check application health")
async def health() -> dict[str, str]:
    """Return a liveness response when the process is running."""

    return {"status": "ok"}


@router.get("/ready", summary="Check application readiness")
async def readiness() -> JSONResponse:
    """Report readiness with checks for key dependencies."""

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