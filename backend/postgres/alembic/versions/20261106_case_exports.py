"""Whole-case export requests. A new table only."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261106_case_exports"
down_revision = "20261108_upload_group_members_total"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "case_exports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("requested_by_email", sa.String(255), nullable=False),
        sa.Column("requested_by_name", sa.String(255), nullable=False),
        sa.Column("whole", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("phase", sa.Text()),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("path", sa.Text()),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("summary", JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_case_exports_case_id", "case_exports", ["case_id"])
    op.create_index("ix_case_exports_status", "case_exports", ["status"])


def downgrade():
    op.drop_table("case_exports")
