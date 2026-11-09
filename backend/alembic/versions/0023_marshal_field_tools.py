"""Add assignment chat, field media, and reviewed response states."""
from alembic import op
import sqlalchemy as sa


revision = "0023_marshal_field_tools"
down_revision = "0022_marshal_location_history"
branch_labels = None
depends_on = None


def upgrade():
    active = "status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE', 'INVESTIGATING', 'PENDING_REVIEW') AND team_key IS NULL"
    for name, column in [("uq_assignments_one_active_offer", "security_event_id"),
                         ("uq_assignments_one_active_reporter", "reporter_incident_id")]:
        op.drop_index(name, table_name="assignments")
        op.create_index(name, "assignments", [column], unique=True,
                        postgresql_where=sa.text(active), sqlite_where=sa.text(active))

    op.create_table(
        "marshal_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploader_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assignment_id", "idempotency_key", name="uq_marshal_evidence_assignment_upload"),
    )
    op.create_index("ix_marshal_evidence_assignment_created", "marshal_evidence", ["assignment_id", "created_at"])
    op.create_table(
        "assignment_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("thread_key", sa.String(100), nullable=False),
        sa.Column("client_message_id", sa.String(80), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sender_user_id", "client_message_id", name="uq_assignment_messages_sender_client_id"),
    )
    op.create_index("ix_assignment_messages_thread_created", "assignment_messages", ["thread_key", "created_at", "id"])


def downgrade():
    raise NotImplementedError("Preserve field evidence and response chat during downgrade.")
