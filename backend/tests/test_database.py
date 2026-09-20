"""Phase 2 database foundation tests."""

import pytest

from app.database.base import Base
from app.database.database import _async_database_url


def test_models_are_registered_with_shared_metadata() -> None:
    import app.models  # noqa: F401

    assert set(Base.metadata.tables) == {"cameras", "security_events", "evidence"}


def test_database_url_normalizes_postgresql_scheme() -> None:
    assert (
        _async_database_url("postgresql://user:password@localhost/db")
        == "postgresql+asyncpg://user:password@localhost/db"
    )


@pytest.mark.parametrize("database_url", ["", "mysql://localhost/db"])
def test_database_url_rejects_missing_or_non_postgresql_urls(database_url: str) -> None:
    with pytest.raises((RuntimeError, ValueError)):
        _async_database_url(database_url)