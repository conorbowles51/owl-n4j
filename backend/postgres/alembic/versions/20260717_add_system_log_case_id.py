"""add system log case id

Revision ID: 20260717_system_log_case_id
Revises: 20260705_timeline_views
Create Date: 2026-07-17 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_system_log_case_id"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("system_logs", sa.Column("case_id", sa.String(length=64), nullable=True))

    dialect_name = op.get_bind().dialect.name
    if dialect_name == "postgresql":
        op.execute(
            """
            UPDATE system_logs
            SET case_id = details ->> 'case_id'
            WHERE case_id IS NULL
              AND details ? 'case_id'
              AND NULLIF(details ->> 'case_id', '') IS NOT NULL
            """
        )
    elif dialect_name == "sqlite":
        op.execute(
            """
            UPDATE system_logs
            SET case_id = json_extract(details, '$.case_id')
            WHERE case_id IS NULL
              AND NULLIF(json_extract(details, '$.case_id'), '') IS NOT NULL
            """
        )

    op.create_index("ix_system_logs_case_timestamp", "system_logs", ["case_id", "timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_logs_case_timestamp", table_name="system_logs")
    op.drop_column("system_logs", "case_id")
