#!/usr/bin/env python3
"""
Audio Ingestion CLI - Entry point for wiretap audio ingestion.

Processes wiretap folders containing audio files and metadata,
transcribes using WhisperAI, and ingests into Neo4j.

This script now uses profile-based folder processing (wiretap profile)
which ensures proper ingestion through the standard pipeline including
vectorization and entity extraction.

Usage:
    python ingest_audio.py --dir ingestion/audio/example_wiretap
    python ingest_audio.py --folder ingestion/audio/example_wiretap/00000128
    python ingest_audio.py --dir ingestion/audio/example_wiretap --model large
    python ingest_audio.py --folder ingestion/audio/example_wiretap/00000128 --case-id test-case
"""

import argparse
import sys
import os
from pathlib import Path

from folder_ingestion import ingest_folder_with_profile
from neo4j_client import Neo4jClient


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
        description="Ingest wiretap audio files into the fraud investigation knowledge graph."
    )

    parser.add_argument(
        "--dir",
        type=str,
        help="Path to directory containing wiretap folders (e.g., example_wiretap)",
    )

    parser.add_argument(
        "--folder",
        type=str,
        help="Path to a specific wiretap folder to process (e.g., 00000128)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base). Larger models are more accurate but slower.",
    )

    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the database before ingesting",
    )
    
    parser.add_argument(
        "--case-id",
        type=str,
        default=None,
        help="Case ID for associating entities (default: uses CASE_ID env var or 'default-case')",
    )
    
    parser.add_argument(
        "--profile",
        type=str,
        default="wiretap",
        help="Profile to use for folder processing (default: wiretap)",
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

    # Get case_id
    case_id = args.case_id or os.getenv("CASE_ID", "default-case")
    
    # Process specific folder
    if args.folder:
        folder_path = Path(args.folder)
        if not folder_path.exists() or not folder_path.is_dir():
            print(f"Folder not found or is not a directory: {folder_path}", flush=True)
            sys.exit(1)
        
        # Use profile-based folder ingestion
        print(f"Processing folder with profile: {args.profile}", flush=True)
        print(f"Case ID: {case_id}", flush=True)
        
        # Create a log callback that prints to stdout (which will be captured by subprocess)
        def log_callback(message: str):
            print(message, flush=True)
        
        try:
            result = ingest_folder_with_profile(
                folder_path=folder_path,
                profile_name=args.profile,
                case_id=case_id,
                log_callback=log_callback
            )
            
            # Print result summary
            print(f"\n{'='*60}", flush=True)
            print(f"Processing Result:", flush=True)
            print(f"  Status: {result.get('status', 'unknown')}", flush=True)
            if result.get('entities_processed'):
                print(f"  Entities processed: {result['entities_processed']}", flush=True)
            if result.get('relationships_processed'):
                print(f"  Relationships processed: {result['relationships_processed']}", flush=True)
            if result.get('folder_processing_info'):
                info = result['folder_processing_info']
                print(f"  Files processed: {info.get('files_processed', 0)}", flush=True)
            print(f"{'='*60}", flush=True)
        except Exception as e:
            print(f"\nERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return

    # Process directory
    if args.dir:
        dir_path = Path(args.dir)
        if not dir_path.exists() or not dir_path.is_dir():
            print(f"Directory not found: {dir_path}")
            sys.exit(1)
        
        stats = process_wiretap_directory(dir_path, args.model)
        print(f"\nFinal stats: {stats}")
        return

    # No arguments provided
    parser.print_help()
    print("\nExample usage:")
    print("  python ingest_audio.py --dir ingestion/audio/example_wiretap")
    print("  python ingest_audio.py --folder ingestion/audio/example_wiretap/00000128")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user, exiting.")
        sys.exit(1)
    except ImportError as e:
        print(f"\nERROR: {e}")
        print("\nPlease install required dependencies:")
        print("  pip install openai-whisper striprtf")
        sys.exit(1)

