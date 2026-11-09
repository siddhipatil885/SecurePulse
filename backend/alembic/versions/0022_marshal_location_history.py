"""Retain a short, incident-scoped marshal GPS trail for dispatch review."""
from alembic import op
import sqlalchemy as sa


revision = "0022_marshal_location_history"
down_revision = "0021_dispatch_teams"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marshal_location_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("marshal_profile_id", sa.Integer(), sa.ForeignKey("marshal_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float()),
        sa.Column("heading", sa.Float()),
        sa.Column("speed_mps", sa.Float()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_marshal_location_history_assignment_recorded", "marshal_location_history", ["assignment_id", "recorded_at"])
    op.create_index("ix_marshal_location_history_property_recorded", "marshal_location_history", ["property_id", "recorded_at"])


def downgrade():
    op.drop_index("ix_marshal_location_history_property_recorded", table_name="marshal_location_history")
    op.drop_index("ix_marshal_location_history_assignment_recorded", table_name="marshal_location_history")
    op.drop_table("marshal_location_history")
