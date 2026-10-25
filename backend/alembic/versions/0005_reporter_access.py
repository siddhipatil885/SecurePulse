"""Add reporter accounts and property access without changing detection tables."""
from alembic import op
import sqlalchemy as sa

revision = "0005_reporter_access"
down_revision = "0004_tracks_and_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("reporter_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table("properties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False))
    op.create_table("property_memberships",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("reporter_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'reporter')", name="reporter_role"))
    op.create_table("property_cameras",
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False))
    op.create_index("ix_property_cameras_property_id", "property_cameras", ["property_id"])


def downgrade() -> None:
    op.drop_table("property_cameras")
    op.drop_table("property_memberships")
    op.drop_table("properties")
    op.drop_table("reporter_users")
