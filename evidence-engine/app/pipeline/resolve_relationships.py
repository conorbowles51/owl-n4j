"""Relationship deduplication — merges duplicate and near-duplicate relationships."""

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import settings
from app.ontology.schema_builder import get_relationship_resolution_schema
from app.pipeline.mandatory_rules import merge_mandatory_instructions, prepend_mandatory_rules
from app.pipeline.resolve_entities import ResolvedRelationship
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _normalize_type(rel_type: str) -> str:
    return "".join(
        c if c.isalnum() or c == "_" else "_" for c in rel_type.upper()
    ).strip("_")


def _group_key(rel: ResolvedRelationship) -> tuple[str, str, str]:
    """Canonical grouping key: entity pair + normalized type."""
    return (rel.source_entity_id, rel.target_entity_id, _normalize_type(rel.type))


def _merge_group(rels: list[ResolvedRelationship]) -> ResolvedRelationship:
    """Merge a group of relationships with identical key into one."""
    all_quotes: list[str] = []
    all_files: set[str] = set()
    merged_props: dict[str, Any] = {}

    for r in rels:
        all_quotes.extend(r.source_quotes)
        all_files.update(r.source_files)
        for k, v in r.properties.items():
            if k not in merged_props or not merged_props[k]:
                merged_props[k] = v

    # Deduplicate quotes
    seen: set[str] = set()
    unique_quotes: list[str] = []
    for q in all_quotes:
        if q and q not in seen:
            seen.add(q)
            unique_quotes.append(q)

    # Pick the longest detail (most informative)
    best_detail = max(rels, key=lambda r: len(r.detail)).detail

    return ResolvedRelationship(
        source_entity_id=rels[0].source_entity_id,
        target_entity_id=rels[0].target_entity_id,
        type=rels[0].type,
        detail=best_detail,
        properties=merged_props,
        source_quotes=unique_quotes,
        confidence=max(r.confidence for r in rels),
        source_files=sorted(all_files),
        mandatory_instructions=merge_mandatory_instructions(
            *[r.mandatory_instructions for r in rels]
        ),
    )


# ---------------------------------------------------------------------------
# Tier 2 — Near-duplicate type normalization via LLM
# ---------------------------------------------------------------------------

async def _normalize_near_duplicate_types(
    merged: list[ResolvedRelationship],
) -> list[ResolvedRelationship]:
    """Find same entity-pair relationships with different types and ask LLM to merge."""
    # Group by entity pair (ignoring type)
    by_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, rel in enumerate(merged):
        by_pair[(rel.source_entity_id, rel.target_entity_id)].append(i)

    # Collect candidate pairs: same entity pair, different types
    candidates: list[tuple[int, int]] = []
    for indices in by_pair.values():
        if len(indices) < 2:
            continue
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = indices[i], indices[j]
                if _normalize_type(merged[a].type) != _normalize_type(merged[b].type):
                    candidates.append((a, b))

    if not candidates:
        return merged

    logger.info("Relationship type normalization: %d candidate pairs", len(candidates))

    template = (PROMPTS_DIR / "relationship_resolution.txt").read_text(encoding="utf-8")
    merge_decisions: list[tuple[int, int, str]] = []  # (idx_a, idx_b, canonical_type)
    batch_size = 20

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        pairs_json = json.dumps(
            [
                {
                    "pair_index": j,
                    "relationship_a": {
                        "type": merged[a].type,
                        "detail": merged[a].detail,
                        "confidence": merged[a].confidence,
                        "mandatory_instructions": merged[a].mandatory_instructions,
                    },
                    "relationship_b": {
                        "type": merged[b].type,
                        "detail": merged[b].detail,
                        "confidence": merged[b].confidence,
                        "mandatory_instructions": merged[b].mandatory_instructions,
                    },
                }
                for j, (a, b) in enumerate(batch)
            ],
            indent=2,
        )
        prompt = prepend_mandatory_rules(
            template.format(pairs_json=pairs_json),
            merge_mandatory_instructions(
                *[
                    merge_mandatory_instructions(
                        merged[a].mandatory_instructions,
                        merged[b].mandatory_instructions,
                    )
                    for a, b in batch
                ]
            ),
            title="MANDATORY PROFILE RULES FOR RELATIONSHIP RESOLUTION",
        )
        response = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a relationship deduplication expert. "
                        "Mandatory profile rules in the user prompt are binding. "
                        "Do not normalize relationship types or details in a way that breaks those rules. "
                        "Respond with valid JSON matching the provided schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            model=settings.openai_resolution_model,
            response_format=get_relationship_resolution_schema(),
        )
        data = json.loads(response)
        for d in data.get("decisions", []):
            idx = d.get("pair_index", -1)
            if 0 <= idx < len(batch) and d.get("decision") == "MERGE":
                a, b = batch[idx]
                canonical = d.get("canonical_type", merged[a].type)
                merge_decisions.append((a, b, canonical))

    if not merge_decisions:
        return merged

    # Apply merges: absorb b into a, mark b for removal
    remove: set[int] = set()
    for idx_a, idx_b, canonical_type in merge_decisions:
        if idx_a in remove or idx_b in remove:
            continue  # Skip if already consumed
        rel_a = merged[idx_a]
        rel_b = merged[idx_b]
        # Merge b into a
        merged[idx_a] = _merge_group([rel_a, rel_b])
        merged[idx_a].type = canonical_type
        remove.add(idx_b)

    result = [r for i, r in enumerate(merged) if i not in remove]
    logger.info(
        "Relationship type normalization: merged %d pairs, %d relationships remain",
        len(remove), len(result),
    )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def resolve_relationships(
    relationships: list[ResolvedRelationship],
) -> list[ResolvedRelationship]:
    """Deduplicate relationships via exact-match grouping + LLM type normalization."""
    if not relationships:
        return []

    original_count = len(relationships)

    # Tier 1: Exact match grouping
    groups: dict[tuple[str, str, str], list[ResolvedRelationship]] = defaultdict(list)
    for rel in relationships:
        groups[_group_key(rel)].append(rel)

    merged = [_merge_group(rels) for rels in groups.values()]

    tier1_merged = original_count - len(merged)
    if tier1_merged:
        logger.info(
            "Relationship dedup tier 1: %d → %d (merged %d exact duplicates)",
            original_count, len(merged), tier1_merged,
        )

    # Tier 2: Near-duplicate type normalization
    result = await _normalize_near_duplicate_types(merged)

    total_merged = original_count - len(result)
    if total_merged:
        logger.info(
            "Relationship dedup total: %d → %d relationships",
            original_count, len(result),
        )

    return result
