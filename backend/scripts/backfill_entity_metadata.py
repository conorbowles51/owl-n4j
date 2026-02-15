"""
Backfill entity metadata (case_id) in ChromaDB.

This script updates entity embeddings in ChromaDB to include case_id metadata,
which enables case-filtered entity search. No re-embedding is needed — this is
purely a metadata update operation.

It reads the case_id for each entity from Neo4j and updates the ChromaDB
entity collection metadata accordingly.

Usage:
    python backend/scripts/backfill_entity_metadata.py --dry-run
    python backend/scripts/backfill_entity_metadata.py
    python backend/scripts/backfill_entity_metadata.py --batch-size 50
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
from services.vector_db_service import vector_db_service


def backfill_entity_metadata(
    dry_run: bool = False,
    batch_size: int = 50,
    log_callback=None,
) -> Dict:
    """
    Update entity embeddings in ChromaDB to include case_id metadata.

    Reads case_id from Neo4j for each entity, then updates the ChromaDB
    entity collection metadata. No re-embedding needed.

    Args:
        dry_run: If True, only report what would be done without making changes
        batch_size: Number of entities to process before showing progress
        log_callback: Optional callback for progress updates (level, message)

    Returns:
        Dictionary with statistics
    """
    def log(level: str, message: str):
        print(f"[{level.upper()}] {message}")
        if log_callback:
            log_callback(level, message)

    log("info", "=" * 60)
    log("info", "Backfilling Entity Metadata (case_id) in ChromaDB")
    log("info", "=" * 60)

    if dry_run:
        log("info", "[DRY RUN MODE] - No changes will be made\n")

    # Step 1: Query Neo4j for all entities with their case_id
    log("info", "Querying Neo4j for entities with case_id...")
    try:
        cypher = """
        MATCH (e)
        WHERE NOT e:Document AND e.case_id IS NOT NULL
        RETURN e.key AS key, e.case_id AS case_id, e.name AS name, labels(e)[0] AS entity_type
        ORDER BY e.key
        """
        entities_with_case_id = neo4j_service.run_cypher(cypher)
        log("info", f"Found {len(entities_with_case_id)} entities with case_id in Neo4j")
    except Exception as e:
        log("error", f"Error querying Neo4j: {e}")
        return {"status": "error", "reason": str(e)}

    if not entities_with_case_id:
        log("info", "No entities with case_id found in Neo4j")
        return {"status": "complete", "stats": {"total": 0, "updated": 0}}

    # Build lookup: entity_key -> case_id
    key_to_case_id = {}
    for ent in entities_with_case_id:
        key = ent.get("key")
        cid = ent.get("case_id")
        if key and cid:
            key_to_case_id[key] = cid

    log("info", f"Built case_id lookup for {len(key_to_case_id)} entities")

    # Step 2: Get all entities from ChromaDB
    log("info", "Querying ChromaDB entity collection...")
    try:
        entity_collection = vector_db_service.entity_collection
        # Get all entities from collection
        all_entities = entity_collection.get(include=["metadatas"])
        entity_ids = all_entities.get("ids", [])
        entity_metadatas = all_entities.get("metadatas", [])
        log("info", f"Found {len(entity_ids)} entities in ChromaDB")
    except Exception as e:
        log("error", f"Error querying ChromaDB: {e}")
        return {"status": "error", "reason": str(e)}

    if not entity_ids:
        log("info", "No entities found in ChromaDB")
        return {"status": "complete", "stats": {"total": 0, "updated": 0}}

    # Statistics
    stats = {
        "total_chromadb": len(entity_ids),
        "total_neo4j_with_case_id": len(key_to_case_id),
        "updated": 0,
        "already_has_case_id": 0,
        "no_case_id_in_neo4j": 0,
        "failed": 0,
    }

    log("info", f"\nProcessing {len(entity_ids)} ChromaDB entities...")
    log("info", "-" * 60)

    start_time = time.time()

    # Process in batches for efficiency
    batch_ids = []
    batch_metadatas = []

    for i, (entity_id, metadata) in enumerate(zip(entity_ids, entity_metadatas), 1):
        metadata = metadata or {}

        # Check if already has case_id
        if metadata.get("case_id"):
            stats["already_has_case_id"] += 1
            continue

        # Look up case_id from Neo4j
        # The entity_id in ChromaDB is the entity key
        neo4j_case_id = key_to_case_id.get(entity_id)

        if not neo4j_case_id:
            stats["no_case_id_in_neo4j"] += 1
            continue

        # Prepare update
        updated_metadata = {**metadata, "case_id": neo4j_case_id}
        batch_ids.append(entity_id)
        batch_metadatas.append(updated_metadata)

        # Process batch
        if len(batch_ids) >= batch_size:
            if dry_run:
                log("info", f"  [DRY RUN] Would update {len(batch_ids)} entities with case_id")
                stats["updated"] += len(batch_ids)
            else:
                try:
                    entity_collection.update(
                        ids=batch_ids,
                        metadatas=batch_metadatas,
                    )
                    stats["updated"] += len(batch_ids)
                    log("info", f"  Updated batch of {len(batch_ids)} entities (total: {stats['updated']})")
                except Exception as e:
                    log("error", f"  Failed to update batch: {e}")
                    stats["failed"] += len(batch_ids)

            batch_ids = []
            batch_metadatas = []

        # Progress update
        if i % (batch_size * 5) == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            log("info", f"  Progress: {i}/{len(entity_ids)} ({i/len(entity_ids)*100:.1f}%)")

    # Process remaining batch
    if batch_ids:
        if dry_run:
            log("info", f"  [DRY RUN] Would update {len(batch_ids)} entities with case_id")
            stats["updated"] += len(batch_ids)
        else:
            try:
                entity_collection.update(
                    ids=batch_ids,
                    metadatas=batch_metadatas,
                )
                stats["updated"] += len(batch_ids)
                log("info", f"  Updated final batch of {len(batch_ids)} entities")
            except Exception as e:
                log("error", f"  Failed to update final batch: {e}")
                stats["failed"] += len(batch_ids)

    # Final summary
    elapsed = time.time() - start_time
    log("info", "\n" + "=" * 60)
    log("info", "Entity Metadata Backfill Complete")
    log("info", "=" * 60)
    log("info", f"Total in ChromaDB:          {stats['total_chromadb']}")
    log("info", f"Total in Neo4j (with case): {stats['total_neo4j_with_case_id']}")
    log("info", f"Updated with case_id:       {stats['updated']}")
    log("info", f"Already had case_id:        {stats['already_has_case_id']}")
    log("info", f"No case_id in Neo4j:        {stats['no_case_id_in_neo4j']}")
    log("info", f"Failed:                     {stats['failed']}")
    log("info", f"\nTime elapsed: {elapsed:.1f} seconds")

    return {
        "status": "complete",
        "stats": stats,
        "elapsed_seconds": elapsed,
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill entity metadata (case_id) in ChromaDB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making changes (dry run mode)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of entities to update per batch (default: 50)"
    )

    args = parser.parse_args()

    result = backfill_entity_metadata(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )

    if result.get("status") == "error":
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
