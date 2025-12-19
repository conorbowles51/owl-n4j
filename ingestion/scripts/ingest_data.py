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

from text_ingestion import ingest_text_file
from pdf_ingestion import ingest_pdf_file
from neo4j_client import Neo4jClient
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


def ingest_file(path: Path, log_callback: Optional[Callable[[str], None]] = None) -> dict:
    """
    Ingest a single file based on its extension.

    Args:
        path: Path to the file
        log_callback: Optional callback function(message: str) to log progress messages

    Returns:
        Ingestion result dict
    """
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return ingest_text_file(path, log_callback=log_callback)
    elif suffix == ".pdf":
        return ingest_pdf_file(path, log_callback=log_callback)
    else:
        print(f"Unsupported file type: {suffix}")
        return {"status": "skipped", "reason": "unsupported_type", "file": str(path)}


def ingest_all_in_data(data_dir: Path) -> dict:
    """
    Ingest all supported files in the data directory.

    Args:
        data_dir: Path to the data directory

    Returns:
        Summary dict with counts
    """
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return {"status": "error", "reason": "data_dir_not_found"}

    print(f"Scanning data directory: {data_dir}")

    # Collect files (non-recursive)
    text_files = sorted(data_dir.glob("*.txt"))
    pdf_files = sorted(data_dir.glob("*.pdf"))

    all_files = text_files + pdf_files

    print(f"Found {len(text_files)} text file(s) and {len(pdf_files)} PDF file(s)")

    if not all_files:
        print("No files to process.")
        return {"status": "complete", "files_processed": 0}

    results = []

    for path in all_files:
        try:
            result = ingest_file(path)
            results.append(result)
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
            break
        except Exception as e:
            print(f"Error processing {path}: {e}")
            results.append({"status": "error", "reason": str(e), "file": str(path)})

    # Summary
    completed = sum(1 for r in results if r.get("status") == "complete")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")

    print(f"\n{'='*60}")
    print("INGESTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Completed: {completed}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {errors}")
    print(f"{'='*60}\n")

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
    print("Clearing database...")

    with Neo4jClient() as db:
        db.clear_database()

    print("Database cleared.")


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

    args = parser.parse_args()

    # Clear database if requested
    if args.clear:
        confirm = input("This will delete ALL data. Continue? (y/N): ")
        if confirm.lower() == "y":
            clear_database()
        else:
            print("Aborted.")
            return

    # Ingest specific file
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        ingest_file(path)
        return

    # Ingest all files in data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = find_data_dir()

    ingest_all_in_data(data_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user, exiting.")
        sys.exit(1)
