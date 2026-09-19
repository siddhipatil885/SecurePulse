"""Health and readiness endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database.database import check_database_connection

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Check application health")
async def health() -> dict[str, str]:
    """Return a liveness response when the process is running."""

    return {"status": "ok"}


@router.get("/ready", summary="Check application readiness")
async def readiness() -> JSONResponse:
    """Report readiness without pretending unimplemented dependencies are healthy."""

    database_ready = await check_database_connection()
    return JSONResponse(
        status_code=200 if database_ready else 503,
        content={
            "status": "ok" if database_ready else "not_ready",
            "checks": {
                "database": "ok" if database_ready else "unavailable",
                "frigate": "not_checked",
                "security_engine": "not_checked",
            },
        },
    )