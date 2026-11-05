"""Store the property address collected by dashboard onboarding."""
from alembic import op
import sqlalchemy as sa

revision = "0012_property_address"
down_revision = "0011_dispatch_orchestration"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("address", sa.String(1000), nullable=True))


def downgrade():
    op.drop_column("properties", "address")
