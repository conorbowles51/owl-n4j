"""add chat persistence tables

Revision ID: 20260407_add_chat_tables
Revises: 20260407_add_geocoding_cache
Create Date: 2026-04-07 23:10:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260407_add_chat_tables"
down_revision: Union[str, None] = "20260407_add_geocoding_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("extra_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "revision_number", name="uq_case_revisions_case_revision"),
    )
    op.create_index("ix_case_revisions_case_id", "case_revisions", ["case_id"], unique=False)
    op.create_index("ix_case_revisions_created_by_user_id", "case_revisions", ["created_by_user_id"], unique=False)

    op.create_table(
        "chat_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_conversations_case_id", "chat_conversations", ["case_id"], unique=False)
    op.create_index("ix_chat_conversations_owner_user_id", "chat_conversations", ["owner_user_id"], unique=False)
    op.create_index("ix_chat_conversations_last_message_at", "chat_conversations", ["last_message_at"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_scope", sa.String(length=32), nullable=True),
        sa.Column("selected_entity_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_provider", sa.String(length=50), nullable=True),
        sa.Column("model_id", sa.String(length=100), nullable=True),
        sa.Column("cost_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_graph_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("case_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_revision_id"], ["case_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cost_record_id"], ["cost_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "sequence_number", name="uq_chat_messages_conversation_sequence"),
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"], unique=False)
    op.create_index("ix_chat_messages_model_id", "chat_messages", ["model_id"], unique=False)
    op.create_index("ix_chat_messages_cost_record_id", "chat_messages", ["cost_record_id"], unique=False)
    op.create_index("ix_chat_messages_case_revision_id", "chat_messages", ["case_revision_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_messages_case_revision_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_cost_record_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_model_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_chat_conversations_last_message_at", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_owner_user_id", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_case_id", table_name="chat_conversations")
    op.drop_table("chat_conversations")

    op.drop_index("ix_case_revisions_created_by_user_id", table_name="case_revisions")
    op.drop_index("ix_case_revisions_case_id", table_name="case_revisions")
    op.drop_table("case_revisions")
