"""
Folder Context Service

Resolves effective processing profiles by walking the folder ancestor chain
and merging context instructions and profile overrides additively.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile
from services.evidence_db_storage import EvidenceDBStorage


def resolve_effective_profile(
    db: Session,
    folder_id: uuid.UUID,
    case_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Walk from folder_id up to root, collecting context_instructions
    and profile_overrides from each ancestor. Merge additively.

    Returns:
        {
            "chain": [{"folder_id", "folder_name", "context_instructions", "profile_overrides"}, ...],
            "merged_context": str,
            "merged_overrides": dict,
        }
    """
    # Get ancestor chain (root-first order)
    chain = EvidenceDBStorage.get_folder_breadcrumbs(db, folder_id)

    merged_context_parts: List[str] = []
    merged_overrides: Dict[str, Any] = {}
    chain_links: List[Dict[str, Any]] = []

    for folder in chain:
        link = {
            "folder_id": str(folder.id),
            "folder_name": folder.name,
            "context_instructions": folder.context_instructions,
            "profile_overrides": folder.profile_overrides,
        }
        chain_links.append(link)

        # Additive: append context instructions
        if folder.context_instructions:
            merged_context_parts.append(
                f"[{folder.name}]: {folder.context_instructions}"
            )

        # Additive merge for profile overrides
        if folder.profile_overrides:
            overrides = folder.profile_overrides
            # List values: append (union)
            if "special_entity_types" in overrides:
                existing = merged_overrides.get("special_entity_types", [])
                merged_overrides["special_entity_types"] = (
                    existing + overrides["special_entity_types"]
                )
            # Scalar values: child overrides parent
            for key in ("temperature", "system_context", "llm_profile"):
                if key in overrides:
                    merged_overrides[key] = overrides[key]

    return {
        "chain": chain_links,
        "merged_context": "\n\n".join(merged_context_parts),
        "merged_overrides": merged_overrides,
    }


def gather_sibling_files(
    db: Session,
    folder_id: Optional[uuid.UUID],
    exclude_file_id: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    """
    Return basic info about all files in the same folder for sibling awareness.
    """
    files = EvidenceDBStorage.list_files(db, case_id=None, folder_id=folder_id)

    # list_files requires case_id — use direct query instead
    from sqlalchemy import select

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
