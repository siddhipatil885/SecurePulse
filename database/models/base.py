"""
SQLAlchemy 2.x base configuration for EDI-SecurePulse.

Provides:
    - DeclarativeBase for all ORM models
    - Engine creation with Neon-compatible pooling
    - Session factory for sync database access

Usage by the FastAPI developer:
    from database.models import SessionLocal, engine
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Load .env from the project root (two levels up from this file)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def get_db_url() -> str:
    """Return the DATABASE_URL from the environment.

    Raises:
        RuntimeError: If DATABASE_URL is not set or is empty.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Create a .env file in the project root with your Neon connection string."
        )
    return url


def _normalize_url(url: str) -> str:
    """Ensure the URL uses the ``postgresql+psycopg`` dialect (psycopg 3).

    Neon connection strings typically start with ``postgresql://`` which causes
    SQLAlchemy to default to the legacy psycopg2 driver.  This helper rewrites
    the scheme so SQLAlchemy picks up psycopg v3 instead.
    """
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    return url


# ---------------------------------------------------------------------------
# Engine — configured for Neon serverless PostgreSQL
# ---------------------------------------------------------------------------
# Neon uses a connection pooler (PgBouncer) by default.
# We keep pool_size small and use pool_pre_ping to handle idle disconnects.
engine = create_engine(
    _normalize_url(get_db_url()),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "options": "-c timezone=utc",
    },
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base class for all SecurePulse ORM models."""

    pass
