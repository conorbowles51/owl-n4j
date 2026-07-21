"""add workflow status to cases

Revision ID: 20260717_case_status
Revises: 20260705_timeline_views
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_case_status"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
    )
    op.create_check_constraint(
        "ck_cases_status",
        "cases",
        "status IN ('active', 'on_hold', 'closed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cases_status", "cases", type_="check")
    op.drop_column("cases", "status")
