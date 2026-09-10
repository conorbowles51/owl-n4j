"""Preserve attributed custody reports and corrections without invented history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = '20260910_custody'
down_revision = '20260910_audit_graph_jobs'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('financial_custody_events',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('evidence_file_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('evidence_sha256', sa.String(64)),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('actor', pg.JSONB(), nullable=False),
        sa.Column('report', pg.JSONB(), nullable=False))
    for column in ('case_id', 'evidence_file_id'):
        op.create_index('ix_financial_custody_events_' + column, 'financial_custody_events', [column])
    op.execute("CREATE TRIGGER capture_financial_audit AFTER INSERT ON financial_custody_events FOR EACH ROW EXECUTE FUNCTION capture_financial_audit_event('direct')")
    op.execute('''CREATE FUNCTION refuse_custody_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Custody history is append-only; record a correction instead'; END $$''')
    op.execute('CREATE TRIGGER refuse_custody_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON financial_custody_events FOR EACH STATEMENT EXECUTE FUNCTION refuse_custody_mutation()')


def downgrade():
    raise RuntimeError('Custody history cannot be silently removed; use an explicitly reviewed backup.')
