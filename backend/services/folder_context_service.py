"""
Folder Context Service

Resolves effective processing profiles by combining the case base processing
profile snapshot with additive folder-local instructions and overrides.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile, EvidenceFolder
from services.evidence_db_storage import EvidenceDBStorage
from services.processing_profile_service import (
    get_case_processing_config,
    merge_instruction_lists,
    merge_special_entity_types,
    normalize_instruction_list,
    normalize_special_entity_types,
)


def _format_chain_context(label: str, context_instructions: str | None) -> str | None:
    if not context_instructions:
        return None
    return f"[{label}]\n{context_instructions.strip()}"


def get_folder_chain(db: Session, folder_id: uuid.UUID | None) -> list[EvidenceFolder]:
    if folder_id is None:
        return []

    current = EvidenceDBStorage.get_folder(db, folder_id)
    if current is None:
        return []

    chain: list[EvidenceFolder] = [current]
    while current.parent_id:
        current = EvidenceDBStorage.get_folder(db, current.parent_id)
        if current is None:
            break
        chain.append(current)
    chain.reverse()
    return chain


def resolve_effective_profile(
    db: Session,
    folder_id: uuid.UUID | None,
    case_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Resolve the effective processing profile for a folder.

    Merge order:
    1. Case processing config snapshot
    2. Folder chain root -> leaf
    """
    case_config = get_case_processing_config(db, case_id)
    folder_chain = get_folder_chain(db, folder_id)

    chain_links: list[dict[str, Any]] = []
    merged_context_parts: list[str] = []
    merged_mandatory_instructions: list[str] = []
    merged_special_entity_types: list[dict[str, str]] = []

    if case_config is not None:
        chain_links.append(
            {
                "scope": "case",
                "folder_id": None,
                "folder_name": "Case Base Profile",
                "context_instructions": case_config.context_instructions,
                "mandatory_instructions": normalize_instruction_list(
                    case_config.mandatory_instructions
                ),
                "profile_overrides": {
                    "special_entity_types": normalize_special_entity_types(
                        case_config.special_entity_types
                    )
                }
                if case_config.special_entity_types
                else None,
                "source_profile_name": case_config.source_profile_name_snapshot,
            }
        )
        context_block = _format_chain_context("Case Base Profile", case_config.context_instructions)
        if context_block:
            merged_context_parts.append(context_block)
        merged_mandatory_instructions = merge_instruction_lists(
            merged_mandatory_instructions,
            case_config.mandatory_instructions,
        )
        merged_special_entity_types = merge_special_entity_types(
            merged_special_entity_types,
            case_config.special_entity_types,
        )

    for folder in folder_chain:
        overrides = folder.profile_overrides or {}
        normalized_overrides: dict[str, Any] | None = None
        mandatory_instructions = normalize_instruction_list(folder.mandatory_instructions)
        special_entity_types = normalize_special_entity_types(
            overrides.get("special_entity_types")
        )
        if special_entity_types:
            normalized_overrides = {"special_entity_types": special_entity_types}

        chain_links.append(
            {
                "scope": "folder",
                "folder_id": str(folder.id),
                "folder_name": folder.name,
                "context_instructions": folder.context_instructions,
                "mandatory_instructions": mandatory_instructions,
                "profile_overrides": normalized_overrides,
            }
        )

        context_block = _format_chain_context(folder.name, folder.context_instructions)
        if context_block:
            merged_context_parts.append(context_block)
        merged_mandatory_instructions = merge_instruction_lists(
            merged_mandatory_instructions,
            mandatory_instructions,
        )
        merged_special_entity_types = merge_special_entity_types(
            merged_special_entity_types,
            special_entity_types,
        )

    effective_context = "\n\n".join(merged_context_parts)

    return {
        "chain": chain_links,
        "effective_context": effective_context,
        "effective_mandatory_instructions": merged_mandatory_instructions,
        "effective_special_entity_types": merged_special_entity_types,
        # Backward-compatible aliases for existing callers.
        "merged_context": effective_context,
        "merged_overrides": {
            "special_entity_types": merged_special_entity_types,
        },
    }


def build_processing_snapshot(
    db: Session,
    *,
    case_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    file_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    effective = resolve_effective_profile(db, folder_id, case_id)
    sibling_files = gather_sibling_files(db, folder_id, exclude_file_id=file_id)
    return {
        "source_folder_id": str(folder_id) if folder_id else None,
        "effective_context": effective["effective_context"],
        "effective_mandatory_instructions": effective["effective_mandatory_instructions"],
        "effective_special_entity_types": effective["effective_special_entity_types"],
        "sibling_files": sibling_files,
        "chain": effective["chain"],
    }


def gather_sibling_files(
    db: Session,
    folder_id: uuid.UUID | None,
    exclude_file_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """
    Return basic info about all files in the same folder for sibling awareness.
    """
    conditions = [EvidenceFile.folder_id == folder_id] if folder_id else [EvidenceFile.folder_id.is_(None)]
    if exclude_file_id:
        conditions.append(EvidenceFile.id != exclude_file_id)

    result = db.scalars(
        select(EvidenceFile).where(*conditions).order_by(EvidenceFile.original_filename)
    ).all()

    import mimetypes

    return [
        {
            "name": f.original_filename,
            "mime_type": mimetypes.guess_type(f.original_filename)[0] or "application/octet-stream",
            "size": f.size,
        }
        for f in result
    ]
