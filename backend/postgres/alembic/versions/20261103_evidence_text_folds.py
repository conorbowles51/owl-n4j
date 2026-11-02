"""Folded document text for Loupe-wide search (03 section 11.3, D-40).

``evidence_text_folds`` holds, per document text, the text folded by ``services.phone.fold.fold_with_map`` (the
same fold the query goes through), a packed map from folded to original character positions so highlights and
citations point at the original characters, the content hash it was folded from and how long folding took. It sits
beside ``evidence_document_texts`` rather than in it: that table is under the audit chain and has many writers, and
a derived column does not belong in an evidence row. The worker's backfill fills and refreshes it; search reads a
row only when its hash matches the current text.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_evidence_text_folds"
down_revision = "20261103_phone_selections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_text_folds",
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("fold_version", sa.Text(), nullable=False),
        sa.Column("content_folded", sa.Text(), nullable=False),
        sa.Column("fold_map", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("original_chars", sa.Integer(), nullable=False),
        sa.Column("fold_ms", sa.Integer(), nullable=False),
        sa.Column("folded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_text_folds_case", "evidence_text_folds", ["case_id"])
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_evidence_text_folds_trgm ON evidence_text_folds USING gin "
               "(content_folded gin_trgm_ops)")


def downgrade():
    op.drop_table("evidence_text_folds")
