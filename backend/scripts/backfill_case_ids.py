"""
Backfill case_id for Neo4j and ChromaDB metadata.

The source of truth for evidence files is Postgres. This script intentionally
does not read evidence.json or any other JSON file-backed storage.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple


project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from postgres.models.evidence import EvidenceFile
from postgres.session import get_background_session
from services.neo4j_service import neo4j_service


EVIDENCE_ROOT_DIR = project_root / "ingestion" / "data"
BATCH_SIZE = 500


def _add_lookup(lookup: Dict[str, str], ambiguous: set[str], key: str | None, case_id: str) -> None:
    if not key or not case_id or key in ambiguous:
        return
    existing = lookup.get(key)
    if existing and existing != case_id:
        lookup.pop(key, None)
        ambiguous.add(key)
        return
    lookup[key] = case_id


def _build_evidence_lookup() -> Tuple[Dict[str, str], set[str]]:
    """Build filename -> case_id mappings from Postgres evidence rows."""
    lookup: Dict[str, str] = {}
    ambiguous: set[str] = set()
    with get_background_session() as db:
        for record in db.query(EvidenceFile).all():
            case_id = str(record.case_id) if record.case_id else ""
            stored_path = Path(record.stored_path) if record.stored_path else None

            if record.original_filename and case_id:
                _add_lookup(lookup, ambiguous, record.original_filename, case_id)
            if stored_path and case_id:
                _add_lookup(lookup, ambiguous, stored_path.name, case_id)
            if record.original_filename and not case_id and stored_path:
                try:
                    relative = stored_path.relative_to(EVIDENCE_ROOT_DIR)
                    if len(relative.parts) >= 2 and relative.parts[0]:
                        _add_lookup(lookup, ambiguous, record.original_filename, relative.parts[0])
                except ValueError:
                    pass
    return lookup, ambiguous


def _scan_evidence_dirs() -> Tuple[Dict[str, str], set[str]]:
    """Build filename -> case_id mappings from the upload directory layout."""
    lookup: Dict[str, str] = {}
    ambiguous: set[str] = set()
    if not EVIDENCE_ROOT_DIR.exists():
        return lookup, ambiguous

    for case_dir in EVIDENCE_ROOT_DIR.iterdir():
        if not case_dir.is_dir():
            continue
        for file_path in case_dir.iterdir():
            if file_path.is_file():
                _add_lookup(lookup, ambiguous, file_path.name, case_dir.name)
    return lookup, ambiguous


def _update_chroma_batch(collection, ids: list[str], metadatas: list[dict], dry_run: bool) -> int:
    if not ids:
        return 0
    if not dry_run:
        collection.update(ids=ids, metadatas=metadatas)
    return len(ids)


def backfill_case_ids(
    dry_run: bool = False,
    include_entities: bool = True,
    include_vector_db: bool = True,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> Dict:
    """Backfill missing case_id metadata without touching file-backed JSON storage."""

    def log(level: str, message: str) -> None:
        print(f"[{level.upper()}] {message}")
        if log_callback:
            log_callback(level, message)

    start_time = time.time()
    log("info", "Backfilling missing case_id values from Postgres evidence metadata")
    if dry_run:
        log("info", "Dry-run mode: no writes will be made")

    evidence_lookup, evidence_ambiguous = _build_evidence_lookup()
    dir_lookup, dir_ambiguous = _scan_evidence_dirs()
    combined_lookup = dict(dir_lookup)
    ambiguous_names = set(dir_ambiguous) | set(evidence_ambiguous)
    for name, case_id in evidence_lookup.items():
        _add_lookup(combined_lookup, ambiguous_names, name, case_id)
    log("info", f"Resolved {len(combined_lookup)} filename to case_id mappings")
    if ambiguous_names:
        log("warning", f"Skipping {len(ambiguous_names)} ambiguous filename mappings")

    doc_stats = {
        "total_missing": 0,
        "updated": 0,
        "not_resolved": 0,
        "not_resolved_names": [],
    }
    entity_stats = {"total_missing": 0, "updated": 0, "not_resolved": 0}
    vector_doc_stats = {"total": 0, "already_has_case_id": 0, "updated": 0, "not_resolved": 0}
    vector_chunk_stats = {"total": 0, "already_has_case_id": 0, "updated": 0, "not_resolved": 0}
    vector_entity_stats = {"total": 0, "already_has_case_id": 0, "updated": 0, "not_resolved": 0}

    try:
        docs_missing = neo4j_service.run_cypher(
            """
            MATCH (d:Document)
            WHERE d.case_id IS NULL OR d.case_id = ''
            RETURN d.id AS id, d.key AS key, d.name AS name
            ORDER BY d.name
            """
        )
        doc_stats["total_missing"] = len(docs_missing)
        log("info", f"Found {len(docs_missing)} Document nodes missing case_id")

        for doc in docs_missing:
            doc_id = doc.get("id")
            doc_name = doc.get("name") or ""
            filename = Path(doc_name).name
            if doc_name in ambiguous_names or filename in ambiguous_names:
                doc_stats["not_resolved"] += 1
                if doc_name:
                    doc_stats["not_resolved_names"].append(f"{doc_name} (ambiguous filename)")
                continue
            resolved_case_id = combined_lookup.get(doc_name) or combined_lookup.get(filename)
            if not doc_id or not resolved_case_id:
                doc_stats["not_resolved"] += 1
                if doc_name:
                    doc_stats["not_resolved_names"].append(doc_name)
                continue
            if not dry_run:
                neo4j_service.run_cypher(
                    "MATCH (d:Document {id: $doc_id}) SET d.case_id = $case_id",
                    {"doc_id": doc_id, "case_id": resolved_case_id},
                )
            doc_stats["updated"] += 1
    except Exception as exc:
        log("error", f"Error updating Neo4j Document case_id values: {exc}")
        return {"status": "error", "reason": str(exc)}

    if include_entities:
        try:
            entities_missing = neo4j_service.run_cypher(
                """
                MATCH (e)
                WHERE NOT e:Document
                  AND (e.case_id IS NULL OR e.case_id = '')
                OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
                WHERE d.case_id IS NOT NULL AND d.case_id <> ''
                RETURN e.id AS id, e.key AS key, e.name AS name,
                       labels(e)[0] AS entity_type,
                       collect(DISTINCT d.case_id) AS doc_case_ids
                ORDER BY e.name
                """
            )
            entity_stats["total_missing"] = len(entities_missing)
            log("info", f"Found {len(entities_missing)} non-Document nodes missing case_id")

            for entity in entities_missing:
                entity_id = entity.get("id")
                doc_case_ids = [case_id for case_id in entity.get("doc_case_ids", []) if case_id]
                distinct_case_ids = sorted(set(doc_case_ids))
                if not entity_id or len(distinct_case_ids) != 1:
                    entity_stats["not_resolved"] += 1
                    continue
                if not dry_run:
                    neo4j_service.run_cypher(
                        "MATCH (e {id: $entity_id}) SET e.case_id = $case_id",
                        {"entity_id": entity_id, "case_id": distinct_case_ids[0]},
                    )
                entity_stats["updated"] += 1
        except Exception as exc:
            log("error", f"Error updating Neo4j entity case_id values: {exc}")

    if include_vector_db:
        try:
            from services.vector_db_service import vector_db_service
        except ImportError as exc:
            vector_db_service = None
            log("warning", f"ChromaDB import failed; skipping vector metadata: {exc}")

        if vector_db_service is not None:
            neo4j_docs = neo4j_service.run_cypher(
                """
                MATCH (d:Document)
                WHERE d.case_id IS NOT NULL AND d.case_id <> ''
                RETURN d.id AS id, d.name AS name, d.case_id AS case_id
                """
            )
            doc_id_to_case_id = {
                doc.get("id"): doc.get("case_id")
                for doc in neo4j_docs
                if doc.get("id") and doc.get("case_id")
            }
            doc_name_to_case_id = {
                doc.get("name"): doc.get("case_id")
                for doc in neo4j_docs
                if doc.get("name") and doc.get("case_id")
            }

            chunks = vector_db_service.chunk_collection.get(include=["metadatas"])
            chunk_ids = chunks.get("ids", [])
            chunk_metas = chunks.get("metadatas", [])
            vector_chunk_stats["total"] = len(chunk_ids)
            batch_ids: list[str] = []
            batch_metas: list[dict] = []
            for chunk_id, meta in zip(chunk_ids, chunk_metas):
                meta = meta or {}
                if meta.get("case_id"):
                    vector_chunk_stats["already_has_case_id"] += 1
                    continue
                doc_name = meta.get("doc_name")
                doc_filename = Path(str(doc_name)).name if doc_name else ""
                if doc_name in ambiguous_names or doc_filename in ambiguous_names:
                    vector_chunk_stats["not_resolved"] += 1
                    continue
                resolved = (
                    doc_id_to_case_id.get(meta.get("doc_id"))
                    or doc_name_to_case_id.get(doc_name)
                    or combined_lookup.get(doc_name)
                    or combined_lookup.get(doc_filename)
                )
                if not resolved:
                    vector_chunk_stats["not_resolved"] += 1
                    continue
                batch_ids.append(chunk_id)
                batch_metas.append({**meta, "case_id": resolved})
                if len(batch_ids) >= BATCH_SIZE:
                    vector_chunk_stats["updated"] += _update_chroma_batch(
                        vector_db_service.chunk_collection, batch_ids, batch_metas, dry_run
                    )
                    batch_ids, batch_metas = [], []
            vector_chunk_stats["updated"] += _update_chroma_batch(
                vector_db_service.chunk_collection, batch_ids, batch_metas, dry_run
            )

            if include_entities:
                neo4j_entities = neo4j_service.run_cypher(
                    """
                    MATCH (e)
                    WHERE NOT e:Document AND e.case_id IS NOT NULL AND e.case_id <> ''
                    RETURN e.key AS key, e.case_id AS case_id
                    """
                )
                entity_key_to_case_id = {
                    entity.get("key"): entity.get("case_id")
                    for entity in neo4j_entities
                    if entity.get("key") and entity.get("case_id")
                }
                entities = vector_db_service.entity_collection.get(include=["metadatas"])
                entity_ids = entities.get("ids", [])
                entity_metas = entities.get("metadatas", [])
                vector_entity_stats["total"] = len(entity_ids)
                batch_ids, batch_metas = [], []
                for entity_id, meta in zip(entity_ids, entity_metas):
                    meta = meta or {}
                    if meta.get("case_id"):
                        vector_entity_stats["already_has_case_id"] += 1
                        continue
                    resolved = entity_key_to_case_id.get(entity_id)
                    if not resolved:
                        vector_entity_stats["not_resolved"] += 1
                        continue
                    batch_ids.append(entity_id)
                    batch_metas.append({**meta, "case_id": resolved})
                    if len(batch_ids) >= BATCH_SIZE:
                        vector_entity_stats["updated"] += _update_chroma_batch(
                            vector_db_service.entity_collection, batch_ids, batch_metas, dry_run
                        )
                        batch_ids, batch_metas = [], []
                vector_entity_stats["updated"] += _update_chroma_batch(
                    vector_db_service.entity_collection, batch_ids, batch_metas, dry_run
                )

    elapsed = time.time() - start_time
    return {
        "status": "complete",
        "stats": {
            "documents": doc_stats,
            "entities": entity_stats,
            "vector_documents": vector_doc_stats,
            "vector_chunks": vector_chunk_stats,
            "vector_entities": vector_entity_stats,
        },
        "elapsed_seconds": elapsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill case_id metadata from Postgres evidence rows")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-entities", action="store_true", default=True)
    parser.add_argument("--docs-only", action="store_true")
    parser.add_argument("--include-vector-db", action="store_true", default=True)
    parser.add_argument("--neo4j-only", action="store_true")
    args = parser.parse_args()

    result = backfill_case_ids(
        dry_run=args.dry_run,
        include_entities=not args.docs_only,
        include_vector_db=not args.neo4j_only,
    )
    sys.exit(1 if result.get("status") == "error" else 0)


if __name__ == "__main__":
    main()
