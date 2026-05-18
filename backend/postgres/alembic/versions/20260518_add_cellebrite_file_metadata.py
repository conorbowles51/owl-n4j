"""add cellebrite file metadata columns

Revision ID: 20260518_cellebrite_meta
Revises: 20260515_profile_runtime_config
Create Date: 2026-05-18

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260518_cellebrite_meta"
down_revision: Union[str, None] = "20260515_profile_runtime_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evidence_files", sa.Column("capture_time", sa.String(64), nullable=True))
    op.add_column("evidence_files", sa.Column("creation_time", sa.String(64), nullable=True))
    op.add_column("evidence_files", sa.Column("modify_time", sa.String(64), nullable=True))
    op.add_column("evidence_files", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("evidence_files", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column(
        "evidence_files",
        sa.Column("has_geotag", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "ix_evidence_files_case_cellebrite_capture",
        "evidence_files",
        ["case_id", "source_type", "capture_time"],
    )
    op.create_index(
        "ix_evidence_files_case_cellebrite_geotag",
        "evidence_files",
        ["case_id", "source_type", "has_geotag"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_files_case_cellebrite_geotag", table_name="evidence_files")
    op.drop_index("ix_evidence_files_case_cellebrite_capture", table_name="evidence_files")
    op.drop_column("evidence_files", "has_geotag")
    op.drop_column("evidence_files", "longitude")
    op.drop_column("evidence_files", "latitude")
    op.drop_column("evidence_files", "modify_time")
    op.drop_column("evidence_files", "creation_time")
    op.drop_column("evidence_files", "capture_time")
