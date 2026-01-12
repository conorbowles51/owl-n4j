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
import json
import sys
import importlib.util
from pathlib import Path

# Import profile_loader from the same directory (ingestion/scripts)
# IMPORTANT: This must happen BEFORE any sys.path manipulation that adds backend/
# Use importlib to explicitly load from the correct path to avoid conflicts
# with backend/profile_loader.py when backend is added to sys.path
_scripts_dir = Path(__file__).resolve().parent
_profile_loader_path = _scripts_dir / "profile_loader.py"
_profile_loader_spec = importlib.util.spec_from_file_location("ingestion_profile_loader_ingestion", _profile_loader_path)
_profile_loader_module_ingestion = importlib.util.module_from_spec(_profile_loader_spec)
_profile_loader_spec.loader.exec_module(_profile_loader_module_ingestion)
get_llm_config = _profile_loader_module_ingestion.get_llm_config

from neo4j_client import Neo4jClient
from llm_client import (
    extract_entities_and_relationships,
    generate_entity_summary,
    update_entity_notes,
)
from entity_resolution import normalise_key, resolve_entity, merge_entity_data
from chunking import chunk_document
from geocoding import get_location_properties
from logging_utils import log_progress, log_error, log_warning


# Import vector DB and embedding services from backend
# Add backend directory to path if not already there
backend_dir = Path(__file__).parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

try:
    from services.vector_db_service import vector_db_service
    from services.embedding_service import EmbeddingService
    # Don't create a global instance - we'll create it based on profile config
    VECTOR_DB_AVAILABLE = True
except (ImportError, ValueError) as e:
    # Note: can't use log_warning here as it's module-level initialization
    print(f"[WARNING] [Ingestion] Vector DB services not available: {e}")
    print("[WARNING] [Ingestion] Document and entity embeddings will be skipped")
    VECTOR_DB_AVAILABLE = False
    vector_db_service = None
    EmbeddingService = None


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
    
    # AI insights (optional - include for richer context)
    if ai_insights:
        insight_texts = [i.get("text", "").strip() for i in ai_insights if i.get("text")]
        if insight_texts:
            parts.append("Insights: " + "; ".join(insight_texts))
    
    return "\n".join(parts)


def store_entity_embedding(
    entity_key: str,
    name: str,
    entity_type: str,
    summary: Optional[str] = None,
    verified_facts: Optional[List[Dict]] = None,
    ai_insights: Optional[List[Dict]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> bool:
    """
    Generate and store embedding for an entity.
    
    Args:
        entity_key: Unique entity key (e.g., 'john-smith')
        name: Entity name
        entity_type: Entity type
        summary: Entity summary
        verified_facts: List of verified facts
        ai_insights: List of AI insights
        log_callback: Optional callback for logging
        
    Returns:
        True if embedding was stored successfully, False otherwise
    """
    if not VECTOR_DB_AVAILABLE or not EmbeddingService:
        return False
    
    try:
        # Build embedding text
        embedding_text = build_entity_embedding_text(
            name=name,
            entity_type=entity_type,
            summary=summary,
            verified_facts=verified_facts,
            ai_insights=ai_insights,
        )
        
        if not embedding_text.strip():
            log_warning(f"Skipping entity embedding for {entity_key}: no text content", log_callback)
            return False
        
        # Determine embedding provider from profile's LLM config
        embedding_provider = None
        embedding_model = None
        llm_config = get_llm_config(profile_name)
        if llm_config and llm_config.get("provider"):
            embedding_provider = llm_config.get("provider").lower()
            if embedding_provider == "openai":
                embedding_model = "text-embedding-3-small"
            elif embedding_provider == "ollama":
                embedding_model = "qwen3-embedding:4b"
        
        # Create embedding service instance based on profile's LLM config
        profile_embedding_service = None
        if embedding_provider:
            try:
                profile_embedding_service = EmbeddingService(
                    provider=embedding_provider,
                    model=embedding_model
                )
            except ValueError as e:
                # Handle missing API key or configuration errors
                error_msg = str(e)
                if "OPENAI_API_KEY" in error_msg:
                    log_warning(
                        f"Entity embedding: Cannot use OpenAI embedding - OPENAI_API_KEY not set. "
                        f"Please set OPENAI_API_KEY in your .env file or switch to Ollama provider in the profile.",
                        log_callback
                    )
                else:
                    log_warning(f"Entity embedding: Configuration error - {error_msg}", log_callback)
                return False
            except Exception as e:
                log_warning(f"Entity embedding: Failed to initialize embedding service - {e}", log_callback)
                return False
        else:
            # Fall back to default embedding service
            try:
                profile_embedding_service = EmbeddingService()
            except Exception as e:
                log_warning(f"Entity embedding: Failed to initialize default embedding service - {e}", log_callback)
                return False
        
        if not profile_embedding_service:
            return False
        
        # Generate embedding
        embedding = profile_embedding_service.generate_embedding(embedding_text)
        
        # Store in vector DB
        vector_db_service.add_entity(
            entity_key=entity_key,
            text=embedding_text,
            embedding=embedding,
            metadata={
                "name": name,
                "entity_type": entity_type,
            }
        )
        
        log_progress(f"Entity embedding stored: {entity_key}", log_callback)
        
        return True
    except Exception as e:
        log_warning(f"Entity embedding failed for {entity_key}: {e}", log_callback)
        return False


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
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
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
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Dict with 'entities_processed' and 'relationships_processed' counts
    """
    page_info = ""
    if page_start is not None:
        if page_end is not None and page_end != page_start:
            page_info = f" (pages {page_start}-{page_end})"
        else:
            page_info = f" (page {page_start})"
    
    log_progress(f"Processing chunk {chunk_index + 1}/{total_chunks}{page_info}...", log_callback, prefix="  ")

    # Extract entities and relationships from chunk with page context
    chunk_num = chunk_index + 1
    try:
        log_progress(f"  [6.{chunk_num}.1] Entity extraction: Calling LLM to extract entities and relationships from chunk...", log_callback)
        extraction = extract_entities_and_relationships(
            text=chunk_text,
            doc_name=doc_name,
            existing_entity_keys=existing_keys,
            page_start=page_start,
            page_end=page_end,
            profile_name=profile_name,
            log_callback=log_callback,
        )
        log_progress(f"  [6.{chunk_num}.1] Entity extraction: LLM extraction completed", log_callback)
    except Exception as e:
        log_error(f"  [6.{chunk_num}.1] Entity extraction: FAILED - {e}", log_callback)
        return {"entities_processed": 0, "relationships_processed": 0}

    entities = extraction.get("entities", [])
    relationships = extraction.get("relationships", [])

    log_progress(f"  [6.{chunk_num}.1] Entity extraction: Extracted {len(entities)} entities, {len(relationships)} relationships", log_callback)

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
        

        if not raw_key or not name:
            log_warning(f"Skipping entity with missing key/name: {ent}", log_callback, prefix="  ")
            continue

        # Normalise the key
        key = normalise_key(raw_key)

        if not key:
            log_warning(f"Skipping entity with empty normalised key: {raw_key}", log_callback, prefix="  ")
            continue

        entity_num = entities.index(ent) + 1 if ent in entities else 0
        log_progress(f"  [6.{chunk_index + 1}.2] Entity resolution: Resolving entity {entity_num}/{len(entities)}: {name} ({entity_type})", log_callback)

        # Resolve: find existing or create new
        facts_str = "\n".join(
            fact.get("text", "") for fact in verified_facts if fact.get("text")
        )
        resolved_key, is_existing = resolve_entity(
            candidate_key=key,
            candidate_name=name,
            candidate_type=entity_type,
            candidate_facts=facts_str,
            db=db,
            profile_name=profile_name,
            log_callback=log_callback,
        )

        if is_existing:
            log_progress(f"  [6.{chunk_index + 1}.2] Entity resolution: Entity '{name}' matched existing entity (key: {resolved_key})", log_callback)
            # Update existing entity
            existing = db.find_entity_by_key(resolved_key)
            if existing:
                # Merge verified facts and AI insights
                merged = merge_entity_data(
                    existing_entity=existing,
                    new_verified_facts=verified_facts,
                    new_ai_insights=ai_insights,
                    doc_name=doc_name,
                )
                merged_facts = merged["verified_facts"]
                merged_insights = merged["ai_insights"]

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
                    all_notes="",  # No longer using notes, verified_facts contains the data
                    related_entities=neighbour_descriptions,
                    verified_facts=merged_facts,
                    profile_name=profile_name,
                    log_callback=log_callback,
                )

                # Check if we should add location data (if not already present)
                extra_props = {}
                location = ent.get("location")
                if location and not existing.get("latitude"):
                    log_progress(f"Geocoding location for existing entity: {location}", log_callback, prefix="    ")
                    location_props = get_location_properties(location)
                    if location_props.get("latitude"):
                        extra_props.update(location_props)
                
                # Add structured data as JSON strings
                extra_props["verified_facts"] = json.dumps(merged_facts)
                extra_props["ai_insights"] = json.dumps(merged_insights)

                # Update in database
                db.update_entity(
                    key=resolved_key,
                    summary=new_summary,
                    extra_props=extra_props,
                )

                log_progress(f"Updated existing entity: {resolved_key}", log_callback, prefix="    ")
                
                # Update entity embedding (summary/facts changed)
                store_entity_embedding(
                    entity_key=resolved_key,
                    name=existing.get("name", name),
                    entity_type=existing.get("type", entity_type),
                    summary=new_summary,
                    verified_facts=merged_facts,
                    ai_insights=merged_insights,
                    log_callback=log_callback,
                    profile_name=profile_name,
                )
        else:
            # Create new entity
            log_progress(f"  [6.{chunk_index + 1}.3] Entity creation: Creating new entity '{name}' (key: {key})", log_callback)
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
                all_notes="",  # No longer using notes, verified_facts contains the data
                related_entities=None,
                verified_facts=enriched_facts,
                profile_name=profile_name,
                log_callback=log_callback,
            )

            # Extract event properties (date, time, amount)
            date = ent.get("date")
            ent_time = ent.get("time")
            amount = ent.get("amount")
            
            # Geocode location if provided
            location = ent.get("location")
            extra_props = {}
            if location:
                log_progress(f"Geocoding location: {location}", log_callback, prefix="    ")
                location_props = get_location_properties(location)
                extra_props.update(location_props)
            
            # Add structured data as JSON strings
            extra_props["verified_facts"] = json.dumps(enriched_facts)
            extra_props["ai_insights"] = json.dumps(enriched_insights)

            db.create_entity(
                key=key,
                entity_type=entity_type,
                name=name,
                notes="",  # Deprecated - using verified_facts instead
                summary=initial_summary,
                date=date,
                time=ent_time,
                amount=amount,
                extra_props=extra_props,
            )

            # Add to existing keys for subsequent chunks
            existing_keys.append(key)

            log_progress(f"Created new entity: {key}", log_callback, prefix="    ")
            
            # Store entity embedding
            store_entity_embedding(
                entity_key=key,
                name=name,
                entity_type=entity_type,
                summary=initial_summary,
                verified_facts=enriched_facts,
                ai_insights=enriched_insights,
                log_callback=log_callback,
                profile_name=profile_name,
            )

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
            log_warning(f"Skipping relationship with missing keys: {rel}", log_callback, prefix="  ")
            continue

        # Validate that both entities exist
        from_exists = db.find_entity_by_key(from_key) is not None
        to_exists = db.find_entity_by_key(to_key) is not None

        if not from_exists:
            log_warning(f"Skipping relationship: source entity '{from_key}' not found", log_callback, prefix="  ")
            continue

        if not to_exists:
            log_warning(f"Skipping relationship: target entity '{to_key}' not found", log_callback, prefix="  ")
            continue

        db.create_relationship(
            from_key=from_key,
            to_key=to_key,
            rel_type=rel_type,
            doc_name=doc_name,
            notes=rel_notes,
        )

        log_progress(f"Created relationship: {from_key} -[{rel_type}]-> {to_key}", log_callback, prefix="    ")
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
    profile_name: Optional[str] = None,
) -> Dict:
    """
    Ingest a complete document into the knowledge graph.

    This is the main entry point for document ingestion.

    Args:
        text: Full document text
        doc_name: Document name/filename
        doc_metadata: Optional additional metadata
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Dict with ingestion statistics
    """
    log_progress(f"{'='*60}", log_callback)
    log_progress(f"Ingesting document: {doc_name}", log_callback)
    log_progress(f"{'='*60}", log_callback)

    # Log LLM configuration from profile
    from config import OLLAMA_BASE_URL
    llm_config = get_llm_config(profile_name)
    
    if llm_config and llm_config.get("provider") and llm_config.get("model_id"):
        # Use profile's LLM config
        llm_provider = llm_config.get("provider")
        llm_model = llm_config.get("model_id")
        log_progress(f"[Configuration] LLM Provider: {llm_provider.capitalize()}", log_callback)
        log_progress(f"[Configuration] LLM Model: {llm_model}", log_callback)
        if llm_provider == "ollama":
            log_progress(f"[Configuration] LLM Server: {OLLAMA_BASE_URL}", log_callback)
        else:
            log_progress(f"[Configuration] LLM Server: OpenAI (Remote)", log_callback)
    else:
        # Fallback to global config
        from config import OLLAMA_MODEL
        log_progress(f"[Configuration] LLM Provider: Ollama (default)", log_callback)
        log_progress(f"[Configuration] LLM Model: {OLLAMA_MODEL}", log_callback)
        log_progress(f"[Configuration] LLM Server: {OLLAMA_BASE_URL}", log_callback)
    
    # Determine embedding provider and model from profile's LLM config
    embedding_provider = None
    embedding_model = None
    
    if llm_config and llm_config.get("provider"):
        # Match embedding provider to LLM provider from profile
        embedding_provider = llm_config.get("provider").lower()
        # Use default embedding models based on provider
        if embedding_provider == "openai":
            embedding_model = "text-embedding-3-small"
        elif embedding_provider == "ollama":
            embedding_model = "qwen3-embedding:4b"  # Default Ollama embedding model
    
    # Log Embedding configuration
    if VECTOR_DB_AVAILABLE and EmbeddingService:
        if embedding_provider:
            log_progress(f"[Configuration] Embedding Provider: {embedding_provider.capitalize()} (matched to LLM provider)", log_callback)
            log_progress(f"[Configuration] Embedding Model: {embedding_model}", log_callback)
        else:
            log_progress(f"[Configuration] Embedding Provider: Using default from config", log_callback)
        log_progress(f"[Configuration] Vector DB: Enabled (ChromaDB)", log_callback)
    else:
        log_progress(f"[Configuration] Vector DB: Disabled", log_callback)
        log_progress(f"[Configuration] Embedding: Not available", log_callback)
    
    log_progress(f"{'='*60}", log_callback)

    if not text or not text.strip():
        log_progress("[Step 1] Document validation: Document is empty, skipping.", log_callback)
        return {"status": "skipped", "reason": "empty"}

    log_progress(f"[Step 1] Document validation: Document has {len(text)} characters", log_callback)

    with Neo4jClient() as db:
        log_progress(f"[Step 2] Neo4j connection: Connected successfully", log_callback)
        
        # Ensure document node exists
        doc_key = normalise_key(doc_name)
        metadata = dict(doc_metadata or {})
        metadata["source_type"] = metadata.get("source_type", "unknown")

        log_progress(f"[Step 3] Document node: Creating/updating document node (key: {doc_key})", log_callback)
        doc_id = db.ensure_document(
            doc_key=doc_key,
            doc_name=doc_name,
            metadata=metadata,
        )
        log_progress(f"[Step 3] Document node: Created/updated successfully (ID: {doc_id})", log_callback)

        # Get existing entity keys for context
        log_progress(f"[Step 4] Graph context: Loading existing entities from graph", log_callback)
        existing_keys = db.get_all_entity_keys()
        existing_count = len(existing_keys)
        log_progress(f"[Step 4] Graph context: Found {existing_count} existing entities in graph", log_callback)

        # Chunk the document
        log_progress(f"[Step 5] Document chunking: Splitting document into chunks", log_callback)
        chunks = chunk_document(text, doc_name)
        total_chunks = len(chunks)
        log_progress(f"[Step 5] Document chunking: Document split into {total_chunks} chunks", log_callback)

        # Process each chunk
        log_progress(f"[Step 6] Chunk processing: Starting to process {total_chunks} chunks", log_callback)
        total_entities = 0
        total_relationships = 0

        for chunk_info in chunks:
            chunk_idx = chunk_info["chunk_index"]
            chunk_num = chunk_idx + 1
            log_progress(f"[Step 6.{chunk_num}] Processing chunk {chunk_num}/{total_chunks}...", log_callback)
            
            result = process_chunk(
                chunk_text=chunk_info["text"],
                doc_name=doc_name,
                chunk_index=chunk_info["chunk_index"],
                total_chunks=chunk_info["total_chunks"],
                db=db,
                existing_keys=existing_keys,
                page_start=chunk_info.get("page_start"),
                page_end=chunk_info.get("page_end"),
                log_callback=log_callback,
                profile_name=profile_name,
            )

            chunk_entities = result["entities_processed"]
            chunk_relationships = result["relationships_processed"]
            
            log_progress(f"[Step 6.{chunk_num}] Chunk {chunk_num} complete: {chunk_entities} entities, {chunk_relationships} relationships", log_callback)
                
            total_entities += chunk_entities
            total_relationships += chunk_relationships
        
        log_progress(f"[Step 6] Chunk processing: All chunks processed. Total: {total_entities} entities, {total_relationships} relationships", log_callback)

        # Generate and store document embedding (after all chunks processed)
        embedding_stored = False
        log_progress(f"[Step 7] Document embedding: Starting embedding generation", log_callback)
        if VECTOR_DB_AVAILABLE and text and text.strip() and EmbeddingService:
            try:
                # Create embedding service instance based on profile's LLM config
                # This ensures embedding provider matches LLM provider
                if embedding_provider:
                    try:
                        profile_embedding_service = EmbeddingService(
                            provider=embedding_provider,
                            model=embedding_model
                        )
                    except ValueError as e:
                        # Handle missing API key or configuration errors
                        error_msg = str(e)
                        if "OPENAI_API_KEY" in error_msg:
                            log_warning(
                                f"[Step 7] Document embedding: Cannot use OpenAI embedding - OPENAI_API_KEY not set in environment variables. "
                                f"Please set OPENAI_API_KEY in your .env file or switch to Ollama provider in the profile.",
                                log_callback
                            )
                        else:
                            log_warning(f"[Step 7] Document embedding: Configuration error - {error_msg}", log_callback)
                        profile_embedding_service = None
                    except Exception as e:
                        log_warning(f"[Step 7] Document embedding: Failed to initialize embedding service - {e}", log_callback)
                        profile_embedding_service = None
                else:
                    # Fall back to default embedding service
                    try:
                        profile_embedding_service = EmbeddingService()
                    except Exception as e:
                        log_warning(f"[Step 7] Document embedding: Failed to initialize default embedding service - {e}", log_callback)
                        profile_embedding_service = None
                
                if not profile_embedding_service:
                    log_progress(f"[Step 7] Document embedding: Skipped (embedding service not available)", log_callback)
                else:
                    log_progress(f"[Step 7] Document embedding: Using {profile_embedding_service.provider} provider with model '{profile_embedding_service.model}'", log_callback)
                    log_progress(f"[Step 7] Document embedding: Generating embedding for document text ({len(text)} characters)", log_callback)
                    
                    # Generate embedding for full document text
                    embedding = profile_embedding_service.generate_embedding(text)
                log_progress(f"[Step 7] Document embedding: Embedding generated successfully (dimension: {len(embedding)})", log_callback)
                
                # Store in vector DB
                log_progress(f"[Step 7] Document embedding: Storing embedding in vector database", log_callback)
                vector_db_service.add_document(
                    doc_id=doc_id,
                    text=text[:10000],  # Limit text length for storage
                    embedding=embedding,
                    metadata={
                        "filename": doc_name,
                        "doc_key": doc_key,
                        "case_id": metadata.get("case_id"),
                        "source_type": metadata.get("source_type", "unknown"),
                    }
                )
                log_progress(f"[Step 7] Document embedding: Embedding stored in vector database", log_callback)
                
                # Update Neo4j Document node with vector_db_id
                log_progress(f"[Step 7] Document embedding: Linking document node to vector database (vector_db_id: {doc_id})", log_callback)
                db.update_document(doc_key, {"vector_db_id": doc_id})
                
                embedding_stored = True
                log_progress(f"[Step 7] Document embedding: Completed successfully", log_callback)
            except Exception as e:
                # Don't fail ingestion if embedding fails
                log_warning(f"[Step 7] Document embedding: FAILED - {e}", log_callback)
        else:
            if not VECTOR_DB_AVAILABLE:
                log_progress(f"[Step 7] Document embedding: Skipped (Vector DB not available)", log_callback)
            else:
                log_progress(f"[Step 7] Document embedding: Skipped (Document text is empty)", log_callback)

    log_progress(f"{'='*60}", log_callback)
    log_progress(f"[Final] Ingestion complete: {doc_name}", log_callback)
    log_progress(f"[Final] Summary: Entities processed: {total_entities}", log_callback)
    log_progress(f"[Final] Summary: Relationships processed: {total_relationships}", log_callback)
    if embedding_stored:
        log_progress(f"[Final] Summary: Document embedding: Stored successfully", log_callback)
    else:
        log_progress(f"[Final] Summary: Document embedding: Not stored", log_callback)
    log_progress(f"{'='*60}", log_callback)

    return {
        "status": "complete",
        "document": doc_name,
        "chunks": len(chunks),
        "entities_processed": total_entities,
        "relationships_processed": total_relationships,
        "embedding_stored": embedding_stored,
    }
