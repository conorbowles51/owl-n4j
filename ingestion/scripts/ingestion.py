"""
Ingestion module - core orchestration for document ingestion.

This is the main logic that:
1. Chunks documents
2. Extracts entities/relationships from each chunk
3. Resolves entities (exact match, fuzzy match, disambiguation)
4. Creates or updates entities in Neo4j
5. Updates summaries inline
6. Stores verified facts with citations and AI insights separately
"""

from typing import Dict, List, Optional, Callable
import time
import threading
import json

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


def merge_verified_facts(existing_facts: List[Dict], new_facts: List[Dict], doc_name: str) -> List[Dict]:
    """
    Merge new verified facts with existing ones, avoiding duplicates.
    
    Args:
        existing_facts: List of existing fact dicts
        new_facts: List of new fact dicts from extraction
        doc_name: Source document name to add to new facts
        
    Returns:
        Merged list of verified facts
    """
    if not existing_facts:
        existing_facts = []
    
    # Add source_doc to new facts
    enriched_new_facts = []
    for fact in (new_facts or []):
        enriched_fact = dict(fact)
        enriched_fact["source_doc"] = doc_name
        enriched_new_facts.append(enriched_fact)
    
    # Simple merge - combine and dedupe by text
    existing_texts = {f.get("text", "").lower().strip() for f in existing_facts}
    
    merged = list(existing_facts)
    for fact in enriched_new_facts:
        fact_text = fact.get("text", "").lower().strip()
        if fact_text and fact_text not in existing_texts:
            merged.append(fact)
            existing_texts.add(fact_text)
    
    return merged


def merge_ai_insights(existing_insights: List[Dict], new_insights: List[Dict], doc_name: str) -> List[Dict]:
    """
    Merge new AI insights with existing ones, avoiding duplicates.
    
    Args:
        existing_insights: List of existing insight dicts
        new_insights: List of new insight dicts from extraction
        doc_name: Source document name to add to new insights
        
    Returns:
        Merged list of AI insights
    """
    if not existing_insights:
        existing_insights = []
    
    # Add source_doc to new insights
    enriched_new_insights = []
    for insight in (new_insights or []):
        enriched_insight = dict(insight)
        enriched_insight["source_doc"] = doc_name
        enriched_new_insights.append(enriched_insight)
    
    # Simple merge - combine and dedupe by text
    existing_texts = {i.get("text", "").lower().strip() for i in existing_insights}
    
    merged = list(existing_insights)
    for insight in enriched_new_insights:
        insight_text = insight.get("text", "").lower().strip()
        if insight_text and insight_text not in existing_texts:
            merged.append(insight)
            existing_texts.add(insight_text)
    
    return merged


def process_chunk(
    chunk_text: str,
    doc_name: str,
    chunk_index: int,
    total_chunks: int,
    db: Neo4jClient,
    existing_keys: List[str],
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
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
        page_start: First page this chunk covers (for citations)
        page_end: Last page this chunk covers (for citations)

    Returns:
        Dict with 'entities_processed' and 'relationships_processed' counts
    """
    page_info = ""
    if page_start is not None:
        if page_end is not None and page_end != page_start:
            page_info = f" (pages {page_start}-{page_end})"
        else:
            page_info = f" (page {page_start})"
    
    print(f"  Processing chunk {chunk_index + 1}/{total_chunks}{page_info}...")

    # Extract entities and relationships from chunk with page context
    try:
        extraction = extract_entities_and_relationships(
            text=chunk_text,
            doc_name=doc_name,
            existing_entity_keys=existing_keys,
            page_start=page_start,
            page_end=page_end,
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
        
        # Get the new structured data
        verified_facts = ent.get("verified_facts", [])
        ai_insights = ent.get("ai_insights", [])
        
        # Build legacy notes from verified facts for backwards compatibility
        notes_parts = [f.get("text", "") for f in verified_facts if f.get("text")]
        notes = "; ".join(notes_parts) if notes_parts else ent.get("notes", "")

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
                # Merge notes (legacy)
                merged = merge_entity_data(existing, notes, doc_name)
                updated_notes = merged["notes"]
                
                # Merge verified facts and AI insights
                existing_facts_json = existing.get("verified_facts")
                existing_facts = json.loads(existing_facts_json) if existing_facts_json else []
                merged_facts = merge_verified_facts(existing_facts, verified_facts, doc_name)
                
                existing_insights_json = existing.get("ai_insights")
                existing_insights = json.loads(existing_insights_json) if existing_insights_json else []
                merged_insights = merge_ai_insights(existing_insights, ai_insights, doc_name)

                # Generate updated summary from verified facts
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
                    verified_facts=merged_facts,
                )

                # Check if we should add location data (if not already present)
                extra_props = {}
                location = ent.get("location")
                if location and not existing.get("latitude"):
                    print(f"    Geocoding location for existing entity: {location}")
                    location_props = get_location_properties(location)
                    if location_props.get("latitude"):
                        extra_props.update(location_props)
                
                # Add structured data as JSON strings
                extra_props["verified_facts"] = json.dumps(merged_facts)
                extra_props["ai_insights"] = json.dumps(merged_insights)

                # Update in database
                db.update_entity(
                    key=resolved_key,
                    notes=updated_notes,
                    summary=new_summary,
                    extra_props=extra_props if extra_props else None,
                )

                print(f"    Updated existing entity: {resolved_key}")
        else:
            # Create new entity
            initial_notes = f"[{doc_name}]\n{notes}"
            
            # Enrich verified facts with source document
            enriched_facts = []
            for fact in verified_facts:
                enriched_fact = dict(fact)
                enriched_fact["source_doc"] = doc_name
                enriched_facts.append(enriched_fact)
            
            # Enrich AI insights with source document
            enriched_insights = []
            for insight in ai_insights:
                enriched_insight = dict(insight)
                enriched_insight["source_doc"] = doc_name
                enriched_insights.append(enriched_insight)

            # Generate initial summary from verified facts
            initial_summary = generate_entity_summary(
                entity_key=key,
                entity_name=name,
                entity_type=entity_type,
                all_notes=initial_notes,
                related_entities=None,
                verified_facts=enriched_facts,
            )

            # Extract event properties (date, time, amount)
            date = ent.get("date")
            ent_time = ent.get("time")
            amount = ent.get("amount")
            
            # Geocode location if provided
            location = ent.get("location")
            extra_props = {}
            if location:
                print(f"    Geocoding location: {location}")
                location_props = get_location_properties(location)
                extra_props.update(location_props)
            
            # Add structured data as JSON strings
            extra_props["verified_facts"] = json.dumps(enriched_facts)
            extra_props["ai_insights"] = json.dumps(enriched_insights)

            db.create_entity(
                key=key,
                entity_type=entity_type,
                name=name,
                notes=initial_notes,
                summary=initial_summary,
                date=date,
                time=ent_time,
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
                    page_start=chunk_info.get("page_start"),
                    page_end=chunk_info.get("page_end"),
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
