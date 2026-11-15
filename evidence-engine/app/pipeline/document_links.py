"""Document links: each entity is MENTIONED_IN the Document node of every file it was read from (lx-retrieval C).

The backend's readers find an entity's documents through ``(entity)-[:MENTIONED_IN]->(doc:Document)``: the
Significant scope of chat (the passages of marked entities), the entities of a selected document, and the file
delete (an entity found only in a deleted file is hidden with it). Before this module no code wrote those links on
purpose: only links the extraction model happened to propose existed (13 over 40 documents in the demo case).

The links come from the entity's ``source_files`` (every file that contributed, accumulated across writes) and its
``source_locations`` (the evidence file id of the latest write). The Document node of a file is the case's existing
Document node with that file name (the ledger's projected statements are such nodes); when the case has none, one is
made with the graph's document key (the chunk ``doc_key``), the file name and its evidence file id.

The links carry ``link_origin = 'source_files'``: they are provenance, not a finding, so graph traversal for answers
and the agent's path search leave them out (backend ``services/neo4j/graph_service.py``, ``services/agent/tools.py``).
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from app.pipeline.chunk_embed import normalize_document_key
from app.services.graph_identity import ENTITY_LABEL_EXPRESSION

LINK_ORIGIN = "source_files"
BATCH = 200

ENSURE_DOCUMENTS = (
    "UNWIND $files AS f "
    "OPTIONAL MATCH (d:Document {case_id: $case_id}) WHERE d.name = f.name "
    "WITH f, count(d) AS existing WHERE existing = 0 "
    "MERGE (n:Document {case_id: $case_id, key: f.key}) "
    "ON CREATE SET n.id = f.key, n.name = f.name, n.evidence_file_id = f.evidence_file_id, "
    "n.created_from = $origin "
    "RETURN count(n) AS created"
)

WRITE_LINKS = (
    "UNWIND $links AS link "
    f"MATCH (e:{ENTITY_LABEL_EXPRESSION} {{id: link.entity_id, case_id: $case_id}}) WHERE NOT e:Document "
    "UNWIND link.files AS name "
    "MATCH (d:Document {case_id: $case_id}) WHERE d.name = name "
    "MERGE (e)-[m:MENTIONED_IN]->(d) "
    "ON CREATE SET m.case_id = $case_id, m.link_origin = $origin "
    "RETURN count(m) AS links"
)


def _locations(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [v for v in value or [] if isinstance(v, dict)] if isinstance(value, list) else []


def plan(entities: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(files, links) for entities given as {"id", "source_files", "source_locations"} (node properties).

    files: one per file name, with its document key and, when a location names it, its evidence file id.
    links: one per entity, the file names it was read from.
    """
    files: dict[str, dict[str, Any]] = {}
    links = []
    for entity in entities:
        names = [str(n).strip() for n in entity.get("source_files") or [] if str(n or "").strip()]
        for loc in _locations(entity.get("source_locations")):
            name = str(loc.get("source_file") or "").strip()
            if not name:
                continue
            if name not in names:
                names.append(name)
            if loc.get("source_document_id"):
                files.setdefault(name, {}).setdefault("evidence_file_id", str(loc["source_document_id"]))
        for name in names:
            key = normalize_document_key(name)
            if not key:
                continue
            entry = files.setdefault(name, {})
            entry.update(name=name, key=key)
            entry.setdefault("evidence_file_id", None)
        names = [n for n in dict.fromkeys(names) if normalize_document_key(n)]
        if names and entity.get("id"):
            links.append({"entity_id": entity["id"], "files": names})
    return [files[n] for n in files if files[n].get("key")], links


async def write_document_links(run, case_id: str, entities: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Make the Document nodes and MENTIONED_IN links of these entities. ``run(query, params)`` executes one write
    (the graph write's checkpointed writer, or a backfill session). Returns the planned counts."""
    files, links = plan(entities)
    for i in range(0, len(files), BATCH):
        await run(ENSURE_DOCUMENTS, {"files": files[i:i + BATCH], "case_id": case_id, "origin": LINK_ORIGIN})
    for i in range(0, len(links), BATCH):
        await run(WRITE_LINKS, {"links": links[i:i + BATCH], "case_id": case_id, "origin": LINK_ORIGIN})
    return {"files": len(files), "entities": len(links), "links": sum(len(l["files"]) for l in links)}
