"""Create the initial SecurePulse persistence schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("frigate_camera_name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cameras"),
        sa.UniqueConstraint("frigate_camera_name", name="uq_cameras_frigate_camera_name"),
    )
    op.create_index("ix_cameras_enabled", "cameras", ["enabled"])

    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("zone", sa.String(length=255), nullable=True),
        sa.Column("frigate_event_id", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name="fk_security_events_camera_id_cameras"),
        sa.PrimaryKeyConstraint("id", name="pk_security_events"),
        sa.UniqueConstraint("frigate_event_id", name="uq_security_events_frigate_event_id"),
    )
    op.create_index(
        "ix_security_events_camera_timestamp",
        "security_events",
        ["camera_id", "timestamp"],
    )
    op.create_index("ix_security_events_severity", "security_events", ["severity"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["security_events.id"], name="fk_evidence_event_id_security_events", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
    )


def downgrade() -> None:
    op.drop_table("evidence")
    op.drop_index("ix_security_events_severity", table_name="security_events")
    op.drop_index("ix_security_events_camera_timestamp", table_name="security_events")
    op.drop_table("security_events")
    op.drop_index("ix_cameras_enabled", table_name="cameras")
    op.drop_table("cameras")