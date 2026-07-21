"""add canonical evidence document text storage

Revision ID: 20260721_evidence_document_texts
Revises: 20260717_case_status, 20260719_significant_entities
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260721_evidence_document_texts"
down_revision: Union[str, Sequence[str], None] = (
    "20260717_case_status",
    "20260719_significant_entities",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "evidence_document_texts",
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engine_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("character_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_locations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evidence_file_id"],
            ["evidence_files.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("evidence_file_id"),
    )
    op.execute(
        "CREATE INDEX ix_evidence_document_texts_content_trgm "
        "ON evidence_document_texts USING gin (lower(content) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_evidence_document_texts_content_trgm")
    op.drop_table("evidence_document_texts")
