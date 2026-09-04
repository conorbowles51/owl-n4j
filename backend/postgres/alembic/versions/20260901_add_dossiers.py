"""evolve Case Profiles and Witnesses into Dossiers

Revision ID: 20260901_dossiers
Revises: 20260901_workspace_filters
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260901_dossiers"
down_revision: Union[str, None] = "20260901_workspace_filters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("case_profiles", sa.Column("canonical_entity_key", sa.String(512), nullable=True))
    op.add_column("case_profiles", sa.Column("linkage_state", sa.String(32), server_default="unlinked", nullable=False))
    op.add_column("case_profiles", sa.Column("status", sa.String(64), server_default="active", nullable=False))
    op.add_column("case_profiles", sa.Column("needs_link_review", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("case_profiles", sa.Column("graph_entity_deleted", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("case_profiles", sa.Column("legacy_source", sa.String(64), nullable=True))
    op.add_column("case_profiles", sa.Column("legacy_id", sa.String(128), nullable=True))
    op.create_index("ix_case_profiles_case_canonical_entity", "case_profiles", ["case_id", "canonical_entity_key"])

    op.create_table(
        "dossier_roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dossier_id", UUID, sa.ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("normalized_name", sa.String(128), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("template_key", sa.String(64), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("dossier_id", "normalized_name", name="uq_dossier_role_name"),
    )
    op.create_index("ix_dossier_roles_dossier_id", "dossier_roles", ["dossier_id"])
    op.create_index("ix_dossier_roles_case_id", "dossier_roles", ["case_id"])

    op.create_table(
        "dossier_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dossier_id", UUID, sa.ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(512), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=True),
        sa.Column("label", sa.String(512), nullable=True),
        sa.Column("source_anchor", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("dossier_id", "target_type", "target_id", name="uq_dossier_link_target"),
    )
    op.create_index("ix_dossier_links_dossier_id", "dossier_links", ["dossier_id"])
    op.create_index("ix_dossier_links_case_id", "dossier_links", ["case_id"])
    op.create_index("ix_dossier_links_case_target", "dossier_links", ["case_id", "target_type", "target_id"])

    op.create_table(
        "dossier_assessments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dossier_id", UUID, sa.ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=True),
        sa.Column("author_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("legacy_label", sa.String(128), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_dossier_assessments_dossier_id", "dossier_assessments", ["dossier_id"])
    op.create_index("ix_dossier_assessments_case_id", "dossier_assessments", ["case_id"])
    op.create_index("ix_dossier_assessments_case_dossier", "dossier_assessments", ["case_id", "dossier_id", "created_at"])

    op.create_table(
        "dossier_assessment_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("assessment_id", UUID, sa.ForeignKey("dossier_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(512), nullable=False),
        sa.Column("label", sa.String(512), nullable=True),
        sa.Column("source_anchor", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("assessment_id", "target_type", "target_id", name="uq_dossier_assessment_link"),
    )
    op.create_index("ix_dossier_assessment_links_assessment_id", "dossier_assessment_links", ["assessment_id"])
    op.create_index("ix_dossier_assessment_links_case_id", "dossier_assessment_links", ["case_id"])

    op.create_table(
        "dossier_media",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dossier_id", UUID, sa.ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", UUID, sa.ForeignKey("evidence_files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_cover", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("ordinal", sa.Integer(), server_default="0", nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("focal_x", sa.Float(), nullable=True),
        sa.Column("focal_y", sa.Float(), nullable=True),
        sa.Column("crop_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("source_anchor", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("dossier_id", "evidence_file_id", name="uq_dossier_media_evidence"),
    )
    op.create_index("ix_dossier_media_dossier_id", "dossier_media", ["dossier_id"])
    op.create_index("ix_dossier_media_case_id", "dossier_media", ["case_id"])
    op.create_index("ix_dossier_media_evidence_file_id", "dossier_media", ["evidence_file_id"])
    op.create_index("ix_dossier_media_dossier_order", "dossier_media", ["dossier_id", "ordinal"])
    op.create_index("uq_dossier_media_single_cover", "dossier_media", ["dossier_id"], unique=True, postgresql_where=sa.text("is_cover"))

    op.create_table(
        "dossier_interviews",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dossier_id", UUID, sa.ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interview_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participants", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("interviewer_user_ids", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", sa.String(64), server_default="planned", nullable=False),
        sa.Column("working_notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_dossier_interviews_dossier_id", "dossier_interviews", ["dossier_id"])
    op.create_index("ix_dossier_interviews_case_id", "dossier_interviews", ["case_id"])
    op.create_index("ix_dossier_interviews_dossier_date", "dossier_interviews", ["dossier_id", "interview_date"])

    op.create_table(
        "dossier_interview_evidence_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("interview_id", UUID, sa.ForeignKey("dossier_interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", UUID, sa.ForeignKey("evidence_files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_anchor", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("interview_id", "evidence_file_id", name="uq_dossier_interview_evidence"),
    )
    op.create_index("ix_dossier_interview_evidence_links_interview_id", "dossier_interview_evidence_links", ["interview_id"])
    op.create_index("ix_dossier_interview_evidence_links_case_id", "dossier_interview_evidence_links", ["case_id"])
    op.create_index("ix_dossier_interview_evidence_links_evidence_file_id", "dossier_interview_evidence_links", ["evidence_file_id"])

    op.create_table(
        "dossier_generated_outputs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dossier_id", UUID, sa.ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("output_type", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("review_status", sa.String(32), server_default="pending_review", nullable=False),
        sa.Column("generated_by_run_id", sa.String(128), nullable=True),
        sa.Column("reviewed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("dossier_id", "output_type", "version", name="uq_dossier_output_version"),
    )
    op.create_index("ix_dossier_generated_outputs_dossier_id", "dossier_generated_outputs", ["dossier_id"])
    op.create_index("ix_dossier_generated_outputs_case_id", "dossier_generated_outputs", ["case_id"])

    op.create_table(
        "dossier_legacy_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dossier_id", UUID, sa.ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("migration_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("case_id", "source_type", "source_id", name="uq_dossier_legacy_mapping"),
    )
    op.create_index("ix_dossier_legacy_mappings_case_id", "dossier_legacy_mappings", ["case_id"])
    op.create_index("ix_dossier_legacy_mappings_dossier_id", "dossier_legacy_mappings", ["dossier_id"])

    connection = op.get_bind()
    from services.dossier_migration import backfill_dossiers
    backfill_dossiers(connection)

    op.create_index(
        "uq_case_profiles_active_canonical_entity",
        "case_profiles",
        ["case_id", "canonical_entity_key"],
        unique=True,
        postgresql_where=sa.text("canonical_entity_key IS NOT NULL AND archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_case_profiles_active_canonical_entity", table_name="case_profiles")
    for table in (
        "dossier_legacy_mappings", "dossier_generated_outputs",
        "dossier_interview_evidence_links", "dossier_interviews", "dossier_media",
        "dossier_assessment_links", "dossier_assessments", "dossier_links", "dossier_roles",
    ):
        op.drop_table(table)
    op.drop_index("ix_case_profiles_case_canonical_entity", table_name="case_profiles")
    for column in (
        "legacy_id", "legacy_source", "graph_entity_deleted", "needs_link_review",
        "status", "linkage_state", "canonical_entity_key",
    ):
        op.drop_column("case_profiles", column)
