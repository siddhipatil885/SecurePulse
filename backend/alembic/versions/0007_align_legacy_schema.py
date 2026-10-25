"""Align legacy Neon schema with current persistence contracts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_align_legacy"
down_revision: Union[str, None] = "0006_repair_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fresh 0001 installations already have these objects; legacy Neon did not.
    op.execute("CREATE INDEX IF NOT EXISTS ix_cameras_enabled ON cameras (enabled)")

    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute("ALTER TABLE evidence ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ")
    op.execute("UPDATE evidence SET timestamp = created_at WHERE timestamp IS NULL")
    op.alter_column("evidence", "timestamp", nullable=False)

    op.execute("UPDATE security_events SET confidence = 0 WHERE confidence IS NULL")
    op.alter_column(
        "security_events",
        "confidence",
        existing_type=sa.Float(),
        nullable=False,
    )

    op.execute("DROP INDEX IF EXISTS ix_security_events_frigate_event_id")
    op.create_index(
        "ix_security_events_frigate_event_id",
        "security_events",
        ["frigate_event_id"],
        unique=False,
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_evidence_event_id ON evidence (event_id)")
    for column in ("camera_id", "event_type", "timestamp"):
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_security_events_{column} ON security_events ({column})")
    op.alter_column("cameras", "location", type_=sa.String(512))
    op.alter_column("evidence", "type", type_=sa.String(100))
    op.alter_column("security_events", "severity", type_=sa.String(50))
    op.alter_column("security_events", "status", type_=sa.String(50))
    op.execute("ALTER TABLE security_events ALTER COLUMN metadata TYPE JSONB USING metadata::jsonb")


def downgrade() -> None:
    """Reject reversal because fresh and legacy schemas have different origins."""
    raise NotImplementedError("0007_align_legacy is not safely reversible; use a forward repair or restore a backup")
