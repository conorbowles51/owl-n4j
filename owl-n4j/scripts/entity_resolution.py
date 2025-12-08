"""
Entity Resolution module - handles entity matching and disambiguation.

Provides functions for:
- Key normalisation
- Exact key matching
- Fuzzy matching with LLM disambiguation
"""

import re
from typing import Optional, Dict, Tuple

from neo4j_client import Neo4jClient
from llm_client import disambiguate_entity


def normalise_key(raw: Optional[str]) -> str:
    """
    Normalise a string into a stable key for deduplication.

    Transformation:
    - Lowercase
    - Strip whitespace
    - Replace spaces with hyphens
    - Remove special characters except hyphens
    - Collapse multiple hyphens

    Examples:
        "John Smith" -> "john-smith"
        "Emerald Imports Ltd." -> "emerald-imports-ltd"
        "ACC-001" -> "acc-001"
    """
    if raw is None:
        return ""

    key = raw.strip().lower()

    # Replace spaces and underscores with hyphens
    key = re.sub(r"[\s_]+", "-", key)

    # Remove special characters except hyphens and alphanumerics
    key = re.sub(r"[^a-z0-9\-]", "", key)

    # Collapse multiple hyphens
    key = re.sub(r"-+", "-", key)

    # Strip leading/trailing hyphens
    key = key.strip("-")

    return key


def resolve_entity(
    candidate_key: str,
    candidate_name: str,
    candidate_type: str,
    candidate_notes: str,
    db: Neo4jClient,
) -> Tuple[str, bool]:
    """
    Resolve a candidate entity to an existing entity or confirm it's new.

    Resolution strategy:
    1. Try exact key match
    2. If no exact match, try fuzzy search
    3. If fuzzy matches found, use LLM to disambiguate

    Args:
        candidate_key: Normalised key for the candidate
        candidate_name: Name of the candidate entity
        candidate_type: Type of the candidate entity
        candidate_notes: Notes about the candidate from current document
        db: Neo4j client instance

    Returns:
        Tuple of (resolved_key, is_existing)
        - resolved_key: The key to use (might be existing entity's key)
        - is_existing: True if matched to existing entity
    """
    # Step 1: Exact key match
    existing = db.find_entity_by_key(candidate_key)
    if existing:
        print(f"  → Exact match found for '{candidate_key}'")
        return candidate_key, True

    # Step 2: Fuzzy search
    fuzzy_matches = db.fuzzy_search_entities(
        name=candidate_name,
        entity_type=candidate_type,
        limit=5,
    )

    if not fuzzy_matches:
        # No matches at all - this is a new entity
        print(f"  → No matches found for '{candidate_name}', creating new entity")
        return candidate_key, False

    # Step 3: LLM disambiguation for each fuzzy match
    print(f"  → Found {len(fuzzy_matches)} fuzzy match(es), disambiguating...")

    for match in fuzzy_matches:
        # Skip if it's the same key (shouldn't happen but safety check)
        if match.get("key") == candidate_key:
            return candidate_key, True

        try:
            is_same = disambiguate_entity(
                candidate_key=candidate_key,
                candidate_name=candidate_name,
                candidate_type=candidate_type,
                candidate_notes=candidate_notes,
                existing_entity=match,
            )

            if is_same:
                matched_key = match.get("key", candidate_key)
                print(f"  → LLM confirmed match: '{candidate_name}' = '{match.get('name')}'")
                return matched_key, True

        except Exception as e:
            print(f"  → Disambiguation error for {match.get('name')}: {e}")
            continue

    # No matches confirmed - this is a new entity
    print(f"  → No confirmed matches, creating new entity for '{candidate_name}'")
    return candidate_key, False


def merge_entity_data(
    existing_entity: Dict,
    new_notes: str,
    doc_name: str,
) -> Dict:
    """
    Merge new document observations into existing entity data.

    Args:
        existing_entity: Current entity data from database
        new_notes: New observations from current document
        doc_name: Name of the current document

    Returns:
        Dict with updated notes (ready for database update)
    """
    current_notes = existing_entity.get("notes", "") or ""

    # Check if this document already has notes
    doc_marker = f"[{doc_name}]"

    if doc_marker in current_notes:
        # Append to existing document section
        # Find the section and append
        parts = current_notes.split(doc_marker)
        if len(parts) >= 2:
            # Find end of this document's section (next doc marker or end)
            rest = parts[1]
            next_doc_start = rest.find("\n\n[")
            if next_doc_start == -1:
                # This is the last section, just append
                updated_notes = current_notes + f"\n{new_notes}"
            else:
                # Insert before next document section
                before_next = rest[:next_doc_start]
                after_next = rest[next_doc_start:]
                updated_notes = (
                    parts[0] + doc_marker + before_next +
                    f"\n{new_notes}" + after_next
                )
        else:
            updated_notes = current_notes + f"\n{new_notes}"
    else:
        # New document section
        new_section = f"\n\n[{doc_name}]\n{new_notes}"
        updated_notes = current_notes.strip() + new_section if current_notes.strip() else f"[{doc_name}]\n{new_notes}"

    return {"notes": updated_notes}
