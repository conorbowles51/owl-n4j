"""Download originals (03 section 8.3): a frozen set of phone files drawn into a zip with a hash manifest, as a job.

One row per request, with true progress in files and bytes. The set is frozen when it is asked for, so what is drawn
is what was selected. Its own table, not ``phone_exports``: a job can run for hours, keeps a heartbeat, and its result
has counts an export does not (hash mismatches, files not included).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261104_phone_original_bundles"
down_revision = "20261105_agent_evidence_rest"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_original_bundles",
        sa.Column("bundle_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scope_words", sa.Text(), nullable=False),
        sa.Column("file_uids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("files_total", sa.Integer(), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False),
        sa.Column("files_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_done", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mismatched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_stored_hash", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state IN ('queued', 'running', 'done', 'failed', 'cancelled', 'removed')",
                           name="ck_phone_original_bundles_state"),
    )
    op.create_index("ix_phone_original_bundles_case", "phone_original_bundles", ["case_id", "created_at"])
    op.create_index("ix_phone_original_bundles_open", "phone_original_bundles", ["created_at"],
                    postgresql_where=sa.text("state IN ('queued', 'running')"))


def downgrade():
    op.drop_index("ix_phone_original_bundles_open", table_name="phone_original_bundles")
    op.drop_index("ix_phone_original_bundles_case", table_name="phone_original_bundles")
    op.drop_table("phone_original_bundles")
