import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings
from app.pipeline.extract_entities import RawEntity, RawRelationship
from app.services.chroma_client import (
    add_embeddings,
    delete_collection,
    get_or_create_collection,
    query_similar,
)
from app.ontology.schema_builder import get_resolution_schema
from app.services.openai_client import chat_completion, embed_texts

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@dataclass
class ResolvedEntity:
    id: str
    category: str
    specific_type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    source_quotes: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source_files: list[str] = field(default_factory=list)
    is_existing: bool = False
    summary: str = ""


@dataclass
class ResolvedRelationship:
    source_entity_id: str
    target_entity_id: str
    type: str
    detail: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    source_quotes: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Union-Find for merge groups
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    return " ".join(name.lower().strip().split())


def _token_overlap(a: str, b: str) -> float:
    ta = set(_normalize(a).split())
    tb = set(_normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


# ---------------------------------------------------------------------------
# Phase 1 — Blocking
# ---------------------------------------------------------------------------

def _blocking_candidates(entities: list[RawEntity]) -> list[tuple[int, int]]:
    by_cat: dict[str, list[int]] = {}
    for i, e in enumerate(entities):
        by_cat.setdefault(e.category, []).append(i)

    candidates: set[tuple[int, int]] = set()

    for indices in by_cat.values():
        # Index by normalized name
        name_map: dict[str, list[int]] = {}
        for idx in indices:
            norm = _normalize(entities[idx].name)
            name_map.setdefault(norm, []).append(idx)

        # Exact name matches
        for group in name_map.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    candidates.add((min(group[i], group[j]), max(group[i], group[j])))

        # Token overlap ≥ 50 %
        norms = list(name_map.keys())
        for i in range(len(norms)):
            for j in range(i + 1, len(norms)):
                if _token_overlap(norms[i], norms[j]) >= 0.5:
                    for a in name_map[norms[i]]:
                        for b in name_map[norms[j]]:
                            candidates.add((min(a, b), max(a, b)))

        # Alias ↔ name matches
        alias_map: dict[str, list[int]] = {}
        for idx in indices:
            for alias in entities[idx].properties.get("aliases", []) or []:
                alias_map.setdefault(_normalize(str(alias)), []).append(idx)

        for norm, alias_indices in alias_map.items():
            if norm in name_map:
                for ai in alias_indices:
                    for ni in name_map[norm]:
                        if ai != ni:
                            candidates.add((min(ai, ni), max(ai, ni)))

    return sorted(candidates)


# ---------------------------------------------------------------------------
# Phase 2 — Embedding similarity
# ---------------------------------------------------------------------------

async def _embedding_candidates(
    entities: list[RawEntity],
    existing: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    by_cat: dict[str, list[int]] = {}
    for i, e in enumerate(entities):
        by_cat.setdefault(e.category, []).append(i)

    new_pairs: set[tuple[int, int]] = set()

    for indices in by_cat.values():
        if len(indices) < 2:
            continue

        texts = []
        for idx in indices:
            e = entities[idx]
            desc = e.name
            if e.properties.get("description"):
                desc += f" — {e.properties['description']}"
            texts.append(desc)

        embeddings = await embed_texts(texts)

        col_name = f"_dedup_{uuid.uuid4().hex[:8]}"
        col = get_or_create_collection(col_name)
        try:
            add_embeddings(
                col,
                ids=[str(idx) for idx in indices],
                embeddings=embeddings,
                documents=texts,
                metadatas=[{"i": idx} for idx in indices],
            )
            for k, idx in enumerate(indices):
                results = query_similar(
                    col,
                    query_embeddings=[embeddings[k]],
                    n_results=min(6, len(indices)),
                )
                if not results or not results.get("ids"):
                    continue
                for nid, dist in zip(
                    results["ids"][0], results.get("distances", [[]])[0]
                ):
                    n = int(nid)
                    if n != idx and dist < 0.15:
                        pair = (min(idx, n), max(idx, n))
                        if pair not in existing:
                            new_pairs.add(pair)
        finally:
            delete_collection(col_name)

    return sorted(new_pairs)


# ---------------------------------------------------------------------------
# Phase 3 — LLM confirmation
# ---------------------------------------------------------------------------

async def _llm_confirm(
    entities: list[RawEntity],
    pairs: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if not pairs:
        return []

    template = (PROMPTS_DIR / "entity_resolution.txt").read_text(encoding="utf-8")
    confirmed: list[tuple[int, int]] = []
    batch_size = 20

    for i in range(0, len(pairs), batch_size):
        batch = pairs[i : i + batch_size]
        pairs_json = json.dumps(
            [
                {
                    "pair_index": j,
                    "entity_a": {
                        "id": entities[a].temp_id,
                        "category": entities[a].category,
                        "name": entities[a].name,
                        "specific_type": entities[a].specific_type,
                        "properties": entities[a].properties,
                    },
                    "entity_b": {
                        "id": entities[b].temp_id,
                        "category": entities[b].category,
                        "name": entities[b].name,
                        "specific_type": entities[b].specific_type,
                        "properties": entities[b].properties,
                    },
                }
                for j, (a, b) in enumerate(batch)
            ],
            indent=2,
        )

        prompt = template.format(pairs_json=pairs_json)
        response = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an entity resolution expert. "
                        "Respond with valid JSON matching the provided schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=get_resolution_schema(),
        )

        data = json.loads(response)
        for d in data.get("decisions", []):
            idx = d.get("pair_index", -1)
            if 0 <= idx < len(batch) and d.get("decision") == "MERGE":
                confirmed.append(batch[idx])

    return confirmed


# ---------------------------------------------------------------------------
# Merge execution
# ---------------------------------------------------------------------------

def _apply_merges(
    entities: list[RawEntity],
    merge_pairs: list[tuple[int, int]],
) -> tuple[list[ResolvedEntity], dict[str, str]]:
    uf = UnionFind()
    for e in entities:
        uf.find(e.temp_id)
    for a, b in merge_pairs:
        uf.union(entities[a].temp_id, entities[b].temp_id)

    groups: dict[str, list[int]] = {}
    for i, e in enumerate(entities):
        groups.setdefault(uf.find(e.temp_id), []).append(i)

    resolved: list[ResolvedEntity] = []
    id_map: dict[str, str] = {}

    for indices in groups.values():
        final_id = str(uuid.uuid4())
        primary_idx = max(
            indices, key=lambda i: (entities[i].confidence, len(entities[i].properties))
        )
        primary = entities[primary_idx]

        all_names: set[str] = set()
        all_quotes: list[str] = []
        all_files: set[str] = set()
        merged_props = dict(primary.properties)

        for idx in indices:
            e = entities[idx]
            id_map[e.temp_id] = final_id
            all_names.add(e.name)
            all_quotes.append(e.source_quote)
            all_files.add(e.source_file)
            for k, v in e.properties.items():
                if k not in merged_props or not merged_props[k]:
                    merged_props[k] = v
            for alias in e.properties.get("aliases", []) or []:
                all_names.add(str(alias))

        all_names.discard(primary.name)

        resolved.append(
            ResolvedEntity(
                id=final_id,
                category=primary.category,
                specific_type=primary.specific_type,
                name=primary.name,
                aliases=sorted(all_names),
                properties=merged_props,
                source_quotes=[q for q in all_quotes if q],
                confidence=max(entities[i].confidence for i in indices),
                source_files=sorted(all_files),
            )
        )

    return resolved, id_map


# ---------------------------------------------------------------------------
# Cross-job deduplication
# ---------------------------------------------------------------------------

async def _cross_job_dedup(
    entities: list[ResolvedEntity],
    case_id: str,
) -> dict[str, str]:
    """Returns mapping of new-entity-id → existing-entity-id for confirmed merges."""
    col_name = f"case_{case_id}_entities"
    try:
        col = get_or_create_collection(col_name)
        if col.count() == 0:
            return {}
    except Exception:
        return {}

    texts = []
    for e in entities:
        desc = f"{e.category}: {e.name}"
        if e.properties.get("description"):
            desc += f" — {e.properties['description']}"
        texts.append(desc)

    if not texts:
        return {}

    embeddings = await embed_texts(texts)

    candidate_pairs: list[tuple[int, str]] = []  # (new_idx, existing_id)
    for k, (emb, entity) in enumerate(zip(embeddings, entities)):
        results = query_similar(
            col,
            query_embeddings=[emb],
            n_results=5,
            where={"category": entity.category},
        )
        if not results or not results.get("ids") or not results["ids"][0]:
            continue
        for existing_id, dist in zip(
            results["ids"][0], results.get("distances", [[]])[0]
        ):
            if dist < 0.15:
                candidate_pairs.append((k, existing_id))

    if not candidate_pairs:
        return {}

    # Fetch existing entity metadata
    existing_ids = list({eid for _, eid in candidate_pairs})
    existing_data = col.get(ids=existing_ids, include=["documents", "metadatas"])
    existing_map: dict[str, dict] = {}
    if existing_data and existing_data["ids"]:
        for eid, doc, meta in zip(
            existing_data["ids"],
            existing_data.get("documents") or [""] * len(existing_data["ids"]),
            existing_data.get("metadatas") or [{}] * len(existing_data["ids"]),
        ):
            existing_map[eid] = {"id": eid, "name": (meta or {}).get("name", ""), "document": doc}

    # LLM confirmation
    template = (PROMPTS_DIR / "entity_resolution.txt").read_text(encoding="utf-8")
    merge_map: dict[str, str] = {}
    batch_size = 20

    for i in range(0, len(candidate_pairs), batch_size):
        batch = candidate_pairs[i : i + batch_size]
        pairs_json = json.dumps(
            [
                {
                    "pair_index": j,
                    "entity_a": {
                        "id": entities[new_idx].id,
                        "category": entities[new_idx].category,
                        "name": entities[new_idx].name,
                        "specific_type": entities[new_idx].specific_type,
                    },
                    "entity_b": existing_map.get(existing_id, {"id": existing_id}),
                }
                for j, (new_idx, existing_id) in enumerate(batch)
            ],
            indent=2,
        )
        prompt = template.format(pairs_json=pairs_json)
        response = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an entity resolution expert. "
                        "Respond with valid JSON matching the provided schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=get_resolution_schema(),
        )
        data = json.loads(response)
        for d in data.get("decisions", []):
            idx = d.get("pair_index", -1)
            if 0 <= idx < len(batch) and d.get("decision") == "MERGE":
                new_idx, existing_id = batch[idx]
                entity_id = entities[new_idx].id
                if entity_id not in merge_map:
                    merge_map[entity_id] = existing_id

    return merge_map


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def resolve_entities(
    raw_entities: list[RawEntity],
    raw_relationships: list[RawRelationship],
    case_id: str,
) -> tuple[list[ResolvedEntity], list[ResolvedRelationship]]:
    if not raw_entities:
        return [], []

    # Phase 1: Blocking
    blocking_pairs = _blocking_candidates(raw_entities)

    # Phase 2: Embedding similarity
    embedding_pairs = await _embedding_candidates(raw_entities, set(blocking_pairs))

    all_candidates = blocking_pairs + embedding_pairs

    # Phase 3: LLM confirmation
    merge_pairs = await _llm_confirm(raw_entities, all_candidates)

    # Apply intra-file merges
    resolved_entities, id_map = _apply_merges(raw_entities, merge_pairs)

    # Cross-job dedup
    cross_merges = await _cross_job_dedup(resolved_entities, case_id)

    # Apply cross-job merges
    for entity in resolved_entities:
        if entity.id in cross_merges:
            old_id = entity.id
            entity.id = cross_merges[old_id]
            entity.is_existing = True

    # Chain id_map through cross-job merges
    for temp_id in id_map:
        if id_map[temp_id] in cross_merges:
            id_map[temp_id] = cross_merges[id_map[temp_id]]

    # Remap relationships
    resolved_relationships: list[ResolvedRelationship] = []
    for r in raw_relationships:
        src = id_map.get(r.source_entity_id)
        tgt = id_map.get(r.target_entity_id)
        if src and tgt:
            resolved_relationships.append(
                ResolvedRelationship(
                    source_entity_id=src,
                    target_entity_id=tgt,
                    type=r.type,
                    detail=r.detail,
                    properties=r.properties,
                    source_quotes=[r.source_quote] if r.source_quote else [],
                    confidence=r.confidence,
                    source_files=[r.source_file] if r.source_file else [],
                )
            )

    # Confidence filtering
    resolved_entities, resolved_relationships = _filter_by_confidence(
        resolved_entities, resolved_relationships
    )

    return resolved_entities, resolved_relationships


def _filter_by_confidence(
    entities: list[ResolvedEntity],
    relationships: list[ResolvedRelationship],
) -> tuple[list[ResolvedEntity], list[ResolvedRelationship]]:
    entity_threshold = settings.entity_confidence_threshold
    rel_threshold = settings.relationship_confidence_threshold

    kept_entities = [e for e in entities if e.confidence >= entity_threshold]
    kept_ids = {e.id for e in kept_entities}

    kept_rels = [
        r for r in relationships
        if r.confidence >= rel_threshold
        and r.source_entity_id in kept_ids
        and r.target_entity_id in kept_ids
    ]

    dropped_e = len(entities) - len(kept_entities)
    dropped_r = len(relationships) - len(kept_rels)
    if dropped_e or dropped_r:
        logger.info(
            "Confidence filter: dropped %d entities (<%s) and %d relationships (<%s or orphaned)",
            dropped_e, entity_threshold, dropped_r, rel_threshold,
        )

    return kept_entities, kept_rels
