"""add mandatory instruction lists to processing profiles and jobs

Revision ID: 20260407_instruction_lists
Revises: 20260407_jobs_schema_merge
Create Date: 2026-04-07 20:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260407_instruction_lists"
down_revision: Union[str, None] = "20260407_jobs_schema_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "processing_profiles",
        sa.Column(
            "mandatory_instructions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "case_processing_configs",
        sa.Column(
            "mandatory_instructions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "evidence_folders",
        sa.Column(
            "mandatory_instructions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.execute(
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS effective_mandatory_instructions JSONB NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS effective_mandatory_instructions")
    op.drop_column("evidence_folders", "mandatory_instructions")
    op.drop_column("case_processing_configs", "mandatory_instructions")
    op.drop_column("processing_profiles", "mandatory_instructions")
