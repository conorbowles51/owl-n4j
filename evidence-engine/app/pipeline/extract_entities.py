import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.ontology import ENTITY_CATEGORIES

logger = logging.getLogger(__name__)
from app.ontology.prompt_builder import (
    build_entity_extraction_prompt,
    build_relationship_extraction_prompt,
)
from app.ontology.schema_builder import get_entity_schema, get_relationship_schema
from app.pipeline.chunk_embed import TextChunk
from app.services.openai_client import chat_completion


def _clean_entity_name(name: str) -> str:
    """Light cleanup of entity names at extraction time."""
    name = name.strip()
    name = name.rstrip('.')
    return " ".join(name.split())


@dataclass
class RawEntity:
    temp_id: str
    category: str
    specific_type: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    source_quote: str = ""
    confidence: float = 0.5
    source_chunk_index: int = 0
    source_file: str = ""


@dataclass
class RawRelationship:
    source_entity_id: str
    target_entity_id: str
    type: str
    detail: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    source_quote: str = ""
    confidence: float = 0.5
    source_chunk_index: int = 0
    source_file: str = ""


async def _extract_entities_from_chunk(
    chunk_text: str,
    chunk_index: int,
    file_name: str,
    case_context: str,
    is_table: bool = False,
    sheet_name: str = "",
) -> list[RawEntity]:
    prompt = build_entity_extraction_prompt(
        chunk_text=chunk_text,
        file_name=file_name,
        case_context=case_context,
        is_table=is_table,
        sheet_name=sheet_name,
    )

    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract structured entities from investigative documents. "
                    "Respond with valid JSON matching the provided schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format=get_entity_schema(),
    )

    data = json.loads(response)
    entities: list[RawEntity] = []
    _categories_set = set(ENTITY_CATEGORIES)

    for i, e in enumerate(data.get("entities", [])):
        category = e.get("category", "Other")
        if category not in _categories_set:
            category = "Other"

        name = _clean_entity_name(e.get("name", ""))
        if not name:
            continue

        entities.append(
            RawEntity(
                temp_id=f"chunk{chunk_index}_E{i}",
                category=category,
                specific_type=e.get("specific_type", category),
                name=name,
                properties=e.get("properties", {}),
                source_quote=e.get("source_quote", ""),
                confidence=float(e.get("confidence", 0.5)),
                source_chunk_index=chunk_index,
                source_file=file_name,
            )
        )

    return entities


async def _extract_relationships_from_chunk(
    chunk_text: str,
    chunk_index: int,
    entities: list[RawEntity],
    file_name: str,
    case_context: str,
) -> list[RawRelationship]:
    if not entities:
        return []

    entities_json = json.dumps(
        [
            {
                "id": e.temp_id,
                "category": e.category,
                "name": e.name,
                "specific_type": e.specific_type,
            }
            for e in entities
        ],
        indent=2,
    )

    prompt = build_relationship_extraction_prompt(
        chunk_text=chunk_text,
        file_name=file_name,
        case_context=case_context,
        entities_json=entities_json,
    )

    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract relationships between entities. "
                    "Respond with valid JSON matching the provided schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format=get_relationship_schema(),
    )

    data = json.loads(response)
    entity_ids = {e.temp_id for e in entities}
    relationships: list[RawRelationship] = []

    for r in data.get("relationships", []):
        src = r.get("source_entity_id", "")
        tgt = r.get("target_entity_id", "")
        if src not in entity_ids or tgt not in entity_ids:
            continue

        relationships.append(
            RawRelationship(
                source_entity_id=src,
                target_entity_id=tgt,
                type=r.get("type", "ASSOCIATED_WITH"),
                detail=r.get("detail", ""),
                properties=r.get("properties", {}),
                source_quote=r.get("source_quote", ""),
                confidence=float(r.get("confidence", 0.5)),
                source_chunk_index=chunk_index,
                source_file=file_name,
            )
        )

    return relationships


_STRIP_PREFIXES = {
    "mr", "mrs", "ms", "dr", "prof", "sir", "lord", "lady",
    "rev", "sgt", "cpl", "lt", "capt", "maj", "col", "gen", "hon",
}


def _normalize_name(name: str) -> str:
    """Normalize for overlap dedup: lowercase, strip punctuation/titles, collapse whitespace."""
    name = unicodedata.normalize("NFKD", name)
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    tokens = name.split()
    if tokens and tokens[0] in _STRIP_PREFIXES:
        tokens = tokens[1:]
    return " ".join(tokens)


def _dedup_within_file(
    entities: list[RawEntity],
    relationships: list[RawRelationship],
) -> tuple[list[RawEntity], list[RawRelationship]]:
    """Merge entities with identical normalized names extracted from
    overlapping chunks within the same file.  Remaps relationship IDs."""
    if not entities:
        return entities, relationships

    # Group by (category, normalized_name)
    groups: dict[tuple[str, str], list[int]] = {}
    for i, e in enumerate(entities):
        key = (e.category, _normalize_name(e.name))
        groups.setdefault(key, []).append(i)

    id_remap: dict[str, str] = {}  # old temp_id → surviving temp_id
    kept: list[RawEntity] = []

    for indices in groups.values():
        if len(indices) == 1:
            kept.append(entities[indices[0]])
            continue

        # Pick primary: highest confidence, then most properties
        primary_idx = max(
            indices, key=lambda i: (entities[i].confidence, len(entities[i].properties))
        )
        primary = entities[primary_idx]

        # Merge from others into primary
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

        all_names.discard(primary.name)
        # Store other name forms as aliases
        existing_aliases = list(merged_props.get("aliases") or [])
        for name in all_names:
            if name not in existing_aliases:
                existing_aliases.append(name)
        if existing_aliases:
            merged_props["aliases"] = existing_aliases

        primary.properties = merged_props
        primary.confidence = best_confidence
        kept.append(primary)

    merged_count = len(entities) - len(kept)
    if merged_count:
        logger.info(
            "Overlap dedup: merged %d duplicate entities (%d → %d)",
            merged_count, len(entities), len(kept),
        )

    # Remap relationship IDs
    remapped_rels: list[RawRelationship] = []
    for r in relationships:
        r.source_entity_id = id_remap.get(r.source_entity_id, r.source_entity_id)
        r.target_entity_id = id_remap.get(r.target_entity_id, r.target_entity_id)
        remapped_rels.append(r)

    return kept, remapped_rels


async def extract_entities_and_relationships(
    chunks: list[TextChunk],
    case_context: str,
    file_name: str,
) -> tuple[list[RawEntity], list[RawRelationship]]:
    """Two-pass extraction: entities first, then relationships with known entities."""
    if not chunks:
        return [], []

    # Pass 1: Extract entities from all chunks (parallel, bounded by semaphore)
    entity_tasks = [
        _extract_entities_from_chunk(
            chunk.text,
            chunk.index,
            file_name,
            case_context,
            is_table=chunk.is_table,
            sheet_name=chunk.metadata.get("sheet_name", ""),
        )
        for chunk in chunks
    ]
    entity_results = await asyncio.gather(*entity_tasks)

    all_entities: list[RawEntity] = []
    entities_by_chunk: dict[int, list[RawEntity]] = {}
    for chunk, chunk_entities in zip(chunks, entity_results):
        all_entities.extend(chunk_entities)
        entities_by_chunk[chunk.index] = chunk_entities

    # Pass 2: Extract relationships using known entities (parallel)
    rel_tasks = [
        _extract_relationships_from_chunk(
            chunk.text,
            chunk.index,
            entities_by_chunk.get(chunk.index, []),
            file_name,
            case_context,
        )
        for chunk in chunks
    ]
    rel_results = await asyncio.gather(*rel_tasks)

    all_relationships: list[RawRelationship] = []
    for chunk_rels in rel_results:
        all_relationships.extend(chunk_rels)

    # Deduplicate entities extracted from overlapping chunks
    all_entities, all_relationships = _dedup_within_file(all_entities, all_relationships)

    return all_entities, all_relationships
