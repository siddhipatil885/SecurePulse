"""
Neon PostgreSQL connection test for EDI-SecurePulse.

Usage:
    python -m database.scripts.test_connection

Verifies:
    1. DATABASE_URL is set in .env
    2. SQLAlchemy can connect to Neon
    3. Prints safe diagnostic info (database name, user, PG version)

NEVER prints the connection string or password.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import text

from database.models.base import engine, get_db_url


def test_connection() -> None:
    """Test the Neon PostgreSQL connection and print safe diagnostics."""
    # 1. Check that DATABASE_URL exists (get_db_url raises RuntimeError if not)
    try:
        get_db_url()
    except RuntimeError as exc:
        print(f"CONFIGURATION ERROR: {exc}")
        sys.exit(1)

    # 2. Connect and run diagnostics
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            db_name = conn.execute(text("SELECT current_database()")).scalar()
            db_user = conn.execute(text("SELECT current_user")).scalar()
    except Exception as exc:
        print(f"CONNECTION FAILED: {exc}")
        sys.exit(1)

    # 3. Print safe information only
    print()
    print("=" * 50)
    print("  SecurePulse — Database Connection Test")
    print("=" * 50)
    print(f"  Status:     CONNECTED")
    print(f"  Database:   {db_name}")
    print(f"  User:       {db_user}")
    print(f"  PostgreSQL: {version}")
    print("=" * 50)
    print()


if __name__ == "__main__":
    test_connection()
