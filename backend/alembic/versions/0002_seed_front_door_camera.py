"""Seed the camera used by the bundled Frigate configuration."""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_seed_front_door"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO cameras (name, frigate_camera_name, location, enabled)
        VALUES ('Front Door', 'front_door', 'Front Door', TRUE)
        ON CONFLICT (frigate_camera_name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM cameras WHERE frigate_camera_name = 'front_door'"
    )