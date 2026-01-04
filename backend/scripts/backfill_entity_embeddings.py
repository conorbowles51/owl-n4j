"""
Backfill embeddings for existing entities.

This script generates embeddings for all entities that are already in Neo4j
but don't have embeddings in the vector database yet.
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
import time
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"

# Add backend directory FIRST so config imports resolve correctly
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import services
from services.neo4j_service import neo4j_service
from services.vector_db_service import vector_db_service
from services.embedding_service import embedding_service


def build_entity_embedding_text(
    name: str,
    entity_type: str,
    summary: Optional[str] = None,
    verified_facts: Optional[List[Dict]] = None,
    ai_insights: Optional[List[Dict]] = None,
) -> str:
    """
    Build text content for entity embedding.
    
    Combines entity name, type, summary, and verified facts into a single
    searchable text representation for semantic search.
    
    Args:
        name: Entity name (e.g., "John Smith")
        entity_type: Entity type (e.g., "Person", "Organization")
        summary: AI-generated entity summary
        verified_facts: List of verified fact dicts with 'text' field
        ai_insights: List of AI insight dicts with 'text' field
        
    Returns:
        Combined text suitable for embedding
    """
    parts = []
    
    # Entity identifier
    parts.append(f"{name} ({entity_type})")
    
    # Summary
    if summary and summary.strip():
        parts.append(f"Summary: {summary.strip()}")
    
    # Verified facts
    if verified_facts:
        fact_texts = [f.get("text", "").strip() for f in verified_facts if f.get("text")]
        if fact_texts:
            parts.append("Verified Facts: " + "; ".join(fact_texts))
    
    # AI insights
    if ai_insights:
        insight_texts = [i.get("text", "").strip() for i in ai_insights if i.get("text")]
        if insight_texts:
            parts.append("Insights: " + "; ".join(insight_texts))
    
    return "\n".join(parts)


def parse_json_field(value: Optional[str]) -> List[Dict]:
    """Parse a JSON string field, returning empty list on failure."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def backfill_entity_embeddings(
    dry_run: bool = False,
    skip_existing: bool = True,
    batch_size: int = 10,
    entity_types: Optional[List[str]] = None,
) -> Dict:
    """
    Generate embeddings for all existing entities.
    
    Args:
        dry_run: If True, only report what would be done without making changes
        skip_existing: If True, skip entities that already have embeddings
        batch_size: Number of entities to process before showing progress
        entity_types: Optional list of entity types to process (e.g., ["Person", "Organization"])
        
    Returns:
        Dictionary with statistics
    """
    print("=" * 60)
    print("Backfilling Embeddings for Existing Entities")
    print("=" * 60)
    
    if embedding_service is None:
        print("\n✗ Embedding service is not configured!")
        print("  Please set OPENAI_API_KEY or configure Ollama")
        return {"status": "error", "reason": "embedding_service_not_configured"}
    
    if dry_run:
        print("\n[DRY RUN MODE] - No changes will be made\n")
    
    # Build query for entities
    # Exclude Document nodes - they have their own embedding
    type_filter = ""
    if entity_types:
        labels = " OR ".join([f"e:{t}" for t in entity_types])
        type_filter = f"WHERE ({labels})"
    
    print("Querying Neo4j for all entities...")
    try:
        cypher = f"""
        MATCH (e)
        WHERE NOT e:Document
        {type_filter}
        RETURN e.key AS key, 
               e.name AS name, 
               labels(e)[0] AS entity_type,
               e.summary AS summary,
               e.verified_facts AS verified_facts,
               e.ai_insights AS ai_insights
        ORDER BY e.key
        """
        entities = neo4j_service.run_cypher(cypher)
        print(f"Found {len(entities)} entities in Neo4j")
    except Exception as e:
        print(f"✗ Error querying Neo4j: {e}")
        return {"status": "error", "reason": str(e)}
    
    if not entities:
        print("No entities found in Neo4j")
        return {"status": "complete", "processed": 0, "skipped": 0, "failed": 0}
    
    # Statistics
    stats = {
        "total": len(entities),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "already_embedded": 0,
        "no_content": 0,
        "embedding_failed": 0,
    }
    
    print(f"\nProcessing {stats['total']} entities...")
    print("-" * 60)
    
    start_time = time.time()
    
    for i, ent in enumerate(entities, 1):
        entity_key = ent.get("key")
        name = ent.get("name", "")
        entity_type = ent.get("entity_type", "Unknown")
        summary = ent.get("summary", "")
        
        # Parse JSON fields
        verified_facts = parse_json_field(ent.get("verified_facts"))
        ai_insights = parse_json_field(ent.get("ai_insights"))
        
        if not entity_key:
            print(f"\n[{i}/{stats['total']}] Skipping entity with missing key")
            stats["skipped"] += 1
            continue
        
        # Check if already embedded
        if skip_existing:
            existing = vector_db_service.get_entity(entity_key)
            if existing:
                print(f"\n[{i}/{stats['total']}] {entity_key} - Already embedded (skipping)")
                stats["already_embedded"] += 1
                continue
        
        print(f"\n[{i}/{stats['total']}] Processing: {entity_key} ({entity_type})")
        
        # Build embedding text
        embedding_text = build_entity_embedding_text(
            name=name,
            entity_type=entity_type,
            summary=summary,
            verified_facts=verified_facts,
            ai_insights=ai_insights,
        )
        
        if not embedding_text.strip():
            print(f"  ✗ No content for embedding")
            stats["no_content"] += 1
            stats["failed"] += 1
            continue
        
        text_length = len(embedding_text)
        print(f"  ✓ Built embedding text ({text_length:,} chars)")
        
        if dry_run:
            print(f"  [DRY RUN] Would generate embedding and store for entity {entity_key}")
            stats["processed"] += 1
            continue
        
        # Generate embedding
        try:
            print("  Generating embedding...")
            embedding = embedding_service.generate_embedding(embedding_text)
            print(f"  ✓ Embedding generated ({len(embedding)} dimensions)")
        except Exception as e:
            print(f"  ✗ Failed to generate embedding: {e}")
            stats["embedding_failed"] += 1
            stats["failed"] += 1
            continue
        
        # Store in vector DB
        try:
            print("  Storing in vector DB...")
            vector_db_service.add_entity(
                entity_key=entity_key,
                text=embedding_text,
                embedding=embedding,
                metadata={
                    "name": name,
                    "entity_type": entity_type,
                }
            )
            print("  ✓ Stored in vector DB")
        except Exception as e:
            print(f"  ✗ Failed to store in vector DB: {e}")
            stats["failed"] += 1
            continue
        
        stats["processed"] += 1
        
        # Progress update every batch_size entities
        if i % batch_size == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = stats["total"] - i
            eta = remaining / rate if rate > 0 else 0
            print(f"\n  Progress: {i}/{stats['total']} ({i/stats['total']*100:.1f}%)")
            print(f"  Rate: {rate:.1f} entities/sec, ETA: {eta:.0f} seconds")
    
    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("Backfill Complete")
    print("=" * 60)
    print(f"Total entities: {stats['total']}")
    print(f"Processed: {stats['processed']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Already embedded: {stats['already_embedded']}")
    print(f"Failed: {stats['failed']}")
    print(f"  - No content: {stats['no_content']}")
    print(f"  - Embedding failed: {stats['embedding_failed']}")
    print(f"\nTime elapsed: {elapsed:.1f} seconds")
    if stats['processed'] > 0:
        print(f"Average time per entity: {elapsed/stats['processed']:.2f} seconds")
    
    return {
        "status": "complete",
        **stats,
        "elapsed_seconds": elapsed,
    }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Backfill embeddings for existing entities"
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
        help="Skip entities that already have embeddings"
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Re-process entities that already have embeddings"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of entities to process before showing progress (default: 10)"
    )
    parser.add_argument(
        "--types",
        nargs="+",
        help="Specific entity types to process (e.g., --types Person Organization)"
    )
    
    args = parser.parse_args()
    
    result = backfill_entity_embeddings(
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        batch_size=args.batch_size,
        entity_types=args.types,
    )
    
    if result.get("status") == "error":
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
