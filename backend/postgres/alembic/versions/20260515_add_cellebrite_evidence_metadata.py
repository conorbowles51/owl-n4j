"""add cellebrite evidence metadata columns

Revision ID: 20260515_cellebrite_evidence
Revises: 20260515_snapshot_logs
Create Date: 2026-05-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260515_cellebrite_evidence"
down_revision: Union[str, None] = "20260515_snapshot_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evidence_files", sa.Column("source_type", sa.String(64), nullable=True))
    op.add_column("evidence_files", sa.Column("cellebrite_report_key", sa.String(255), nullable=True))
    op.add_column("evidence_files", sa.Column("cellebrite_file_id", sa.String(255), nullable=True))
    op.add_column("evidence_files", sa.Column("cellebrite_model_id", sa.String(255), nullable=True))
    op.add_column("evidence_files", sa.Column("cellebrite_category", sa.String(64), nullable=True))
    op.add_column("evidence_files", sa.Column("tags", JSONB, server_default="[]", nullable=False))
    op.add_column("evidence_files", sa.Column("linked_entity_ids", JSONB, server_default="[]", nullable=False))

    op.create_index("ix_evidence_files_source_type", "evidence_files", ["source_type"])
    op.create_index("ix_evidence_files_case_source", "evidence_files", ["case_id", "source_type"])
    op.create_index(
        "ix_evidence_files_case_cellebrite_report",
        "evidence_files",
        ["case_id", "cellebrite_report_key"],
    )
    op.create_index(
        "ix_evidence_files_case_cellebrite_file",
        "evidence_files",
        ["case_id", "cellebrite_file_id"],
    )
    op.create_index(
        "ix_evidence_files_case_cellebrite_model",
        "evidence_files",
        ["case_id", "cellebrite_model_id"],
    )
    op.create_index(
        "ix_evidence_files_case_cellebrite_source_report",
        "evidence_files",
        ["case_id", "source_type", "cellebrite_report_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_files_case_cellebrite_source_report", table_name="evidence_files")
    op.drop_index("ix_evidence_files_case_cellebrite_model", table_name="evidence_files")
    op.drop_index("ix_evidence_files_case_cellebrite_file", table_name="evidence_files")
    op.drop_index("ix_evidence_files_case_cellebrite_report", table_name="evidence_files")
    op.drop_index("ix_evidence_files_case_source", table_name="evidence_files")
    op.drop_index("ix_evidence_files_source_type", table_name="evidence_files")

    op.drop_column("evidence_files", "linked_entity_ids")
    op.drop_column("evidence_files", "tags")
    op.drop_column("evidence_files", "cellebrite_category")
    op.drop_column("evidence_files", "cellebrite_model_id")
    op.drop_column("evidence_files", "cellebrite_file_id")
    op.drop_column("evidence_files", "cellebrite_report_key")
    op.drop_column("evidence_files", "source_type")
