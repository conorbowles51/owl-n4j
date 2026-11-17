"""Ratings of agent answers: missed something, not relevant, too thin (lx-agenttools D20).

Append-only: a rating and its withdrawal are each a row.

Revision ID: 20261117_agent_answer_ratings
Revises: 20261117_corroborate_facts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261117_agent_answer_ratings"
down_revision = "20261117_corroborate_facts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_answer_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("action", sa.String(12), nullable=False, server_default="rate"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("record_ref", sa.Text(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for column in ("case_id", "thread_id", "message_id", "run_id"):
        op.create_index("ix_agent_answer_ratings_%s" % column, "agent_answer_ratings", [column])


def downgrade():
    op.drop_table("agent_answer_ratings")
