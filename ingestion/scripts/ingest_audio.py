#!/usr/bin/env python3
"""
Audio Ingestion CLI - Entry point for wiretap audio ingestion.

Processes wiretap folders containing audio files and metadata,
transcribes using WhisperAI, and ingests into Neo4j.

Usage:
    python ingest_audio.py --dir ingestion/audio/example_wiretap
    python ingest_audio.py --folder ingestion/audio/example_wiretap/00000128
    python ingest_audio.py --dir ingestion/audio/example_wiretap --model large
"""

import argparse
import sys
from pathlib import Path

from audio_processor import process_wiretap_directory, ingest_wiretap_folder, load_whisper_model
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

    args = parser.parse_args()

    # Clear database if requested
    if args.clear:
        confirm = input("This will delete ALL data. Continue? (y/N): ")
        if confirm.lower() == "y":
            clear_database()
        else:
            print("Aborted.")
            return

    # Process specific folder
    if args.folder:
        folder_path = Path(args.folder)
        if not folder_path.exists() or not folder_path.is_dir():
            print(f"Folder not found or is not a directory: {folder_path}", flush=True)
            sys.exit(1)
        
        print(f"Loading Whisper model: {args.model}", flush=True)
        model = load_whisper_model(args.model)
        
        # Create a log callback that prints to stdout (which will be captured by subprocess)
        def log_callback(message: str):
            print(message, flush=True)
        
        result = ingest_wiretap_folder(folder_path, model, log_callback)
        print(f"\nResult: {result}", flush=True)
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

