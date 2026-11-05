"""Enforce a single active assignment per manually reported incident.

Existing duplicate active rows cause this migration to fail safely; an operator
must reconcile them explicitly. No assignments or historical events are deleted.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_reporter_active_assignment"
down_revision = "0016_alert_review"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uq_assignments_one_active_reporter", "assignments", ["reporter_incident_id"],
        unique=True, postgresql_where=sa.text("status IN ('OFFERED', 'ACCEPTED', 'EN_ROUTE', 'ON_SCENE')"))


def downgrade():
    op.drop_index("uq_assignments_one_active_reporter", table_name="assignments")
