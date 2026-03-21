"""Create jobs table

Revision ID: 001
Revises:
Create Date: 2026-03-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.String(255), nullable=False, index=True),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "extracting_text",
                "chunking",
                "extracting_entities",
                "resolving_entities",
                "writing_graph",
                "completed",
                "failed",
                name="jobstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("progress", sa.Float, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("entity_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("relationship_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("llm_profile", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS jobstatus")
