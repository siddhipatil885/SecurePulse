"""Add persisted camera zones and health observations."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_camera_zones_health"
down_revision: Union[str, None] = "0007_align_legacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(64), server_default="restricted", nullable=False),
        sa.Column("coordinates", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["camera_id"], ["cameras.id"], name="fk_zones_camera_id_cameras", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_zones"),
        sa.UniqueConstraint("camera_id", "external_id", name="uq_zones_camera_external_id"),
    )
    op.create_index("ix_zones_camera_active", "zones", ["camera_id", "active"])

    op.create_table(
        "camera_health_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["camera_id"],
            ["cameras.id"],
            name="fk_camera_health_observations_camera_id_cameras",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_camera_health_observations"),
    )
    op.create_index(
        "ix_camera_health_observations_camera_time",
        "camera_health_observations",
        ["camera_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_camera_health_observations_camera_time",
        table_name="camera_health_observations",
    )
    op.drop_table("camera_health_observations")
    op.drop_index("ix_zones_camera_active", table_name="zones")
    op.drop_table("zones")
