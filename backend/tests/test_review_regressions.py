"""Regression checks for migration safety and scoped read locking."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.incidents import IncidentRepository


def test_legacy_downgrade_refuses_before_any_database_operation(monkeypatch):
    """An irreversible repair must fail before deleting pre-existing objects."""
    path = Path(__file__).parents[1] / "alembic/versions/0007_align_legacy_schema.py"
    spec = importlib.util.spec_from_file_location("legacy_repair", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class NoDatabaseOperations:
        def __getattr__(self, name):
            pytest.fail(f"Downgrade attempted database operation: {name}")

    monkeypatch.setattr(module, "op", NoDatabaseOperations())
    with pytest.raises(NotImplementedError, match="not safely reversible"):
        module.downgrade()


async def test_read_lookup_is_scoped_without_row_lock():
    """Read authorization must retain tenant filtering without locking commands."""
    session = AsyncMock()
    repository = IncidentRepository(session)
    await repository.get(7, frozenset({3}))
    statement = session.scalar.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "FOR UPDATE" not in sql
    assert "security_events.id = 7" in sql and "security_events.property_id IN (3)" in sql
    await repository.get_for_update(7, frozenset({3}))
    statement = session.scalar.call_args.args[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))
