"""FastAPI application entry point."""

import asyncio
import logging
import queue
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.cameras import router as cameras_router
from app.api.dispatch import router as dispatch_router
from app.api.evidence import router as evidence_router
from app.api.events import router as events_router
from app.api.frigate import router as frigate_router
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.properties import router as properties_router
from app.api.realtime import router as realtime_router
from app.api.reporter import router as reporter_router
from app.api.tracks import router as tracks_router
from app.core.config import get_settings
from app.core.dependencies import get_event_publisher, get_person_tracker
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.database.database import dispose_database, get_session_factory
from app.domain.events import DetectionEvent
from app.integrations.local_security_engine import LocalSecurityEngine
from app.integrations.security_engine import HttpSecurityEngine
from app.repositories.cameras import CameraRepository
from app.repositories.events import EventRepository
from app.services.dispatch_workers import (
    NotificationDispatcher,
    RecordingFakeProvider,
    TimeoutEscalator,
)
from app.services.event_processor import EventProcessor
from app.workers.frigate_listener import FrigateListener

logger = logging.getLogger(__name__)

# Global state for MQTT listener and related services
_frigate_listener: FrigateListener | None = None
_mqtt_connected = False
_mqtt_event_queue: queue.Queue[DetectionEvent] | None = None
_mqtt_queue_rejections = 0
_mqtt_processing_failures = 0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize MQTT listener and manage application lifecycle."""

    global _frigate_listener, _mqtt_connected, _mqtt_event_queue
    global _mqtt_queue_rejections, _mqtt_processing_failures

    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Application startup", extra={"app_name": settings.app_name})

    _mqtt_event_queue = queue.Queue(maxsize=settings.mqtt_event_queue_size)
    _mqtt_queue_rejections = 0
    _mqtt_processing_failures = 0

    track_reaper_task: asyncio.Task[None] | None = None
    detection_worker_task: asyncio.Task[None] | None = None
    dispatch_worker_task: asyncio.Task[None] | None = None
    session_factory = None

    try:
        event_publisher = get_event_publisher()
        person_tracker = get_person_tracker()
        session_factory = get_session_factory()

        using_local_security_engine = settings.use_local_security_engine
        security_engine = (
            LocalSecurityEngine()
            if using_local_security_engine
            else HttpSecurityEngine(settings)
        )

        async def on_detection_async(detection: DetectionEvent) -> None:
            """Process one Frigate event."""
            global _mqtt_processing_failures

            try:
                async with session_factory() as session:
                    processor = EventProcessor(
                        session=session,
                        camera_repository=CameraRepository(session),
                        event_repository=EventRepository(session),
                        security_engine=security_engine,
                        security_engine_failure_mode=settings.security_engine_failure_mode,
                        publisher=event_publisher,
                        event_cooldown_seconds=settings.frigate_event_cooldown_seconds,
                        person_tracker=person_tracker,
                        security_engine_supports_tracking=(
                            using_local_security_engine
                            or settings.security_engine_supports_tracking
                        ),
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
                _mqtt_processing_failures += 1
                logger.error(
                    "Failed to process Frigate detection",
                    extra={
                        "source_event_id": detection.source_event_id,
                        "camera": detection.camera,
                        "stage": "event_processor",
                        "reason": str(error),
                    },
                    exc_info=True,
                )

        def on_detection(detection: DetectionEvent) -> None:
            """Enqueue work without blocking the Paho MQTT callback."""
            global _mqtt_queue_rejections

            event_queue = _mqtt_event_queue
            if event_queue is None:
                logger.error(
                    "Frigate event queue is unavailable",
                    extra={
                        "source_event_id": detection.source_event_id,
                        "camera": detection.camera,
                        "reason": "queue_unavailable",
                    },
                )
                return

            try:
                event_queue.put_nowait(detection)
            except queue.Full:
                _mqtt_queue_rejections += 1
                logger.error(
                    "Frigate event queue is full; event rejected",
                    extra={
                        "source_event_id": detection.source_event_id,
                        "camera": detection.camera,
                        "reason": "queue_full",
                    },
                )
            else:
                logger.debug(
                    "Queued Frigate event",
                    extra={
                        "source_event_id": detection.source_event_id,
                        "camera": detection.camera,
                        "queue_depth": event_queue.qsize(),
                        "stage": "queued",
                    },
                )

        async def process_detection_queue() -> None:
            """Process queued events one at a time."""
            event_queue = _mqtt_event_queue
            if event_queue is None:
                return

            while True:
                try:
                    detection = await asyncio.to_thread(
                        event_queue.get,
                        True,
                        1.0,
                    )
                except queue.Empty:
                    continue

                try:
                    await on_detection_async(detection)
                finally:
                    event_queue.task_done()

        detection_worker_task = asyncio.create_task(process_detection_queue())

        _frigate_listener = FrigateListener(
            on_detection=on_detection,
            settings=settings,
        )
        _mqtt_connected = _frigate_listener.start()

        if _mqtt_connected:
            logger.info(
                "Frigate MQTT listener started",
                extra={"host": settings.mqtt_host, "port": settings.mqtt_port},
            )
        else:
            logger.warning("Frigate MQTT listener failed to connect")

        async def expire_lost_tracks() -> None:
            while True:
                await asyncio.sleep(1)
                expired = person_tracker.expire_stale()
                for camera_id in {track.camera_id for track in expired}:
                    await event_publisher.publish_tracks(
                        camera_id,
                        person_tracker.tracks_for_camera(camera_id),
                    )

        track_reaper_task = asyncio.create_task(expire_lost_tracks())

    except Exception as error:
        logger.error(
            "Failed to initialize MQTT listener",
            extra={"error": str(error)},
            exc_info=True,
        )

    if session_factory is not None:

        async def run_dispatch_workers() -> None:
            timeout_worker = TimeoutEscalator(session_factory)
            fake_provider = RecordingFakeProvider()

            # This local drill provider records intents in memory and does not
            # contact marshals or public emergency services.
            app.state.notification_provider = fake_provider
            notification_worker = NotificationDispatcher(
                session_factory,
                fake_provider,
                worker_id="local-fake-provider",
            )

            while True:
                try:
                    await timeout_worker.run_once()
                    await notification_worker.run_once()
                except Exception:
                    logger.exception("Dispatch worker iteration failed")

                await asyncio.sleep(2)

        dispatch_worker_task = asyncio.create_task(run_dispatch_workers())

    yield

    if _frigate_listener is not None:
        _frigate_listener.stop()
        logger.info("Frigate MQTT listener stopped")

    if track_reaper_task is not None:
        track_reaper_task.cancel()
        try:
            await track_reaper_task
        except asyncio.CancelledError:
            pass

    # Give queued detections a chance to finish before stopping the worker.
    if detection_worker_task is not None:
        event_queue = _mqtt_event_queue
        if event_queue is not None:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(event_queue.join),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Timed out draining Frigate events at shutdown",
                    extra={"queue_depth": event_queue.qsize()},
                )

        detection_worker_task.cancel()
        try:
            await detection_worker_task
        except asyncio.CancelledError:
            pass

    if dispatch_worker_task is not None:
        dispatch_worker_task.cancel()
        try:
            await dispatch_worker_task
        except asyncio.CancelledError:
            pass

    _mqtt_event_queue = None
    _mqtt_connected = False

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
        allow_origins=settings.parsed_cors_origins,
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
    app.include_router(incidents_router, prefix="/api/v1")
    app.include_router(properties_router, prefix="/api/v1")
    app.include_router(evidence_router, prefix="/api/v1")
    app.include_router(reporter_router, prefix="/api/v1")
    app.include_router(dispatch_router, prefix="/api/v1")

    register_exception_handlers(app)
    return app


app = create_app()