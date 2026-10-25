"""Align the incident camera foreign key with the mapped cascade contract."""

from alembic import op

revision = "0009_event_camera_cascade"
down_revision = "0008_camera_zones_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace the original camera foreign key without deleting any rows."""
    op.drop_constraint("fk_security_events_camera_id_cameras", "security_events", type_="foreignkey")
    op.create_foreign_key("fk_security_events_camera_id_cameras", "security_events", "cameras",
                          ["camera_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Restore the non-cascading foreign key used by the initial migration."""
    op.drop_constraint("fk_security_events_camera_id_cameras", "security_events", type_="foreignkey")
    op.create_foreign_key("fk_security_events_camera_id_cameras", "security_events", "cameras",
                          ["camera_id"], ["id"])
