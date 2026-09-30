"""Persist anonymous tracks and operator alerts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_tracks_and_alerts"
down_revision: Union[str, None] = "0003_seed_laptop_camera"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("security_events") as batch:
        batch.drop_constraint("uq_security_events_frigate_event_id", type_="unique")
        batch.add_column(sa.Column("incident_key", sa.String(length=512), nullable=True))
        batch.create_unique_constraint("uq_security_events_incident_key", ["incident_key"])
    op.add_column("evidence", sa.Column("metadata", sa.JSON(), nullable=True))
    op.execute("UPDATE evidence SET metadata = '{}' WHERE metadata IS NULL")
    op.alter_column("evidence", "metadata", nullable=False)
    op.create_table(
        "tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.String(length=255), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.Column("frame_width", sa.Integer(), nullable=False),
        sa.Column("frame_height", sa.Integer(), nullable=False),
        sa.Column("face_visible", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name="fk_tracks_camera_id_cameras"),
        sa.PrimaryKeyConstraint("id", name="pk_tracks"),
        sa.UniqueConstraint("track_id", name="uq_tracks_track_id"),
    )
    op.create_index("ix_tracks_camera_last_seen", "tracks", ["camera_id", "last_seen"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("security_event_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name="fk_alerts_camera_id_cameras"),
        sa.ForeignKeyConstraint(["security_event_id"], ["security_events.id"], name="fk_alerts_security_event_id_security_events", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_alerts"),
    )
    op.create_index("ix_alerts_camera_status", "alerts", ["camera_id", "status"])


def downgrade() -> None:
    with op.batch_alter_table("security_events") as batch:
        batch.drop_constraint("uq_security_events_incident_key", type_="unique")
        batch.drop_column("incident_key")
        batch.create_unique_constraint("uq_security_events_frigate_event_id", ["frigate_event_id"])
    op.drop_column("evidence", "metadata")
    op.drop_index("ix_alerts_camera_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_tracks_camera_last_seen", table_name="tracks")
    op.drop_table("tracks")