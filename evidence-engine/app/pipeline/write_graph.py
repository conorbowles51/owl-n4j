import asyncio
import json
import logging
from contextvars import ContextVar
from typing import Any

from app.services.ingestion_checkpoints import checkpointed
from app.ontology import load_ontology
from app.pipeline.resolve_entities import (
    ResolvedEntity,
    ResolvedRelationship,
    coalesce_resolved_entities_by_id,
)
from app.pipeline.property_canonicalization import (
    canonicalize_properties,
    is_neo4j_primitive_list,
)
from app.services import chroma_client, neo4j_client
from app.services.graph_identity import ENTITY_LABEL_EXPRESSION, ensure_identity_indexes
from app.services.geocoding import build_geocode_request, geocoding_service
from app.services.embedding_refusal import ENTITY_VECTORS_PENDING, is_embedding_refusal, note_skipped
from app.services.pending_chunks import request_gap_backfill
from app.services.openai_client import embed_texts
from app.utils.text_sanitize import sanitize_json

logger = logging.getLogger(__name__)


_ontology = load_ontology()
ENTITY_CATEGORIES = _ontology.categories
GEOCODABLE_CATEGORIES = set(_ontology.geocodable_categories)
_replacement_transaction = ContextVar('audio_graph_replacement_transaction', default=None)


async def _ensure_indexes() -> None:
    await ensure_identity_indexes()
    # Per-category case_id and key indexes
    for label in ENTITY_CATEGORIES:
        await neo4j_client.execute_write(
            f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.case_id)"
        )
        await neo4j_client.execute_write(
            f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.key)"
        )

    # Spatial indexes for mapable categories
    for label in GEOCODABLE_CATEGORIES:
        await neo4j_client.execute_write(
            f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.latitude, n.longitude)"
        )

    # Temporal indexes for all timeline categories
    for cat in _ontology.temporal_categories:
        await neo4j_client.execute_write(
            f"CREATE INDEX IF NOT EXISTS FOR (n:{cat}) ON (n.date)"
        )

    # Lookup indexes for specific categories
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:Vehicle) ON (n.registration_plate)"
    )
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:CyberIdentity) ON (n.identity_type, n.handle)"
    )
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:Company) ON (n.registration_number)"
    )
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:Bank) ON (n.swift_bic)"
    )
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:DigitalAccount) ON (n.account_type, n.handle)"
    )
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:PhoneNumber) ON (n.number_e164)"
    )
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:NetworkIdentifier) ON (n.identifier_type, n.value)"
    )

    # Fulltext index across all entity labels
    try:
        labels = "|".join(ENTITY_CATEGORIES)
        await neo4j_client.execute_write(
            f"CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS "
            f"FOR (n:{labels}) ON EACH [n.name, n.description]"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------


def _has_coordinates(properties: dict[str, Any]) -> bool:
    return properties.get("latitude") is not None and properties.get("longitude") is not None


async def _apply_geocoding(entities: list[ResolvedEntity]) -> None:
    for entity in entities:
        if entity.category not in GEOCODABLE_CATEGORIES:
            continue
        force_regeocode = bool(entity.properties.pop("_force_regeocode", False))
        previous_geocoding_state = entity.properties.pop(
            "_previous_geocoding_state", {}
        )
        if _has_coordinates(entity.properties) and not force_regeocode:
            continue

        request = build_geocode_request(entity.category, entity.name, entity.properties)
        if request is None:
            if force_regeocode:
                entity.properties.update(previous_geocoding_state)
            continue

        result = await geocoding_service.geocode(request)
        if force_regeocode and result.status != "success":
            # Keep the existing, valid coarse pin if an attempted specificity
            # upgrade cannot be resolved. Its metadata must continue to describe
            # the coordinates that are actually stored.
            entity.properties.update(previous_geocoding_state)
            continue

        entity.properties["location_raw"] = request.location_raw
        entity.properties["location_specificity"] = request.location_specificity
        entity.properties["geocoding_status"] = result.status

        if result.status != "success":
            continue

        entity.properties["latitude"] = result.latitude
        entity.properties["longitude"] = result.longitude
        entity.properties["location_formatted"] = result.formatted_address
        entity.properties["geocoding_confidence"] = result.confidence
        entity.properties["geocoding_provider"] = result.provider
        entity.properties["geocoding_query"] = result.original_query
        entity.properties["geocoding_formatted_address"] = result.formatted_address
        if result.provider_importance is not None:
            entity.properties["geocoding_provider_importance"] = result.provider_importance
        if result.location_granularity:
            entity.properties["location_granularity"] = result.location_granularity


# ---------------------------------------------------------------------------
# Write entities
# ---------------------------------------------------------------------------

async def _write_entities(
    entities: list[ResolvedEntity],
    case_id: str,
    job_id: str,
) -> None:
    for entity in entities:
        entity.properties = canonicalize_properties(entity.category, entity.properties)

    await _apply_geocoding(entities)

    # Group by category and batch-write
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for e in entities:
        # Build flat property dict for Neo4j (no nested objects)
        props: dict[str, Any] = {
            "id": e.id,
            "key": e.id,
            "case_id": case_id,
            "name": e.name,
            "aliases": e.aliases,
            "description": e.properties.get("description", ""),
            "summary": e.summary,
            "confidence": e.confidence,
            "source_files": e.source_files,
            "source_quotes": e.source_quotes,
            "source_locations": json.dumps(e.source_locations),
            "source_claim_ids": e.source_claim_ids,
            "job_id": job_id,
            "specific_type": e.specific_type,
            "verified_facts": json.dumps(e.verified_facts),
            "ai_insights": json.dumps(e.ai_insights),
            '_transcript_binding': e.properties.get('_transcript_entity_id'),
        }
        for k, v in e.properties.items():
            if k.startswith("_") or k in props:
                continue
            if isinstance(v, (str, int, float, bool)) or is_neo4j_primitive_list(v):
                props[k] = v
        by_cat.setdefault(e.category, []).append(props)

    batch_size = 100
    for category, nodes in by_cat.items():
        for i in range(0, len(nodes), batch_size):
            batch = sanitize_json(nodes[i : i + batch_size])
            query = (
                f"UNWIND $nodes AS node "
                f"OPTIONAL MATCH (existing:{ENTITY_LABEL_EXPRESSION} {{id: node.id, case_id: node.case_id}}) "
                f"WITH node, existing "
                f"CALL apoc.util.validate(node._transcript_binding IS NOT NULL AND (existing IS NULL OR NOT existing:Person OR existing:RecycleBin), 'Selected transcript person is no longer available', []) "
                f"FOREACH (_ IN CASE WHEN existing IS NULL THEN [1] ELSE [] END | "
                f"CREATE (created:{category} {{id: node.id, case_id: node.case_id}})) "
                f"WITH node "
                f"MATCH (n:{ENTITY_LABEL_EXPRESSION} {{id: node.id, case_id: node.case_id}}) "
                f"WITH n, node, coalesce(n.manual_fields, []) AS manual_fields, "
                f"n.aliases AS prev_aliases, "
                f"n.source_files AS prev_sf, n.source_quotes AS prev_sq, "
                f"n.source_claim_ids AS prev_claim_ids, "
                f"n.description AS prev_desc, n.summary AS prev_summary, "
                f"n.confidence AS prev_conf, n.role AS prev_role, "
                f"n.specific_type AS prev_st, n.verified_facts AS prev_vf, "
                f"n.ai_insights AS prev_ai "
                f"FOREACH (_ IN CASE WHEN NOT 'category' IN manual_fields THEN [1] ELSE [] END | "
                f"SET n:{category}) "
                f"SET n += apoc.map.removeKeys(node, manual_fields + ['_transcript_binding']), "
                # List properties: accumulate with dedup
                f"n.aliases = reduce(acc = [], x IN (coalesce(prev_aliases, []) + coalesce(node.aliases, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END), "
                f"n.source_files = reduce(acc = [], x IN (coalesce(prev_sf, []) + coalesce(node.source_files, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END), "
                f"n.source_quotes = coalesce(prev_sq, []) + "
                f"[q IN coalesce(node.source_quotes, []) WHERE NOT q IN coalesce(prev_sq, [])], "
                f"n.source_claim_ids = reduce(acc = [], x IN (coalesce(prev_claim_ids, []) + coalesce(node.source_claim_ids, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END), "
                # description: prefer longer non-empty value
                f"n.description = CASE "
                f"WHEN 'description' IN manual_fields THEN prev_desc "
                f"WHEN prev_desc IS NULL OR prev_desc = '' THEN node.description "
                f"WHEN node.description IS NULL OR node.description = '' THEN prev_desc "
                f"WHEN size(node.description) > size(prev_desc) THEN node.description "
                f"ELSE prev_desc END, "
                # summary: always use new (merge prompt ensures it incorporates old)
                f"n.summary = CASE "
                f"WHEN 'summary' IN manual_fields THEN prev_summary "
                f"WHEN node.summary IS NULL OR node.summary = '' THEN coalesce(prev_summary, '') "
                f"ELSE node.summary END, "
                # confidence: prefer higher
                f"n.confidence = CASE "
                f"WHEN prev_conf IS NULL THEN node.confidence "
                f"WHEN node.confidence IS NULL THEN prev_conf "
                f"WHEN node.confidence > prev_conf THEN node.confidence "
                f"ELSE prev_conf END, "
                # role: prefer longer non-empty value
                f"n.role = CASE "
                f"WHEN 'role' IN manual_fields THEN prev_role "
                f"WHEN prev_role IS NULL OR prev_role = '' THEN node.role "
                f"WHEN node.role IS NULL OR node.role = '' THEN prev_role "
                f"WHEN size(coalesce(node.role, '')) > size(prev_role) THEN node.role "
                f"ELSE prev_role END, "
                # specific_type: prefer existing (first extraction has best context)
                f"n.specific_type = CASE "
                f"WHEN 'specific_type' IN manual_fields THEN prev_st "
                f"WHEN prev_st IS NULL OR prev_st = '' THEN node.specific_type "
                f"ELSE prev_st END, "
                f"n.verified_facts = CASE "
                f"WHEN prev_vf IS NULL OR prev_vf = '' THEN node.verified_facts "
                f"WHEN node.verified_facts IS NULL OR node.verified_facts = '' THEN prev_vf "
                f"ELSE node.verified_facts END, "
                f"n.ai_insights = CASE "
                f"WHEN prev_ai IS NULL OR prev_ai = '' THEN node.ai_insights "
                f"WHEN node.ai_insights IS NULL OR node.ai_insights = '' THEN prev_ai "
                f"ELSE node.ai_insights END"
            )
            await _checkpointed_graph_write(query, {"nodes": batch, "case_id": case_id})


# ---------------------------------------------------------------------------
# Write relationships
# ---------------------------------------------------------------------------

async def _write_relationships(
    relationships: list[ResolvedRelationship],
    case_id: str,
) -> None:
    # Group by type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        props: dict[str, Any] = {
            "source_id": rel.source_entity_id,
            "target_id": rel.target_entity_id,
            "case_id": case_id,
            "detail": rel.detail,
            "confidence": rel.confidence,
            "source_quotes": rel.source_quotes,
            "source_files": rel.source_files,
            "source_locations": json.dumps(rel.source_locations),
            "source_claim_ids": rel.source_claim_ids,
        }
        for k, v in rel.properties.items():
            if k not in props and isinstance(v, (str, int, float, bool)):
                props[k] = v

        safe_type = "".join(
            c if c.isalnum() or c == "_" else "_" for c in rel.type.upper()
        )
        by_type.setdefault(safe_type, []).append(props)

    batch_size = 100
    for rel_type, rels in by_type.items():
        for i in range(0, len(rels), batch_size):
            batch = sanitize_json(rels[i : i + batch_size])
            query = (
                f"UNWIND $rels AS rel "
                f"MATCH (a:{ENTITY_LABEL_EXPRESSION} {{id: rel.source_id, case_id: $case_id}}) "
                f"MATCH (b:{ENTITY_LABEL_EXPRESSION} {{id: rel.target_id, case_id: $case_id}}) "
                f"MERGE (a)-[r:{rel_type} {{source_id: rel.source_id, target_id: rel.target_id}}]->(b) "
                f"WITH r, rel, r.source_files AS prev_sf, r.source_quotes AS prev_sq, "
                f"r.source_claim_ids AS prev_claim_ids "
                f"SET r += rel, "
                f"r.source_files = reduce(acc = [], x IN (coalesce(prev_sf, []) + coalesce(rel.source_files, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END), "
                f"r.source_quotes = coalesce(prev_sq, []) + "
                f"[q IN coalesce(rel.source_quotes, []) WHERE NOT q IN coalesce(prev_sq, [])], "
                f"r.source_claim_ids = reduce(acc = [], x IN (coalesce(prev_claim_ids, []) + coalesce(rel.source_claim_ids, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END)"
            )
            await _checkpointed_graph_write(query, {"rels": batch, "case_id": case_id})


# ---------------------------------------------------------------------------
# Embed entities for RAG
# ---------------------------------------------------------------------------

async def _embed_entities(
    entities: list[ResolvedEntity],
    case_id: str,
) -> None:
    if not entities:
        return

    texts = []
    for e in entities:
        desc = f"{e.category}: {e.name}"
        if e.properties.get("description"):
            desc += f" — {e.properties['description']}"
        if e.aliases:
            desc += f" (aliases: {', '.join(e.aliases)})"
        if e.verified_facts:
            fact_snippets = [
                fact.get("text", "").strip()
                for fact in e.verified_facts[:5]
                if fact.get("text")
            ]
            if fact_snippets:
                desc += f" Facts: {'; '.join(fact_snippets)}"
        texts.append(desc)

    try:
        embeddings = await embed_texts(texts)
    except Exception as exc:
        if not is_embedding_refusal(exc):
            raise
        logger.warning("Entity vectors wait for the embedding service: %s", exc)
        await _mark_vectors_pending(entities, case_id)
        note_skipped(ENTITY_VECTORS_PENDING)
        return

    # Upsert so existing entities get updated embeddings (merged aliases, etc.)
    def upsert_entity_embeddings() -> None:
        collection = chroma_client.get_or_create_collection("entities")
        chroma_client.upsert_embeddings(
            collection=collection,
            ids=[e.id for e in entities],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    "category": e.category,
                    "specific_type": e.specific_type,
                    "name": e.name,
                    "case_id": case_id,
                    "aliases": ",".join(e.aliases) if e.aliases else "",
                }
                for e in entities
            ],
        )

    await asyncio.to_thread(upsert_entity_embeddings)


async def _mark_vectors_pending(entities: list[ResolvedEntity], case_id: str) -> None:
    """The backend's gap backfill embeds marked entities when the service answers (services/entity_vectors.py)."""
    ids = [e.id for e in entities]
    for start in range(0, len(ids), 500):
        await _checkpointed_graph_write(
            f"UNWIND $ids AS entity_id MATCH (n:{ENTITY_LABEL_EXPRESSION} {{id: entity_id, case_id: $case_id}}) "
            "SET n.vector_pending = true",
            {"ids": ids[start:start + 500], "case_id": case_id},
        )
    await request_gap_backfill()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def write_graph(
    entities: list[ResolvedEntity],
    relationships: list[ResolvedRelationship],
    case_id: str,
    job_id: str,
    retired_claims: list[dict] | None = None,
) -> None:
    entities = coalesce_resolved_entities_by_id(entities)
    await _ensure_indexes()
    if retired_claims:
        from app.pipeline.transcript_replacement import retire_graph_contributions
        async with neo4j_client.get_neo4j_driver().session() as session:
            async with await session.begin_transaction() as tx:
                await (await tx.run('MERGE (lock:IngestionCaseWriteLock {case_id:$case_id}) '
                    'SET lock.sequence=coalesce(lock.sequence,0)+1', {'case_id': case_id})).consume()
                token = _replacement_transaction.set(tx)
                try:
                    await retire_graph_contributions(tx, case_id, retired_claims)
                    await _write_entities(entities, case_id, job_id)
                    await _write_relationships(relationships, case_id)
                    await _embed_entities(entities, case_id)
                    await tx.commit()
                finally:
                    _replacement_transaction.reset(token)
        return
    await _write_entities(entities, case_id, job_id)
    await _write_relationships(relationships, case_id)
    await _embed_entities(entities, case_id)


async def _checkpointed_graph_write(query, parameters):
    transaction = _replacement_transaction.get()
    if transaction is not None:
        # Never checkpoint an uncommitted part of an atomic replacement. A
        # retry after rollback must execute every write again.
        await (await transaction.run(query, parameters)).consume()
        return
    await _bounded_graph_write(query, parameters)


@checkpointed("graph-write-v2")
async def _bounded_graph_write(query, parameters):
    # Acquire a case-scoped graph lock in the same transaction as the bounded
    # write. Two ingestion runs must not both observe a missing entity and CREATE
    # it. This survives separate worker processes and releases on rollback/crash.
    guarded = ('MERGE (writeLock:IngestionCaseWriteLock {case_id: $case_id}) '
        'SET writeLock.sequence = coalesce(writeLock.sequence, 0) + 1 WITH writeLock ' + query)
    await neo4j_client.execute_write(guarded, parameters)
