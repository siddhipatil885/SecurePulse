"""Store reporter device registrations and notification preferences."""

from alembic import op
import sqlalchemy as sa

revision = "0015_reporter_notifications"
down_revision = "0014_reporter_dispatch_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_device_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(255), nullable=False),
        sa.Column("push_token", sa.String(512), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "device_id", name="uq_user_device_tokens_user_device"),
    )
    op.create_index("ix_user_device_tokens_active", "user_device_tokens", ["user_id", "active"])
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "category", name="uq_notification_preferences_user_category"),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("ix_user_device_tokens_active", table_name="user_device_tokens")
    op.drop_table("user_device_tokens")
