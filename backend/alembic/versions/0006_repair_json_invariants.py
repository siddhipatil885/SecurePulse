"""Repair legacy nullable JSON values required by API contracts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_repair_json"
down_revision: Union[str, None] = "0005_tenancy_operations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE security_events SET metadata = '{}'::json WHERE metadata IS NULL")
    op.alter_column(
        "security_events",
        "metadata",
        existing_type=sa.JSON(),
        nullable=False,
        server_default=sa.text("'{}'::json"),
    )


def downgrade() -> None:
    op.alter_column(
        "security_events",
        "metadata",
        existing_type=sa.JSON(),
        nullable=True,
        server_default=None,
    )
