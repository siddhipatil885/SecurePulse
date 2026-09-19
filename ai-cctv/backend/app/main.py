"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.cameras import router as cameras_router
from app.api.events import router as events_router
from app.api.realtime import router as realtime_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.database.database import dispose_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Log application lifecycle events without requiring external services."""

    settings = get_settings()
    logger.info("Application startup", extra={"app_name": settings.app_name})
    yield
    await dispose_database()
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Edge-oriented security surveillance backend.",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(cameras_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(realtime_router, prefix="/api/v1")
    register_exception_handlers(app)
    return app


app = create_app()