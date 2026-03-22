from typing import Any

import httpx

from app.config import settings
from app.ontology import load_ontology
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship
from app.services import chroma_client, neo4j_client
from app.services.openai_client import embed_texts

_ontology = load_ontology()
ENTITY_CATEGORIES = _ontology.categories


async def _ensure_indexes() -> None:
    # Per-category case_id and key indexes
    for label in ENTITY_CATEGORIES:
        await neo4j_client.execute_write(
            f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.case_id)"
        )
        await neo4j_client.execute_write(
            f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.key)"
        )

    # Location spatial index
    await neo4j_client.execute_write(
        "CREATE INDEX IF NOT EXISTS FOR (n:Location) ON (n.latitude, n.longitude)"
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

_geocode_cache: dict[str, tuple[float, float] | None] = {}


async def _geocode(address: str) -> tuple[float, float] | None:
    if not settings.google_maps_api_key:
        return None
    if address in _geocode_cache:
        return _geocode_cache[address]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": settings.google_maps_api_key},
            )
            data = resp.json()
            if data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                result = (loc["lat"], loc["lng"])
                _geocode_cache[address] = result
                return result
    except Exception:
        pass

    _geocode_cache[address] = None
    return None


# ---------------------------------------------------------------------------
# Write entities
# ---------------------------------------------------------------------------

async def _write_entities(
    entities: list[ResolvedEntity],
    case_id: str,
    job_id: str,
) -> None:
    # Geocode locations
    for entity in entities:
        if entity.category == "Location" and not entity.is_existing:
            parts = [
                entity.properties.get("address", ""),
                entity.properties.get("city", ""),
                entity.properties.get("country", ""),
            ]
            address = ", ".join(p for p in parts if p) or entity.name
            coords = await _geocode(address)
            if coords:
                entity.properties["latitude"] = coords[0]
                entity.properties["longitude"] = coords[1]

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
            "job_id": job_id,
            "specific_type": e.specific_type,
        }
        for k, v in e.properties.items():
            if k in ("description", "aliases"):
                continue
            if isinstance(v, (str, int, float, bool)):
                props[k] = v
        by_cat.setdefault(e.category, []).append(props)

    batch_size = 500
    for category, nodes in by_cat.items():
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            query = (
                f"UNWIND $nodes AS node "
                f"MERGE (n:{category} {{id: node.id}}) "
                f"WITH n, node, n.aliases AS prev_aliases, "
                f"n.source_files AS prev_sf, n.source_quotes AS prev_sq "
                f"SET n += node, "
                f"n.aliases = reduce(acc = [], x IN (coalesce(prev_aliases, []) + coalesce(node.aliases, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END), "
                f"n.source_files = reduce(acc = [], x IN (coalesce(prev_sf, []) + coalesce(node.source_files, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END), "
                f"n.source_quotes = coalesce(prev_sq, []) + "
                f"[q IN coalesce(node.source_quotes, []) WHERE NOT q IN coalesce(prev_sq, [])]"
            )
            await neo4j_client.execute_write(query, {"nodes": batch})


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
        }
        for k, v in rel.properties.items():
            if isinstance(v, (str, int, float, bool)):
                props[k] = v

        safe_type = "".join(
            c if c.isalnum() or c == "_" else "_" for c in rel.type.upper()
        )
        by_type.setdefault(safe_type, []).append(props)

    batch_size = 500
    for rel_type, rels in by_type.items():
        for i in range(0, len(rels), batch_size):
            batch = rels[i : i + batch_size]
            query = (
                f"UNWIND $rels AS rel "
                f"MATCH (a {{id: rel.source_id}}) "
                f"MATCH (b {{id: rel.target_id}}) "
                f"MERGE (a)-[r:{rel_type} {{source_id: rel.source_id, target_id: rel.target_id}}]->(b) "
                f"WITH r, rel, r.source_files AS prev_sf, r.source_quotes AS prev_sq "
                f"SET r += rel, "
                f"r.source_files = reduce(acc = [], x IN (coalesce(prev_sf, []) + coalesce(rel.source_files, [])) "
                f"| CASE WHEN x IN acc THEN acc ELSE acc + x END), "
                f"r.source_quotes = coalesce(prev_sq, []) + "
                f"[q IN coalesce(rel.source_quotes, []) WHERE NOT q IN coalesce(prev_sq, [])]"
            )
            await neo4j_client.execute_write(query, {"rels": batch})


# ---------------------------------------------------------------------------
# Embed entities for RAG
# ---------------------------------------------------------------------------

async def _embed_entities(
    entities: list[ResolvedEntity],
    case_id: str,
) -> None:
    if not entities:
        return

    collection = chroma_client.get_or_create_collection("entities")

    texts = []
    for e in entities:
        desc = f"{e.category}: {e.name}"
        if e.properties.get("description"):
            desc += f" — {e.properties['description']}"
        if e.aliases:
            desc += f" (aliases: {', '.join(e.aliases)})"
        texts.append(desc)

    embeddings = await embed_texts(texts)

    # Upsert so existing entities get updated embeddings (merged aliases, etc.)
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
            }
            for e in entities
        ],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def write_graph(
    entities: list[ResolvedEntity],
    relationships: list[ResolvedRelationship],
    case_id: str,
    job_id: str,
) -> None:
    await _ensure_indexes()
    await _write_entities(entities, case_id, job_id)
    await _write_relationships(relationships, case_id)
    await _embed_entities(entities, case_id)
