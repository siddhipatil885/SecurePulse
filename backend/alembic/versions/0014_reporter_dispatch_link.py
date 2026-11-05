"""Allow dispatch assignments to target reporter-created incidents."""

from alembic import op
import sqlalchemy as sa

revision = "0014_reporter_dispatch_link"
down_revision = "0013_reporter_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("assignments", "security_event_id", nullable=True)
    op.add_column("assignments", sa.Column("reporter_incident_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_assignments_reporter_incident_id",
        "assignments",
        "reporter_incidents",
        ["reporter_incident_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_assignments_one_incident_source",
        "assignments",
        "(security_event_id IS NOT NULL AND reporter_incident_id IS NULL) OR "
        "(security_event_id IS NULL AND reporter_incident_id IS NOT NULL)",
    )
    op.create_index("ix_assignments_reporter_incident_status", "assignments", ["reporter_incident_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_assignments_reporter_incident_status", table_name="assignments")
    op.drop_constraint("ck_assignments_one_incident_source", "assignments", type_="check")
    op.drop_constraint("fk_assignments_reporter_incident_id", "assignments", type_="foreignkey")
    op.drop_column("assignments", "reporter_incident_id")
    op.alter_column("assignments", "security_event_id", nullable=False)
