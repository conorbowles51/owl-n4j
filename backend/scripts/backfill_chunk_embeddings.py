"""
Backfill chunk embeddings for existing documents.

This script generates chunk-level embeddings for documents that are already in Neo4j
but don't have chunk embeddings in the ChromaDB chunks collection.

It reads original files from disk, re-chunks them (pure text splitting, no LLM),
and embeds each chunk. This is much cheaper than re-ingestion since no entity
extraction is needed.

Usage:
    python backend/scripts/backfill_chunk_embeddings.py --dry-run
    python backend/scripts/backfill_chunk_embeddings.py --case-id <case_id>
    python backend/scripts/backfill_chunk_embeddings.py --skip-existing
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
import time

# Add project root to path
project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"
ingestion_dir = project_root / "ingestion" / "scripts"

# Add backend directory FIRST so config imports resolve correctly
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Add ingestion scripts for chunking module
if str(ingestion_dir) not in sys.path:
    sys.path.insert(0, str(ingestion_dir))

# Import services
from services.neo4j_service import neo4j_service
from services.vector_db_service import vector_db_service
from services.embedding_service import embedding_service
from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR

# Import chunking
from chunking import chunk_document

# Import text extraction from backfill router
from routers.backfill import extract_text_from_file, find_evidence_file


def backfill_chunk_embeddings(
    dry_run: bool = False,
    skip_existing: bool = True,
    case_id: Optional[str] = None,
    batch_size: int = 10,
    log_callback=None,
) -> Dict:
    """
    Generate chunk-level embeddings for existing documents.

    Reads original files from disk, chunks them, embeds each chunk,
    and stores in the ChromaDB chunks collection.

    Args:
        dry_run: If True, only report what would be done without making changes
        skip_existing: If True, skip documents that already have chunk embeddings
        case_id: Optional case_id to filter documents
        batch_size: Number of documents to process before showing progress
        log_callback: Optional callback for progress updates (level, message)

    Returns:
        Dictionary with statistics
    """
    def log(level: str, message: str):
        print(f"[{level.upper()}] {message}")
        if log_callback:
            log_callback(level, message)

    log("info", "=" * 60)
    log("info", "Backfilling Chunk Embeddings for Existing Documents")
    log("info", "=" * 60)

    if embedding_service is None:
        log("error", "Embedding service is not configured!")
        log("error", "  Please set OPENAI_API_KEY or configure Ollama")
        return {"status": "error", "reason": "embedding_service_not_configured"}

    if dry_run:
        log("info", "[DRY RUN MODE] - No changes will be made\n")

    # Query Neo4j for documents
    log("info", "Querying Neo4j for documents...")
    try:
        if case_id:
            cypher = """
            MATCH (d:Document)
            WHERE d.case_id = $case_id
            RETURN d.id AS id, d.key AS key, d.name AS name,
                   d.case_id AS case_id
            ORDER BY d.name
            """
            documents = neo4j_service.run_cypher(cypher, {"case_id": case_id})
        else:
            cypher = """
            MATCH (d:Document)
            RETURN d.id AS id, d.key AS key, d.name AS name,
                   d.case_id AS case_id
            ORDER BY d.name
            """
            documents = neo4j_service.run_cypher(cypher)

        log("info", f"Found {len(documents)} documents in Neo4j")
    except Exception as e:
        log("error", f"Error querying Neo4j: {e}")
        return {"status": "error", "reason": str(e)}

    if not documents:
        log("info", "No documents found in Neo4j")
        return {"status": "complete", "stats": {"total": 0, "processed": 0}}

    # Statistics
    stats = {
        "total": len(documents),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "already_has_chunks": 0,
        "file_not_found": 0,
        "extraction_failed": 0,
        "embedding_failed": 0,
        "total_chunks_created": 0,
        "file_not_found_names": [],
    }

    log("info", f"\nProcessing {stats['total']} documents...")
    log("info", "-" * 60)

    start_time = time.time()

    for i, doc in enumerate(documents, 1):
        doc_id = doc.get("id")
        doc_key = doc.get("key")
        doc_name = doc.get("name")
        doc_case_id = doc.get("case_id")

        if not doc_id or not doc_name:
            log("warning", f"[{i}/{stats['total']}] Skipping document with missing id/name")
            stats["skipped"] += 1
            continue

        # Check if this document already has chunks
        if skip_existing:
            try:
                existing_count = vector_db_service.count_chunks(doc_id)
                if existing_count > 0:
                    log("info", f"[{i}/{stats['total']}] {doc_name} - Already has {existing_count} chunks (skipping)")
                    stats["already_has_chunks"] += 1
                    continue
            except Exception as e:
                log("warning", f"Could not check existing chunks for {doc_name}: {e}")

        log("info", f"\n[{i}/{stats['total']}] Processing: {doc_name}")

        # Find the original file on disk
        file_path = find_evidence_file(doc_name)
        if not file_path:
            log("warning", f"  File not found on disk for: {doc_name}")
            stats["file_not_found"] += 1
            stats["file_not_found_names"].append(doc_name)
            continue

        log("info", f"  Found file: {file_path}")

        # Extract text from file
        try:
            text = extract_text_from_file(file_path)
            if not text or not text.strip():
                log("warning", f"  Empty text extracted from {doc_name}")
                stats["extraction_failed"] += 1
                continue
            log("info", f"  Extracted {len(text):,} characters")
        except Exception as e:
            log("error", f"  Text extraction failed for {doc_name}: {e}")
            stats["extraction_failed"] += 1
            continue

        # Chunk the document
        try:
            chunks = chunk_document(text, doc_name)
            if not chunks:
                log("warning", f"  No chunks produced for {doc_name}")
                stats["extraction_failed"] += 1
                continue
            log("info", f"  Chunked into {len(chunks)} chunks")
        except Exception as e:
            log("error", f"  Chunking failed for {doc_name}: {e}")
            stats["extraction_failed"] += 1
            continue

        if dry_run:
            log("info", f"  [DRY RUN] Would create {len(chunks)} chunk embeddings")
            stats["processed"] += 1
            stats["total_chunks_created"] += len(chunks)
            continue

        # Embed and store each chunk
        chunks_stored = 0
        for chunk_idx, chunk_data in enumerate(chunks):
            chunk_text = chunk_data.get("text", "")
            if not chunk_text.strip():
                continue

            chunk_id = f"{doc_id}_chunk_{chunk_idx}"

            try:
                # Generate embedding
                embedding = embedding_service.generate_embedding(chunk_text)
                if not embedding:
                    log("warning", f"  Chunk {chunk_idx}: empty embedding")
                    continue

                # Build metadata
                page_start = chunk_data.get("page_start")
                page_end = chunk_data.get("page_end")

                metadata = {
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "doc_key": doc_key or "",
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "page_start": page_start if page_start is not None else -1,
                    "page_end": page_end if page_end is not None else -1,
                }

                if doc_case_id:
                    metadata["case_id"] = doc_case_id

                # Store in ChromaDB
                vector_db_service.add_chunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    embedding=embedding,
                    metadata=metadata,
                )
                chunks_stored += 1

            except Exception as e:
                log("error", f"  Chunk {chunk_idx}: failed to embed/store: {e}")
                stats["embedding_failed"] += 1

        if chunks_stored > 0:
            log("info", f"  Stored {chunks_stored}/{len(chunks)} chunk embeddings")
            stats["processed"] += 1
            stats["total_chunks_created"] += chunks_stored
        else:
            log("error", f"  Failed to store any chunks for {doc_name}")
            stats["failed"] += 1

        # Progress update
        if i % batch_size == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = stats["total"] - i
            eta = remaining / rate if rate > 0 else 0
            log("info", f"\n  Progress: {i}/{stats['total']} ({i/stats['total']*100:.1f}%)")
            log("info", f"  Rate: {rate:.1f} docs/sec, ETA: {eta:.0f} seconds")

    # Final summary
    elapsed = time.time() - start_time
    log("info", "\n" + "=" * 60)
    log("info", "Chunk Backfill Complete")
    log("info", "=" * 60)
    log("info", f"Total documents:       {stats['total']}")
    log("info", f"Processed:             {stats['processed']}")
    log("info", f"Already had chunks:    {stats['already_has_chunks']}")
    log("info", f"Skipped:               {stats['skipped']}")
    log("info", f"File not found:        {stats['file_not_found']}")
    log("info", f"Extraction failed:     {stats['extraction_failed']}")
    log("info", f"Embedding failed:      {stats['embedding_failed']}")
    log("info", f"Failed:                {stats['failed']}")
    log("info", f"Total chunks created:  {stats['total_chunks_created']}")
    log("info", f"\nTime elapsed: {elapsed:.1f} seconds")
    if stats['processed'] > 0:
        log("info", f"Average time per document: {elapsed/stats['processed']:.2f} seconds")

    if stats["file_not_found_names"]:
        log("info", f"\nFiles not found ({len(stats['file_not_found_names'])}):")
        for name in stats["file_not_found_names"][:20]:
            log("info", f"  - {name}")
        if len(stats["file_not_found_names"]) > 20:
            log("info", f"  ... and {len(stats['file_not_found_names']) - 20} more")

    return {
        "status": "complete",
        "stats": stats,
        "elapsed_seconds": elapsed,
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill chunk embeddings for existing documents"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making changes (dry run mode)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip documents that already have chunk embeddings (default: True)"
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Re-process documents that already have chunk embeddings"
    )
    parser.add_argument(
        "--case-id",
        type=str,
        default=None,
        help="Only process documents for this case_id"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of documents to process before showing progress (default: 10)"
    )

    args = parser.parse_args()

    result = backfill_chunk_embeddings(
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        case_id=args.case_id,
        batch_size=args.batch_size,
    )

    if result.get("status") == "error":
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
