"""Machine-generated text from phone media (03 section 8.3, M-3): text read from an image (OCR) or a transcript of
audio, made by a local model on request. The model and its version are stored with the text, the original file is
never changed, and the text is searchable as its own kind, tagged machine-generated.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_derived_texts"
down_revision = "20261103_phone_exports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_derived_texts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_uid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("text_folded", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("segments", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('ocr', 'transcript')", name="ck_phone_derived_texts_kind"),
        sa.CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="ck_phone_derived_texts_state"),
    )
    op.create_index("ix_phone_derived_texts_file", "phone_derived_texts", ["case_id", "file_uid", "created_at"])
    op.create_index("ix_phone_derived_texts_queued", "phone_derived_texts", ["created_at"],
                    postgresql_where=sa.text("state IN ('queued', 'running')"))


def downgrade():
    op.drop_index("ix_phone_derived_texts_queued", table_name="phone_derived_texts")
    op.drop_index("ix_phone_derived_texts_file", table_name="phone_derived_texts")
    op.drop_table("phone_derived_texts")
