"""Kept copies of removed analyst work (followups m11032229063349).

``removed_records``: one row per removal of a dossier assessment, interview, media item, link or saved snapshot,
holding the removed rows as they were, so the removal can be undone. New table; no existing row changes. On live
2026-11-04: 26 assessments, 18 interviews, 5 dossier links, 0 media and 0 snapshots could be removed with no copy.
"""
from alembic import op

revision = "20261104_removed_records"
down_revision = "20261103_phone_search_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE removed_records (
            id uuid PRIMARY KEY,
            case_id uuid NULL REFERENCES cases(id) ON DELETE CASCADE,
            kind varchar(32) NOT NULL,
            subject_id varchar(255) NOT NULL,
            label varchar(500) NULL,
            data jsonb NOT NULL,
            removed_by_user_id uuid NULL REFERENCES users(id) ON DELETE SET NULL,
            removed_by varchar(255) NULL,
            removed_at timestamptz NOT NULL DEFAULT now(),
            restored_at timestamptz NULL,
            restored_by varchar(255) NULL,
            CONSTRAINT ck_removed_records_kind CHECK (kind IN ('dossier_assessment', 'dossier_interview',
                'dossier_media', 'dossier_link', 'dossier_evidence_link', 'snapshot'))
        )""")
    op.execute("CREATE INDEX ix_removed_records_case_removed ON removed_records (case_id, removed_at)")
    op.execute("CREATE INDEX ix_removed_records_subject ON removed_records (kind, subject_id)")


def downgrade():
    op.execute("DROP TABLE removed_records")
