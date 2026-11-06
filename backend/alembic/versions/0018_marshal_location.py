"""Persist the latest authorized marshal location."""
from alembic import op
import sqlalchemy as sa

revision = "0018_marshal_location"
down_revision = "0017_reporter_active_assignment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("marshal_availability", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("marshal_availability", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("marshal_availability", sa.Column("location_accuracy_m", sa.Float(), nullable=True))
    op.add_column("marshal_availability", sa.Column("location_heading", sa.Float(), nullable=True))
    op.add_column("marshal_availability", sa.Column("location_speed_mps", sa.Float(), nullable=True))
    op.add_column("marshal_availability", sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for name in (
        "location_updated_at",
        "location_speed_mps",
        "location_heading",
        "location_accuracy_m",
        "longitude",
        "latitude",
    ):
        op.drop_column("marshal_availability", name)
