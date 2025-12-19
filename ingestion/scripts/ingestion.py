"""
Ingestion module - core orchestration for document ingestion.

This is the main logic that:
1. Chunks documents
2. Extracts entities/relationships from each chunk
3. Resolves entities (exact match, fuzzy match, disambiguation)
4. Creates or updates entities in Neo4j
5. Updates summaries inline
"""

from typing import Dict, List, Optional, Callable
import time
import threading

from neo4j_client import Neo4jClient
from llm_client import (
    extract_entities_and_relationships,
    generate_entity_summary,
    update_entity_notes,
    get_processing_estimate,
    get_processing_progress_update,
)
from entity_resolution import normalise_key, resolve_entity, merge_entity_data
from chunking import chunk_document
from geocoding import get_location_properties


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

                # Check if we should add location data (if not already present)
                extra_props = None
                location = ent.get("location")
                if location and not existing.get("latitude"):
                    print(f"    Geocoding location for existing entity: {location}")
                    location_props = get_location_properties(location)
                    if location_props.get("latitude"):
                        extra_props = location_props

                # Update in database
                db.update_entity(
                    key=resolved_key,
                    notes=updated_notes,
                    summary=new_summary,
                    extra_props=extra_props,
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
            
            # Geocode location if provided
            location = ent.get("location")
            extra_props = {}
            if location:
                print(f"    Geocoding location: {location}")
                location_props = get_location_properties(location)
                extra_props.update(location_props)

            db.create_entity(
                key=key,
                entity_type=entity_type,
                name=name,
                notes=initial_notes,
                summary=initial_summary,
                date=date,
                time=time,
                amount=amount,
                extra_props=extra_props if extra_props else None,
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
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict:
    """
    Ingest a complete document into the knowledge graph.

    This is the main entry point for document ingestion.

    Args:
        text: Full document text
        doc_name: Document name/filename
        doc_metadata: Optional additional metadata
        log_callback: Optional callback function(message: str) to log progress messages

    Returns:
        Dict with ingestion statistics
    """
    print(f"\n{'='*60}")
    print(f"Ingesting document: {doc_name}")
    print(f"{'='*60}")

    if not text or not text.strip():
        print("Document is empty, skipping.")
        if log_callback:
            log_callback("Document is empty, skipping.")
        return {"status": "skipped", "reason": "empty"}

    # Progress tracking state (shared between main thread and timer thread)
    progress_state = {
        "chunks_processed": 0,
        "total_chunks": 0,
        "entities_processed": 0,
        "relationships_processed": 0,
        "start_time": None,
        "initial_estimate_seconds": None,
        "timer_active": False,
    }
    timer = None

    def get_progress_update():
        """Get a progress update from the LLM and log it."""
        if not progress_state["timer_active"]:
            return
        
        elapsed = int(time.time() - progress_state["start_time"])
        try:
            update = get_processing_progress_update(
                doc_name=doc_name,
                chunks_processed=progress_state["chunks_processed"],
                total_chunks=progress_state["total_chunks"],
                entities_processed=progress_state["entities_processed"],
                relationships_processed=progress_state["relationships_processed"],
                elapsed_seconds=elapsed,
                initial_estimate_seconds=progress_state["initial_estimate_seconds"],
            )
            
            message = f"Progress Update: {update.get('work_completed', '')} "
            message += f"Remaining: {update.get('remaining_work', '')} "
            message += f"Estimated time remaining: {update.get('estimated_remaining_text', '')}"
            if update.get('observations'):
                message += f" {update.get('observations', '')}"
            
            print(f"[Progress] {message}")
            if log_callback:
                log_callback(message)
        except Exception as e:
            # Don't let progress update failures break ingestion
            print(f"[Progress] Failed to get progress update: {e}")
            if log_callback:
                log_callback(f"Progress update error: {e}")
        
        # Schedule next update if still active
        if progress_state["timer_active"]:
            nonlocal timer
            timer = threading.Timer(10.0, get_progress_update)
            timer.start()

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
        existing_count = len(existing_keys)
        print(f"Found {existing_count} existing entities in graph")

        # Chunk the document
        chunks = chunk_document(text, doc_name)
        total_chunks = len(chunks)
        print(f"Document split into {total_chunks} chunks")
        
        progress_state["total_chunks"] = total_chunks
        progress_state["start_time"] = time.time()

        # Get initial processing estimate
        try:
            text_preview = text[:2000] if len(text) > 2000 else text
            estimate = get_processing_estimate(
                doc_name=doc_name,
                text_preview=text_preview,
                total_chunks=total_chunks,
                existing_entity_count=existing_count,
            )
            progress_state["initial_estimate_seconds"] = estimate["estimated_duration_seconds"]
            
            estimate_message = f"Processing estimate: {estimate['estimated_duration_text']}"
            if estimate.get('reasoning'):
                estimate_message += f" ({estimate['reasoning']})"
            
            print(f"[Estimate] {estimate_message}")
            if log_callback:
                log_callback(estimate_message)
        except Exception as e:
            # Don't let estimate failures break ingestion
            print(f"[Estimate] Failed to get initial estimate: {e}")
            if log_callback:
                log_callback(f"Could not get initial estimate: {e}")

        # Start progress tracking timer (updates every 10 seconds)
        progress_state["timer_active"] = True
        timer = threading.Timer(10.0, get_progress_update)
        timer.start()

        # Process each chunk
        total_entities = 0
        total_relationships = 0

        try:
            for chunk_info in chunks:
                result = process_chunk(
                    chunk_text=chunk_info["text"],
                    doc_name=doc_name,
                    chunk_index=chunk_info["chunk_index"],
                    total_chunks=chunk_info["total_chunks"],
                    db=db,
                    existing_keys=existing_keys,
                )

                chunk_entities = result["entities_processed"]
                chunk_relationships = result["relationships_processed"]
                
                total_entities += chunk_entities
                total_relationships += chunk_relationships
                
                # Update progress state
                progress_state["chunks_processed"] += 1
                progress_state["entities_processed"] = total_entities
                progress_state["relationships_processed"] = total_relationships
        finally:
            # Stop the timer
            progress_state["timer_active"] = False
            if timer:
                timer.cancel()

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
