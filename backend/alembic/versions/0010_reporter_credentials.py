"""Add password credentials to the shared tenant user model.

Reporter accounts now use the existing users and property membership tables.
This keeps reporter access aligned with camera ownership and avoids a second,
independent property catalog.
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_reporter_credentials"
down_revision = "0009_event_camera_cascade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(256), nullable=True))
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_attempts")
    op.drop_column("users", "token_version")
    op.drop_column("users", "password_hash")
