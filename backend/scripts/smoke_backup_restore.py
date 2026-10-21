"""Rollback-only logical backup/restore rehearsal using dedicated test data."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

import psycopg2

from app.core.config import Settings


def main() -> None:
    settings = Settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not configured")

    marker = uuid4().hex
    connection = psycopg2.connect(settings.database_url)
    connection.autocommit = False
    started = perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO properties (slug, name, active) VALUES (%s, %s, TRUE) RETURNING id",
                (f"restore-{marker}", "Restore Rehearsal Property"),
            )
            property_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO users (subject, email, display_name, active) VALUES (%s, %s, %s, TRUE) RETURNING id",
                (f"restore-user-{marker}", f"{marker}@example.invalid", "Restore Rehearsal User"),
            )
            user_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO property_memberships (user_id, property_id, role, active) VALUES (%s, %s, 'operator', TRUE) RETURNING id",
                (user_id, property_id),
            )
            membership_id = cursor.fetchone()[0]

            cursor.execute(
                "SELECT slug, name, active FROM properties WHERE id = %s", (property_id,)
            )
            property_backup = cursor.fetchone()
            cursor.execute(
                "SELECT subject, email, display_name, active FROM users WHERE id = %s", (user_id,)
            )
            user_backup = cursor.fetchone()
            cursor.execute(
                "SELECT role, active FROM property_memberships WHERE id = %s", (membership_id,)
            )
            membership_backup = cursor.fetchone()

            cursor.execute("DELETE FROM property_memberships WHERE id = %s", (membership_id,))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            cursor.execute("DELETE FROM properties WHERE id = %s", (property_id,))

            cursor.execute(
                "INSERT INTO properties (id, slug, name, active) VALUES (%s, %s, %s, %s)",
                (property_id, *property_backup),
            )
            cursor.execute(
                "INSERT INTO users (id, subject, email, display_name, active) VALUES (%s, %s, %s, %s, %s)",
                (user_id, *user_backup),
            )
            cursor.execute(
                "INSERT INTO property_memberships (id, user_id, property_id, role, active) VALUES (%s, %s, %s, %s, %s)",
                (membership_id, user_id, property_id, *membership_backup),
            )
            cursor.execute(
                """
                SELECT count(*)
                FROM property_memberships membership
                JOIN users app_user ON app_user.id = membership.user_id
                JOIN properties property ON property.id = membership.property_id
                WHERE membership.id = %s AND app_user.id = %s AND property.id = %s
                """,
                (membership_id, user_id, property_id),
            )
            if cursor.fetchone()[0] != 1:
                raise AssertionError("Restored tenant relationship failed validation")
    finally:
        connection.rollback()
        connection.close()

    elapsed_ms = (perf_counter() - started) * 1000
    print(f"backup_restore_smoke=passed rollback=clean elapsed_ms={elapsed_ms:.1f}")


if __name__ == "__main__":
    main()
