"""Ratings cover chat answers too (lx-agenttools D20).

A rating names its answer by ``source`` ('agent' or 'chat') and ids; the two kinds sit in different tables, so the
foreign keys on the thread and message columns are dropped (the case key stays).

Revision ID: 20261118_answer_ratings_chat
Revises: 20261117_agent_answer_ratings
"""
from alembic import op
import sqlalchemy as sa

revision = "20261118_answer_ratings_chat"
down_revision = "20261117_agent_answer_ratings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_answer_ratings", sa.Column("source", sa.String(8), nullable=False, server_default="agent"))
    op.drop_constraint("agent_answer_ratings_thread_id_fkey", "agent_answer_ratings", type_="foreignkey")
    op.drop_constraint("agent_answer_ratings_message_id_fkey", "agent_answer_ratings", type_="foreignkey")


def downgrade():
    op.create_foreign_key("agent_answer_ratings_message_id_fkey", "agent_answer_ratings", "agent_messages",
                          ["message_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("agent_answer_ratings_thread_id_fkey", "agent_answer_ratings", "agent_threads",
                          ["thread_id"], ["id"], ondelete="CASCADE")
    op.drop_column("agent_answer_ratings", "source")
