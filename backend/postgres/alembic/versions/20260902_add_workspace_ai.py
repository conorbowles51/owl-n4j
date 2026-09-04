"""add durable reviewable workspace AI outputs

Revision ID: 20260902_workspace_ai
Revises: 20260902_workspace_attention
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260902_workspace_ai"
down_revision: Union[str, None] = "20260902_workspace_attention"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    connection = op.get_bind()
    existing_tables = set(sa.inspect(connection).get_table_names())
    has_output_rollback = "workspace_ai_outputs_rollback" in existing_tables
    has_assessment_rollback = "dossier_assessment_ai_provenance_rollback" in existing_tables
    op.create_table(
        "workspace_ai_outputs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", UUID, nullable=False),
        sa.Column("output_type", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_output_id", UUID, sa.ForeignKey("workspace_ai_outputs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("review_status", sa.String(32), server_default="pending_review", nullable=False),
        sa.Column("citation_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("content", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("citations", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_set", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("generation_input", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("proposed_actions", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("accepted_targets", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("model_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("mandate_version_id", UUID, sa.ForeignKey("case_mandate_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_type IN ('dossier', 'theory')", name="ck_workspace_ai_outputs_target_type"),
        sa.CheckConstraint("output_type IN ('statement_summary', 'statement_comparison', 'theory_analysis')", name="ck_workspace_ai_outputs_output_type"),
        sa.CheckConstraint("job_status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name="ck_workspace_ai_outputs_job_status"),
        sa.CheckConstraint("review_status IN ('pending_review', 'accepted', 'rejected')", name="ck_workspace_ai_outputs_review_status"),
        sa.CheckConstraint("citation_status IN ('pending', 'valid', 'invalid')", name="ck_workspace_ai_outputs_citation_status"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_workspace_ai_outputs_progress"),
        sa.UniqueConstraint("case_id", "target_type", "target_id", "output_type", "version", name="uq_workspace_ai_output_version"),
    )
    op.create_index("ix_workspace_ai_outputs_case_id", "workspace_ai_outputs", ["case_id"])
    op.create_index("ix_workspace_ai_outputs_mandate_version_id", "workspace_ai_outputs", ["mandate_version_id"])
    op.create_index("ix_workspace_ai_outputs_requested_by_user_id", "workspace_ai_outputs", ["requested_by_user_id"])
    op.create_index("ix_workspace_ai_outputs_case_target", "workspace_ai_outputs", ["case_id", "target_type", "target_id", "created_at"])
    op.create_index("ix_workspace_ai_outputs_case_status", "workspace_ai_outputs", ["case_id", "job_status", "review_status"])

    op.add_column(
        "dossier_assessments",
        sa.Column("provenance_type", sa.String(32), server_default="investigator", nullable=False),
    )
    op.add_column(
        "dossier_assessments",
        sa.Column("generated_output_id", UUID, nullable=True),
    )
    op.create_foreign_key(
        "fk_dossier_assessments_generated_output",
        "dossier_assessments",
        "workspace_ai_outputs",
        ["generated_output_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_dossier_assessments_generated_output_id", "dossier_assessments", ["generated_output_id"])

    if has_output_rollback:
        op.execute(
            """
            INSERT INTO workspace_ai_outputs
                (id, case_id, target_type, target_id, output_type, version,
                 parent_output_id, job_status, review_status, citation_status,
                 progress, cancel_requested, content, citations, source_set,
                 generation_input, proposed_actions, accepted_targets,
                 model_metadata, error_message, rejection_reason,
                 mandate_version_id, requested_by_user_id, reviewed_by_user_id,
                 started_at, completed_at, reviewed_at, created_at, updated_at)
            SELECT
                 id, case_id, target_type, target_id, output_type, version,
                 parent_output_id, job_status, review_status, citation_status,
                 progress, cancel_requested, content, citations, source_set,
                 generation_input, proposed_actions, accepted_targets,
                 model_metadata, error_message, rejection_reason,
                 mandate_version_id, requested_by_user_id, reviewed_by_user_id,
                 started_at, completed_at, reviewed_at, created_at, updated_at
            FROM workspace_ai_outputs_rollback
            """
        )
    if has_assessment_rollback:
        op.execute(
            """
            UPDATE dossier_assessments AS assessment
            SET provenance_type = archive.provenance_type,
                generated_output_id = archive.generated_output_id
            FROM dossier_assessment_ai_provenance_rollback AS archive
            WHERE assessment.id = archive.assessment_id
            """
        )
    if has_assessment_rollback:
        op.execute("DROP TABLE dossier_assessment_ai_provenance_rollback")
    if has_output_rollback:
        op.execute("DROP TABLE workspace_ai_outputs_rollback")


def downgrade() -> None:
    # A Phase 7 rollback must not destroy newly generated analysis or its
    # acceptance provenance. Archive both in ordinary PostgreSQL tables; the
    # next upgrade restores them before removing these rollback tables.
    op.execute("DROP TABLE IF EXISTS dossier_assessment_ai_provenance_rollback")
    op.execute("DROP TABLE IF EXISTS workspace_ai_outputs_rollback")
    op.execute(
        """
        CREATE TABLE workspace_ai_outputs_rollback AS
        SELECT * FROM workspace_ai_outputs
        """
    )
    op.execute(
        """
        CREATE TABLE dossier_assessment_ai_provenance_rollback AS
        SELECT id AS assessment_id, provenance_type, generated_output_id
        FROM dossier_assessments
        WHERE provenance_type <> 'investigator' OR generated_output_id IS NOT NULL
        """
    )
    op.drop_index("ix_dossier_assessments_generated_output_id", table_name="dossier_assessments")
    op.drop_constraint("fk_dossier_assessments_generated_output", "dossier_assessments", type_="foreignkey")
    op.drop_column("dossier_assessments", "generated_output_id")
    op.drop_column("dossier_assessments", "provenance_type")
    op.drop_table("workspace_ai_outputs")
