"""Phase 2 database foundation tests."""

import pytest

from app.database.base import Base
from app.database.database import _async_database_url


def test_models_are_registered_with_shared_metadata() -> None:
    import app.models  # noqa: F401

    assert set(Base.metadata.tables) == {
        "alerts",
        "assignment_events",
        "assignments",
        "audit_records",
        "camera_health_observations",
        "cameras",
        "evidence",
        "incident_status_history",
        "marshal_availability",
        "marshal_profiles",
        "notification_attempts",
        "notification_outbox",
        "properties",
        "property_memberships",
        "security_events",
        "source_event_receipts",
        "tracks",
        "users",
        "zones",
    }


def test_database_url_normalizes_postgresql_scheme() -> None:
    assert (
        _async_database_url("postgresql://user:password@localhost/db")
        == "postgresql+asyncpg://user:password@localhost/db"
    )


def test_database_url_translates_neon_libpq_options_for_asyncpg() -> None:
    normalized = _async_database_url(
        "postgresql://user:password@example.neon.tech/db?sslmode=require&channel_binding=require"
    )

    assert normalized == "postgresql+asyncpg://user:password@example.neon.tech/db?ssl=require"
    assert "channel_binding" not in normalized


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"])
def test_database_tls_mode_is_preserved(mode):
    """Never silently weaken a caller's configured TLS verification level."""
    from sqlalchemy.engine import make_url
    url = _async_database_url(f"postgresql://user:password@localhost/db?sslmode={mode}")
    assert make_url(url).query["ssl"] == mode


def test_unknown_database_tls_mode_fails_closed():
    with pytest.raises(ValueError, match="sslmode"):
        _async_database_url("postgresql://user:password@localhost/db?sslmode=typo")


@pytest.mark.parametrize("database_url", ["", "mysql://localhost/db"])
def test_database_url_rejects_missing_or_non_postgresql_urls(database_url: str) -> None:
    with pytest.raises((RuntimeError, ValueError)):
        _async_database_url(database_url)
