"""Merge pipeline — AI-powered entity merging.

Receives entity snapshots via job.merge_payload, uses LLM to regenerate
shared properties, writes the merged entity to Neo4j, transfers
relationships, and embeds for RAG.
"""

import json
import logging
import re
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
    category: str,
) -> tuple[str, int]:
    """Create the merged entity in Neo4j and transfer relationships.

    Returns (new_entity_key, relationship_count).
    """
    new_key = str(uuid.uuid4())

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
    safe_category = re.sub(r"[^A-Za-z0-9_]", "_", category)

    # Create entity in Neo4j
    await neo4j_client.execute_write(
        f"CREATE (n:{safe_category} $props)",
        {"props": props},
    )

    # Pre-aggregate relationships across source entities. Multiple sources
    # contributing the same (type, direction, target) merge into a single
    # MERGE with their scalar properties unioned (first non-empty wins per key).
    source_key_set = {e.get("key") for e in entities if e.get("key")}

    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    source_names: dict[tuple[str, str, str], str] = {}

    for entity in entities:
        for rel in entity.get("relationships") or []:
            target_key = rel.get("target_key", "")
            if not target_key or target_key in source_key_set:
                continue
            direction = rel.get("direction", "outgoing")
            if direction not in ("outgoing", "incoming"):
                direction = "outgoing"
            rel_type = rel.get("type", "RELATED_TO")
            safe_type = re.sub(r"[^A-Z0-9_]", "_", rel_type.upper()) or "RELATED_TO"
            key = (safe_type, direction, target_key)
            bucket = agg.setdefault(key, {"case_id": case_id})
            for k, v in (rel.get("properties") or {}).items():
                if isinstance(v, (str, int, float, bool)) and k not in bucket:
                    bucket[k] = v
            source_names.setdefault(key, entity.get("name", "?"))

    rel_count = 0
    for (safe_type, direction, target_key), rel_props in agg.items():
        if direction == "outgoing":
            query = (
                f"MATCH (a {{id: $source_id}}) "
                f"MATCH (b {{key: $target_key, case_id: $case_id}}) "
                f"MERGE (a)-[r:{safe_type}]->(b) "
                f"SET r += $props "
                f"RETURN count(r) AS matched"
            )
        else:
            query = (
                f"MATCH (a {{key: $target_key, case_id: $case_id}}) "
                f"MATCH (b {{id: $source_id}}) "
                f"MERGE (a)-[r:{safe_type}]->(b) "
                f"SET r += $props "
                f"RETURN count(r) AS matched"
            )

        result = await neo4j_client.execute_query(
            query,
            {
                "source_id": new_key,
                "target_key": target_key,
                "case_id": case_id,
                "props": rel_props,
            },
        )
        matched = (result[0]["matched"] if result else 0) or 0
        if matched == 0:
            logger.warning(
                "Merge job %s: relationship target gone — %s %s %s (from source %s)",
                job_id, safe_type, direction, target_key,
                source_names.get((safe_type, direction, target_key), "?"),
            )
            continue
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
    category: str,
) -> None:
    """Embed the merged entity in ChromaDB for RAG and future dedup."""
    desc = f"{category}: {merged.get('name', '')}"
    if merged.get("description"):
        desc += f" — {merged['description']}"
    all_aliases = _union_lists(
        *[e.get("aliases") or [] for e in entities],
        [e.get("name", "") for e in entities if e.get("name")],
    )
    if all_aliases:
        desc += f" (aliases: {', '.join(all_aliases)})"
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
            "aliases": ",".join(all_aliases) if all_aliases else "",
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

    # Verify source entities still exist in Neo4j (request-time snapshot
    # may be stale by now). Fail fast rather than merging from a phantom.
    source_keys = [e.get("key") for e in entities if e.get("key")]
    if source_keys:
        existing_rows = await neo4j_client.execute_query(
            "MATCH (n {case_id: $case_id}) WHERE n.key IN $keys RETURN n.key AS k",
            {"case_id": case_id, "keys": source_keys},
        )
        existing_keys = {r["k"] for r in existing_rows or []}
        missing = [k for k in source_keys if k not in existing_keys]
        if missing:
            msg = f"Source entities no longer exist: {missing}"
            await _update_job(
                job, JobStatus.FAILED, 0.0, db, msg, error_message=msg,
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

            # Resolve category once so Neo4j label and ChromaDB metadata match.
            category = merged.get("category") or entities[0].get("category", "Entity")
            if user_preferences and user_preferences.get("type"):
                category = user_preferences["type"]

            # Stage 2: Write to Neo4j (60–85%)
            await _update_job(
                job, JobStatus.WRITING_GRAPH, 0.60, db,
                "Writing merged entity to graph...",
            )
            new_key, rel_count = await _write_merged_entity(
                merged, entities, case_id, str(job.id), category,
            )
            await _update_job(
                job, JobStatus.WRITING_GRAPH, 0.85, db,
                f"Entity created with {rel_count} relationships",
            )

            # Stage 3: Embed for RAG (85–100%). If embedding fails, the merged
            # entity would be invisible to cross-job dedup → leaks duplicates.
            # Roll back the Neo4j write rather than leave a half-indexed entity.
            try:
                await _embed_merged_entity(merged, new_key, case_id, entities, category)
            except Exception:
                logger.exception(
                    "Embedding failed for merge job %s; rolling back Neo4j writes",
                    job_id,
                )
                try:
                    await neo4j_client.execute_write(
                        "MATCH (n {id: $id, case_id: $case_id}) DETACH DELETE n",
                        {"id": new_key, "case_id": case_id},
                    )
                except Exception:
                    logger.exception(
                        "Compensating delete failed for merged entity %s in case %s",
                        new_key, case_id,
                    )
                raise

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
