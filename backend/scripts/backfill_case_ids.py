"""
Backfill case_id for documents and entities in Neo4j and ChromaDB.

This script finds Document and entity nodes missing the case_id property and
attempts to resolve it from:

  1. Evidence storage records (evidence.json) — maps original_filename → case_id
  2. File path parsing — files stored under ingestion/data/<case_id>/filename
  3. Relationship traversal — entities inherit case_id from connected Documents

Phases:
  1. Neo4j Documents — resolve case_id from evidence storage
  2. Neo4j Entities — inherit case_id from connected Documents
  3. ChromaDB Documents — update metadata with case_id (matched via doc_id/filename)
  4. ChromaDB Chunks — update metadata with case_id (inherited from parent doc)
  5. ChromaDB Entities — update metadata with case_id (from Neo4j)

No LLM calls. No re-embedding. Pure metadata updates.

Usage:
    python backend/scripts/backfill_case_ids.py --dry-run
    python backend/scripts/backfill_case_ids.py
    python backend/scripts/backfill_case_ids.py --include-entities
    python backend/scripts/backfill_case_ids.py --include-vector-db
    python backend/scripts/backfill_case_ids.py --neo4j-only
"""

import sys
from pathlib import Path
from typing import Dict, Optional
import time

# Add project root to path
project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"

# Add backend directory FIRST so config imports resolve correctly
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import services
from services.neo4j_service import neo4j_service
from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR


def _build_evidence_lookup() -> Dict[str, str]:
    """
    Build a lookup from original_filename → case_id using evidence storage.
    Also parses case_id from stored_path as a fallback.

    Returns:
        Dict mapping document name to case_id
    """
    lookup = {}
    all_evidence = evidence_storage.get_all()

    for record in all_evidence:
        original_filename = record.get("original_filename", "")
        case_id = record.get("case_id", "")

        if original_filename and case_id:
            lookup[original_filename] = case_id
            continue

        # Fallback: parse case_id from stored_path
        # stored_path looks like: /path/to/ingestion/data/<case_id>/filename
        if original_filename and not case_id:
            stored_path_str = record.get("stored_path", "")
            if stored_path_str:
                stored_path = Path(stored_path_str)
                # Try to extract case_id from the directory structure
                # The parent directory of the file is the case_id directory
                try:
                    # Check if parent is under EVIDENCE_ROOT_DIR
                    relative = stored_path.relative_to(EVIDENCE_ROOT_DIR)
                    parts = relative.parts
                    if len(parts) >= 2:
                        # parts[0] is case_id, parts[-1] is filename
                        parsed_case_id = parts[0]
                        if parsed_case_id:
                            lookup[original_filename] = parsed_case_id
                except (ValueError, IndexError):
                    pass

    return lookup


def _scan_evidence_dirs() -> Dict[str, str]:
    """
    Scan the evidence root directory to build filename → case_id mapping.
    This catches files that might not be in evidence.json.

    Returns:
        Dict mapping filename to case_id (from directory name)
    """
    lookup = {}
    if not EVIDENCE_ROOT_DIR.exists():
        return lookup

    for case_dir in EVIDENCE_ROOT_DIR.iterdir():
        if case_dir.is_dir():
            case_id = case_dir.name
            for file_path in case_dir.iterdir():
                if file_path.is_file():
                    lookup[file_path.name] = case_id

    return lookup


def backfill_case_ids(
    dry_run: bool = False,
    include_entities: bool = True,
    include_vector_db: bool = True,
    log_callback=None,
) -> Dict:
    """
    Backfill case_id for documents and entities missing it in Neo4j and ChromaDB.

    Strategy:
    1. Neo4j Documents: Look up case_id from evidence storage or file path
    2. Neo4j Entities: Inherit case_id from connected Document nodes
    3. ChromaDB Documents: Update metadata with case_id (matched via doc_id/filename)
    4. ChromaDB Chunks: Update metadata with case_id (inherited from parent doc)
    5. ChromaDB Entities: Update metadata with case_id (from Neo4j)

    Args:
        dry_run: If True, only report what would be done without making changes
        include_entities: If True, also backfill entities (default True)
        include_vector_db: If True, also backfill ChromaDB metadata (default True)
        log_callback: Optional callback for progress updates (level, message)

    Returns:
        Dictionary with statistics
    """
    def log(level: str, message: str):
        print(f"[{level.upper()}] {message}")
        if log_callback:
            log_callback(level, message)

    log("info", "=" * 60)
    log("info", "Backfilling case_id for Documents and Entities in Neo4j")
    log("info", "=" * 60)

    if dry_run:
        log("info", "[DRY RUN MODE] - No changes will be made\n")

    start_time = time.time()

    # Build lookups from evidence storage and directory scan
    log("info", "Building case_id lookup from evidence storage...")
    evidence_lookup = _build_evidence_lookup()
    log("info", f"  Found {len(evidence_lookup)} filename→case_id mappings from evidence records")

    dir_lookup = _scan_evidence_dirs()
    log("info", f"  Found {len(dir_lookup)} filename→case_id mappings from directory scan")

    # Merge lookups (evidence records take priority)
    combined_lookup = {**dir_lookup, **evidence_lookup}
    log("info", f"  Combined lookup: {len(combined_lookup)} unique filename→case_id mappings")

    # ── Phase 1: Documents ───────────────────────────────────────────────
    log("info", "\n" + "-" * 60)
    log("info", "Phase 1: Backfilling case_id on Document nodes")
    log("info", "-" * 60)

    doc_stats = {
        "total_missing": 0,
        "updated": 0,
        "not_resolved": 0,
        "not_resolved_names": [],
    }

    try:
        # Find documents missing case_id
        doc_cypher = """
        MATCH (d:Document)
        WHERE d.case_id IS NULL OR d.case_id = ''
        RETURN d.id AS id, d.key AS key, d.name AS name
        ORDER BY d.name
        """
        docs_missing = neo4j_service.run_cypher(doc_cypher)
        doc_stats["total_missing"] = len(docs_missing)
        log("info", f"Found {len(docs_missing)} documents missing case_id")

        for i, doc in enumerate(docs_missing, 1):
            doc_id = doc.get("id")
            doc_name = doc.get("name", "")
            doc_key = doc.get("key", "")

            if not doc_id:
                continue

            # Try to resolve case_id
            resolved_case_id = combined_lookup.get(doc_name)

            if not resolved_case_id:
                log("warning", f"  [{i}/{len(docs_missing)}] Cannot resolve case_id for: {doc_name}")
                doc_stats["not_resolved"] += 1
                doc_stats["not_resolved_names"].append(doc_name)
                continue

            if dry_run:
                log("info", f"  [{i}/{len(docs_missing)}] [DRY RUN] Would set case_id='{resolved_case_id}' on: {doc_name}")
                doc_stats["updated"] += 1
            else:
                try:
                    neo4j_service.run_cypher(
                        "MATCH (d:Document {id: $doc_id}) SET d.case_id = $case_id",
                        {"doc_id": doc_id, "case_id": resolved_case_id}
                    )
                    log("info", f"  [{i}/{len(docs_missing)}] Set case_id='{resolved_case_id}' on: {doc_name}")
                    doc_stats["updated"] += 1
                except Exception as e:
                    log("error", f"  [{i}/{len(docs_missing)}] Failed to update {doc_name}: {e}")
                    doc_stats["not_resolved"] += 1

    except Exception as e:
        log("error", f"Error querying Neo4j for documents: {e}")
        return {"status": "error", "reason": str(e)}

    # ── Phase 2: Entities ────────────────────────────────────────────────
    entity_stats = {
        "total_missing": 0,
        "updated": 0,
        "not_resolved": 0,
    }

    if include_entities:
        log("info", "\n" + "-" * 60)
        log("info", "Phase 2: Backfilling case_id on Entity nodes")
        log("info", "-" * 60)

        try:
            # Find entities missing case_id that are connected to documents WITH case_id
            # This uses the MENTIONED_IN relationship to inherit case_id from documents
            entity_cypher = """
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
            entities_missing = neo4j_service.run_cypher(entity_cypher)
            entity_stats["total_missing"] = len(entities_missing)
            log("info", f"Found {len(entities_missing)} entities missing case_id")

            for i, ent in enumerate(entities_missing, 1):
                ent_id = ent.get("id")
                ent_name = ent.get("name", "")
                ent_key = ent.get("key", "")
                doc_case_ids = ent.get("doc_case_ids", [])

                if not ent_id:
                    continue

                # Filter out empty strings
                doc_case_ids = [cid for cid in doc_case_ids if cid]

                if not doc_case_ids:
                    entity_stats["not_resolved"] += 1
                    if i <= 20:  # Only log first 20
                        log("warning", f"  [{i}/{len(entities_missing)}] No connected document with case_id for: {ent_name}")
                    continue

                # Use the first (most common) case_id if entity connects to multiple cases
                # In most cases there will be exactly one
                resolved_case_id = doc_case_ids[0]

                if dry_run:
                    log("info", f"  [{i}/{len(entities_missing)}] [DRY RUN] Would set case_id='{resolved_case_id}' on: {ent_name} ({ent.get('entity_type', 'Unknown')})")
                    entity_stats["updated"] += 1
                else:
                    try:
                        neo4j_service.run_cypher(
                            "MATCH (e {id: $ent_id}) SET e.case_id = $case_id",
                            {"ent_id": ent_id, "case_id": resolved_case_id}
                        )
                        entity_stats["updated"] += 1
                        if i <= 50 or i % 100 == 0:  # Log first 50 and every 100th
                            log("info", f"  [{i}/{len(entities_missing)}] Set case_id='{resolved_case_id}' on: {ent_name}")
                    except Exception as e:
                        log("error", f"  [{i}/{len(entities_missing)}] Failed to update {ent_name}: {e}")
                        entity_stats["not_resolved"] += 1

                # Progress update every 100
                if i % 100 == 0:
                    elapsed = time.time() - start_time
                    log("info", f"  Progress: {i}/{len(entities_missing)} entities processed ({elapsed:.1f}s)")

        except Exception as e:
            log("error", f"Error querying Neo4j for entities: {e}")

    # ── Phase 3–5: ChromaDB (Vector DB) ─────────────────────────────────
    vector_doc_stats = {
        "total": 0,
        "already_has_case_id": 0,
        "updated": 0,
        "not_resolved": 0,
    }
    vector_chunk_stats = {
        "total": 0,
        "already_has_case_id": 0,
        "updated": 0,
        "not_resolved": 0,
    }
    vector_entity_stats = {
        "total": 0,
        "already_has_case_id": 0,
        "updated": 0,
        "not_resolved": 0,
    }

    if include_vector_db:
        try:
            from services.vector_db_service import vector_db_service
            if vector_db_service is None:
                log("warning", "\nChromaDB not available — skipping vector DB phases")
            else:
                # Build a doc_id → case_id lookup from Neo4j (the source of truth after phases 1-2)
                log("info", "\nBuilding doc_id → case_id lookup from Neo4j...")
                try:
                    neo4j_doc_lookup_cypher = """
                    MATCH (d:Document)
                    WHERE d.case_id IS NOT NULL AND d.case_id <> ''
                    RETURN d.id AS id, d.name AS name, d.case_id AS case_id
                    """
                    neo4j_docs = neo4j_service.run_cypher(neo4j_doc_lookup_cypher)
                    doc_id_to_case_id = {}
                    doc_name_to_case_id = {}
                    for doc in neo4j_docs:
                        did = doc.get("id")
                        dname = doc.get("name", "")
                        cid = doc.get("case_id", "")
                        if did and cid:
                            doc_id_to_case_id[did] = cid
                        if dname and cid:
                            doc_name_to_case_id[dname] = cid
                    log("info", f"  {len(doc_id_to_case_id)} doc_id→case_id mappings from Neo4j")
                    log("info", f"  {len(doc_name_to_case_id)} doc_name→case_id mappings from Neo4j")
                except Exception as e:
                    log("error", f"Failed to build Neo4j doc lookup: {e}")
                    doc_id_to_case_id = {}
                    doc_name_to_case_id = {}

                # Also build entity_key → case_id from Neo4j
                entity_key_to_case_id = {}
                if include_entities:
                    try:
                        neo4j_entity_cypher = """
                        MATCH (e)
                        WHERE NOT e:Document AND e.case_id IS NOT NULL AND e.case_id <> ''
                        RETURN e.key AS key, e.case_id AS case_id
                        """
                        neo4j_entities = neo4j_service.run_cypher(neo4j_entity_cypher)
                        for ent in neo4j_entities:
                            ekey = ent.get("key")
                            ecid = ent.get("case_id")
                            if ekey and ecid:
                                entity_key_to_case_id[ekey] = ecid
                        log("info", f"  {len(entity_key_to_case_id)} entity_key→case_id mappings from Neo4j")
                    except Exception as e:
                        log("error", f"Failed to build Neo4j entity lookup: {e}")

                # ── Phase 3: ChromaDB Documents ──────────────────────────
                log("info", "\n" + "-" * 60)
                log("info", "Phase 3: Backfilling case_id on ChromaDB Document metadata")
                log("info", "-" * 60)

                try:
                    doc_collection = vector_db_service.collection
                    all_docs = doc_collection.get(include=["metadatas"])
                    chroma_doc_ids = all_docs.get("ids", [])
                    chroma_doc_metas = all_docs.get("metadatas", [])
                    vector_doc_stats["total"] = len(chroma_doc_ids)
                    log("info", f"Found {len(chroma_doc_ids)} documents in ChromaDB")

                    batch_ids = []
                    batch_metas = []
                    BATCH_SIZE = 50

                    for i, (doc_id, meta) in enumerate(zip(chroma_doc_ids, chroma_doc_metas), 1):
                        meta = meta or {}

                        if meta.get("case_id") and meta["case_id"] != "":
                            vector_doc_stats["already_has_case_id"] += 1
                            continue

                        # Resolve case_id: try doc_id directly, then filename from metadata
                        resolved = doc_id_to_case_id.get(doc_id)
                        if not resolved:
                            filename = meta.get("filename", "")
                            if filename:
                                resolved = doc_name_to_case_id.get(filename) or combined_lookup.get(filename)

                        if not resolved:
                            vector_doc_stats["not_resolved"] += 1
                            continue

                        batch_ids.append(doc_id)
                        batch_metas.append({**meta, "case_id": resolved})

                        if len(batch_ids) >= BATCH_SIZE:
                            if dry_run:
                                vector_doc_stats["updated"] += len(batch_ids)
                            else:
                                try:
                                    doc_collection.update(ids=batch_ids, metadatas=batch_metas)
                                    vector_doc_stats["updated"] += len(batch_ids)
                                except Exception as e:
                                    log("error", f"  Failed to update doc batch: {e}")
                            batch_ids = []
                            batch_metas = []

                    # Final batch
                    if batch_ids:
                        if dry_run:
                            vector_doc_stats["updated"] += len(batch_ids)
                        else:
                            try:
                                doc_collection.update(ids=batch_ids, metadatas=batch_metas)
                                vector_doc_stats["updated"] += len(batch_ids)
                            except Exception as e:
                                log("error", f"  Failed to update final doc batch: {e}")

                    log("info", f"  Updated: {vector_doc_stats['updated']}, Already had: {vector_doc_stats['already_has_case_id']}, Unresolved: {vector_doc_stats['not_resolved']}")

                except Exception as e:
                    log("error", f"Error processing ChromaDB documents: {e}")

                # ── Phase 4: ChromaDB Chunks ─────────────────────────────
                log("info", "\n" + "-" * 60)
                log("info", "Phase 4: Backfilling case_id on ChromaDB Chunk metadata")
                log("info", "-" * 60)

                try:
                    chunk_collection = vector_db_service.chunk_collection
                    all_chunks = chunk_collection.get(include=["metadatas"])
                    chroma_chunk_ids = all_chunks.get("ids", [])
                    chroma_chunk_metas = all_chunks.get("metadatas", [])
                    vector_chunk_stats["total"] = len(chroma_chunk_ids)
                    log("info", f"Found {len(chroma_chunk_ids)} chunks in ChromaDB")

                    batch_ids = []
                    batch_metas = []

                    for i, (chunk_id, meta) in enumerate(zip(chroma_chunk_ids, chroma_chunk_metas), 1):
                        meta = meta or {}

                        if meta.get("case_id") and meta["case_id"] != "":
                            vector_chunk_stats["already_has_case_id"] += 1
                            continue

                        # Resolve case_id from parent doc_id or doc_name
                        parent_doc_id = meta.get("doc_id", "")
                        parent_doc_name = meta.get("doc_name", "")

                        resolved = None
                        if parent_doc_id:
                            resolved = doc_id_to_case_id.get(parent_doc_id)
                        if not resolved and parent_doc_name:
                            resolved = doc_name_to_case_id.get(parent_doc_name) or combined_lookup.get(parent_doc_name)

                        if not resolved:
                            vector_chunk_stats["not_resolved"] += 1
                            continue

                        batch_ids.append(chunk_id)
                        batch_metas.append({**meta, "case_id": resolved})

                        if len(batch_ids) >= BATCH_SIZE:
                            if dry_run:
                                vector_chunk_stats["updated"] += len(batch_ids)
                            else:
                                try:
                                    chunk_collection.update(ids=batch_ids, metadatas=batch_metas)
                                    vector_chunk_stats["updated"] += len(batch_ids)
                                except Exception as e:
                                    log("error", f"  Failed to update chunk batch: {e}")
                            batch_ids = []
                            batch_metas = []

                        if i % 500 == 0:
                            log("info", f"  Progress: {i}/{len(chroma_chunk_ids)} chunks processed")

                    # Final batch
                    if batch_ids:
                        if dry_run:
                            vector_chunk_stats["updated"] += len(batch_ids)
                        else:
                            try:
                                chunk_collection.update(ids=batch_ids, metadatas=batch_metas)
                                vector_chunk_stats["updated"] += len(batch_ids)
                            except Exception as e:
                                log("error", f"  Failed to update final chunk batch: {e}")

                    log("info", f"  Updated: {vector_chunk_stats['updated']}, Already had: {vector_chunk_stats['already_has_case_id']}, Unresolved: {vector_chunk_stats['not_resolved']}")

                except Exception as e:
                    log("error", f"Error processing ChromaDB chunks: {e}")

                # ── Phase 5: ChromaDB Entities ───────────────────────────
                if include_entities:
                    log("info", "\n" + "-" * 60)
                    log("info", "Phase 5: Backfilling case_id on ChromaDB Entity metadata")
                    log("info", "-" * 60)

                    try:
                        entity_collection = vector_db_service.entity_collection
                        all_ents = entity_collection.get(include=["metadatas"])
                        chroma_ent_ids = all_ents.get("ids", [])
                        chroma_ent_metas = all_ents.get("metadatas", [])
                        vector_entity_stats["total"] = len(chroma_ent_ids)
                        log("info", f"Found {len(chroma_ent_ids)} entities in ChromaDB")

                        batch_ids = []
                        batch_metas = []

                        for i, (ent_id, meta) in enumerate(zip(chroma_ent_ids, chroma_ent_metas), 1):
                            meta = meta or {}

                            if meta.get("case_id") and meta["case_id"] != "":
                                vector_entity_stats["already_has_case_id"] += 1
                                continue

                            # Resolve from Neo4j entity lookup (entity_id in ChromaDB = entity key)
                            resolved = entity_key_to_case_id.get(ent_id)

                            if not resolved:
                                vector_entity_stats["not_resolved"] += 1
                                continue

                            batch_ids.append(ent_id)
                            batch_metas.append({**meta, "case_id": resolved})

                            if len(batch_ids) >= BATCH_SIZE:
                                if dry_run:
                                    vector_entity_stats["updated"] += len(batch_ids)
                                else:
                                    try:
                                        entity_collection.update(ids=batch_ids, metadatas=batch_metas)
                                        vector_entity_stats["updated"] += len(batch_ids)
                                    except Exception as e:
                                        log("error", f"  Failed to update entity batch: {e}")
                                batch_ids = []
                                batch_metas = []

                        # Final batch
                        if batch_ids:
                            if dry_run:
                                vector_entity_stats["updated"] += len(batch_ids)
                            else:
                                try:
                                    entity_collection.update(ids=batch_ids, metadatas=batch_metas)
                                    vector_entity_stats["updated"] += len(batch_ids)
                                except Exception as e:
                                    log("error", f"  Failed to update final entity batch: {e}")

                        log("info", f"  Updated: {vector_entity_stats['updated']}, Already had: {vector_entity_stats['already_has_case_id']}, Unresolved: {vector_entity_stats['not_resolved']}")

                    except Exception as e:
                        log("error", f"Error processing ChromaDB entities: {e}")

        except ImportError as e:
            log("warning", f"\nChromaDB import failed — skipping vector DB phases: {e}")

    # ── Final Summary ────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    log("info", "\n" + "=" * 60)
    log("info", "Case ID Backfill Complete")
    log("info", "=" * 60)
    log("info", f"Neo4j Documents:")
    log("info", f"  Missing case_id:     {doc_stats['total_missing']}")
    log("info", f"  Updated:             {doc_stats['updated']}")
    log("info", f"  Not resolved:        {doc_stats['not_resolved']}")
    if include_entities:
        log("info", f"Neo4j Entities:")
        log("info", f"  Missing case_id:     {entity_stats['total_missing']}")
        log("info", f"  Updated:             {entity_stats['updated']}")
        log("info", f"  Not resolved:        {entity_stats['not_resolved']}")
    if include_vector_db:
        log("info", f"ChromaDB Documents:")
        log("info", f"  Total:               {vector_doc_stats['total']}")
        log("info", f"  Updated:             {vector_doc_stats['updated']}")
        log("info", f"  Already had case_id: {vector_doc_stats['already_has_case_id']}")
        log("info", f"  Not resolved:        {vector_doc_stats['not_resolved']}")
        log("info", f"ChromaDB Chunks:")
        log("info", f"  Total:               {vector_chunk_stats['total']}")
        log("info", f"  Updated:             {vector_chunk_stats['updated']}")
        log("info", f"  Already had case_id: {vector_chunk_stats['already_has_case_id']}")
        log("info", f"  Not resolved:        {vector_chunk_stats['not_resolved']}")
        if include_entities:
            log("info", f"ChromaDB Entities:")
            log("info", f"  Total:               {vector_entity_stats['total']}")
            log("info", f"  Updated:             {vector_entity_stats['updated']}")
            log("info", f"  Already had case_id: {vector_entity_stats['already_has_case_id']}")
            log("info", f"  Not resolved:        {vector_entity_stats['not_resolved']}")
    log("info", f"\nTime elapsed: {elapsed:.1f} seconds")

    if doc_stats["not_resolved_names"]:
        log("info", f"\nDocuments not resolved ({len(doc_stats['not_resolved_names'])}):")
        for name in doc_stats["not_resolved_names"][:20]:
            log("info", f"  - {name}")
        if len(doc_stats["not_resolved_names"]) > 20:
            log("info", f"  ... and {len(doc_stats['not_resolved_names']) - 20} more")

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


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill case_id for documents and entities in Neo4j and ChromaDB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making changes (dry run mode)"
    )
    parser.add_argument(
        "--include-entities",
        action="store_true",
        default=True,
        help="Also backfill entities via relationship traversal (default: True)"
    )
    parser.add_argument(
        "--docs-only",
        action="store_true",
        help="Only backfill documents, skip entities"
    )
    parser.add_argument(
        "--include-vector-db",
        action="store_true",
        default=True,
        help="Also backfill case_id metadata in ChromaDB (default: True)"
    )
    parser.add_argument(
        "--neo4j-only",
        action="store_true",
        help="Only backfill Neo4j, skip ChromaDB"
    )

    args = parser.parse_args()

    include_entities = not args.docs_only
    include_vector_db = not args.neo4j_only

    result = backfill_case_ids(
        dry_run=args.dry_run,
        include_entities=include_entities,
        include_vector_db=include_vector_db,
    )

    if result.get("status") == "error":
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
