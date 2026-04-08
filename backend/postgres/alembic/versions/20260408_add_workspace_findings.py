"""add workspace findings table

Revision ID: 20260408_add_workspace_findings
Revises: 20260407_add_chat_tables, 20260324_add_entity_counts, 20260407_processing_profiles
Create Date: 2026-04-08 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260408_add_workspace_findings"
down_revision: Union[str, Sequence[str], None] = (
    "20260407_add_chat_tables",
    "20260324_add_entity_counts",
    "20260407_processing_profiles",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", sa.String(length=64), nullable=False),
        sa.Column("data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "finding_id", name="uq_workspace_findings_case_finding"),
    )
    op.create_index("ix_workspace_findings_case_id", "workspace_findings", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workspace_findings_case_id", table_name="workspace_findings")
    op.drop_table("workspace_findings")
