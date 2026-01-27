#!/usr/bin/env python3
"""
ChromaDB Migration Script

Merges documents and entities from legacy ChromaDB stores into a target store,
remapping case_ids according to the provided configuration.

Features:
- Read-only access to legacy stores
- Idempotent: uses upsert() so it can be run multiple times safely
- Dry-run mode to verify before actual migration
- Embedding dimension validation

Usage:
    python migrate_chromadb.py --config migration_config.json
    python migrate_chromadb.py --config migration_config.json --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

import chromadb
from chromadb.config import Settings


def clean_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean metadata for ChromaDB compatibility.
    ChromaDB only accepts str, int, float, bool values.
    """
    cleaned = {}
    for k, v in metadata.items():
        if v is None:
            cleaned[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        else:
            cleaned[k] = str(v)
    return cleaned


def get_collection_dimension(collection) -> Optional[int]:
    """Get the embedding dimension from a collection, if it has any records."""
    if collection.count() > 0:
        sample = collection.peek(1)
        if sample and sample.get("embeddings") and len(sample["embeddings"]) > 0:
            return len(sample["embeddings"][0])
    return None


def extract_records(
    collection,
    case_id_mapping: Dict[str, str],
    collection_name: str
) -> List[Dict[str, Any]]:
    """
    Extract all records from a collection that match the case_id mapping.

    Args:
        collection: ChromaDB collection
        case_id_mapping: Dict mapping legacy case_id -> target case_id
        collection_name: Name of collection (for logging)

    Returns:
        List of record dicts with remapped case_ids
    """
    records = []
    legacy_case_ids = set(case_id_mapping.keys())

    # Get all records including embeddings
    all_data = collection.get(include=["embeddings", "documents", "metadatas"])

    if not all_data or not all_data.get("ids"):
        return records

    for i, record_id in enumerate(all_data["ids"]):
        metadata = all_data.get("metadatas", [{}])[i] if all_data.get("metadatas") else {}
        legacy_case_id = metadata.get("case_id")

        # Skip records not in the mapping
        if legacy_case_id not in legacy_case_ids:
            continue

        embedding = all_data.get("embeddings", [[]])[i] if all_data.get("embeddings") else []
        text = all_data.get("documents", [""])[i] if all_data.get("documents") else ""

        # Remap case_id
        new_metadata = metadata.copy()
        new_metadata["case_id"] = case_id_mapping[legacy_case_id]
        new_metadata = clean_metadata(new_metadata)

        records.append({
            "id": record_id,
            "embedding": embedding,
            "document": text,
            "metadata": new_metadata,
            "original_case_id": legacy_case_id,
            "new_case_id": case_id_mapping[legacy_case_id]
        })

    return records


def migrate_records(
    target_collection,
    records: List[Dict[str, Any]],
    collection_name: str,
    dry_run: bool = True
) -> Dict[str, int]:
    """
    Upsert records into the target collection.

    Args:
        target_collection: Target ChromaDB collection
        records: List of record dicts to upsert
        collection_name: Name of collection (for logging)
        dry_run: If True, don't actually upsert

    Returns:
        Dict with migration statistics
    """
    stats = {
        "total": len(records),
        "migrated": 0,
        "skipped": 0,
        "errors": 0
    }

    if not records:
        return stats

    # Verify dimension compatibility
    target_dim = get_collection_dimension(target_collection)
    if target_dim and records:
        sample_dim = len(records[0]["embedding"]) if records[0]["embedding"] else 0
        if sample_dim and sample_dim != target_dim:
            print(f"  ERROR: Dimension mismatch! Target {collection_name} has {target_dim} dims, "
                  f"but records have {sample_dim} dims")
            stats["errors"] = len(records)
            return stats

    for record in records:
        try:
            if not record["embedding"]:
                print(f"  SKIP: Record {record['id']} has no embedding")
                stats["skipped"] += 1
                continue

            if dry_run:
                print(f"  [DRY-RUN] Would upsert {record['id']} "
                      f"(case_id: {record['original_case_id']} -> {record['new_case_id']})")
            else:
                target_collection.upsert(
                    ids=[record["id"]],
                    embeddings=[record["embedding"]],
                    documents=[record["document"]],
                    metadatas=[record["metadata"]]
                )
            stats["migrated"] += 1

        except Exception as e:
            print(f"  ERROR: Failed to migrate {record['id']}: {e}")
            stats["errors"] += 1

    return stats


def run_migration(config: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    """
    Run the full migration process.

    Args:
        config: Migration configuration dict
        dry_run: If True, don't actually modify target DB

    Returns:
        Dict with migration results
    """
    results = {
        "dry_run": dry_run,
        "stores_processed": 0,
        "documents": {"total": 0, "migrated": 0, "skipped": 0, "errors": 0},
        "entities": {"total": 0, "migrated": 0, "skipped": 0, "errors": 0},
        "errors": []
    }

    # Connect to target DB
    target_path = config["target_db_path"]
    print(f"\n{'='*60}")
    print(f"ChromaDB Migration {'(DRY RUN)' if dry_run else '(LIVE)'}")
    print(f"{'='*60}")
    print(f"\nTarget DB: {target_path}")

    if not Path(target_path).exists():
        error = f"Target DB path does not exist: {target_path}"
        print(f"ERROR: {error}")
        results["errors"].append(error)
        return results

    try:
        target_client = chromadb.PersistentClient(
            path=target_path,
            settings=Settings(anonymized_telemetry=False)
        )
        target_docs = target_client.get_or_create_collection(
            name="documents",
            metadata={"description": "Document embeddings for semantic search"}
        )
        target_entities = target_client.get_or_create_collection(
            name="entities",
            metadata={"description": "Entity embeddings for semantic search"}
        )

        print(f"Target documents count: {target_docs.count()}")
        print(f"Target entities count: {target_entities.count()}")

        target_doc_dim = get_collection_dimension(target_docs)
        target_entity_dim = get_collection_dimension(target_entities)
        print(f"Target document dimension: {target_doc_dim or 'N/A (empty)'}")
        print(f"Target entity dimension: {target_entity_dim or 'N/A (empty)'}")

    except Exception as e:
        error = f"Failed to connect to target DB: {e}"
        print(f"ERROR: {error}")
        results["errors"].append(error)
        return results

    # Process each legacy store
    for store_config in config.get("legacy_stores", []):
        legacy_path = store_config["path"]
        case_id_mapping = store_config.get("case_id_mapping", {})

        print(f"\n{'-'*60}")
        print(f"Processing legacy store: {legacy_path}")
        print(f"Case ID mapping: {case_id_mapping}")

        if not Path(legacy_path).exists():
            error = f"Legacy store path does not exist: {legacy_path}"
            print(f"  ERROR: {error}")
            results["errors"].append(error)
            continue

        try:
            legacy_client = chromadb.PersistentClient(
                path=legacy_path,
                settings=Settings(anonymized_telemetry=False)
            )
        except Exception as e:
            error = f"Failed to connect to legacy store {legacy_path}: {e}"
            print(f"  ERROR: {error}")
            results["errors"].append(error)
            continue

        results["stores_processed"] += 1

        # Process documents collection
        try:
            legacy_docs = legacy_client.get_collection("documents")
            print(f"\n  Documents collection: {legacy_docs.count()} total records")

            doc_records = extract_records(legacy_docs, case_id_mapping, "documents")
            print(f"  Found {len(doc_records)} documents matching case_id mapping")

            if doc_records:
                doc_stats = migrate_records(target_docs, doc_records, "documents", dry_run)
                for key in ["total", "migrated", "skipped", "errors"]:
                    results["documents"][key] += doc_stats[key]

        except Exception as e:
            if "does not exist" in str(e).lower():
                print(f"  Documents collection not found in {legacy_path}")
            else:
                error = f"Error processing documents from {legacy_path}: {e}"
                print(f"  ERROR: {error}")
                results["errors"].append(error)

        # Process entities collection
        try:
            legacy_entities = legacy_client.get_collection("entities")
            print(f"\n  Entities collection: {legacy_entities.count()} total records")

            entity_records = extract_records(legacy_entities, case_id_mapping, "entities")
            print(f"  Found {len(entity_records)} entities matching case_id mapping")

            if entity_records:
                entity_stats = migrate_records(target_entities, entity_records, "entities", dry_run)
                for key in ["total", "migrated", "skipped", "errors"]:
                    results["entities"][key] += entity_stats[key]

        except Exception as e:
            if "does not exist" in str(e).lower():
                print(f"  Entities collection not found in {legacy_path}")
            else:
                error = f"Error processing entities from {legacy_path}: {e}"
                print(f"  ERROR: {error}")
                results["errors"].append(error)

    # Print summary
    print(f"\n{'='*60}")
    print("MIGRATION SUMMARY")
    print(f"{'='*60}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}")
    print(f"Legacy stores processed: {results['stores_processed']}")
    print(f"\nDocuments:")
    print(f"  Total found: {results['documents']['total']}")
    print(f"  {'Would migrate' if dry_run else 'Migrated'}: {results['documents']['migrated']}")
    print(f"  Skipped: {results['documents']['skipped']}")
    print(f"  Errors: {results['documents']['errors']}")
    print(f"\nEntities:")
    print(f"  Total found: {results['entities']['total']}")
    print(f"  {'Would migrate' if dry_run else 'Migrated'}: {results['entities']['migrated']}")
    print(f"  Skipped: {results['entities']['skipped']}")
    print(f"  Errors: {results['entities']['errors']}")

    if results["errors"]:
        print(f"\nErrors encountered:")
        for error in results["errors"]:
            print(f"  - {error}")

    if not dry_run:
        print(f"\nTarget DB final counts:")
        print(f"  Documents: {target_docs.count()}")
        print(f"  Entities: {target_entities.count()}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Migrate ChromaDB data from legacy stores to target store"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to migration config JSON file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (don't modify target DB)"
    )

    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        config = json.load(f)

    # Dry-run can be set via CLI flag or config file
    dry_run = args.dry_run or config.get("dry_run", True)

    # Run migration
    results = run_migration(config, dry_run=dry_run)

    # Exit with error code if there were errors
    if results["errors"] or results["documents"]["errors"] or results["entities"]["errors"]:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
