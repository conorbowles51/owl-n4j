"""
Repair/rebuild ChromaDB collections by re-embedding stored text.

ChromaDB stores original text alongside embeddings in SQLite. This script
extracts text + metadata from corrupted or dimension-mismatched collections
and re-embeds with the current model.

If the HNSW index is so corrupt that ChromaDB segfaults on startup, use
--nuke-hnsw to delete the HNSW index files first (data is preserved in SQLite).

Usage:
    python backend/scripts/repair_chromadb.py --dry-run
    python backend/scripts/repair_chromadb.py
    python backend/scripts/repair_chromadb.py --nuke-hnsw
    python backend/scripts/repair_chromadb.py --collection chunks
"""

import shutil
import sqlite3
import sys
import time
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from config import BASE_DIR, CHROMADB_PATH


BATCH_SIZE = 50
COLLECTIONS_TO_REPAIR = ["chunks", "entities"]


def get_chromadb_path() -> Path:
    return BASE_DIR / CHROMADB_PATH


def get_chromadb_client():
    """Initialize and return a ChromaDB client."""
    import chromadb
    from chromadb.config import Settings

    db_path = get_chromadb_path()
    db_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False),
    )


def inspect_sqlite(db_path: Path) -> dict:
    """
    Read collection info directly from ChromaDB's SQLite database.
    This works even when HNSW indices are corrupt (no C extension involved).

    Returns dict mapping collection_name -> {id, hnsw_segment_id, metadata_segment_id, count}
    """
    sqlite_file = db_path / "chroma.sqlite3"
    if not sqlite_file.exists():
        return {}

    conn = sqlite3.connect(str(sqlite_file))
    cursor = conn.cursor()

    info = {}
    try:
        cursor.execute("SELECT id, name FROM collections")
        collections = cursor.fetchall()

        for col_id, col_name in collections:
            # Get segments
            cursor.execute(
                "SELECT id, type FROM segments WHERE collection = ?", (col_id,)
            )
            segments = cursor.fetchall()
            hnsw_id = None
            meta_id = None
            for seg_id, seg_type in segments:
                if "hnsw" in seg_type:
                    hnsw_id = seg_id
                elif "metadata" in seg_type or "sqlite" in seg_type:
                    meta_id = seg_id

            # Count items in metadata segment
            count = 0
            if meta_id:
                cursor.execute(
                    "SELECT COUNT(*) FROM embeddings WHERE segment_id = ?",
                    (meta_id,),
                )
                count = cursor.fetchone()[0]

            info[col_name] = {
                "id": col_id,
                "hnsw_segment_id": hnsw_id,
                "metadata_segment_id": meta_id,
                "count": count,
            }
    finally:
        conn.close()

    return info


def nuke_hnsw_indices(db_path: Path, dry_run: bool = False) -> list:
    """
    Delete all HNSW index directories (UUID-named folders) from the ChromaDB
    data directory. This forces ChromaDB to rebuild them on next startup.

    The text, metadata, and embeddings remain safe in chroma.sqlite3.

    Returns list of deleted directory names.
    """
    deleted = []
    for item in db_path.iterdir():
        if item.is_dir() and len(item.name) == 36 and item.name.count("-") == 4:
            # UUID-format directory = HNSW index
            if dry_run:
                print(f"  [DRY RUN] Would delete HNSW index: {item.name}")
            else:
                print(f"  Deleting HNSW index: {item.name}")
                shutil.rmtree(item)
            deleted.append(item.name)
    return deleted


def diagnose_collection(client, name: str) -> dict:
    """
    Diagnose a collection for corruption or dimension mismatches.

    Returns a dict with keys:
        exists, count, healthy, dimensions, error
    """
    existing = [c.name for c in client.list_collections()]
    if name not in existing:
        return {"exists": False, "count": 0, "healthy": True, "dimensions": {}, "error": None}

    col = client.get_collection(name)
    count = col.count()
    if count == 0:
        return {"exists": True, "count": 0, "healthy": True, "dimensions": {}, "error": None}

    # Check if peek/query work (HNSW index health)
    try:
        peeked = col.peek(1)
        embeddings = peeked.get("embeddings") if peeked else None
        if embeddings is None or len(embeddings) == 0:
            return {
                "exists": True, "count": count, "healthy": False,
                "dimensions": {}, "error": "peek() returned no embeddings",
            }

        # Try a query to exercise HNSW
        sample_emb = embeddings[0]
        col.query(query_embeddings=[sample_emb], n_results=1)
    except Exception as e:
        return {
            "exists": True, "count": count, "healthy": False,
            "dimensions": {}, "error": str(e),
        }

    # Check for mixed dimensions (reads from SQLite)
    try:
        all_data = col.get(include=["embeddings"])
        dims = {}
        for emb in all_data.get("embeddings", []):
            d = len(emb)
            dims[d] = dims.get(d, 0) + 1
    except Exception as e:
        return {
            "exists": True, "count": count, "healthy": False,
            "dimensions": {}, "error": f"Cannot read embeddings: {e}",
        }

    needs_repair = len(dims) > 1
    return {
        "exists": True,
        "count": count,
        "healthy": not needs_repair,
        "dimensions": dims,
        "error": "Mixed dimensions" if needs_repair else None,
    }


def repair_collection(client, name: str, embedding_service, dry_run: bool = False) -> dict:
    """
    Repair a collection by extracting text from SQLite and re-embedding.

    Returns stats dict.
    """
    stats = {"items_found": 0, "items_recovered": 0, "items_failed": 0, "new_dimension": None}

    existing = [c.name for c in client.list_collections()]
    if name not in existing:
        print(f"  Collection '{name}' does not exist — nothing to repair.")
        return stats

    col = client.get_collection(name)
    count = col.count()
    if count == 0:
        print(f"  Collection '{name}' is empty — nothing to repair.")
        return stats

    # Extract all items from SQLite (documents + metadatas — NOT embeddings)
    print(f"  Extracting {count} items from '{name}' (SQLite)...")
    try:
        all_data = col.get(include=["documents", "metadatas"])
    except Exception as e:
        print(f"  ERROR: Cannot read from SQLite: {e}")
        print(f"  Collection may need full reset. Use reset_chromadb.py + re-ingest.")
        return stats

    ids = all_data.get("ids", [])
    documents = all_data.get("documents", [])
    metadatas = all_data.get("metadatas", [])
    stats["items_found"] = len(ids)

    if dry_run:
        print(f"  [DRY RUN] Would rebuild {len(ids)} items in '{name}'")
        valid = sum(1 for i in range(len(ids)) if documents[i] and documents[i].strip())
        empty = len(ids) - valid
        print(f"  [DRY RUN] {valid} items have text, {empty} have empty/missing text")
        stats["items_recovered"] = valid
        stats["items_failed"] = empty
        return stats

    # Delete and recreate the collection
    print(f"  Deleting collection '{name}'...")
    client.delete_collection(name)
    new_col = client.get_or_create_collection(
        name=name,
        metadata={"description": f"{name.capitalize()} embeddings for semantic search"},
    )

    # Re-embed and upsert in batches
    print(f"  Re-embedding {len(ids)} items in batches of {BATCH_SIZE}...")
    start_time = time.time()

    for batch_start in range(0, len(ids), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(ids))
        batch_ids = ids[batch_start:batch_end]
        batch_docs = documents[batch_start:batch_end]
        batch_metas = metadatas[batch_start:batch_end]

        valid_ids = []
        valid_embeddings = []
        valid_docs = []
        valid_metas = []

        for j in range(len(batch_ids)):
            text = batch_docs[j] if batch_docs[j] else ""
            if not text.strip():
                print(f"    Skipping {batch_ids[j]}: empty text")
                stats["items_failed"] += 1
                continue

            try:
                emb = embedding_service.generate_embedding(text)
                valid_ids.append(batch_ids[j])
                valid_embeddings.append(emb)
                valid_docs.append(text)
                valid_metas.append(batch_metas[j] if batch_metas[j] else {})

                if stats["new_dimension"] is None:
                    stats["new_dimension"] = len(emb)
            except Exception as e:
                print(f"    Failed to embed {batch_ids[j]}: {e}")
                stats["items_failed"] += 1

        if valid_ids:
            try:
                new_col.upsert(
                    ids=valid_ids,
                    embeddings=valid_embeddings,
                    documents=valid_docs,
                    metadatas=valid_metas,
                )
                stats["items_recovered"] += len(valid_ids)
            except Exception as e:
                print(f"    Batch upsert failed: {e}")
                stats["items_failed"] += len(valid_ids)

        processed = min(batch_end, len(ids))
        elapsed = time.time() - start_time
        print(f"    Progress: {processed}/{len(ids)} ({elapsed:.1f}s)")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Repair/rebuild ChromaDB collections by re-embedding stored text"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report issues without modifying anything",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Target a specific collection (chunks or entities)",
    )
    parser.add_argument(
        "--nuke-hnsw",
        action="store_true",
        help="Delete all HNSW index files before connecting to ChromaDB. "
             "Use this when ChromaDB segfaults on startup due to corrupt indices. "
             "Data in SQLite is preserved.",
    )
    args = parser.parse_args()

    collections = [args.collection] if args.collection else COLLECTIONS_TO_REPAIR

    print("=" * 60)
    print("ChromaDB Repair Script")
    print("=" * 60)

    db_path = get_chromadb_path()

    # Phase 0: If --nuke-hnsw, delete HNSW index directories BEFORE loading ChromaDB
    if args.nuke_hnsw:
        print("\n--- Phase 0: Nuking HNSW index files ---")
        print(f"  ChromaDB path: {db_path}")

        # Show what's in SQLite first
        sqlite_info = inspect_sqlite(db_path)
        if sqlite_info:
            print("\n  Collections in SQLite (data will be preserved):")
            for name, info in sqlite_info.items():
                print(f"    {name}: {info['count']} items, HNSW segment: {info['hnsw_segment_id']}")
        else:
            print("  WARNING: No SQLite database found. Nothing to preserve.")

        if args.dry_run:
            print("\n  [DRY RUN] Would delete HNSW directories:")
            nuke_hnsw_indices(db_path, dry_run=True)
        else:
            deleted = nuke_hnsw_indices(db_path, dry_run=False)
            if deleted:
                print(f"\n  Deleted {len(deleted)} HNSW index directories.")
                print("  ChromaDB will rebuild indices when collections are populated.")
            else:
                print("\n  No HNSW index directories found.")

        if args.dry_run:
            print("\n[DRY RUN] Exiting. Run without --dry-run to actually delete.")
            return

    # Initialize ChromaDB client (should work now if HNSW was nuked)
    print("\nConnecting to ChromaDB...")
    try:
        client = get_chromadb_client()
    except Exception as e:
        print(f"ERROR: ChromaDB client failed to initialize: {e}")
        if not args.nuke_hnsw:
            print("\nTip: If ChromaDB segfaults, try: python backend/scripts/repair_chromadb.py --nuke-hnsw")
        sys.exit(1)

    # Phase 1: Diagnose
    print("\n--- Diagnosis ---")
    diagnoses = {}
    for name in collections:
        diag = diagnose_collection(client, name)
        diagnoses[name] = diag
        if not diag["exists"]:
            print(f"  {name}: does not exist")
        elif diag["count"] == 0:
            print(f"  {name}: empty (HNSW was removed, needs rebuild)")
        elif diag["healthy"]:
            dim, n = next(iter(diag["dimensions"].items()))
            print(f"  {name}: OK — {n} items, {dim}d")
        else:
            print(f"  {name}: NEEDS REPAIR — {diag['count']} items, error: {diag['error']}")
            if diag["dimensions"]:
                for dim, n in sorted(diag["dimensions"].items()):
                    print(f"    {dim}d: {n} items")

    # Also check for legacy documents collection
    existing_collections = [c.name for c in client.list_collections()]
    if "documents" in existing_collections:
        doc_col = client.get_collection("documents")
        doc_count = doc_col.count()
        print(f"  documents (LEGACY): {doc_count} items — will be deleted")

    # Determine which collections need repair
    needs_repair = [name for name in collections if diagnoses.get(name, {}).get("error")]

    # After --nuke-hnsw, collections with data need rebuild even if they appear "healthy"
    # (they'll show count=0 since HNSW was removed, but SQLite still has data)
    if args.nuke_hnsw:
        sqlite_info = inspect_sqlite(db_path)
        for name in collections:
            if name not in needs_repair and sqlite_info.get(name, {}).get("count", 0) > 0:
                count_in_sqlite = sqlite_info[name]["count"]
                diag = diagnoses.get(name, {})
                if diag.get("count", 0) < count_in_sqlite:
                    print(f"  {name}: SQLite has {count_in_sqlite} items but collection shows {diag.get('count', 0)} — needs rebuild")
                    needs_repair.append(name)

    if not needs_repair and "documents" not in existing_collections:
        print("\nAll collections are healthy. Nothing to do.")
        return

    if args.dry_run:
        print("\n--- Dry Run ---")

    # Phase 2: Repair collections that need it
    if needs_repair:
        print("\n--- Repair ---")

        # Initialize embedding service
        print("Initializing embedding service...")
        try:
            from services.embedding_service import embedding_service
            if embedding_service is None:
                print("ERROR: Embedding service is not configured.")
                print("Set OPENAI_API_KEY or configure Ollama before running repair.")
                sys.exit(1)
            print(f"Using: {embedding_service.provider}/{embedding_service.model}")
        except Exception as e:
            print(f"ERROR: Could not initialize embedding service: {e}")
            sys.exit(1)

        for name in needs_repair:
            print(f"\nRepairing '{name}'...")
            stats = repair_collection(client, name, embedding_service, dry_run=args.dry_run)
            print(f"  Result: {stats['items_recovered']} recovered, "
                  f"{stats['items_failed']} failed"
                  + (f", new dimension: {stats['new_dimension']}d" if stats["new_dimension"] else ""))

    # Phase 3: Delete legacy documents collection
    if "documents" in existing_collections:
        if args.dry_run:
            doc_col = client.get_collection("documents")
            print(f"\n[DRY RUN] Would delete legacy 'documents' collection ({doc_col.count()} items)")
        else:
            print("\nDeleting legacy 'documents' collection...")
            client.delete_collection("documents")
            print("  Done.")

    print("\n" + "=" * 60)
    print("Repair complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
