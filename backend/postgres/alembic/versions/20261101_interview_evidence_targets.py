"""Interview evidence takes registry targets (07 section 6.4 item 5).

dossier_interview_evidence_links gains target_type and target_id; evidence_file_id becomes nullable, and a check
requires exactly one of the evidence file or the (target_type, target_id) pair. Every existing row has an
evidence file and no target, so every existing row satisfies the check unchanged. The upgrade counts the rows
before and after and refuses to finish if the count moved.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261101_interview_evidence_targets'
down_revision = '20261101_phone_file_evidence'
branch_labels = None
depends_on = None

CHECK = ("(evidence_file_id IS NOT NULL AND target_type IS NULL AND target_id IS NULL) OR "
         "(evidence_file_id IS NULL AND target_type IS NOT NULL AND target_id IS NOT NULL)")


def _count():
    return op.get_bind().execute(sa.text("SELECT count(*) FROM dossier_interview_evidence_links")).scalar_one()


def upgrade():
    before = _count()
    op.add_column('dossier_interview_evidence_links', sa.Column('target_type', sa.String(64), nullable=True))
    op.add_column('dossier_interview_evidence_links', sa.Column('target_id', sa.String(512), nullable=True))
    op.alter_column('dossier_interview_evidence_links', 'evidence_file_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_check_constraint('ck_dossier_interview_evidence_one_target', 'dossier_interview_evidence_links', CHECK)
    op.create_unique_constraint('uq_dossier_interview_evidence_target', 'dossier_interview_evidence_links',
                                ['interview_id', 'target_type', 'target_id'])
    after = _count()
    print(f"dossier_interview_evidence_links rows: before {before}, after {after}")
    if after != before:
        raise RuntimeError(f"dossier_interview_evidence_links row count moved from {before} to {after}")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM dossier_interview_evidence_links WHERE evidence_file_id IS NULL")).scalar_one():
        raise RuntimeError('Cannot restore the old shape: interview evidence holds registry targets.')
    op.drop_constraint('uq_dossier_interview_evidence_target', 'dossier_interview_evidence_links', type_='unique')
    op.drop_constraint('ck_dossier_interview_evidence_one_target', 'dossier_interview_evidence_links', type_='check')
    op.alter_column('dossier_interview_evidence_links', 'evidence_file_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_column('dossier_interview_evidence_links', 'target_id')
    op.drop_column('dossier_interview_evidence_links', 'target_type')
