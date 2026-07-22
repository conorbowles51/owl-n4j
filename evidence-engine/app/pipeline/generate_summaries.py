"""Generate evidence-grounded narrative summaries for resolved entities."""

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.ontology.schema_builder import get_summary_schema
from app.pipeline.mandatory_rules import merge_mandatory_instructions, prepend_mandatory_rules
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship
from app.pipeline.prompt_security import secure_system_prompt
from app.services.openai_client import chat_completion

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

BATCH_SIZE = 5
CENTRAL_ENTITY_BATCH_SIZE = 1
CENTRAL_ENTITY_EVIDENCE_THRESHOLD = 10
MAX_QUOTES_PER_ENTITY = 10
MAX_QUOTE_LENGTH = 500
MAX_FACTS_PER_ENTITY = 100
MAX_FACT_CONTEXT_CHARS = 50_000
MAX_RELATIONSHIPS_PER_ENTITY = 40
MAX_QUOTES_PER_RELATIONSHIP = 3


def _source_file_for_fact(fact: dict[str, Any]) -> str:
    location = fact.get("source_location")
    if not isinstance(location, dict):
        location = {}
    return str(fact.get("source_doc") or location.get("source_file") or "").strip()


def _page_for_fact(fact: dict[str, Any]) -> int | None:
    location = fact.get("source_location")
    if not isinstance(location, dict):
        location = {}
    raw_page = fact.get("page") or location.get("page_start")
    try:
        return int(raw_page) if raw_page is not None else None
    except (TypeError, ValueError):
        return None


def _document_citation(source_file: str, page: int | None) -> str:
    if not source_file:
        return ""
    if page is None:
        return f"[{source_file}](evidence://{source_file})"
    return f"[{source_file}, p.{page}](doc://{quote(source_file, safe='')}/{page})"


def _select_verified_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select a broad, source-balanced dossier under an explicit context cap."""
    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None]] = set()
    for fact in facts:
        text = str(fact.get("text") or "").strip()
        if not text:
            continue
        source_file = _source_file_for_fact(fact)
        page = _page_for_fact(fact)
        key = (" ".join(text.lower().split()), source_file.lower(), page)
        if key in seen:
            continue
        seen.add(key)
        try:
            importance = int(fact.get("importance", 3) or 3)
        except (TypeError, ValueError):
            importance = 3
        deduplicated.append(
            {
                "statement": text,
                "evidence_quote": str(fact.get("quote") or "").strip(),
                "source_file": source_file,
                "page": page,
                "citation": _document_citation(source_file, page),
                "importance": importance,
            }
        )

    # Round-robin across source documents so one verbose document cannot crowd
    # all other evidence out of a central entity's dossier.
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_order: list[str] = []
    for fact in deduplicated:
        source = fact["source_file"] or "__unknown__"
        if source not in by_source:
            source_order.append(source)
        by_source[source].append(fact)
    for items in by_source.values():
        items.sort(key=lambda item: (-item["importance"], item["page"] or 0))

    selected: list[dict[str, Any]] = []
    selected_chars = 0
    while len(selected) < MAX_FACTS_PER_ENTITY:
        added = False
        for source in source_order:
            if not by_source[source]:
                continue
            candidate = by_source[source].pop(0)
            candidate_chars = len(json.dumps(candidate, ensure_ascii=False))
            if selected and selected_chars + candidate_chars > MAX_FACT_CONTEXT_CHARS:
                continue
            selected.append(candidate)
            selected_chars += candidate_chars
            added = True
            if len(selected) >= MAX_FACTS_PER_ENTITY:
                break
        if not added:
            break
    return selected


def _summary_is_comprehensive(summary: str, context: dict[str, Any]) -> bool:
    """Reject suspiciously thin central-entity prose before it reaches users."""
    if not summary.strip():
        return False
    dossier = context.get("evidence_dossier") or {}
    fact_count = int(dossier.get("evidence_item_count", 0) or 0)
    relationship_count = int(
        dossier.get("documented_relationship_count", 0) or 0
    )
    if fact_count + relationship_count < CENTRAL_ENTITY_EVIDENCE_THRESHOLD:
        return True

    minimum_chars = min(
        2_500,
        400 + (fact_count * 35) + (relationship_count * 30),
    )
    if len(summary.strip()) < minimum_chars:
        return False

    page_citation_sources = {
        fact.get("source_file")
        for fact in context.get("verified_facts", [])
        if "doc://" in str(fact.get("citation") or "")
    }
    required_page_links = min(3, len(page_citation_sources))
    return summary.count("doc://") >= required_page_links


def _build_entity_context(
    entity: ResolvedEntity,
    entity_rels: list[ResolvedRelationship],
    entity_names: dict[str, str],
) -> dict:
    """Build the context dict for a single entity to send to the LLM."""
    # Truncate quotes for cost control
    quotes = entity.source_quotes[:MAX_QUOTES_PER_ENTITY]
    quotes = [q[:MAX_QUOTE_LENGTH] for q in quotes]
    facts = _select_verified_facts(entity.verified_facts)

    # Build relationship context with names and page-level citations.
    rel_context = []
    for rel in entity_rels[:MAX_RELATIONSHIPS_PER_ENTITY]:
        source_quotes = [
            quote[:MAX_QUOTE_LENGTH]
            for quote in rel.source_quotes[:MAX_QUOTES_PER_RELATIONSHIP]
            if quote.strip()
        ]
        if not source_quotes:
            continue

        if rel.source_entity_id == entity.id:
            other_id = rel.target_entity_id
            direction = "outgoing"
        else:
            other_id = rel.source_entity_id
            direction = "incoming"

        locations = [
            location
            for location in rel.source_locations
            if isinstance(location, dict)
        ]
        source_file = str(
            (locations[0].get("source_file") if locations else "")
            or (rel.source_files[0] if rel.source_files else "")
        )
        raw_page = locations[0].get("page_start") if locations else None
        try:
            page = int(raw_page) if raw_page is not None else None
        except (TypeError, ValueError):
            page = None

        rel_context.append({
            "type": rel.type,
            "direction": direction,
            "connected_entity": entity_names.get(other_id, "unknown"),
            "detail": rel.detail,
            "source_quotes": source_quotes,
            "source_files": rel.source_files,
            "confidence": rel.confidence,
            "citation": _document_citation(source_file, page),
        })

    context: dict = {
        "name": entity.name,
        "category": entity.category,
        "specific_type": entity.specific_type,
    }
    if entity.mandatory_instructions:
        context["mandatory_instructions"] = entity.mandatory_instructions
    if entity.aliases:
        context["aliases"] = entity.aliases
    if facts:
        context["verified_facts"] = facts
    elif quotes:
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

    context["evidence_dossier"] = {
        "evidence_item_count": len(facts),
        "total_verified_fact_count": len(entity.verified_facts),
        "documented_relationship_count": len(rel_context),
        "total_source_count": len(set(entity.source_files)),
        "coverage_note": (
            "The dossier contains all available deduplicated facts."
            if len(facts) >= len(entity.verified_facts)
            else "The dossier is source-balanced and bounded by the ingestion context limit."
        ),
    }

    return context


def _fallback_summary(
    entity: ResolvedEntity,
    entity_rels: list[ResolvedRelationship],
    entity_names: dict[str, str],
) -> str:
    """Build a deterministic evidence-only summary if the model omits an entity."""
    lines = ["## Evidence Summary"]
    selected_facts = _select_verified_facts(entity.verified_facts)
    if selected_facts:
        lines.extend(
            f"- {fact['statement']} {fact['citation']}".rstrip()
            for fact in selected_facts
        )
    elif entity.source_quotes:
        lines.append(f'- Documented source text: "{entity.source_quotes[0][:500]}"')
    else:
        lines.append(f"- {entity.name} is identified as {entity.specific_type or entity.category}.")

    supported_relationships = [rel for rel in entity_rels if rel.source_quotes]
    if supported_relationships:
        lines.extend(["", "## Documented Connections"])
        for rel in supported_relationships[:MAX_RELATIONSHIPS_PER_ENTITY]:
            if rel.source_entity_id == entity.id:
                other_id = rel.target_entity_id
                direction = "to"
            else:
                other_id = rel.source_entity_id
                direction = "from"
            other_name = entity_names.get(other_id, "unknown entity")
            detail = f": {rel.detail}" if rel.detail else ""
            lines.append(f"- {rel.type} {direction} {other_name}{detail}")

    lines.extend(["", "## Source References"])
    source_files = list(dict.fromkeys(entity.source_files))
    if not source_files:
        source_files = [
            str(fact.get("source_doc") or "").strip()
            for fact in entity.verified_facts
            if str(fact.get("source_doc") or "").strip()
        ]
        source_files = list(dict.fromkeys(source_files))
    lines.extend(
        f"- [{source_file}](evidence://{source_file})"
        for source_file in source_files
    )
    if not source_files:
        lines.append("- No source filename was recorded.")
    return "\n".join(lines)


async def _review_batch_summaries(
    batch: list[tuple[int, ResolvedEntity]],
    results: list[tuple[int, str]],
    contexts: list[dict[str, Any]],
) -> list[tuple[int, str]]:
    """Run the generated prose back through a source-entailment editor."""
    by_original_index = {index: summary for index, summary in results}
    context_by_original_index = {
        original_index: contexts[local_index]
        for local_index, (original_index, _) in enumerate(batch)
    }
    review_items: list[dict[str, Any]] = []
    local_to_original: dict[int, int] = {}
    for local_index, (original_index, entity) in enumerate(batch):
        draft = by_original_index.get(original_index)
        if not draft:
            continue
        review_index = len(review_items)
        local_to_original[review_index] = original_index
        review_items.append(
            {
                "entity_index": review_index,
                "entity_name": entity.name,
                "evidence_context": contexts[local_index],
                "draft_summary": draft,
            }
        )
    if not review_items:
        return results

    prompt = (
        "Audit each draft entity summary against its complete accumulated evidence_context. Return a complete "
        "corrected summary for every entity_index. Natural paraphrase and cross-document synthesis are permitted "
        "when the supplied verified facts jointly entail the prose; exact phrase matching is not required. Preserve "
        "all supported factual detail and exact supplied citations. Remove unsupported counts, identities, ownership, duties, motives, "
        "intent, culpability, significance, patterns, causal claims, and phrases such as 'may be relevant' or "
        "'consistent with' unless the evidence itself explicitly makes that statement. Preserve allegation and "
        "dispute attribution. A role title does not prove duties beyond the title; initials do not prove identity; "
        "phone-tower activity does not prove travel. Keep factual details and Source References. Do not add an "
        "Analysis, Assessment, or AI insight section.\n\n"
        + json.dumps(review_items, ensure_ascii=False)
    )
    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": secure_system_prompt(
                    "You are a strict evidence-entailment editor. Return facts-only entity summaries."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        workload="ingestion_quality",
        response_format=get_summary_schema(),
    )
    reviewed = json.loads(response).get("summaries", [])
    corrected = dict(by_original_index)
    for item in reviewed:
        review_index = item.get("entity_index")
        summary = str(item.get("summary") or "").strip()
        original_index = local_to_original.get(review_index)
        if (
            original_index is not None
            and summary
            and _summary_is_comprehensive(
                summary,
                context_by_original_index[original_index],
            )
        ):
            corrected[original_index] = summary
    return [(index, corrected[index]) for index, _ in results if index in corrected]


async def _summarize_batch(
    batch: list[tuple[int, ResolvedEntity]],
    entity_rels: dict[str, list[ResolvedRelationship]],
    entity_names: dict[str, str],
    *,
    merge: bool = False,
    _allow_retry: bool = True,
    _review: bool = True,
) -> list[tuple[int, str]]:
    """Generate summaries for a batch of entities. Returns (original_index, summary) pairs.

    When merge=True, uses the merge prompt — entities must have existing_summary set.
    """
    # Existing profiles are regenerated from accumulated atomic evidence.
    # Prior generated prose is intentionally not part of the evidence input.
    template = (PROMPTS_DIR / "entity_summary.txt").read_text(encoding="utf-8")

    items = []
    contexts: list[dict[str, Any]] = []
    for j, (_, entity) in enumerate(batch):
        ctx = _build_entity_context(entity, entity_rels.get(entity.id, []), entity_names)
        contexts.append(ctx)
        item = {"entity_index": j, **ctx}
        items.append(item)

    entities_json = json.dumps(items, indent=2)

    prompt = prepend_mandatory_rules(
        template.format(entities_json=entities_json),
        merge_mandatory_instructions(*[entity.mandatory_instructions for _, entity in batch]),
        title="MANDATORY PROFILE RULES FOR SUMMARY GENERATION",
    )
    response = await chat_completion(
        messages=[
            {
                "role": "system",
                "content": secure_system_prompt(
                    "You are an expert investigative analyst. "
                    "Write evidence-bound entity summaries, not investigative analysis. "
                    "Mandatory profile rules in the user prompt are binding. "
                    "Preserve rule-compliant names and classifications in your summaries. "
                    "Respond with valid JSON matching the provided schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        workload="ingestion_entity_summary",
        response_format=get_summary_schema(),
    )

    data = json.loads(response)
    results: list[tuple[int, str]] = []
    completed_local_indices: set[int] = set()
    for s in data.get("summaries", []):
        batch_idx = s.get("entity_index", -1)
        summary = s.get("summary", "")
        if (
            0 <= batch_idx < len(batch)
            and summary
            and _summary_is_comprehensive(summary, contexts[batch_idx])
            and batch_idx not in completed_local_indices
        ):
            original_idx = batch[batch_idx][0]
            results.append((original_idx, summary))
            completed_local_indices.add(batch_idx)

    missing_indices = [
        index for index in range(len(batch)) if index not in completed_local_indices
    ]
    if missing_indices and _allow_retry:
        logger.warning(
            "Entity summary response omitted %d/%d entities; retrying omitted entities once",
            len(missing_indices),
            len(batch),
        )
        retry_batch = [batch[index] for index in missing_indices]
        results.extend(
            await _summarize_batch(
                retry_batch,
                entity_rels,
                entity_names,
                merge=merge,
                _allow_retry=False,
                _review=False,
            )
        )
    elif missing_indices:
        logger.error(
            "Entity summary retry omitted %d entities; using deterministic evidence-only summaries",
            len(missing_indices),
        )
        for index in missing_indices:
            original_idx, entity = batch[index]
            summary = _fallback_summary(
                entity,
                entity_rels.get(entity.id, []),
                entity_names,
            )
            results.append((original_idx, summary))

    if _review:
        try:
            return await _review_batch_summaries(batch, results, contexts)
        except Exception:
            logger.exception("Entity summary quality review failed; retaining source-bound draft summaries")
    return results


async def generate_summaries(
    entities: list[ResolvedEntity],
    relationships: list[ResolvedRelationship],
) -> list[ResolvedEntity]:
    """Enrich entities with evidence-grounded narrative summaries."""
    if not entities:
        return entities

    # Build relationship index for fast lookup
    entity_rels: dict[str, list[ResolvedRelationship]] = defaultdict(list)
    for rel in relationships:
        entity_rels[rel.source_entity_id].append(rel)
        entity_rels[rel.target_entity_id].append(rel)

    # Build entity name lookup
    entity_names: dict[str, str] = {e.id: e.name for e in entities}

    indexed = list(enumerate(entities))
    central = [
        item
        for item in indexed
        if len(item[1].verified_facts) + len(entity_rels.get(item[1].id, []))
        >= CENTRAL_ENTITY_EVIDENCE_THRESHOLD
    ]
    central_ids = {id(entity) for _, entity in central}
    regular = [item for item in indexed if id(item[1]) not in central_ids]
    central_batches = [
        central[index : index + CENTRAL_ENTITY_BATCH_SIZE]
        for index in range(0, len(central), CENTRAL_ENTITY_BATCH_SIZE)
    ]
    regular_batches = [
        regular[index : index + BATCH_SIZE]
        for index in range(0, len(regular), BATCH_SIZE)
    ]
    batches = central_batches + regular_batches

    logger.info(
        "Generating evidence-dossier summaries: %d central, %d regular in %d batches (model: %s)",
        len(central), len(regular), len(batches), settings.openai_summary_model,
    )

    # Run all batches with concurrency bounded by the openai_client semaphore
    tasks = [_summarize_batch(batch, entity_rels, entity_names) for batch in batches]
    batch_results = await asyncio.gather(*tasks)

    # Apply summaries
    summary_count = 0
    for results in batch_results:
        for idx, summary in results:
            entities[idx].summary = summary
            summary_count += 1

    logger.info("Generated %d entity summaries", summary_count)
    return entities
