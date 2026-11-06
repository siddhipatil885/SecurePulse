"""Require reviewed onboarding before a marshal becomes eligible."""
from alembic import op
import sqlalchemy as sa

revision = '0020_marshal_onboarding'
down_revision = '0019_broadcast_offers'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('marshal_profiles', sa.Column('verification_status', sa.String(20), nullable=False, server_default='REQUIRED'))
    op.create_table('marshal_onboarding',
        sa.Column('marshal_profile_id', sa.Integer(), sa.ForeignKey('marshal_profiles.id'), primary_key=True),
        sa.Column('encrypted_details', sa.LargeBinary(), nullable=False),
        sa.Column('documents', sa.JSON(), nullable=False),
        sa.Column('id_type', sa.String(32), nullable=False),
        sa.Column('id_last_four', sa.String(4), nullable=False),
        sa.Column('consent_version', sa.String(32), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('reviewed_by', sa.String(255)),
        sa.Column('review_note', sa.String(1000)))
    op.execute('UPDATE marshal_availability SET on_duty = false, available = false')


def downgrade():
    raise NotImplementedError('Archive identity records securely before removing onboarding storage.')
