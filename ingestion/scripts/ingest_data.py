#!/usr/bin/env python3
"""
Ingest Data CLI - Entry point for batch document ingestion.

Scans the data/ directory for .txt and .pdf files and ingests them
into the Neo4j knowledge graph.

Usage:
    python ingest_data.py              # Ingest all files in data/
    python ingest_data.py --file FILE  # Ingest a specific file
    python ingest_data.py --clear      # Clear the database first
"""

import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from text_ingestion import ingest_text_file
from pdf_ingestion import ingest_pdf_file
from neo4j_client import Neo4jClient
from logging_utils import log_progress, log_error, log_warning
from config import MAX_INGESTION_WORKERS
from typing import Optional, Callable


def find_data_dir() -> Path:
    """
    Resolve the 'data' directory relative to the project root.

    Assumes this file lives in PROJECT_ROOT/scripts/ingest_data.py
    """
    scripts_dir = Path(__file__).resolve().parent
    project_root = scripts_dir.parent
    data_dir = project_root / "data"
    return data_dir


def ingest_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> dict:
    """
    Ingest a single file based on its extension.

    Args:
        path: Path to the file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for file ingestion")

    log_progress(f"Using LLM profile: {profile_name}", log_callback)
    log_progress(f"Case ID: {case_id}", log_callback)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return ingest_text_file(path, case_id=case_id, log_callback=log_callback, profile_name=profile_name)
    elif suffix == ".pdf":
        return ingest_pdf_file(path, case_id=case_id, log_callback=log_callback, profile_name=profile_name)
    else:
        log_warning(f"Unsupported file type: {suffix}", log_callback)
        return {"status": "skipped", "reason": "unsupported_type", "file": str(path)}


def ingest_all_in_data(
    data_dir: Path,
    max_workers: int = MAX_INGESTION_WORKERS,
    profile_name: Optional[str] = None,
) -> dict:
    """
    Ingest all supported files in the data directory using parallel processing.

    Args:
        data_dir: Path to the data directory
        max_workers: Maximum number of files to process concurrently
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Summary dict with counts
    """
    if not data_dir.exists():
        log_error(f"Data directory not found: {data_dir}")
        return {"status": "error", "reason": "data_dir_not_found"}

    log_progress(f"Scanning data directory: {data_dir}")

    # Collect files (non-recursive)
    text_files = sorted(data_dir.glob("*.txt"))
    pdf_files = sorted(data_dir.glob("*.pdf"))

    all_files = text_files + pdf_files

    log_progress(f"Found {len(text_files)} text file(s) and {len(pdf_files)} PDF file(s)")
    log_progress(f"Processing with max_workers={max_workers}")

    if not all_files:
        log_progress("No files to process.")
        return {"status": "complete", "files_processed": 0}

    results = []
    results_lock = Lock()

    def process_single_file(path: Path) -> dict:
        """Process a single file and return result."""
        try:
            result = ingest_file(path, profile_name=profile_name)
            return result
        except Exception as e:
            log_error(f"Error processing {path}: {e}")
            return {"status": "error", "reason": str(e), "file": str(path)}

    # Use ThreadPoolExecutor for parallel file processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all files
        future_to_path = {
            executor.submit(process_single_file, path): path
            for path in all_files
        }

        try:
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    result = future.result()
                    with results_lock:
                        results.append(result)
                    log_progress(f"Completed: {path.name} - {result.get('status', 'unknown')}")
                except Exception as e:
                    log_error(f"Exception processing {path}: {e}")
                    with results_lock:
                        results.append({"status": "error", "reason": str(e), "file": str(path)})
        except KeyboardInterrupt:
            log_warning("Interrupted by user. Cancelling remaining tasks...")
            executor.shutdown(wait=False, cancel_futures=True)

    # Summary
    completed = sum(1 for r in results if r.get("status") == "complete")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")

    log_progress(f"{'='*60}")
    log_progress("INGESTION SUMMARY")
    log_progress(f"{'='*60}")
    log_progress(f"  Completed: {completed}")
    log_progress(f"  Skipped:   {skipped}")
    log_progress(f"  Errors:    {errors}")
    log_progress(f"{'='*60}")

    return {
        "status": "complete",
        "files_processed": len(results),
        "completed": completed,
        "skipped": skipped,
        "errors": errors,
    }


def clear_database():
    """
    Clear all data from the Neo4j database.
    """
    log_progress("Clearing database...")

    with Neo4jClient() as db:
        db.clear_database()

    log_progress("Database cleared.")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into the fraud investigation knowledge graph."
    )

    parser.add_argument(
        "--file",
        type=str,
        help="Path to a specific file to ingest",
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        help="Path to data directory (default: PROJECT_ROOT/data)",
    )

    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the database before ingesting",
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help=f"Maximum number of files to process in parallel (default: {MAX_INGESTION_WORKERS})",
    )

    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Name of the LLM profile to use (e.g., 'fraud', 'generic')",
    )

    args = parser.parse_args()

    # Clear database if requested
    if args.clear:
        confirm = input("This will delete ALL data. Continue? (y/N): ")
        if confirm.lower() == "y":
            clear_database()
        else:
            log_progress("Aborted.")
            return

    # Determine max_workers (CLI arg overrides config)
    max_workers = args.max_workers if args.max_workers else MAX_INGESTION_WORKERS

    # Ingest specific file
    if args.file:
        path = Path(args.file)
        if not path.exists():
            log_error(f"File not found: {path}")
            sys.exit(1)
        ingest_file(path, profile_name=args.profile)
        return

    # Ingest all files in data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = find_data_dir()

    ingest_all_in_data(data_dir, max_workers=max_workers, profile_name=args.profile)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_warning("Interrupted by user, exiting.")
        sys.exit(1)
