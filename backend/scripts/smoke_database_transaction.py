"""Rollback-only PostgreSQL smoke test for the Engineer 2 transaction contract."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import psycopg2
from psycopg2.errors import UniqueViolation
from psycopg2.extras import Json

from app.core.config import Settings


def main() -> None:
    settings = Settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not configured")

    marker = uuid4().hex
    slug = f"smoke-{marker}"
    connection = psycopg2.connect(settings.database_url)
    connection.autocommit = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO properties (slug, name, active) VALUES (%s, %s, TRUE) RETURNING id",
                (slug, "Rollback Smoke Property"),
            )
            property_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO users (subject, email, active) VALUES (%s, %s, TRUE) RETURNING id",
                (f"smoke-user-{marker}", f"{marker}@example.invalid"),
            )
            user_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO property_memberships (user_id, property_id, role, active) VALUES (%s, %s, 'operator', TRUE)",
                (user_id, property_id),
            )
            cursor.execute(
                """
                INSERT INTO cameras (property_id, name, frigate_camera_name, location, enabled)
                VALUES (%s, 'Smoke Camera', %s, 'Rollback only', TRUE) RETURNING id
                """,
                (property_id, f"smoke-camera-{marker}"),
            )
            camera_id = cursor.fetchone()[0]
            observed_at = datetime.now(timezone.utc)
            cursor.execute(
                """
                INSERT INTO zones (camera_id, external_id, name, kind, coordinates, active)
                VALUES (%s, 'restricted-entry', 'Restricted Entry', 'restricted', %s, TRUE)
                """,
                (camera_id, Json([[0, 0], [100, 0], [100, 100], [0, 100]])),
            )
            cursor.execute(
                """
                INSERT INTO camera_health_observations
                    (camera_id, status, source, observed_at, details)
                VALUES (%s, 'ONLINE', 'smoke', %s, %s)
                """,
                (camera_id, observed_at, Json({"smoke": True})),
            )
            cursor.execute(
                """
                INSERT INTO source_event_receipts
                    (property_id, camera_id, source_system, source_event_id, event_phase,
                     revision, observed_at, payload)
                VALUES (%s, %s, 'smoke', %s, 'new', '0', %s, %s) RETURNING id
                """,
                (property_id, camera_id, f"smoke-event-{marker}", observed_at, Json({"smoke": True})),
            )
            receipt_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO security_events
                    (property_id, camera_id, event_type, object_type, confidence, timestamp,
                     severity, status, frigate_event_id, incident_key, metadata)
                VALUES (%s, %s, 'SMOKE', 'person', 0.9, %s, 'HIGH', 'OPEN', %s, %s, %s)
                RETURNING id
                """,
                (
                    property_id,
                    camera_id,
                    observed_at,
                    f"smoke-event-{marker}",
                    f"smoke-incident-{marker}",
                    Json({"smoke": True}),
                ),
            )
            incident_id = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE source_event_receipts SET security_event_id = %s WHERE id = %s",
                (incident_id, receipt_id),
            )
            cursor.execute(
                """
                INSERT INTO incident_status_history
                    (security_event_id, previous_status, new_status, actor_subject, reason, correlation_id)
                VALUES (%s, NULL, 'OPEN', 'system:smoke', 'Rollback smoke test', %s)
                """,
                (incident_id, marker),
            )
            cursor.execute(
                """
                INSERT INTO notification_outbox
                    (property_id, security_event_id, kind, dedupe_key, status, payload)
                VALUES (%s, %s, 'INCIDENT_OPENED', %s, 'PENDING', %s)
                """,
                (property_id, incident_id, f"smoke-outbox-{marker}", Json({"smoke": True})),
            )

            cursor.execute("SAVEPOINT duplicate_receipt")
            duplicate_rejected = False
            try:
                cursor.execute(
                    """
                    INSERT INTO source_event_receipts
                        (property_id, camera_id, source_system, source_event_id, event_phase,
                         revision, observed_at, payload)
                    VALUES (%s, %s, 'smoke', %s, 'new', '0', %s, %s)
                    """,
                    (property_id, camera_id, f"smoke-event-{marker}", observed_at, Json({})),
                )
            except UniqueViolation:
                duplicate_rejected = True
                cursor.execute("ROLLBACK TO SAVEPOINT duplicate_receipt")
            if not duplicate_rejected:
                raise AssertionError("Duplicate source receipt was not rejected")

            cursor.execute(
                "SELECT count(*) FROM notification_outbox WHERE security_event_id = %s",
                (incident_id,),
            )
            if cursor.fetchone()[0] != 1:
                raise AssertionError("Incident transaction did not create exactly one outbox row")
            cursor.execute(
                """
                SELECT z.camera_id, h.status
                FROM zones z
                JOIN camera_health_observations h ON h.camera_id = z.camera_id
                WHERE z.camera_id = %s
                """,
                (camera_id,),
            )
            if cursor.fetchone() != (camera_id, "ONLINE"):
                raise AssertionError("Camera zone/health persistence did not round-trip")
    finally:
        connection.rollback()
        connection.close()

    verification = psycopg2.connect(settings.database_url)
    try:
        verification.set_session(readonly=True)
        with verification.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM properties WHERE slug = %s", (slug,))
            if cursor.fetchone()[0] != 0:
                raise AssertionError("Rollback smoke data remained in the database")
    finally:
        verification.close()

    print(
        "transaction_smoke=passed duplicate_receipt=rejected "
        "camera_operations=verified rollback=clean"
    )


if __name__ == "__main__":
    main()
