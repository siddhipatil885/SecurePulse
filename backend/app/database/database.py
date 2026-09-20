"""Async PostgreSQL engine and session lifecycle."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when a database operation is attempted without a database URL."""


def _async_database_url(database_url: str) -> str:
    if not database_url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not configured")
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("DATABASE_URL must use the PostgreSQL scheme")


@lru_cache
def get_engine() -> AsyncEngine:
    """Create the shared pooled async PostgreSQL engine on first use."""

    database_url = _async_database_url(get_settings().database_url)
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared async session factory."""

    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session and roll back failed transactions."""

    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database_connection() -> bool:
    """Return whether PostgreSQL accepts a lightweight connection."""

    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except (DatabaseNotConfiguredError, SQLAlchemyError, OSError, ValueError):
        return False


async def dispose_database() -> None:
    """Dispose the engine if it has been created."""

    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()