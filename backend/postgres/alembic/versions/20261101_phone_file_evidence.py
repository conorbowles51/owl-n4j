"""Evidence rows for phone files, registered one at a time on demand (07 section 6.4 item 4).

Adds the nullable evidence_files.source_ref (the phone file id) and a unique index on (case_id, source_ref) for
phone_file rows only. Existing rows are untouched: source_ref is NULL for every one of them.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261101_phone_file_evidence'
down_revision = '20261101_collection_memberships'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('evidence_files', sa.Column('source_ref', sa.String(255), nullable=True))
    op.create_index('uq_evidence_files_case_phone_file', 'evidence_files', ['case_id', 'source_ref'], unique=True,
                    postgresql_where=sa.text("source_type = 'phone_file'"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM evidence_files WHERE source_type = 'phone_file'")).scalar_one():
        raise RuntimeError('Cannot remove source_ref: phone file evidence rows exist.')
    op.drop_index('uq_evidence_files_case_phone_file', table_name='evidence_files')
    op.drop_column('evidence_files', 'source_ref')
