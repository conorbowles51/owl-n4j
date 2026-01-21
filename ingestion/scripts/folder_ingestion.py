"""
Folder Ingestion module - profile-based folder processing and ingestion.

Provides functions to process folders using profiles and ingest the results
through the standard document ingestion pipeline (with vectorization, entity extraction, etc.).
"""

from pathlib import Path
from typing import Dict, Optional, Callable

from folder_processor import process_folder_with_profile
from ingestion import ingest_document
from logging_utils import log_progress, log_error


def ingest_folder_with_profile(
    folder_path: Path,
    profile_name: str,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    Process a folder using a profile and ingest it through the standard pipeline.
    
    This function:
    1. Processes the folder according to profile rules (transcription, metadata extraction)
    2. Combines results into structured text
    3. Ingests the text using ingest_document() (chunking, entity extraction, vectorization, Neo4j storage)
    
    The result goes through the same ingestion pipeline as regular documents:
    - Document chunking
    - Entity/relationship extraction via LLM
    - Entity resolution
    - Neo4j storage (entities, relationships, document node)
    - Vector DB storage (document chunks and entity embeddings)
    
    Args:
        folder_path: Path to the folder to process
        profile_name: Name of the profile to use (must have folder_processing config)
        case_id: REQUIRED - Case ID to associate with all entities/relationships
        log_callback: Optional logging callback
    
    Returns:
        Dict with ingestion result (same format as ingest_document)
    
    Raises:
        ValueError: If case_id is not provided or profile doesn't have folder_processing config
    """
    if not case_id:
        raise ValueError("case_id is required for folder ingestion")
    
    def log(message: str):
        if log_callback:
            log_callback(message)
        print(message, flush=True)
    
    log("="*60)
    log(f"Processing and ingesting folder: {folder_path.name}")
    log(f"Profile: {profile_name}")
    log(f"Case ID: {case_id}")
    log("="*60)
    
    try:
        # Step 1: Process folder according to profile
        log("[Folder Processing] Processing folder files according to profile rules...")
        folder_data = process_folder_with_profile(
            folder_path=folder_path,
            profile_name=profile_name,
            case_id=case_id,
            log_callback=log_callback
        )
        
        structured_text = folder_data["text"]
        metadata = folder_data["metadata"]
        folder_name = folder_data["folder_name"]
        processing_info = folder_data["processing_info"]
        
        log(f"[Folder Processing] Generated structured text: {len(structured_text)} characters")
        log(f"[Folder Processing] Processing info: {processing_info}")
        
        if not structured_text or not structured_text.strip():
            log("[Folder Processing] WARNING: No text generated from folder processing")
            return {
                "status": "skipped",
                "reason": "no_text_generated",
                "folder": folder_name,
                "processing_info": processing_info
            }
        
        # Step 2: Generate document name
        # Use folder name with profile prefix for clarity
        doc_name = f"{profile_name}_{folder_name}"
        
        # Step 3: Ingest using standard document ingestion pipeline
        log("[Ingestion] Ingesting processed folder content through standard pipeline...")
        log("[Ingestion] This will: chunk, extract entities, resolve entities, store in Neo4j, and vectorize")
        
        ingestion_result = ingest_document(
            text=structured_text,
            doc_name=doc_name,
            case_id=case_id,
            doc_metadata=metadata,
            log_callback=log_callback,
            profile_name=profile_name,  # Use same profile for LLM extraction
        )
        
        # Add folder processing info to result
        if isinstance(ingestion_result, dict):
            ingestion_result["folder_processing_info"] = processing_info
            ingestion_result["folder_name"] = folder_name
            ingestion_result["profile_used"] = profile_name
        
        log("[Ingestion] Folder ingestion complete")
        log("="*60)
        
        return ingestion_result
    
    except Exception as e:
        error_msg = f"Failed to process and ingest folder: {str(e)}"
        log_error(error_msg, log_callback)
        return {
            "status": "error",
            "error": str(e),
            "folder": folder_path.name if folder_path else "unknown"
        }
