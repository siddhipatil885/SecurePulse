"""Seed the camera from the active local Frigate configuration."""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_seed_laptop_camera"
down_revision: Union[str, None] = "0002_seed_front_door"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO cameras (name, frigate_camera_name, location, enabled)
        VALUES ('Laptop Camera', 'laptop_camera', 'Local Test Camera', TRUE)
        ON CONFLICT (frigate_camera_name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM cameras WHERE frigate_camera_name = 'laptop_camera'"
    )