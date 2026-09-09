"""expand investigator importance summary

Revision ID: 20260901_dossier_importance
Revises: 20260901_dossiers
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260901_dossier_importance"
down_revision: Union[str, None] = "20260901_dossiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "case_profiles", "importance",
        existing_type=sa.String(length=32), type_=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    connection = op.get_bind()
    overlong = connection.scalar(sa.text("SELECT count(*) FROM case_profiles WHERE length(importance) > 32"))
    if overlong:
        raise RuntimeError("Cannot safely downgrade: Dossier importance values exceed 32 characters")
    op.alter_column(
        "case_profiles", "importance",
        existing_type=sa.String(length=255), type_=sa.String(length=32),
        existing_nullable=True,
    )
