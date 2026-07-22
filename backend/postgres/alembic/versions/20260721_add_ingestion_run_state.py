"""add durable evidence ingestion run state

Revision ID: 20260721_ingestion_state
Revises: 20260721_evidence_document_texts
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260721_ingestion_state"
down_revision: Union[str, Sequence[str], None] = "20260721_evidence_document_texts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "pipeline_version",
            sa.String(length=64),
            server_default="evidence-v2",
            nullable=False,
        ),
    )
    op.create_table(
        "evidence_claims",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", sa.String(length=64), nullable=False),
        sa.Column("engine_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("predicate", sa.String(length=255), nullable=False),
        sa.Column("object_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("source_location", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="grounded", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_file_id"], ["evidence_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["engine_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_claims_case_id", "evidence_claims", ["case_id"])
    op.create_index("ix_evidence_claims_evidence_file_id", "evidence_claims", ["evidence_file_id"])
    op.create_index("ix_evidence_claims_revision_id", "evidence_claims", ["revision_id"])
    op.add_column(
        "jobs",
        sa.Column(
            "pipeline_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "quality_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_claims_revision_id", table_name="evidence_claims")
    op.drop_index("ix_evidence_claims_evidence_file_id", table_name="evidence_claims")
    op.drop_index("ix_evidence_claims_case_id", table_name="evidence_claims")
    op.drop_table("evidence_claims")
    op.drop_column("jobs", "quality_report")
    op.drop_column("jobs", "pipeline_state")
    op.drop_column("jobs", "pipeline_version")
