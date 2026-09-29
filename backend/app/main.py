"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.cameras import router as cameras_router
from app.api.events import router as events_router
from app.api.frigate import router as frigate_router
from app.api.realtime import router as realtime_router
from app.api.tracks import router as tracks_router
from app.core.config import get_settings
from app.core.dependencies import get_event_publisher, get_person_tracker
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.database.database import dispose_database, get_session_factory
from app.domain.events import DetectionEvent
from app.integrations.frigate import FrigateClient
from app.integrations.security_engine import HttpSecurityEngine
from app.repositories.cameras import CameraRepository
from app.repositories.events import EventRepository
from app.services.event_processor import EventProcessor
from app.workers.frigate_listener import FrigateListener

logger = logging.getLogger(__name__)

# Global state for MQTT listener and related services
_frigate_listener: FrigateListener | None = None
_mqtt_connected = False


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize MQTT listener and manage application lifecycle."""

    global _frigate_listener, _mqtt_connected
    settings = get_settings()
    logger.info("Application startup", extra={"app_name": settings.app_name})
    event_loop = asyncio.get_running_loop()
    track_reaper_task: asyncio.Task[None] | None = None
    
    # Initialize MQTT listener
    try:
        event_publisher = get_event_publisher()
        person_tracker = get_person_tracker()
        session_factory = get_session_factory()
        security_engine = HttpSecurityEngine(settings)
        
        async def on_detection_async(detection: DetectionEvent) -> None:
            """Async wrapper for detection processing."""
            try:
                async with session_factory() as session:
                    camera_repo = CameraRepository(session)
                    event_repo = EventRepository(session)
                    processor = EventProcessor(
                        session=session,
                        camera_repository=camera_repo,
                        event_repository=event_repo,
                        security_engine=security_engine,
                        security_engine_failure_mode=settings.security_engine_failure_mode,
                        publisher=event_publisher,
                        event_cooldown_seconds=settings.frigate_event_cooldown_seconds,
                        person_tracker=person_tracker,
                        security_engine_supports_tracking=settings.security_engine_supports_tracking,
                    )
                    result = await processor.process(detection)
                    logger.info(
                        "Processed Frigate detection",
                        extra={
                            "event_id": detection.source_event_id,
                            "camera": detection.camera,
                            "duplicate": result.duplicate,
                        },
                    )
            except Exception as error:
                logger.error("Failed to process detection", extra={"error": str(error)}, exc_info=True)
        
        def on_detection(detection: DetectionEvent) -> None:
            """Synchronous callback wrapper that schedules async processing."""
            try:
                event_loop.call_soon_threadsafe(
                    event_loop.create_task, on_detection_async(detection)
                )
            except RuntimeError:
                logger.warning("Event loop closed before Frigate detection could be processed")
        
        _frigate_listener = FrigateListener(on_detection=on_detection, settings=settings)
        _mqtt_connected = _frigate_listener.start()
        if _mqtt_connected:
            logger.info("Frigate MQTT listener started", extra={"host": settings.mqtt_host, "port": settings.mqtt_port})
        else:
            logger.warning("Frigate MQTT listener failed to connect")

        async def expire_lost_tracks() -> None:
            while True:
                await asyncio.sleep(1)
                expired = person_tracker.expire_stale()
                for camera_id in {track.camera_id for track in expired}:
                    await event_publisher.publish_tracks(
                        camera_id, person_tracker.tracks_for_camera(camera_id)
                    )

        track_reaper_task = asyncio.create_task(expire_lost_tracks())
    except Exception as error:
        logger.error("Failed to initialize MQTT listener", extra={"error": str(error)}, exc_info=True)
    
    yield
    
    # Cleanup
    if _frigate_listener:
        _frigate_listener.stop()
        logger.info("Frigate MQTT listener stopped")
    if track_reaper_task is not None:
        track_reaper_task.cancel()
        try:
            await track_reaper_task
        except asyncio.CancelledError:
            pass
    
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5500",
            "http://127.0.0.1:5500",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(cameras_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(frigate_router, prefix="/api/v1")
    app.include_router(realtime_router, prefix="/api/v1")
    app.include_router(tracks_router, prefix="/api/v1")
    register_exception_handlers(app)
    return app


app = create_app()
