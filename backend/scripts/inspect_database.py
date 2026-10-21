"""Read-only PostgreSQL/Neon schema inspection without printing credentials."""

from __future__ import annotations

import psycopg2

from app.core.config import Settings


def main() -> None:
    settings = Settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not configured")

    connection = psycopg2.connect(settings.database_url)
    try:
        connection.set_session(readonly=True, autocommit=False)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, current_schema()")
            database, user, schema = cursor.fetchone()
            print(f"database={database} user={user} schema={schema}")

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
            tables = [row[0] for row in cursor.fetchall()]
            print("tables=" + (", ".join(tables) if tables else "<none>"))
            for table in (
                "properties", "users", "property_memberships", "cameras",
                "zones", "camera_health_observations",
                "source_event_receipts", "security_events", "incident_status_history",
                "evidence", "tracks", "alerts", "audit_records",
                "notification_outbox", "notification_attempts", "marshal_profiles",
                "marshal_availability", "assignments", "assignment_events",
            ):
                if table in tables:
                    cursor.execute(f'SELECT count(*) FROM "{table}"')
                    print(f"rows.{table}={cursor.fetchone()[0]}")

            if "properties" in tables:
                cursor.execute("SELECT count(*) FROM properties WHERE slug = 'legacy-unassigned'")
                print(f"invariant.legacy_property={cursor.fetchone()[0]}")
            if "cameras" in tables and "properties" in tables:
                cursor.execute("SELECT count(*) FROM cameras WHERE property_id IS NULL")
                print(f"invariant.camera_null_property={cursor.fetchone()[0]}")
            if "security_events" in tables and "properties" in tables:
                cursor.execute("SELECT count(*) FROM security_events WHERE property_id IS NULL")
                print(f"invariant.event_null_property={cursor.fetchone()[0]}")

            cursor.execute("SELECT to_regclass('public.alembic_version')")
            if cursor.fetchone()[0] is None:
                print("alembic_revision=<none>")
            else:
                cursor.execute("SELECT version_num FROM alembic_version")
                revisions = [row[0] for row in cursor.fetchall()]
                print("alembic_revision=" + ", ".join(revisions))
    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
