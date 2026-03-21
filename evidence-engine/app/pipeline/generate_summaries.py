"""Generate LLM narrative summaries for resolved entities using GPT-4o."""

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path

from app.config import settings
from app.ontology.schema_builder import get_summary_schema
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

BATCH_SIZE = 5
MAX_QUOTES_PER_ENTITY = 10
MAX_QUOTE_LENGTH = 500
MAX_RELATIONSHIPS_PER_ENTITY = 15


def _build_entity_context(
    entity: ResolvedEntity,
    entity_rels: list[ResolvedRelationship],
    entity_names: dict[str, str],
) -> dict:
    """Build the context dict for a single entity to send to the LLM."""
    # Truncate quotes for cost control
    quotes = entity.source_quotes[:MAX_QUOTES_PER_ENTITY]
    quotes = [q[:MAX_QUOTE_LENGTH] for q in quotes]

    # Build relationship context with names
    rel_context = []
    for rel in entity_rels[:MAX_RELATIONSHIPS_PER_ENTITY]:
        if rel.source_entity_id == entity.id:
            other_id = rel.target_entity_id
            direction = "outgoing"
        else:
            other_id = rel.source_entity_id
            direction = "incoming"

        rel_context.append({
            "type": rel.type,
            "direction": direction,
            "connected_entity": entity_names.get(other_id, "unknown"),
            "detail": rel.detail,
        })

    context: dict = {
        "name": entity.name,
        "category": entity.category,
        "specific_type": entity.specific_type,
    }
    if entity.aliases:
        context["aliases"] = entity.aliases
    if quotes:
        context["source_quotes"] = quotes
    if entity.source_files:
        context["source_files"] = entity.source_files

    # Include key properties (skip internal fields)
    skip_keys = {"description", "aliases"}
    props = {k: v for k, v in entity.properties.items() if k not in skip_keys and v}
    if props:
        context["properties"] = props
    if entity.properties.get("description"):
        context["description"] = entity.properties["description"]
    if rel_context:
        context["relationships"] = rel_context

    return context


async def _summarize_batch(
    batch: list[tuple[int, ResolvedEntity]],
    entity_rels: dict[str, list[ResolvedRelationship]],
    entity_names: dict[str, str],
) -> list[tuple[int, str]]:
    """Generate summaries for a batch of entities. Returns (original_index, summary) pairs."""
    template = (PROMPTS_DIR / "entity_summary.txt").read_text(encoding="utf-8")

    entities_json = json.dumps(
        [
            {
                "entity_index": j,
                **_build_entity_context(entity, entity_rels.get(entity.id, []), entity_names),
            }
            for j, (_, entity) in enumerate(batch)
        ],
        indent=2,
    )

    prompt = template.format(entities_json=entities_json)
    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert investigative analyst. "
                    "Respond with valid JSON matching the provided schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model=settings.openai_quality_model,
        response_format=get_summary_schema(),
    )

    data = json.loads(response)
    results: list[tuple[int, str]] = []
    for s in data.get("summaries", []):
        batch_idx = s.get("entity_index", -1)
        summary = s.get("summary", "")
        if 0 <= batch_idx < len(batch) and summary:
            original_idx = batch[batch_idx][0]
            results.append((original_idx, summary))

    return results


async def generate_summaries(
    entities: list[ResolvedEntity],
    relationships: list[ResolvedRelationship],
) -> list[ResolvedEntity]:
    """Enrich entities with LLM-generated narrative summaries using GPT-4o."""
    if not entities:
        return entities

    # Build relationship index for fast lookup
    entity_rels: dict[str, list[ResolvedRelationship]] = defaultdict(list)
    for rel in relationships:
        entity_rels[rel.source_entity_id].append(rel)
        entity_rels[rel.target_entity_id].append(rel)

    # Build entity name lookup
    entity_names: dict[str, str] = {e.id: e.name for e in entities}

    # Build batches — include all entities (including is_existing for re-summarization)
    indexed_entities = list(enumerate(entities))
    batches = [
        indexed_entities[i : i + BATCH_SIZE]
        for i in range(0, len(indexed_entities), BATCH_SIZE)
    ]

    logger.info(
        "Generating summaries for %d entities in %d batches (model: %s)",
        len(entities), len(batches), settings.openai_quality_model,
    )

    # Run batches with concurrency bounded by the openai_client semaphore
    tasks = [
        _summarize_batch(batch, entity_rels, entity_names)
        for batch in batches
    ]
    batch_results = await asyncio.gather(*tasks)

    # Apply summaries
    summary_count = 0
    for results in batch_results:
        for idx, summary in results:
            entities[idx].summary = summary
            summary_count += 1

    logger.info("Generated %d entity summaries", summary_count)
    return entities
