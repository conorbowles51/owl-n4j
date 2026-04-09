"""Merge pipeline — AI-powered entity merging.

Receives entity snapshots via job.merge_payload, uses LLM to regenerate
shared properties, writes the merged entity to Neo4j, transfers
relationships, and embeds for RAG.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.job import Job, JobStatus
from app.ontology.schema_builder import get_merge_schema
from app.services import chroma_client, neo4j_client
from app.services.cost_tracking import ingestion_cost_context
from app.services.openai_client import chat_completion, embed_texts
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _update_job(
    job: Job,
    status: JobStatus,
    progress: float,
    db: AsyncSession,
    message: str = "",
    error_message: str | None = None,
) -> None:
    job.status = status
    job.progress = progress
    if error_message is not None:
        job.error_message = error_message
    await db.commit()
    payload = {
        "job_id": str(job.id),
        "status": status.value,
        "progress": progress,
        "message": message,
    }
    if error_message is not None:
        payload["error_message"] = error_message
    await publish_progress(str(job.id), payload)


def _union_lists(*lists: list | None) -> list:
    """Union multiple lists, deduplicating values."""
    seen: set[str] = set()
    result: list = []
    for lst in lists:
        for item in lst or []:
            key = str(item)
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def _collect_all_properties(entities: list[dict]) -> dict[str, Any]:
    """Collect properties unique to one entity (not needing AI merge)."""
    all_keys: dict[str, list[Any]] = {}
    for entity in entities:
        for k, v in (entity.get("properties") or {}).items():
            all_keys.setdefault(k, []).append(v)
    # Keep properties as-is; AI-merged ones will override later
    result: dict[str, Any] = {}
    for k, values in all_keys.items():
        non_none = [v for v in values if v is not None]
        if non_none:
            result[k] = non_none[0]
    return result


# ---------------------------------------------------------------------------
# Stage 1: AI property merge
# ---------------------------------------------------------------------------

async def _merge_properties(
    entities: list[dict],
    user_preferences: dict | None,
) -> dict[str, Any]:
    """Call LLM to merge entity properties."""
    template = (PROMPTS_DIR / "entity_merge.txt").read_text(encoding="utf-8")

    # Build entity context for the prompt
    entity_contexts = []
    for i, entity in enumerate(entities):
        ctx: dict[str, Any] = {
            "entity_index": i,
            "name": entity.get("name", ""),
            "category": entity.get("category", ""),
            "specific_type": entity.get("specific_type", ""),
        }
        if entity.get("summary"):
            ctx["summary"] = entity["summary"]
        if entity.get("description"):
            ctx["description"] = entity["description"]
        if entity.get("verified_facts"):
            ctx["verified_facts"] = entity["verified_facts"][:30]
        if entity.get("ai_insights"):
            ctx["ai_insights"] = entity["ai_insights"][:20]
        if entity.get("source_files"):
            ctx["source_files"] = entity["source_files"]
        if entity.get("aliases"):
            ctx["aliases"] = entity["aliases"]
        # Include key custom properties
        props = {
            k: v for k, v in (entity.get("properties") or {}).items()
            if isinstance(v, (str, int, float, bool)) and k not in ("description", "aliases")
        }
        if props:
            ctx["properties"] = props
        # Include relationship context
        if entity.get("relationships"):
            ctx["relationships"] = entity["relationships"][:15]
        entity_contexts.append(ctx)

    name_pref = ""
    if user_preferences and user_preferences.get("name"):
        name_pref = f'The user has requested the merged entity be named "{user_preferences["name"]}".'
    else:
        name_pref = "Choose the most complete, canonical name."

    prompt = template.format(
        entities_json=json.dumps(entity_contexts, indent=2),
        user_name_preference=name_pref,
    )

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
        model=settings.openai_summary_model,
        response_format=get_merge_schema(),
    )

    return json.loads(response)


# ---------------------------------------------------------------------------
# Stage 2: Write merged entity + relationships to Neo4j
# ---------------------------------------------------------------------------

async def _write_merged_entity(
    merged: dict[str, Any],
    entities: list[dict],
    case_id: str,
    job_id: str,
    user_preferences: dict | None,
) -> tuple[str, int]:
    """Create the merged entity in Neo4j and transfer relationships.

    Returns (new_entity_key, relationship_count).
    """
    new_key = str(uuid.uuid4())
    category = merged.get("category") or entities[0].get("category", "Entity")

    # Override with user preferences if provided
    if user_preferences:
        if user_preferences.get("type"):
            category = user_preferences["type"]

    # Build additive properties (union, no AI needed)
    all_aliases = _union_lists(
        *[e.get("aliases") or [] for e in entities],
        # Add old entity names as aliases
        [e.get("name", "") for e in entities if e.get("name")],
    )
    all_source_files = _union_lists(*[e.get("source_files") or [] for e in entities])
    all_source_quotes = _union_lists(*[e.get("source_quotes") or [] for e in entities])
    max_confidence = max((e.get("confidence") or 0.0 for e in entities), default=0.5)

    # Collect base properties from all entities
    base_props = _collect_all_properties(entities)

    # Overlay AI-merged custom properties
    for k, v in (merged.get("merged_properties") or {}).items():
        if isinstance(v, (str, int, float, bool)):
            base_props[k] = v

    # Build final node properties
    props: dict[str, Any] = {
        "id": new_key,
        "key": new_key,
        "case_id": case_id,
        "name": merged.get("name") or entities[0].get("name", "Merged Entity"),
        "aliases": all_aliases,
        "description": merged.get("description", ""),
        "summary": merged.get("summary", ""),
        "confidence": max_confidence,
        "source_files": all_source_files,
        "source_quotes": all_source_quotes,
        "job_id": job_id,
        "specific_type": merged.get("specific_type", ""),
        "verified_facts": json.dumps(merged.get("verified_facts", [])),
        "ai_insights": json.dumps(merged.get("ai_insights", [])),
    }
    # Add scalar custom properties
    for k, v in base_props.items():
        if k not in props and isinstance(v, (str, int, float, bool)):
            props[k] = v

    # Sanitize category label
    safe_category = "".join(
        c if c.isalnum() or c == "_" else "_" for c in category
    )

    # Create entity in Neo4j
    create_query = (
        f"CREATE (n:{safe_category} $props) "
        f"SET n:{safe_category}"
    )
    await neo4j_client.execute_write(create_query, {"props": props})

    # Transfer relationships from all source entities
    source_keys = [e.get("key") for e in entities if e.get("key")]
    source_key_set = set(source_keys)

    rel_count = 0
    seen_rels: set[str] = set()

    for entity in entities:
        for rel in entity.get("relationships") or []:
            target_key = rel.get("target_key", "")
            # Skip relationships between merging entities (would be self-referential)
            if target_key in source_key_set:
                continue

            direction = rel.get("direction", "outgoing")
            rel_type = rel.get("type", "RELATED_TO")
            safe_type = "".join(
                c if c.isalnum() or c == "_" else "_" for c in rel_type.upper()
            )

            # Deduplicate: same type + direction + target
            dedup_key = f"{safe_type}:{direction}:{target_key}"
            if dedup_key in seen_rels:
                continue
            seen_rels.add(dedup_key)

            # Build relationship properties
            rel_props: dict[str, Any] = {
                "case_id": case_id,
            }
            for k, v in (rel.get("properties") or {}).items():
                if isinstance(v, (str, int, float, bool)):
                    rel_props[k] = v

            if direction == "outgoing":
                query = (
                    f"MATCH (a {{id: $source_id}}) "
                    f"MATCH (b {{key: $target_key, case_id: $case_id}}) "
                    f"MERGE (a)-[r:{safe_type}]->(b) "
                    f"SET r += $props"
                )
            else:
                query = (
                    f"MATCH (a {{key: $target_key, case_id: $case_id}}) "
                    f"MATCH (b {{id: $source_id}}) "
                    f"MERGE (a)-[r:{safe_type}]->(b) "
                    f"SET r += $props"
                )

            await neo4j_client.execute_write(
                query,
                {
                    "source_id": new_key,
                    "target_key": target_key,
                    "case_id": case_id,
                    "props": rel_props,
                },
            )
            rel_count += 1

    return new_key, rel_count


# ---------------------------------------------------------------------------
# Stage 3: Embed merged entity for RAG
# ---------------------------------------------------------------------------

async def _embed_merged_entity(
    merged: dict[str, Any],
    new_key: str,
    case_id: str,
    entities: list[dict],
) -> None:
    """Embed the merged entity in ChromaDB for RAG and future dedup."""
    category = merged.get("category") or entities[0].get("category", "Entity")

    desc = f"{category}: {merged.get('name', '')}"
    if merged.get("description"):
        desc += f" — {merged['description']}"
    all_aliases = _union_lists(
        *[e.get("aliases") or [] for e in entities],
        [e.get("name", "") for e in entities if e.get("name")],
    )
    if all_aliases:
        desc += f" (aliases: {', '.join(all_aliases[:10])})"
    if merged.get("verified_facts"):
        facts = [f.get("text", "").strip() for f in merged["verified_facts"][:5] if f.get("text")]
        if facts:
            desc += f" Facts: {'; '.join(facts)}"

    embeddings = await embed_texts([desc])

    collection = chroma_client.get_or_create_collection("entities")
    chroma_client.upsert_embeddings(
        collection=collection,
        ids=[new_key],
        embeddings=embeddings,
        documents=[desc],
        metadatas=[{
            "category": category,
            "specific_type": merged.get("specific_type", ""),
            "name": merged.get("name", ""),
            "case_id": case_id,
            "aliases": ",".join(all_aliases[:10]) if all_aliases else "",
        }],
    )


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

async def run_merge_pipeline(job_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    payload = job.merge_payload or {}
    entities = payload.get("entities", [])
    user_preferences = payload.get("user_preferences")
    case_id = job.case_id

    if len(entities) < 2:
        await _update_job(
            job, JobStatus.FAILED, 0.0, db,
            "At least 2 entities required for merge",
            error_message="At least 2 entities required for merge",
        )
        return

    try:
        async with ingestion_cost_context(
            case_id=case_id,
            requested_by_user_id=str(job.requested_by_user_id) if job.requested_by_user_id else None,
            engine_job_id=str(job.id),
            description=f"Entity merge: {', '.join(e.get('name', '?') for e in entities)}",
            extra_metadata={"pipeline_scope": "entity_merge"},
            job_type="entity_merge",
        ):
            # Stage 1: AI property merge (0–60%)
            await _update_job(
                job, JobStatus.MERGING_PROPERTIES, 0.0, db,
                f"Merging properties from {len(entities)} entities...",
            )
            merged = await _merge_properties(entities, user_preferences)
            await _update_job(
                job, JobStatus.MERGING_PROPERTIES, 0.60, db,
                "Properties merged",
            )

            # Stage 2: Write to Neo4j (60–90%)
            await _update_job(
                job, JobStatus.WRITING_GRAPH, 0.60, db,
                "Writing merged entity to graph...",
            )
            new_key, rel_count = await _write_merged_entity(
                merged, entities, case_id, str(job.id), user_preferences,
            )
            await _update_job(
                job, JobStatus.WRITING_GRAPH, 0.85, db,
                f"Entity created with {rel_count} relationships",
            )

            # Stage 3: Embed for RAG (85–100%)
            await _update_job(
                job, JobStatus.WRITING_GRAPH, 0.85, db,
                "Embedding merged entity...",
            )
            await _embed_merged_entity(merged, new_key, case_id, entities)

        # Complete
        job.entity_count = 1
        job.relationship_count = rel_count
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        await db.commit()
        await publish_progress(
            str(job.id),
            {
                "job_id": str(job.id),
                "status": JobStatus.COMPLETED.value,
                "progress": 1.0,
                "message": "Merge complete",
                "merged_entity_key": new_key,
                "entity_count": 1,
                "relationship_count": rel_count,
            },
        )
    except Exception as e:
        logger.exception("Merge pipeline failed for job %s", job_id)
        await _update_job(
            job, JobStatus.FAILED, job.progress, db,
            f"Failed: {e}",
            error_message=str(e),
        )
        raise
