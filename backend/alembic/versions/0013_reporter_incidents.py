"""Add reporter-owned incident reporting and evidence metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0013_reporter_incidents"
down_revision = "0012_property_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reporter_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reporter_user_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("incident_type", sa.String(64), nullable=False),
        sa.Column("description", sa.String(4000), nullable=True),
        sa.Column("address", sa.String(1000), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("location_accuracy", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="RECEIVED"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("reporter_user_id", "idempotency_key", name="uq_reporter_incident_idempotency"),
    )
    op.create_index("ix_reporter_incidents_property_created", "reporter_incidents", ["property_id", "created_at"])
    op.create_index("ix_reporter_incidents_reporter_created", "reporter_incidents", ["reporter_user_id", "created_at"])
    op.create_table(
        "reporter_incident_timeline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["reporter_incidents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reporter_incident_timeline_incident_time", "reporter_incident_timeline", ["incident_id", "occurred_at"])
    op.create_table(
        "reporter_incident_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["reporter_incidents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reporter_incident_evidence_incident", "reporter_incident_evidence", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_reporter_incident_evidence_incident", table_name="reporter_incident_evidence")
    op.drop_table("reporter_incident_evidence")
    op.drop_index("ix_reporter_incident_timeline_incident_time", table_name="reporter_incident_timeline")
    op.drop_table("reporter_incident_timeline")
    op.drop_index("ix_reporter_incidents_reporter_created", table_name="reporter_incidents")
    op.drop_index("ix_reporter_incidents_property_created", table_name="reporter_incidents")
    op.drop_table("reporter_incidents")
