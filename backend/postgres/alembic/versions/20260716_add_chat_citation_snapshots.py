"""add chat citation snapshots

Revision ID: 20260716_chat_citation_snapshots
Revises: 20260705_timeline_views
Create Date: 2026-07-16 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260716_chat_citation_snapshots"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_citation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assistant_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.String(length=50), nullable=True),
        sa.Column("model_id", sa.String(length=100), nullable=True),
        sa.Column("context_scope", sa.String(length=32), nullable=True),
        sa.Column("selected_entity_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("context_text", sa.Text(), nullable=True),
        sa.Column("final_prompt", sa.Text(), nullable=True),
        sa.Column("retrieval_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("answer_citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_revision_id"], ["case_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_citation_snapshots_case_id", "chat_citation_snapshots", ["case_id"], unique=False)
    op.create_index("ix_chat_citation_snapshots_conversation_id", "chat_citation_snapshots", ["conversation_id"], unique=False)
    op.create_index("ix_chat_citation_snapshots_assistant_message_id", "chat_citation_snapshots", ["assistant_message_id"], unique=False)
    op.create_index("ix_chat_citation_snapshots_created_by_user_id", "chat_citation_snapshots", ["created_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_citation_snapshots_created_by_user_id", table_name="chat_citation_snapshots")
    op.drop_index("ix_chat_citation_snapshots_assistant_message_id", table_name="chat_citation_snapshots")
    op.drop_index("ix_chat_citation_snapshots_conversation_id", table_name="chat_citation_snapshots")
    op.drop_index("ix_chat_citation_snapshots_case_id", table_name="chat_citation_snapshots")
    op.drop_table("chat_citation_snapshots")
