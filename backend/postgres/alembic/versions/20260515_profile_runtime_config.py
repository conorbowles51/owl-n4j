"""store runtime profile configuration in postgres

Revision ID: 20260515_profile_runtime_config
Revises: 20260515_case_profiles
Create Date: 2026-05-15 14:05:00.000000

"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260515_profile_runtime_config"
down_revision: Union[str, None] = "20260515_case_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "processing_profiles",
        sa.Column("chat_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "processing_profiles",
        sa.Column("llm_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "processing_profiles",
        sa.Column("folder_processing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    _migrate_filesystem_runtime_profile_config()


def downgrade() -> None:
    op.drop_column("processing_profiles", "folder_processing")
    op.drop_column("processing_profiles", "llm_config")
    op.drop_column("processing_profiles", "chat_config")


def _migrate_filesystem_runtime_profile_config() -> None:
    """One-time import from legacy profile files into Postgres-backed profiles."""
    profiles_dir = Path(__file__).resolve().parents[4] / "profiles"
    if not profiles_dir.exists():
        return

    bind = op.get_bind()
    upsert = sa.text(
        """
        INSERT INTO processing_profiles (
            id,
            name,
            description,
            context_instructions,
            mandatory_instructions,
            special_entity_types,
            chat_config,
            llm_config,
            folder_processing
        )
        VALUES (
            CAST(:id AS uuid),
            :name,
            :description,
            :context_instructions,
            CAST(:mandatory_instructions AS jsonb),
            CAST(:special_entity_types AS jsonb),
            CAST(:chat_config AS jsonb),
            CAST(:llm_config AS jsonb),
            CAST(:folder_processing AS jsonb)
        )
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            context_instructions = EXCLUDED.context_instructions,
            mandatory_instructions = EXCLUDED.mandatory_instructions,
            special_entity_types = EXCLUDED.special_entity_types,
            chat_config = EXCLUDED.chat_config,
            llm_config = EXCLUDED.llm_config,
            folder_processing = EXCLUDED.folder_processing
        """
    )

    for profile_path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        name = str(data.get("name") or profile_path.stem).strip()
        if not name:
            continue

        ingestion = data.get("ingestion") or {}
        bind.execute(
            upsert,
            {
                "id": str(_uuid_from_name(name)),
                "name": name,
                "description": data.get("description"),
                "context_instructions": ingestion.get("system_context"),
                "mandatory_instructions": json.dumps(
                    _normalize_instruction_list(ingestion.get("mandatory_instructions"))
                ),
                "special_entity_types": json.dumps(
                    _normalize_special_entity_types(ingestion.get("special_entity_types"))
                ),
                "chat_config": _json_or_null(data.get("chat")),
                "llm_config": _json_or_null(data.get("llm_config")),
                "folder_processing": _json_or_null(data.get("folder_processing")),
            },
        )


def _json_or_null(value: object) -> str | None:
    if value in (None, {}, []):
        return None
    return json.dumps(value)


def _normalize_instruction_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        instruction = str(item or "").strip()
        if not instruction:
            continue
        key = instruction.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(instruction)
    return normalized


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
