"""
Pytest fixtures for EDI-SecurePulse database tests.

Uses a transactional rollback strategy so that each test runs inside a
nested SAVEPOINT that is rolled back after the test — leaving the real
Neon database unchanged.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import event

# Ensure project root is importable
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from database.models.base import SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session")
def connection():
    """Yield a single database connection for the entire test session."""
    conn = engine.connect()
    yield conn
    conn.close()


@pytest.fixture()
def db_session(connection):
    """Yield a session that rolls back all changes after each test.

    Strategy:
    1. Begin a top-level transaction on the connection.
    2. Bind a Session to that connection.
    3. After the test, roll back the transaction.

    This prevents any test data from persisting in Neon.
    """
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    # If the ORM issues a commit (e.g., session.commit()), restart a nested
    # savepoint so the outer transaction is never actually committed.
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        nonlocal nested
        if trans.nested and not trans._parent.nested:
            nested = connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
