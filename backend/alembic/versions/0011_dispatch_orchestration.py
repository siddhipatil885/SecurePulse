"""Complete dispatch orchestration and notification delivery persistence."""
from alembic import op
import sqlalchemy as sa

revision = "0011_dispatch_orchestration"
down_revision = "0010_reporter_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.execute("UPDATE assignments SET idempotency_key = 'legacy-assignment-' || id WHERE idempotency_key IS NULL")
    op.alter_column("assignments", "idempotency_key", nullable=False)
    op.create_unique_constraint("uq_assignments_idempotency_key", "assignments", ["idempotency_key"])
    op.add_column("notification_outbox", sa.Column("destination", sa.String(255), nullable=True))
    op.add_column("notification_outbox", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification_outbox", sa.Column("claimed_by", sa.String(128), nullable=True))
    op.add_column("notification_attempts", sa.Column("error_detail", sa.String(1000), nullable=True))
    op.add_column("notification_attempts", sa.Column("response_metadata", sa.JSON(), nullable=True))
    op.execute("UPDATE notification_attempts SET response_metadata = '{}' WHERE response_metadata IS NULL")
    op.alter_column("notification_attempts", "response_metadata", nullable=False)
    op.execute("""CREATE OR REPLACE FUNCTION reject_assignment_event_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'assignment_events is append-only'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER assignment_events_immutable BEFORE UPDATE OR DELETE ON assignment_events
        FOR EACH ROW EXECUTE FUNCTION reject_assignment_event_mutation()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS assignment_events_immutable ON assignment_events")
    op.execute("DROP FUNCTION IF EXISTS reject_assignment_event_mutation()")
    op.drop_column("notification_attempts", "response_metadata")
    op.drop_column("notification_attempts", "error_detail")
    op.drop_column("notification_outbox", "claimed_by")
    op.drop_column("notification_outbox", "claimed_at")
    op.drop_column("notification_outbox", "destination")
    op.drop_constraint("uq_assignments_idempotency_key", "assignments", type_="unique")
    op.drop_column("assignments", "idempotency_key")
