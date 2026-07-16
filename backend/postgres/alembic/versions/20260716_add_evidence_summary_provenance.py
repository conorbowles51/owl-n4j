"""add evidence summary provenance

Revision ID: 20260716_summary_provenance
Revises: 20260705_timeline_views
Create Date: 2026-07-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_summary_provenance"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evidence_files",
        sa.Column("summary_source", sa.String(length=16), server_default="ai", nullable=False),
    )
    op.add_column(
        "evidence_files",
        sa.Column("summary_edited_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "evidence_files",
        sa.Column("summary_edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE evidence_files SET summary_source = 'ai' WHERE summary_source IS NULL")


def downgrade() -> None:
    op.drop_column("evidence_files", "summary_edited_at")
    op.drop_column("evidence_files", "summary_edited_by")
    op.drop_column("evidence_files", "summary_source")
