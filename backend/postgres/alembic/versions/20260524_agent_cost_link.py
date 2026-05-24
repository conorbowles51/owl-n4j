"""link agent cost records to agent runs

Revision ID: 20260524_agent_cost_link
Revises: 20260524_agent_tables
Create Date: 2026-05-24 18:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260524_agent_cost_link"
down_revision: Union[str, None] = "20260524_agent_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cost_records",
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_cost_records_agent_run_id", "cost_records", ["agent_run_id"], unique=False)
    op.create_foreign_key(
        "fk_cost_records_agent_run_id_agent_runs",
        "cost_records",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE cost_records AS c
        SET agent_run_id = (c.extra_metadata ->> 'run_id')::uuid
        FROM agent_runs AS r
        WHERE c.job_type = 'ai_assistant'
          AND c.extra_metadata ->> 'agent' = 'true'
          AND c.extra_metadata ? 'run_id'
          AND c.extra_metadata ->> 'run_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
          AND r.id = (c.extra_metadata ->> 'run_id')::uuid
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_cost_records_agent_run_id_agent_runs", "cost_records", type_="foreignkey")
    op.drop_index("ix_cost_records_agent_run_id", table_name="cost_records")
    op.drop_column("cost_records", "agent_run_id")
