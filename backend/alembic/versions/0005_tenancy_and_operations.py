"""Add tenant isolation, durable receipts, audit, outbox, and assignments.

This migration preserves pre-existing camera and event rows by assigning them
to an explicit system-owned legacy property. It does not infer a real customer
or organization for those records.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_tenancy_operations"
down_revision: Union[str, None] = "0004_tracks_and_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_properties"),
        sa.UniqueConstraint("slug", name="uq_properties_slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("subject", name="uq_users_subject"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.execute(
        "INSERT INTO properties (slug, name, active) VALUES ('legacy-unassigned', 'Legacy / Unassigned', TRUE)"
    )

    op.add_column("cameras", sa.Column("property_id", sa.Integer(), nullable=True))
    op.execute("UPDATE cameras SET property_id = (SELECT id FROM properties WHERE slug = 'legacy-unassigned')")
    op.alter_column("cameras", "property_id", nullable=False)
    op.create_foreign_key("fk_cameras_property_id_properties", "cameras", "properties", ["property_id"], ["id"])
    op.create_index("ix_cameras_property_enabled", "cameras", ["property_id", "enabled"])

    op.create_table(
        "property_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_property_memberships_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], name="fk_property_memberships_property_id_properties", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_property_memberships"),
        sa.UniqueConstraint("user_id", "property_id", name="uq_property_memberships_user_property"),
    )
    op.create_index("ix_property_memberships_property_role", "property_memberships", ["property_id", "role"])

    op.create_table(
        "source_event_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column("security_event_id", sa.Integer(), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.String(255), nullable=False),
        sa.Column("event_phase", sa.String(32), nullable=False),
        sa.Column("revision", sa.String(64), server_default="0", nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], name="fk_source_event_receipts_property_id_properties"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name="fk_source_event_receipts_camera_id_cameras"),
        sa.ForeignKeyConstraint(["security_event_id"], ["security_events.id"], name="fk_source_event_receipts_security_event_id_security_events", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_source_event_receipts"),
        sa.UniqueConstraint("source_system", "source_event_id", "event_phase", "revision", name="uq_source_event_receipts_identity"),
    )
    op.create_index("ix_source_event_receipts_property_received", "source_event_receipts", ["property_id", "received_at"])

    op.add_column("security_events", sa.Column("property_id", sa.Integer(), nullable=True))
    op.execute("UPDATE security_events SET property_id = cameras.property_id FROM cameras WHERE cameras.id = security_events.camera_id")
    op.alter_column("security_events", "property_id", nullable=False)
    op.create_foreign_key("fk_security_events_property_id_properties", "security_events", "properties", ["property_id"], ["id"])

    op.create_table(
        "incident_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("security_event_id", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("correlation_id", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["security_event_id"], ["security_events.id"], name="fk_incident_status_history_security_event_id_security_events", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_incident_status_history"),
    )
    op.create_index("ix_incident_status_history_event_time", "incident_status_history", ["security_event_id", "occurred_at"])
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("correlation_id", sa.String(255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], name="fk_audit_records_property_id_properties"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_records"),
    )
    op.create_index("ix_audit_records_property_time", "audit_records", ["property_id", "occurred_at"])

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("security_event_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), server_default="PENDING", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], name="fk_notification_outbox_property_id_properties"),
        sa.ForeignKeyConstraint(["security_event_id"], ["security_events.id"], name="fk_notification_outbox_security_event_id_security_events", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_notification_outbox"),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),
    )
    op.create_index("ix_notification_outbox_status_available", "notification_outbox", ["status", "available_at"])
    op.create_table(
        "notification_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("outbox_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["outbox_id"], ["notification_outbox.id"], name="fk_notification_attempts_outbox_id_notification_outbox", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_notification_attempts"),
        sa.UniqueConstraint("outbox_id", "attempt_number", name="uq_notification_attempts_number"),
    )

    op.create_table(
        "marshal_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("service_area", sa.String(255), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("capacity", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_marshal_profiles_user_id_users"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], name="fk_marshal_profiles_property_id_properties"),
        sa.PrimaryKeyConstraint("id", name="pk_marshal_profiles"),
        sa.UniqueConstraint("user_id", name="uq_marshal_profiles_user_id"),
        sa.CheckConstraint("capacity > 0", name="ck_marshal_profiles_capacity_positive"),
    )
    op.create_index("ix_marshal_profiles_property_active", "marshal_profiles", ["property_id", "active"])
    op.create_table(
        "marshal_availability",
        sa.Column("marshal_profile_id", sa.Integer(), nullable=False),
        sa.Column("on_duty", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("available", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["marshal_profile_id"], ["marshal_profiles.id"], name="fk_marshal_availability_marshal_profile_id_marshal_profiles", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("marshal_profile_id", name="pk_marshal_availability"),
    )
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("security_event_id", sa.Integer(), nullable=False),
        sa.Column("marshal_profile_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], name="fk_assignments_property_id_properties"),
        sa.ForeignKeyConstraint(["security_event_id"], ["security_events.id"], name="fk_assignments_security_event_id_security_events", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["marshal_profile_id"], ["marshal_profiles.id"], name="fk_assignments_marshal_profile_id_marshal_profiles"),
        sa.PrimaryKeyConstraint("id", name="pk_assignments"),
    )
    op.create_index("ix_assignments_event_status", "assignments", ["security_event_id", "status"])
    op.create_index("uq_assignments_one_active_offer", "assignments", ["security_event_id"], unique=True, postgresql_where=sa.text("status IN ('OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE')"))
    op.create_table(
        "assignment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], name="fk_assignment_events_assignment_id_assignments", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_assignment_events"),
    )
    op.create_index("ix_assignment_events_assignment_time", "assignment_events", ["assignment_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_assignment_events_assignment_time", table_name="assignment_events")
    op.drop_table("assignment_events")
    op.drop_index("uq_assignments_one_active_offer", table_name="assignments")
    op.drop_index("ix_assignments_event_status", table_name="assignments")
    op.drop_table("assignments")
    op.drop_table("marshal_availability")
    op.drop_index("ix_marshal_profiles_property_active", table_name="marshal_profiles")
    op.drop_table("marshal_profiles")
    op.drop_table("notification_attempts")
    op.drop_index("ix_notification_outbox_status_available", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_audit_records_property_time", table_name="audit_records")
    op.drop_table("audit_records")
    op.drop_index("ix_incident_status_history_event_time", table_name="incident_status_history")
    op.drop_table("incident_status_history")
    op.drop_constraint("fk_security_events_property_id_properties", "security_events", type_="foreignkey")
    op.drop_column("security_events", "property_id")
    op.drop_index("ix_source_event_receipts_property_received", table_name="source_event_receipts")
    op.drop_table("source_event_receipts")
    op.drop_index("ix_property_memberships_property_role", table_name="property_memberships")
    op.drop_table("property_memberships")
    op.drop_index("ix_cameras_property_enabled", table_name="cameras")
    op.drop_constraint("fk_cameras_property_id_properties", "cameras", type_="foreignkey")
    op.drop_column("cameras", "property_id")
    op.drop_table("users")
    op.drop_table("properties")
