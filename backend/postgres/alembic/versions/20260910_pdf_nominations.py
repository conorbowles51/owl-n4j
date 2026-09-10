"""Retain source-bound model nomination attempts and immutable terminal outcomes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='20260910_pdf_nominations'
down_revision='20260910_counterparty_parties'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('financial_pdf_nominations',
        sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('case_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('cases.id',ondelete='CASCADE'),nullable=False),
        sa.Column('evidence_file_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('evidence_files.id',ondelete='CASCADE'),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('request_sha256',sa.String(64),nullable=False),
        sa.Column('request',postgresql.JSONB(),nullable=False),sa.Column('actor',postgresql.JSONB(),nullable=False),
        sa.Column('outcome_actor',postgresql.JSONB(none_as_null=True),nullable=True),sa.Column('result',postgresql.JSONB(none_as_null=True),nullable=True),sa.Column('error_code',sa.String(64),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('completed_at',sa.DateTime(timezone=True),nullable=True),
        sa.CheckConstraint("status IN ('pending','completed','failed')",name='ck_pdf_nomination_status'),
        sa.CheckConstraint('length(request_sha256)=64',name='ck_pdf_nomination_request_hash'),
        sa.CheckConstraint("(status='pending' AND outcome_actor IS NULL AND result IS NULL AND error_code IS NULL AND completed_at IS NULL) OR (status='completed' AND outcome_actor IS NOT NULL AND result IS NOT NULL AND error_code IS NULL AND completed_at IS NOT NULL) OR (status='failed' AND outcome_actor IS NOT NULL AND result IS NULL AND error_code IS NOT NULL AND completed_at IS NOT NULL)",name='ck_pdf_nomination_outcome'))
    op.create_index('ix_financial_pdf_nominations_case_id','financial_pdf_nominations',['case_id'])
    op.execute('''CREATE FUNCTION guard_financial_pdf_nomination() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending' OR NOT EXISTS (SELECT 1 FROM evidence_files WHERE id=NEW.evidence_file_id AND case_id=NEW.case_id)
           OR (NEW.request->>'case_id') IS DISTINCT FROM NEW.case_id::text
           OR (NEW.request->>'evidence_file_id') IS DISTINCT FROM NEW.evidence_file_id::text
        THEN RAISE EXCEPTION 'PDF nomination source scope is inconsistent'; END IF;
        RETURN NEW;
      END IF;
      IF OLD.status <> 'pending' OR NEW.status NOT IN ('completed','failed') OR
         ROW(NEW.id,NEW.case_id,NEW.evidence_file_id,NEW.request_sha256,NEW.request,NEW.actor,NEW.created_at)
         IS DISTINCT FROM ROW(OLD.id,OLD.case_id,OLD.evidence_file_id,OLD.request_sha256,OLD.request,OLD.actor,OLD.created_at)
      THEN RAISE EXCEPTION 'PDF nomination inputs and terminal outcomes are immutable'; END IF;
      RETURN NEW;
    END $$''')
    op.execute('CREATE TRIGGER guard_financial_pdf_nomination BEFORE INSERT OR UPDATE ON financial_pdf_nominations FOR EACH ROW EXECUTE FUNCTION guard_financial_pdf_nomination()')

def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM financial_pdf_nominations')).scalar_one():
        raise RuntimeError('Cannot downgrade while PDF nomination history exists.')
    op.drop_table('financial_pdf_nominations')
    op.execute('DROP FUNCTION guard_financial_pdf_nomination()')
