"""add canonical typed Workspace entries

Revision ID: 20260901_workspace_entries
Revises: 20260807_deepseek
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from postgres.backfills.workspace_entries import backfill_workspace_entries


revision: str = "20260901_workspace_entries"
down_revision: Union[str, None] = "20260807_deepseek"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=True),
        sa.Column("significance", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("confidence_rationale", sa.Text(), nullable=True),
        sa.Column(
            "review_state",
            sa.String(length=16),
            server_default="accepted",
            nullable=False,
        ),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_email", sa.String(length=255), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_email", sa.String(length=255), nullable=True),
        sa.Column("updated_by_name", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_theory_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("legacy_source", sa.String(length=64), nullable=True),
        sa.Column("legacy_id", sa.String(length=255), nullable=True),
        sa.Column(
            "migration_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "needs_migration_review",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('note', 'finding', 'theory')",
            name="ck_workspace_entries_type",
        ),
        sa.CheckConstraint(
            "entry_type = 'note' OR needs_migration_review = true OR "
            "(title IS NOT NULL AND length(trim(title)) > 0)",
            name="ck_workspace_entries_required_title",
        ),
        sa.CheckConstraint(
            "lifecycle_state IS NULL OR lifecycle_state IN "
            "('draft', 'active', 'superseded', 'withdrawn', 'proposed', "
            "'investigating', 'substantiated', 'weakened', 'rejected', 'converted')",
            name="ck_workspace_entries_lifecycle",
        ),
        sa.CheckConstraint(
            "significance IS NULL OR significance IN ('high', 'medium', 'low')",
            name="ck_workspace_entries_significance",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_workspace_entries_confidence",
        ),
        sa.CheckConstraint(
            "review_state IN ('accepted', 'pending', 'rejected')",
            name="ck_workspace_entries_review_state",
        ),
        sa.CheckConstraint(
            "(entry_type = 'note' AND lifecycle_state IS NULL AND significance IS NULL "
            "AND confidence IS NULL) OR "
            "(entry_type = 'finding' AND lifecycle_state IN "
            "('draft', 'active', 'superseded', 'withdrawn') AND confidence IS NULL "
            "AND (significance IS NOT NULL OR needs_migration_review = true)) OR "
            "(entry_type = 'theory' AND lifecycle_state IN "
            "('proposed', 'investigating', 'substantiated', 'weakened', 'rejected', "
            "'converted') AND significance IS NULL)",
            name="ck_workspace_entries_type_specific_fields",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_theory_entry_id"], ["workspace_entries.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id",
            "legacy_source",
            "legacy_id",
            name="uq_workspace_entries_legacy_identity",
        ),
    )
    op.create_index("ix_workspace_entries_case_id", "workspace_entries", ["case_id"])
    op.create_index("ix_workspace_entries_deleted_at", "workspace_entries", ["deleted_at"])
    op.create_index(
        "ix_workspace_entries_case_type_state",
        "workspace_entries",
        ["case_id", "entry_type", "lifecycle_state"],
    )
    op.create_index(
        "ix_workspace_entries_case_updated",
        "workspace_entries",
        ["case_id", "updated_at"],
    )
    op.create_index(
        "ix_workspace_entries_case_author",
        "workspace_entries",
        ["case_id", "author_user_id"],
    )
    op.create_index(
        "ix_workspace_entries_case_deleted",
        "workspace_entries",
        ["case_id", "deleted_at"],
    )
    op.create_index(
        "ix_workspace_entries_source_theory",
        "workspace_entries",
        ["source_theory_entry_id"],
    )

    op.create_table(
        "workspace_entry_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=True),
        sa.Column("significance", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("confidence_rationale", sa.Text(), nullable=True),
        sa.Column("review_state", sa.String(length=16), nullable=False),
        sa.Column("editor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("editor_email", sa.String(length=255), nullable=True),
        sa.Column("editor_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["editor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entry_id"], ["workspace_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entry_id", "revision_number", name="uq_workspace_entry_revision_number"
        ),
    )
    op.create_index("ix_workspace_entry_revisions_entry_id", "workspace_entry_revisions", ["entry_id"])
    op.create_index("ix_workspace_entry_revisions_case_id", "workspace_entry_revisions", ["case_id"])
    op.create_index(
        "ix_workspace_entry_revisions_case_entry",
        "workspace_entry_revisions",
        ["case_id", "entry_id"],
    )

    op.create_table(
        "workspace_entry_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=512), nullable=False),
        sa.Column("target_label", sa.String(length=512), nullable=True),
        sa.Column(
            "relationship",
            sa.String(length=16),
            server_default="unclassified",
            nullable=False,
        ),
        sa.Column(
            "source_anchor",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relationship IN ('unclassified', 'supports', 'contradicts', 'context')",
            name="ck_workspace_entry_links_relationship",
        ),
        sa.CheckConstraint(
            "target_type IN ('evidence', 'graph_entity', 'dossier', 'entry', 'task', "
            "'deadline', 'timeline_event', 'agent_artifact', 'witness')",
            name="ck_workspace_entry_links_target_type",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entry_id"], ["workspace_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entry_id", "target_type", "target_id", name="uq_workspace_entry_link_target"
        ),
    )
    op.create_index("ix_workspace_entry_links_entry_id", "workspace_entry_links", ["entry_id"])
    op.create_index("ix_workspace_entry_links_case_id", "workspace_entry_links", ["case_id"])
    op.create_index(
        "ix_workspace_entry_links_case_target",
        "workspace_entry_links",
        ["case_id", "target_type", "target_id"],
    )

    op.create_table(
        "workspace_entry_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "before_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "after_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'updated', 'lifecycle_changed', "
            "'confidence_changed', 'converted', 'deleted', 'restored', 'review_changed', "
            "'migrated', 'link_added', 'link_updated', 'link_removed')",
            name="ck_workspace_entry_events_type",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entry_id"], ["workspace_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_entry_events_entry_id", "workspace_entry_events", ["entry_id"])
    op.create_index("ix_workspace_entry_events_case_id", "workspace_entry_events", ["case_id"])
    op.create_index(
        "ix_workspace_entry_events_case_entry",
        "workspace_entry_events",
        ["case_id", "entry_id"],
    )
    op.create_index(
        "ix_workspace_entry_events_case_created",
        "workspace_entry_events",
        ["case_id", "created_at"],
    )

    op.create_table(
        "workspace_legacy_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=512), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=512), nullable=False),
        sa.Column(
            "migration_state",
            sa.String(length=32),
            server_default="migrated",
            nullable=False,
        ),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id",
            "source_type",
            "source_id",
            "target_type",
            name="uq_workspace_legacy_mapping_source",
        ),
    )
    op.create_index("ix_workspace_legacy_mappings_case_id", "workspace_legacy_mappings", ["case_id"])
    op.create_index(
        "ix_workspace_legacy_mapping_target",
        "workspace_legacy_mappings",
        ["case_id", "target_type", "target_id"],
    )

    op.add_column(
        "case_profile_note_links",
        sa.Column("workspace_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_case_profile_note_links_workspace_entry",
        "case_profile_note_links",
        "workspace_entries",
        ["workspace_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_case_profile_note_links_workspace_entry_id",
        "case_profile_note_links",
        ["workspace_entry_id"],
    )
    op.add_column(
        "case_profile_finding_links",
        sa.Column("workspace_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_case_profile_finding_links_workspace_entry",
        "case_profile_finding_links",
        "workspace_entries",
        ["workspace_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_case_profile_finding_links_workspace_entry_id",
        "case_profile_finding_links",
        ["workspace_entry_id"],
    )

    report = backfill_workspace_entries(op.get_bind())
    print("Workspace entry backfill: " + json.dumps(report["summary"], sort_keys=True))


def downgrade() -> None:
    op.drop_index(
        "ix_case_profile_finding_links_workspace_entry_id",
        table_name="case_profile_finding_links",
    )
    op.drop_constraint(
        "fk_case_profile_finding_links_workspace_entry",
        "case_profile_finding_links",
        type_="foreignkey",
    )
    op.drop_column("case_profile_finding_links", "workspace_entry_id")
    op.drop_index(
        "ix_case_profile_note_links_workspace_entry_id",
        table_name="case_profile_note_links",
    )
    op.drop_constraint(
        "fk_case_profile_note_links_workspace_entry",
        "case_profile_note_links",
        type_="foreignkey",
    )
    op.drop_column("case_profile_note_links", "workspace_entry_id")

    op.drop_index("ix_workspace_legacy_mapping_target", table_name="workspace_legacy_mappings")
    op.drop_index("ix_workspace_legacy_mappings_case_id", table_name="workspace_legacy_mappings")
    op.drop_table("workspace_legacy_mappings")
    op.drop_index("ix_workspace_entry_events_case_created", table_name="workspace_entry_events")
    op.drop_index("ix_workspace_entry_events_case_entry", table_name="workspace_entry_events")
    op.drop_index("ix_workspace_entry_events_case_id", table_name="workspace_entry_events")
    op.drop_index("ix_workspace_entry_events_entry_id", table_name="workspace_entry_events")
    op.drop_table("workspace_entry_events")
    op.drop_index("ix_workspace_entry_links_case_target", table_name="workspace_entry_links")
    op.drop_index("ix_workspace_entry_links_case_id", table_name="workspace_entry_links")
    op.drop_index("ix_workspace_entry_links_entry_id", table_name="workspace_entry_links")
    op.drop_table("workspace_entry_links")
    op.drop_index("ix_workspace_entry_revisions_case_entry", table_name="workspace_entry_revisions")
    op.drop_index("ix_workspace_entry_revisions_case_id", table_name="workspace_entry_revisions")
    op.drop_index("ix_workspace_entry_revisions_entry_id", table_name="workspace_entry_revisions")
    op.drop_table("workspace_entry_revisions")
    op.drop_index("ix_workspace_entries_source_theory", table_name="workspace_entries")
    op.drop_index("ix_workspace_entries_case_deleted", table_name="workspace_entries")
    op.drop_index("ix_workspace_entries_case_author", table_name="workspace_entries")
    op.drop_index("ix_workspace_entries_case_updated", table_name="workspace_entries")
    op.drop_index("ix_workspace_entries_case_type_state", table_name="workspace_entries")
    op.drop_index("ix_workspace_entries_deleted_at", table_name="workspace_entries")
    op.drop_index("ix_workspace_entries_case_id", table_name="workspace_entries")
    op.drop_table("workspace_entries")
