"""
Ingestion module - core orchestration for document ingestion.

This is the main logic that:
1. Chunks documents
2. Extracts entities/relationships from each chunk
3. Resolves entities (exact match, fuzzy match, disambiguation)
4. Creates or updates entities in Neo4j
5. Updates summaries inline
"""

from typing import Dict, List, Optional

from neo4j_client import Neo4jClient
from llm_client import (
    extract_entities_and_relationships,
    generate_entity_summary,
    update_entity_notes,
)
from entity_resolution import normalise_key, resolve_entity, merge_entity_data
from chunking import chunk_document


def process_chunk(
    chunk_text: str,
    doc_name: str,
    chunk_index: int,
    total_chunks: int,
    db: Neo4jClient,
    existing_keys: List[str],
) -> Dict:
    """
    Process a single text chunk: extract and resolve entities.

    Args:
        chunk_text: The text chunk to process
        doc_name: Source document name
        chunk_index: Index of this chunk
        total_chunks: Total number of chunks in document
        db: Neo4j client
        existing_keys: List of existing entity keys (for LLM context)

    Returns:
        Dict with 'entities_processed' and 'relationships_processed' counts
    """
    print(f"  Processing chunk {chunk_index + 1}/{total_chunks}...")

    # Extract entities and relationships from chunk
    try:
        extraction = extract_entities_and_relationships(
            text=chunk_text,
            doc_name=doc_name,
            existing_entity_keys=existing_keys,
        )
    except Exception as e:
        print(f"  Error extracting from chunk: {e}")
        return {"entities_processed": 0, "relationships_processed": 0}

    entities = extraction.get("entities", [])
    relationships = extraction.get("relationships", [])

    print(f"  Extracted {len(entities)} entities, {len(relationships)} relationships")

    entities_processed = 0
    relationships_processed = 0

    # Process each entity
    for ent in entities:
        raw_key = ent.get("key", "") or ent.get("name", "")
        name = ent.get("name", raw_key)
        entity_type = ent.get("type", "Other")
        notes = ent.get("notes", "")

        if not raw_key or not name:
            print(f"  Skipping entity with missing key/name: {ent}")
            continue

        # Normalise the key
        key = normalise_key(raw_key)

        if not key:
            print(f"  Skipping entity with empty normalised key: {raw_key}")
            continue

        print(f"  Resolving entity: {name} ({entity_type})")

        # Resolve: find existing or create new
        resolved_key, is_existing = resolve_entity(
            candidate_key=key,
            candidate_name=name,
            candidate_type=entity_type,
            candidate_notes=notes,
            db=db,
        )

        if is_existing:
            # Update existing entity
            existing = db.find_entity_by_key(resolved_key)
            if existing:
                # Merge notes
                merged = merge_entity_data(existing, notes, doc_name)
                updated_notes = merged["notes"]

                # Generate updated summary
                neighbours = db.get_entity_neighbours(resolved_key, limit=5)
                neighbour_descriptions = [
                    f"{n['name']} ({n['type']}) - {n['relationship']}"
                    for n in neighbours
                ]

                new_summary = generate_entity_summary(
                    entity_key=resolved_key,
                    entity_name=existing.get("name", name),
                    entity_type=existing.get("type", entity_type),
                    all_notes=updated_notes,
                    related_entities=neighbour_descriptions,
                )

                # Update in database
                db.update_entity(
                    key=resolved_key,
                    notes=updated_notes,
                    summary=new_summary,
                )

                print(f"    Updated existing entity: {resolved_key}")
        else:
            # Create new entity
            initial_notes = f"[{doc_name}]\n{notes}"

            # Generate initial summary
            initial_summary = generate_entity_summary(
                entity_key=key,
                entity_name=name,
                entity_type=entity_type,
                all_notes=initial_notes,
                related_entities=None,
            )

            # Extract event properties (date, time, amount)
            date = ent.get("date")
            time = ent.get("time")
            amount = ent.get("amount")

            db.create_entity(
                key=key,
                entity_type=entity_type,
                name=name,
                notes=initial_notes,
                summary=initial_summary,
                date=date,
                time=time,
                amount=amount
            )

            # Add to existing keys for subsequent chunks
            existing_keys.append(key)

            print(f"    Created new entity: {key}")

        # Link entity to document
        doc_key = normalise_key(doc_name)
        db.link_entity_to_document(resolved_key if is_existing else key, doc_key)

        entities_processed += 1

    # Process relationships
    for rel in relationships:
        from_key = normalise_key(rel.get("from_key", ""))
        to_key = normalise_key(rel.get("to_key", ""))
        rel_type = rel.get("type", "RELATED_TO")
        rel_notes = rel.get("notes", "")

        if not from_key or not to_key:
            print(f"  Skipping relationship with missing keys: {rel}")
            continue

        # Validate that both entities exist
        from_exists = db.find_entity_by_key(from_key) is not None
        to_exists = db.find_entity_by_key(to_key) is not None

        if not from_exists:
            print(f"  Skipping relationship: source entity '{from_key}' not found")
            continue

        if not to_exists:
            print(f"  Skipping relationship: target entity '{to_key}' not found")
            continue

        db.create_relationship(
            from_key=from_key,
            to_key=to_key,
            rel_type=rel_type,
            doc_name=doc_name,
            notes=rel_notes,
        )

        print(f"    Created relationship: {from_key} -[{rel_type}]-> {to_key}")
        relationships_processed += 1

    return {
        "entities_processed": entities_processed,
        "relationships_processed": relationships_processed,
    }


def ingest_document(
    text: str,
    doc_name: str,
    doc_metadata: Optional[Dict] = None,
) -> Dict:
    """
    Ingest a complete document into the knowledge graph.

    This is the main entry point for document ingestion.

    Args:
        text: Full document text
        doc_name: Document name/filename
        doc_metadata: Optional additional metadata

    Returns:
        Dict with ingestion statistics
    """
    print(f"\n{'='*60}")
    print(f"Ingesting document: {doc_name}")
    print(f"{'='*60}")

    if not text or not text.strip():
        print("Document is empty, skipping.")
        return {"status": "skipped", "reason": "empty"}

    with Neo4jClient() as db:
        # Ensure document node exists
        doc_key = normalise_key(doc_name)
        metadata = dict(doc_metadata or {})
        metadata["source_type"] = metadata.get("source_type", "unknown")

        db.ensure_document(
            doc_key=doc_key,
            doc_name=doc_name,
            metadata=metadata,
        )

        # Get existing entity keys for context
        existing_keys = db.get_all_entity_keys()
        print(f"Found {len(existing_keys)} existing entities in graph")

        # Chunk the document
        chunks = chunk_document(text, doc_name)
        print(f"Document split into {len(chunks)} chunks")

        # Process each chunk
        total_entities = 0
        total_relationships = 0

        for chunk_info in chunks:
            result = process_chunk(
                chunk_text=chunk_info["text"],
                doc_name=doc_name,
                chunk_index=chunk_info["chunk_index"],
                total_chunks=chunk_info["total_chunks"],
                db=db,
                existing_keys=existing_keys,
            )

            total_entities += result["entities_processed"]
            total_relationships += result["relationships_processed"]

    print(f"\n{'='*60}")
    print(f"Ingestion complete: {doc_name}")
    print(f"  Entities processed: {total_entities}")
    print(f"  Relationships processed: {total_relationships}")
    print(f"{'='*60}\n")

    return {
        "status": "complete",
        "document": doc_name,
        "chunks": len(chunks),
        "entities_processed": total_entities,
        "relationships_processed": total_relationships,
    }
