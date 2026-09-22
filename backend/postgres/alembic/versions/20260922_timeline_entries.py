"""Explicit financial and casework additions to Timeline."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260922_timeline_entries"
down_revision = "20260921_financial_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("timeline_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_kind", sa.String(24), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("added_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("case_id", "source_kind", "source_id", name="uq_timeline_entry_source"))
    op.create_index("ix_timeline_entries_case_id", "timeline_entries", ["case_id"])


def downgrade():
    op.drop_table("timeline_entries")
