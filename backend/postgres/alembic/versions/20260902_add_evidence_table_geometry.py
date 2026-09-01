"""add durable per-page table geometry storage

Revision ID: 20260902_evidence_table_geometry
Revises: 20260901_admit_financial_document
Create Date: 2026-09-02

The engine's PDF extraction builds per-table cell geometry (the ``per_table``
list: one entry per extracted table, each carrying the table's own rectangle
and a locator for every cell value) and until now dropped it: the quality
report keeps only the summary counts, and job metadata is never persisted.
This table is where that geometry survives, bounded per page so a single
statement covering a busy year does not become one unbounded JSONB value.

One row per (evidence file, page). ``payload`` holds the geometry-bearing
``per_table`` entries whose table landed on that page, in extraction order.
Entries without geometry carry no page and nothing drawable, so they have no
row here; their absence is already counted by the extraction quality report.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260902_evidence_table_geometry"
down_revision: Union[str, Sequence[str], None] = "20260901_admit_financial_document"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_table_geometry",
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("engine_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "payload",
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
        sa.CheckConstraint("page_number >= 1", name="ck_evidence_table_geometry_page"),
        sa.ForeignKeyConstraint(
            ["evidence_file_id"],
            ["evidence_files.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("evidence_file_id", "page_number"),
    )


def downgrade() -> None:
    op.drop_table("evidence_table_geometry")
