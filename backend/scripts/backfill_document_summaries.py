"""
Backfill AI summaries for existing documents.

This script generates AI summaries for documents in Neo4j that don't have one.
It reads the original files from disk, sends the first 5000 characters to the LLM,
and stores the resulting 2-4 sentence summary on the Document node.

NOTE: Unlike chunk/entity metadata backfills, this script uses LLM calls and has
a per-document cost (small, but non-zero). Estimated ~$0.001-0.005 per document
with OpenAI, free with Ollama.

Usage:
    python backend/scripts/backfill_document_summaries.py --dry-run
    python backend/scripts/backfill_document_summaries.py --case-id <case_id>
    python backend/scripts/backfill_document_summaries.py --skip-existing
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
from services.llm_service import LLMService

# Import text extraction from backfill router
from routers.backfill import extract_text_from_file, find_evidence_file


SUMMARY_PROMPT_TEMPLATE = """Summarize the following document content in 2-4 sentences. Focus on the main topics, key facts, and important information.

Document: {doc_name}
Content:
{content}

Provide a concise summary that captures the essential information:"""


def backfill_document_summaries(
    dry_run: bool = False,
    skip_existing: bool = True,
    case_id: Optional[str] = None,
    batch_size: int = 10,
    log_callback=None,
) -> Dict:
    """
    Generate AI summaries for existing documents that don't have one.

    Reads original files from disk, sends first 5000 chars to LLM,
    stores summary on Document node in Neo4j and in ChromaDB metadata.

    Args:
        dry_run: If True, only report what would be done without making changes
        skip_existing: If True, skip documents that already have summaries
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
    log("info", "Backfilling AI Summaries for Existing Documents")
    log("info", "=" * 60)

    if dry_run:
        log("info", "[DRY RUN MODE] - No changes will be made\n")

    # Initialize LLM service
    try:
        llm = LLMService()
        provider, model = llm.get_current_config()
        log("info", f"Using LLM: {provider}/{model}")
    except Exception as e:
        log("error", f"Failed to initialize LLM service: {e}")
        return {"status": "error", "reason": str(e)}

    # Query Neo4j for documents
    log("info", "Querying Neo4j for documents...")
    try:
        if case_id:
            if skip_existing:
                cypher = """
                MATCH (d:Document)
                WHERE d.case_id = $case_id
                  AND (d.summary IS NULL OR d.summary = '')
                RETURN d.id AS id, d.key AS key, d.name AS name,
                       d.case_id AS case_id, d.summary AS summary
                ORDER BY d.name
                """
            else:
                cypher = """
                MATCH (d:Document)
                WHERE d.case_id = $case_id
                RETURN d.id AS id, d.key AS key, d.name AS name,
                       d.case_id AS case_id, d.summary AS summary
                ORDER BY d.name
                """
            documents = neo4j_service.run_cypher(cypher, {"case_id": case_id})
        else:
            if skip_existing:
                cypher = """
                MATCH (d:Document)
                WHERE d.summary IS NULL OR d.summary = ''
                RETURN d.id AS id, d.key AS key, d.name AS name,
                       d.case_id AS case_id, d.summary AS summary
                ORDER BY d.name
                """
            else:
                cypher = """
                MATCH (d:Document)
                RETURN d.id AS id, d.key AS key, d.name AS name,
                       d.case_id AS case_id, d.summary AS summary
                ORDER BY d.name
                """
            documents = neo4j_service.run_cypher(cypher)

        log("info", f"Found {len(documents)} documents to process")
    except Exception as e:
        log("error", f"Error querying Neo4j: {e}")
        return {"status": "error", "reason": str(e)}

    if not documents:
        msg = "No documents need summary generation"
        if skip_existing:
            msg += " (all documents already have summaries)"
        log("info", msg)
        return {"status": "complete", "stats": {"total": 0, "processed": 0}}

    # Statistics
    stats = {
        "total": len(documents),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "already_has_summary": 0,
        "file_not_found": 0,
        "extraction_failed": 0,
        "llm_failed": 0,
        "file_not_found_names": [],
    }

    log("info", f"\nProcessing {stats['total']} documents...")
    log("info", f"NOTE: Each document requires an LLM call (~$0.001-0.005 with OpenAI)")
    log("info", "-" * 60)

    start_time = time.time()

    for i, doc in enumerate(documents, 1):
        doc_id = doc.get("id")
        doc_key = doc.get("key")
        doc_name = doc.get("name")
        doc_case_id = doc.get("case_id")
        existing_summary = doc.get("summary")

        if not doc_id or not doc_name:
            log("warning", f"[{i}/{stats['total']}] Skipping document with missing id/name")
            stats["skipped"] += 1
            continue

        # Double-check existing summary (in case skip_existing=False but we want to report)
        if skip_existing and existing_summary and existing_summary.strip():
            log("info", f"[{i}/{stats['total']}] {doc_name} - Already has summary (skipping)")
            stats["already_has_summary"] += 1
            continue

        log("info", f"\n[{i}/{stats['total']}] Processing: {doc_name}")

        # Find the original file on disk
        file_path = find_evidence_file(doc_name)
        if not file_path:
            log("warning", f"  File not found on disk for: {doc_name}")
            stats["file_not_found"] += 1
            stats["file_not_found_names"].append(doc_name)
            continue

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

        if dry_run:
            log("info", f"  [DRY RUN] Would generate summary using {provider}/{model}")
            stats["processed"] += 1
            continue

        # Generate summary using LLM
        try:
            summary_text = text[:5000] if len(text) > 5000 else text
            prompt = SUMMARY_PROMPT_TEMPLATE.format(
                doc_name=doc_name,
                content=summary_text,
            )

            log("info", f"  Generating summary via {provider}/{model}...")
            summary = llm.call(prompt, temperature=0.3)

            if not summary or not summary.strip():
                log("warning", f"  LLM returned empty summary for {doc_name}")
                stats["llm_failed"] += 1
                continue

            summary = summary.strip()
            log("info", f"  Generated summary ({len(summary)} chars)")
        except Exception as e:
            log("error", f"  LLM summary generation failed for {doc_name}: {e}")
            stats["llm_failed"] += 1
            continue

        # Store summary in Neo4j
        try:
            neo4j_service.run_cypher(
                "MATCH (d:Document {id: $doc_id}) SET d.summary = $summary",
                {"doc_id": doc_id, "summary": summary}
            )
            log("info", f"  Stored summary in Neo4j")
        except Exception as e:
            log("error", f"  Failed to store summary in Neo4j for {doc_name}: {e}")
            stats["failed"] += 1
            continue

        # Also update ChromaDB document metadata if the document has an embedding
        try:
            existing_docs = vector_db_service.collection.get(ids=[doc_id])
            if existing_docs and existing_docs.get("ids"):
                existing_metadata = existing_docs.get("metadatas", [{}])[0] or {}
                updated_metadata = dict(existing_metadata)
                updated_metadata["summary"] = summary
                vector_db_service.collection.update(
                    ids=[doc_id],
                    metadatas=[updated_metadata]
                )
                log("info", f"  Updated ChromaDB metadata with summary")
        except Exception as e:
            # Non-fatal - the summary is already in Neo4j
            log("warning", f"  Could not update ChromaDB metadata: {e}")

        stats["processed"] += 1

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
    log("info", "Document Summary Backfill Complete")
    log("info", "=" * 60)
    log("info", f"Total documents:       {stats['total']}")
    log("info", f"Processed:             {stats['processed']}")
    log("info", f"Already had summary:   {stats['already_has_summary']}")
    log("info", f"Skipped:               {stats['skipped']}")
    log("info", f"File not found:        {stats['file_not_found']}")
    log("info", f"Extraction failed:     {stats['extraction_failed']}")
    log("info", f"LLM failed:            {stats['llm_failed']}")
    log("info", f"Failed:                {stats['failed']}")
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
        description="Backfill AI summaries for existing documents"
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
        help="Skip documents that already have summaries (default: True)"
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Re-generate summaries for all documents (even those with existing summaries)"
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

    result = backfill_document_summaries(
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
