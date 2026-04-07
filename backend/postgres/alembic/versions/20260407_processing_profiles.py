"""add processing profiles and stale evidence tracking

Revision ID: 20260407_processing_profiles
Revises: 20260322_evidence_summary
Create Date: 2026-04-07 12:30:00.000000

"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260407_processing_profiles"
down_revision: Union[str, None] = "20260322_evidence_summary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processing_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("context_instructions", sa.Text(), nullable=True),
        sa.Column("special_entity_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_processing_profiles_name"), "processing_profiles", ["name"], unique=True)

    op.create_table(
        "case_processing_configs",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_profile_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("context_instructions", sa.Text(), nullable=True),
        sa.Column("special_entity_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_profile_id"], ["processing_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index(op.f("ix_case_processing_configs_source_profile_id"), "case_processing_configs", ["source_profile_id"], unique=False)

    op.add_column("evidence_files", sa.Column("processing_stale", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("evidence_files", sa.Column("last_processed_profile_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("evidence_files", sa.Column("last_processed_folder_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_evidence_files_last_processed_folder_id",
        "evidence_files",
        "evidence_folders",
        ["last_processed_folder_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _migrate_filesystem_profiles()
    _normalize_folder_profiles()


def downgrade() -> None:
    op.drop_constraint("fk_evidence_files_last_processed_folder_id", "evidence_files", type_="foreignkey")
    op.drop_column("evidence_files", "last_processed_folder_id")
    op.drop_column("evidence_files", "last_processed_profile_snapshot")
    op.drop_column("evidence_files", "processing_stale")
    op.drop_index(op.f("ix_case_processing_configs_source_profile_id"), table_name="case_processing_configs")
    op.drop_table("case_processing_configs")
    op.drop_index(op.f("ix_processing_profiles_name"), table_name="processing_profiles")
    op.drop_table("processing_profiles")


def _migrate_filesystem_profiles() -> None:
    bind = op.get_bind()
    project_root = Path(__file__).resolve().parents[4]
    profiles_dir = project_root / "profiles"
    if not profiles_dir.exists():
        return

    processing_profiles = sa.table(
        "processing_profiles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("context_instructions", sa.Text),
        sa.column("special_entity_types", postgresql.JSONB),
    )

    rows = []
    for profile_path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        ingestion = data.get("ingestion") or {}
        name = str(data.get("name") or profile_path.stem).strip()
        if not name:
            continue

        rows.append(
            {
                "id": _uuid_from_name(name),
                "name": name,
                "description": data.get("description"),
                "context_instructions": ingestion.get("system_context"),
                "special_entity_types": _normalize_special_entity_types(ingestion.get("special_entity_types")),
            }
        )

    if rows:
        op.bulk_insert(processing_profiles, rows)


def _normalize_folder_profiles() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, context_instructions, profile_overrides "
            "FROM evidence_folders "
            "WHERE context_instructions IS NOT NULL OR profile_overrides IS NOT NULL"
        )
    ).mappings().all()

    for row in rows:
        overrides = row["profile_overrides"] or {}
        extra_context = overrides.get("system_context")
        merged_context = row["context_instructions"]
        if extra_context:
            merged_context = "\n\n".join(
                part for part in [merged_context, str(extra_context).strip()] if part
            ) or None

        normalized_overrides = {}
        special_entity_types = _normalize_special_entity_types(overrides.get("special_entity_types"))
        if special_entity_types:
            normalized_overrides["special_entity_types"] = special_entity_types

        bind.execute(
            sa.text(
                "UPDATE evidence_folders "
                "SET context_instructions = :context_instructions, profile_overrides = :profile_overrides "
                "WHERE id = :folder_id"
            ),
            {
                "folder_id": row["id"],
                "context_instructions": merged_context,
                "profile_overrides": json.dumps(normalized_overrides) if normalized_overrides else None,
            },
        )


def _normalize_special_entity_types(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        normalized_item = {"name": name}
        description = str(item.get("description", "")).strip()
        if description:
            normalized_item["description"] = description
        normalized.append(normalized_item)
    return normalized


def _uuid_from_name(name: str):
    import uuid

    return uuid.uuid5(uuid.NAMESPACE_DNS, f"processing-profile:{name.lower()}")
