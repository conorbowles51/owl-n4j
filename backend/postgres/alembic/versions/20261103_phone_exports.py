"""Phone exports as jobs (03 section 12.2): ``phone_exports``.

One row per export: who asked and when, the format and source, the filter and options as sent and the snapshot
they were read at (so an export can be reproduced and its content explained), the state and progress of the job,
the counts printed on the cover, and the finished file's name, size, SHA-256 and storage path. A failed export keeps
its choices and an error with a reference id; nothing is half-delivered.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_exports"
down_revision = "20261103_evidence_text_folds"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_exports",
        sa.Column("export_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("filter", postgresql.JSONB(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("counts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("format IN ('pdf', 'rsmf')", name="ck_phone_exports_format"),
        sa.CheckConstraint("state IN ('queued', 'rendering', 'done', 'failed')", name="ck_phone_exports_state"),
    )
    op.create_index("ix_phone_exports_case", "phone_exports", ["case_id", "created_at"])
    op.create_index("ix_phone_exports_queued", "phone_exports", ["created_at"],
                    postgresql_where=sa.text("state IN ('queued', 'rendering')"))


def downgrade():
    op.drop_index("ix_phone_exports_queued", table_name="phone_exports")
    op.drop_index("ix_phone_exports_case", table_name="phone_exports")
    op.drop_table("phone_exports")
