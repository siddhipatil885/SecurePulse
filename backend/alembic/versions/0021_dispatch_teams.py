"""Allow multiple active responders to join one dispatch team."""
from alembic import op
import sqlalchemy as sa


revision = "0021_dispatch_teams"
down_revision = "0020_marshal_onboarding"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assignments", sa.Column("team_key", sa.String(length=64), nullable=True))
    op.add_column("assignments", sa.Column("team_role", sa.String(length=80), nullable=True))
    for name, column in [("uq_assignments_one_active_offer", "security_event_id"),
                         ("uq_assignments_one_active_reporter", "reporter_incident_id")]:
        op.drop_index(name, table_name="assignments")
        op.create_index(
            name,
            "assignments",
            [column],
            unique=True,
            postgresql_where=sa.text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE') AND team_key IS NULL"),
            sqlite_where=sa.text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE') AND team_key IS NULL"),
        )


def downgrade():
    raise NotImplementedError("Reconcile active response teams before reverting team dispatch.")
