"""Post-extraction entity consolidation step.

Runs between extraction (stage 3) and resolution (stage 4) to merge
duplicate entities that were extracted from overlapping chunks or
across multiple documents in a batch.

Pass 1 — Deterministic: exact normalized-name matches + alias cross-refs.
Pass 2 — LLM-assisted: present entities per category to GPT-4o to catch
          subtle variations invisible to mechanical matching.
"""

import json
import logging
import re
import unicodedata
from pathlib import Path

from app.config import settings
from app.ontology.schema_builder import get_consolidation_schema
from app.pipeline.extract_entities import RawEntity, RawRelationship
from app.pipeline.mandatory_rules import merge_mandatory_instructions, prepend_mandatory_rules
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Categories where multiple entities with the same name are legitimate
INSTANCE_CATEGORIES = {"Transaction", "Event", "Communication"}

_STRIP_PREFIXES = {
    "mr", "mrs", "ms", "dr", "prof", "sir", "lord", "lady",
    "rev", "sgt", "cpl", "lt", "capt", "maj", "col", "gen", "hon",
}


def _normalize(name: str) -> str:
    """Normalize name: lowercase, strip punctuation/titles, collapse whitespace."""
    name = unicodedata.normalize("NFKD", name)
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    tokens = name.split()
    if tokens and tokens[0] in _STRIP_PREFIXES:
        tokens = tokens[1:]
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Pass 1 — Deterministic consolidation
# ---------------------------------------------------------------------------

def _deterministic_consolidate(
    entities: list[RawEntity],
    relationships: list[RawRelationship],
) -> tuple[list[RawEntity], list[RawRelationship], dict[str, str], int]:
    """Merge entities with identical normalized names within the same category.
    Also cross-matches aliases against names.

    Returns (entities, relationships, id_remap, merge_count).
    """
    if not entities:
        return entities, relationships, {}, 0

    # Group by (category, normalized_name), skip instance categories
    groups: dict[tuple[str, str], list[int]] = {}
    for i, e in enumerate(entities):
        if e.category in INSTANCE_CATEGORIES:
            continue
        key = (e.category, _normalize(e.name))
        groups.setdefault(key, []).append(i)

    # Also build alias → entity index lookup
    alias_map: dict[tuple[str, str], list[int]] = {}
    for i, e in enumerate(entities):
        if e.category in INSTANCE_CATEGORIES:
            continue
        for alias in e.properties.get("aliases") or []:
            alias_key = (e.category, _normalize(str(alias)))
            alias_map.setdefault(alias_key, []).append(i)

    # Merge alias matches into groups
    for alias_key, alias_indices in alias_map.items():
        if alias_key in groups:
            existing = set(groups[alias_key])
            for idx in alias_indices:
                if idx not in existing:
                    groups[alias_key].append(idx)

    # Build merge sets using a simple union-find approach
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for indices in groups.values():
        if len(indices) > 1:
            for i in range(1, len(indices)):
                union(indices[0], indices[i])

    # Collect merge groups
    merge_groups: dict[int, list[int]] = {}
    for i in range(len(entities)):
        if i in parent:
            root = find(i)
            merge_groups.setdefault(root, []).append(i)

    # Apply merges
    id_remap: dict[str, str] = {}
    remove_indices: set[int] = set()

    for root, indices in merge_groups.items():
        if len(indices) <= 1:
            continue

        # Pick primary: highest confidence, most properties
        primary_idx = max(
            indices, key=lambda i: (entities[i].confidence, len(entities[i].properties))
        )
        primary = entities[primary_idx]

        all_names: set[str] = set()
        merged_props = dict(primary.properties)
        best_confidence = primary.confidence

        for idx in indices:
            e = entities[idx]
            id_remap[e.temp_id] = primary.temp_id
            all_names.add(e.name)
            best_confidence = max(best_confidence, e.confidence)
            for k, v in e.properties.items():
                if k not in merged_props or not merged_props[k]:
                    merged_props[k] = v
            for alias in e.properties.get("aliases") or []:
                all_names.add(str(alias))
            if idx != primary_idx:
                remove_indices.add(idx)

        all_names.discard(primary.name)
        existing_aliases = list(merged_props.get("aliases") or [])
        for name in sorted(all_names):
            if name not in existing_aliases:
                existing_aliases.append(name)
        if existing_aliases:
            merged_props["aliases"] = existing_aliases

        primary.properties = merged_props
        primary.confidence = best_confidence
        primary.mandatory_instructions = merge_mandatory_instructions(
            *[entities[idx].mandatory_instructions for idx in indices]
        )

    # Filter out merged entities
    kept_entities = [e for i, e in enumerate(entities) if i not in remove_indices]

    # Remap relationship IDs
    for r in relationships:
        r.source_entity_id = id_remap.get(r.source_entity_id, r.source_entity_id)
        r.target_entity_id = id_remap.get(r.target_entity_id, r.target_entity_id)

    merge_count = len(remove_indices)
    return kept_entities, relationships, id_remap, merge_count


# ---------------------------------------------------------------------------
# Pass 2 — LLM-assisted consolidation
# ---------------------------------------------------------------------------

async def _llm_consolidate(
    entities: list[RawEntity],
    relationships: list[RawRelationship],
) -> tuple[list[RawEntity], list[RawRelationship], int]:
    """Present entities per category to GPT-4o for consolidation.

    Returns (entities, relationships, merge_count).
    """
    if len(entities) < 2:
        return entities, relationships, 0

    template = (PROMPTS_DIR / "entity_consolidation.txt").read_text(encoding="utf-8")
    schema = get_consolidation_schema()

    # Group entity indices by category (skip instance categories)
    by_cat: dict[str, list[int]] = {}
    for i, e in enumerate(entities):
        if e.category in INSTANCE_CATEGORIES:
            continue
        by_cat.setdefault(e.category, []).append(i)

    id_remap: dict[str, str] = {}
    remove_indices: set[int] = set()
    total_merges = 0

    for category, indices in by_cat.items():
        if len(indices) < 2:
            continue

        # Build entity list for the LLM
        entity_list = []
        for local_idx, global_idx in enumerate(indices):
            e = entities[global_idx]
            entry = {
                "index": local_idx,
                "name": e.name,
                "category": e.category,
                "specific_type": e.specific_type,
                "source_file": e.source_file,
            }
            if e.mandatory_instructions:
                entry["mandatory_instructions"] = e.mandatory_instructions
            aliases = e.properties.get("aliases")
            if aliases:
                entry["aliases"] = aliases
            desc = e.properties.get("description")
            if desc:
                entry["description"] = desc
            entity_list.append(entry)

        entities_json = json.dumps(entity_list, indent=2)
        prompt = prepend_mandatory_rules(
            template.format(entities_json=entities_json),
            merge_mandatory_instructions(
                *[entities[global_idx].mandatory_instructions for global_idx in indices]
            ),
            title="MANDATORY PROFILE RULES FOR CONSOLIDATION",
        )

        try:
            response = await chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an entity consolidation expert. "
                            "Mandatory profile rules in the user prompt are binding. "
                            "Preserve rule-compliant naming and typing instead of normalizing outputs back to defaults. "
                            "Respond with valid JSON matching the provided schema."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                model=settings.openai_resolution_model,
                response_format=schema,
            )

            data = json.loads(response)
            groups = data.get("groups", [])

            for group in groups:
                local_indices = group.get("indices", [])
                canonical_name = group.get("canonical_name", "")

                if len(local_indices) < 2:
                    continue

                # Map local indices back to global indices
                global_indices = []
                for li in local_indices:
                    if 0 <= li < len(indices):
                        global_indices.append(indices[li])

                if len(global_indices) < 2:
                    continue

                # Pick primary
                primary_idx = max(
                    global_indices,
                    key=lambda i: (entities[i].confidence, len(entities[i].properties)),
                )
                primary = entities[primary_idx]

                # Use canonical name from LLM if provided
                if canonical_name:
                    if primary.name != canonical_name:
                        all_names = {primary.name, canonical_name}
                        primary.name = canonical_name
                    else:
                        all_names = set()
                else:
                    all_names = set()

                merged_props = dict(primary.properties)
                best_confidence = primary.confidence

                for idx in global_indices:
                    e = entities[idx]
                    id_remap[e.temp_id] = primary.temp_id
                    all_names.add(e.name)
                    best_confidence = max(best_confidence, e.confidence)
                    for k, v in e.properties.items():
                        if k not in merged_props or not merged_props[k]:
                            merged_props[k] = v
                    for alias in e.properties.get("aliases") or []:
                        all_names.add(str(alias))
                    if idx != primary_idx:
                        remove_indices.add(idx)

                all_names.discard(primary.name)
                existing_aliases = list(merged_props.get("aliases") or [])
                for name in sorted(all_names):
                    if name not in existing_aliases:
                        existing_aliases.append(name)
                if existing_aliases:
                    merged_props["aliases"] = existing_aliases

                primary.properties = merged_props
                primary.confidence = best_confidence
                primary.mandatory_instructions = merge_mandatory_instructions(
                    *[entities[idx].mandatory_instructions for idx in global_indices]
                )
                total_merges += len(global_indices) - 1

                logger.info(
                    "LLM consolidation merged %d %s entities → '%s' (%s)",
                    len(global_indices), category, primary.name,
                    group.get("reasoning", ""),
                )

        except Exception:
            logger.exception("LLM consolidation failed for category %s", category)
            continue

    # Filter out merged entities
    kept_entities = [e for i, e in enumerate(entities) if i not in remove_indices]

    # Remap relationship IDs
    for r in relationships:
        r.source_entity_id = id_remap.get(r.source_entity_id, r.source_entity_id)
        r.target_entity_id = id_remap.get(r.target_entity_id, r.target_entity_id)

    return kept_entities, relationships, total_merges


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def consolidate_entities(
    entities: list[RawEntity],
    relationships: list[RawRelationship],
) -> tuple[list[RawEntity], list[RawRelationship]]:
    """Two-pass entity consolidation: deterministic + LLM-assisted.

    Called between extraction (stage 3) and resolution (stage 4).
    Returns (consolidated_entities, consolidated_relationships).
    """
    if not entities:
        return entities, relationships

    initial_count = len(entities)

    # Pass 1: Deterministic
    entities, relationships, _, det_merges = _deterministic_consolidate(
        entities, relationships
    )
    if det_merges:
        logger.info(
            "Consolidation pass 1 (deterministic): merged %d entities (%d → %d)",
            det_merges, initial_count, len(entities),
        )

    # Pass 2: LLM-assisted
    entities, relationships, llm_merges = await _llm_consolidate(
        entities, relationships
    )
    if llm_merges:
        logger.info(
            "Consolidation pass 2 (LLM): merged %d entities (%d → %d)",
            llm_merges, initial_count - det_merges, len(entities),
        )

    total_merges = det_merges + llm_merges
    if total_merges:
        logger.info(
            "Consolidation complete: %d → %d entities (%d merged)",
            initial_count, len(entities), total_merges,
        )

    return entities, relationships
