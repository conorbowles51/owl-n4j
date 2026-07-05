"""add case notebook tables

Revision ID: 20260705_notebook_tables
Revises: 20260607_audio_transcriptions
Create Date: 2026-07-05 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260705_notebook_tables"
down_revision: Union[str, None] = "20260607_audio_transcriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notebook_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_email", sa.String(length=255), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("visibility", sa.String(length=32), server_default="case", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notebook_notes_case_id", "notebook_notes", ["case_id"], unique=False)
    op.create_index("ix_notebook_notes_author_user_id", "notebook_notes", ["author_user_id"], unique=False)
    op.create_index("ix_notebook_notes_deleted_at", "notebook_notes", ["deleted_at"], unique=False)
    op.create_index("ix_notebook_notes_case_updated", "notebook_notes", ["case_id", "updated_at"], unique=False)
    op.create_index("ix_notebook_notes_author_case", "notebook_notes", ["author_user_id", "case_id"], unique=False)

    op.create_table(
        "notebook_note_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=512), nullable=False),
        sa.Column("target_label", sa.String(length=512), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["notebook_notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id", "target_type", "target_id", name="uq_notebook_note_target"),
    )
    op.create_index("ix_notebook_note_links_note_id", "notebook_note_links", ["note_id"], unique=False)
    op.create_index("ix_notebook_note_links_case_id", "notebook_note_links", ["case_id"], unique=False)
    op.create_index(
        "ix_notebook_links_case_target",
        "notebook_note_links",
        ["case_id", "target_type", "target_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notebook_links_case_target", table_name="notebook_note_links")
    op.drop_index("ix_notebook_note_links_case_id", table_name="notebook_note_links")
    op.drop_index("ix_notebook_note_links_note_id", table_name="notebook_note_links")
    op.drop_table("notebook_note_links")

    op.drop_index("ix_notebook_notes_author_case", table_name="notebook_notes")
    op.drop_index("ix_notebook_notes_case_updated", table_name="notebook_notes")
    op.drop_index("ix_notebook_notes_deleted_at", table_name="notebook_notes")
    op.drop_index("ix_notebook_notes_author_user_id", table_name="notebook_notes")
    op.drop_index("ix_notebook_notes_case_id", table_name="notebook_notes")
    op.drop_table("notebook_notes")
