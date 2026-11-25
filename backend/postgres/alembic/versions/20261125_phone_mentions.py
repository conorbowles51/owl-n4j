"""Mentions read out of phone texts and the per-phone runs that read them (lx-mentions).

``phone_mentions`` holds each checkable mention Loupe read in a message, note or calendar entry ("I'll drive up Friday
night"), with what Loupe read, a person's correction beside it, and the outcome rules computed from the case.
``phone_mention_runs`` holds one reading of one phone, with the last text finished so it carries on after a restart.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261125_phone_mentions"
down_revision = "20261125_phone_asks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_uid", sa.String(64), nullable=False),
        sa.Column("record_kind", sa.String(16), nullable=False, server_default="message"),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("copy_key", sa.String(80), nullable=False, server_default=""),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("phrase", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reading", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reader", sa.String(40), nullable=False, server_default="rules"),
        sa.Column("state", sa.String(16), nullable=False, server_default="read"),
        sa.Column("corrected", postgresql.JSONB(), nullable=True),
        sa.Column("corrected_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_by_name", sa.String(300), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_reason", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(24), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "record_uid", "start", "reader", name="uq_phone_mentions_record_span"),
        sa.CheckConstraint("state IN ('read', 'corrected', 'confirmed', 'rejected')", name="ck_phone_mentions_state"),
        sa.CheckConstraint("kind IN ('travel', 'meeting', 'at_place', 'home_away', 'plan', 'money', 'sent', 'deleted')",
                           name="ck_phone_mentions_kind"),
    )
    op.create_index("ix_phone_mentions_case_kind", "phone_mentions", ["case_id", "kind", "outcome"])
    op.create_index("ix_phone_mentions_case_record", "phone_mentions", ["case_id", "record_uid"])
    op.create_index("ix_phone_mentions_case_at", "phone_mentions", ["case_id", "at"])
    op.create_table(
        "phone_mention_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reader", sa.String(40), nullable=False, server_default="rules"),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("phase", sa.String(16), nullable=False, server_default="messages"),
        sa.Column("cursor_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_uid", sa.String(64), nullable=True),
        sa.Column("texts_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("texts_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mentions_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_by_name", sa.String(300), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running', 'done', 'failed', 'stopped')", name="ck_phone_mention_runs_status"),
    )
    op.create_index("ix_phone_mention_runs_case", "phone_mention_runs", ["case_id", "extraction_id", "started_at"])


def downgrade():
    op.drop_index("ix_phone_mention_runs_case", table_name="phone_mention_runs")
    op.drop_table("phone_mention_runs")
    op.drop_index("ix_phone_mentions_case_at", table_name="phone_mentions")
    op.drop_index("ix_phone_mentions_case_record", table_name="phone_mentions")
    op.drop_index("ix_phone_mentions_case_kind", table_name="phone_mentions")
    op.drop_table("phone_mentions")
