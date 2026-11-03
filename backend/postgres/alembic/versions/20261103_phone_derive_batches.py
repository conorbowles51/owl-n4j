"""Batch transcription and text reading of phone media (07 5 Media, M-5).

``phone_derive_batches`` holds one request to read every eligible file of one kind in a Media scope: the scope, the
true total queued, what was left out and why, who asked, and whether it was cancelled. Each queued reading names
its batch in ``phone_derived_texts.batch_id``; progress is counted from those rows, never estimated.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_derive_batches"
down_revision = "20261103_phone_machine_text_review"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_derive_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scope_words", sa.Text(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("left_out", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("kind IN ('ocr', 'transcript')", name="ck_phone_derive_batches_kind"),
    )
    op.create_index("ix_phone_derive_batches_case", "phone_derive_batches", ["case_id", "created_at"])
    op.add_column("phone_derived_texts", sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey(
        "phone_derive_batches.id", ondelete="SET NULL", name="fk_phone_derived_texts_batch"), nullable=True))
    op.create_index("ix_phone_derived_texts_batch", "phone_derived_texts", ["batch_id", "state"])


def downgrade():
    op.drop_index("ix_phone_derived_texts_batch", table_name="phone_derived_texts")
    op.drop_column("phone_derived_texts", "batch_id")
    op.drop_index("ix_phone_derive_batches_case", table_name="phone_derive_batches")
    op.drop_table("phone_derive_batches")
