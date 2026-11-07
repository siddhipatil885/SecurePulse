"""Isolated browser-test API. Never connects to the deployment DB or MQTT."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api import account_recovery, dashboard, dispatch, evidence, marshal, operator_cases, reporter, reporter_live
from app.core import auth, reporter_auth
from app.core.config import Settings
from app.core.dependencies import get_session
from app.core.exceptions import register_exception_handlers
from app.core.rate_limit import SlidingWindowRateLimiter
from app.database.base import Base
from app.models import (Camera, Evidence, MarshalAvailability, MarshalProfile, Property,
    PropertyMembership, SecurityEvent, User)

settings = Settings(_env_file=None, app_env="development", database_url="", auth_enabled=True,
                    dispatch_notification_provider="disabled", jwt_secret="browser-test-only-secret-at-least-32-characters",
                    cors_origins="http://127.0.0.1:15173", frigate_url="http://127.0.0.1:1", go2rtc_url="http://127.0.0.1:1")
for module in (auth, reporter_auth, dashboard, evidence, marshal, operator_cases, reporter, reporter_live, account_recovery):
    module.get_settings = lambda: settings


async def seed(factory, reset=False):
    dashboard.auth_limiter = SlidingWindowRateLimiter(5000)
    async with factory() as session:
        if reset:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))
        session.add_all([Property(id=id, slug=f'test-{id}', name=name, address=address)
            for id, name, address in [(1, 'North residence', '11 North Street'), (2, 'South office', '22 South Street'), (3, 'Private site', '33 Private Street')]])
        session.add_all([User(id=1, subject='test-owner', email='owner@example.test', display_name='Test Owner', password_hash=reporter_auth.hash_password('Dashboard-test-pass123')),
                        User(id=2, subject='test-reader', email='reader@example.test', display_name='Test Reader', password_hash=reporter_auth.hash_password('Dashboard-test-pass123')),
                        User(id=3, subject='test-marshal', email='marshal@example.test', display_name='Test Marshal', password_hash=reporter_auth.hash_password('Dashboard-test-pass123'))])
        await session.flush()
        session.add_all([PropertyMembership(user_id=1, property_id=id, role='owner') for id in (1, 2)])
        session.add_all([PropertyMembership(user_id=2, property_id=1, role='reporter'), PropertyMembership(user_id=3, property_id=1, role='marshal')])
        session.add(MarshalProfile(id=1, user_id=3, property_id=1, capacity=1, service_area='North', verification_status='APPROVED'))
        await session.flush()
        session.add(MarshalAvailability(marshal_profile_id=1, on_duty=True, available=True, updated_at=datetime.now(timezone.utc)))
        for id, label in [(1, 'NORTH_INTRUSION'), (2, 'SOUTH_LOITERING'), (3, 'PRIVATE_INCIDENT')]:
            session.add(Camera(id=id, property_id=id, name=f'Camera {id}', frigate_camera_name=f'test-camera-{id}', enabled=False))
            session.add(SecurityEvent(id=id, property_id=id, camera_id=id, event_type=label, object_type='person',
                confidence=.9, timestamp=datetime.now(timezone.utc), severity='HIGH', status='OPEN', event_metadata={}))
        await session.flush()
        session.add(Evidence(id=1, event_id=1, type='SNAPSHOT', file_path='evidence.png', timestamp=datetime.now(timezone.utc)))
        await session.commit()


@asynccontextmanager
async def lifespan(app):
    with tempfile.TemporaryDirectory(prefix="securepulse-dashboard-e2e-") as directory:
        settings.evidence_root = directory
        # A tiny valid PNG proves authenticated evidence actually renders.
        import base64
        Path(directory, "evidence.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
        engine = create_async_engine(f"sqlite+aiosqlite:///{directory}/test.sqlite")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        app.state.test_factory = factory
        dashboard.get_session_factory = lambda: factory
        await seed(factory)
        async def override():
            async with factory() as session:
                yield session
        app.dependency_overrides[get_session] = override
        try:
            yield
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(operator_cases.router, prefix="/api/v1")
app.include_router(reporter.router, prefix="/api/v1")
app.include_router(dispatch.router, prefix="/api/v1")
app.include_router(marshal.router, prefix="/api/v1")
app.include_router(reporter_live.router, prefix='/api/v1')
app.include_router(account_recovery.router, prefix='/api/v1')
register_exception_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "isolated-browser-test"}


@app.post('/__test/reset')
async def reset_test_database():
    # Only this isolated app has the route. The real app never imports it.
    await seed(app.state.test_factory, reset=True)
    return {'mode': 'isolated-browser-test', 'reset': True}
