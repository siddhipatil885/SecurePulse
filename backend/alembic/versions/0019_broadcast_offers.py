"""Allow multiple invitations, with at most one responding marshal per incident."""
from alembic import op
import sqlalchemy as sa

revision = '0019_broadcast_offers'
down_revision = '0018_marshal_location'
branch_labels = None
depends_on = None


def upgrade():
    for name, column in [('uq_assignments_one_active_offer', 'security_event_id'),
                         ('uq_assignments_one_active_reporter', 'reporter_incident_id')]:
        op.drop_index(name, table_name='assignments')
        op.create_index(name, 'assignments', [column], unique=True,
                        postgresql_where=sa.text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE')"),
                        sqlite_where=sa.text("status IN ('ACCEPTED', 'EN_ROUTE', 'ON_SCENE')"))
    for suffix, column in [('camera', 'security_event_id'), ('reporter', 'reporter_incident_id')]:
        op.create_index(f'uq_assignment_pending_{suffix}_marshal', 'assignments', [column, 'marshal_profile_id'],
                        unique=True, postgresql_where=sa.text("status = 'OFFERED'"), sqlite_where=sa.text("status = 'OFFERED'"))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("UPDATE assignments SET expires_at = offered_at + interval '5 minutes' "
                   "WHERE status = 'OFFERED' AND expires_at > offered_at + interval '5 minutes'")


def downgrade():
    raise NotImplementedError('Broadcast offers must be reconciled before restoring a single-offer index.')
