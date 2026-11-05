"""Record authenticated reporter review decisions for alerts."""

from alembic import op
import sqlalchemy as sa

revision = "0016_alert_review"
down_revision = "0015_reporter_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("reviewed_by", sa.String(255), nullable=True))
    op.add_column("alerts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "reviewed_at")
    op.drop_column("alerts", "reviewed_by")
