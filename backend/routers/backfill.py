"""
Backfill Router - endpoints for backfilling document embeddings.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user
from services.neo4j_service import neo4j_service
from services.vector_db_service import vector_db_service
from services.embedding_service import embedding_service
from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR
from pathlib import Path
import sys
import importlib.util

# Import pdf_ingestion from ingestion/scripts without modifying sys.path globally
project_root = Path(__file__).parent.parent.parent
pdf_ingestion_path = project_root / "ingestion" / "scripts" / "pdf_ingestion.py"

PDF_EXTRACTION_AVAILABLE = False
extract_text_from_pdf = None

if pdf_ingestion_path.exists():
    try:
        spec = importlib.util.spec_from_file_location("pdf_ingestion", pdf_ingestion_path)
        pdf_ingestion_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pdf_ingestion_module)
        extract_text_from_pdf = pdf_ingestion_module.extract_text_from_pdf
        PDF_EXTRACTION_AVAILABLE = True
    except Exception:
        PDF_EXTRACTION_AVAILABLE = False

router = APIRouter(prefix="/api/backfill", tags=["backfill"])


class BackfillRequest(BaseModel):
    """Request model for backfill endpoint."""
    username: Optional[str] = None  # If None, backfill all documents
    document_ids: Optional[List[str]] = None  # Specific document IDs to backfill
    skip_existing: bool = True
    dry_run: bool = False


class BackfillResponse(BaseModel):
    """Response model for backfill endpoint."""
    status: str
    message: str
    task_id: Optional[str] = None


def extract_text_from_file(file_path: Path) -> Optional[str]:
    """Extract text from a file based on its extension."""
    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {file_path}")
    
    suffix = file_path.suffix.lower()
    
    try:
        if suffix == '.pdf':
            if PDF_EXTRACTION_AVAILABLE:
                try:
                    text = extract_text_from_pdf(file_path)
                    if not text or len(text.strip()) == 0:
                        raise Exception("PDF extraction returned empty result")
                    return text
                except Exception as e:
                    raise Exception(f"PDF extraction failed: {str(e)}")
            else:
                raise Exception("PDF extraction not available (pdf_ingestion module not found)")
        elif suffix in ['.txt', '.md', '.csv', '.json', '.xml', '.html']:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                    if not text or len(text.strip()) == 0:
                        raise Exception("File is empty or contains only whitespace")
                    return text
            except UnicodeDecodeError as e:
                raise Exception(f"Unicode decode error: {str(e)}")
            except Exception as e:
                raise Exception(f"Error reading file: {str(e)}")
        else:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                    if not text or len(text.strip()) == 0:
                        raise Exception("File is empty or contains only whitespace")
                    return text
            except UnicodeDecodeError as e:
                raise Exception(f"Unicode decode error (unsupported file type {suffix}): {str(e)}")
            except Exception as e:
                raise Exception(f"Error reading file (unsupported file type {suffix}): {str(e)}")
    except Exception as e:
        # Re-raise with more context
        raise Exception(f"Text extraction failed for {file_path.name} ({suffix}): {str(e)}")


def find_evidence_file(doc_name: str) -> Optional[Path]:
    """Find the evidence file corresponding to a document name."""
    # Search through all evidence records
    all_evidence = evidence_storage.get_all()
    
    for evidence in all_evidence:
        original_filename = evidence.get("original_filename", "")
        if original_filename == doc_name:
            stored_path_str = evidence.get("stored_path", "")
            if stored_path_str:
                stored_path = Path(stored_path_str)
                if stored_path.exists():
                    return stored_path
    
    # Also try direct search in evidence root directory
    for case_dir in EVIDENCE_ROOT_DIR.iterdir():
        if case_dir.is_dir():
            potential_file = case_dir / doc_name
            if potential_file.exists():
                return potential_file
            
            for file_path in case_dir.rglob(doc_name):
                if file_path.is_file():
                    return file_path
    
    return None


def backfill_documents_for_user(
    username: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    skip_existing: bool = True,
    dry_run: bool = False,
    log_callback=None,
):
    """
    Backfill embeddings for documents.
    
    Args:
        username: Username to filter documents by (None for all users)
        document_ids: Specific document IDs to backfill (if provided, only these will be processed)
        skip_existing: Skip documents that already have embeddings
        dry_run: If True, only report what would be done
        log_callback: Optional callback function for progress updates
    """
    if embedding_service is None:
        if log_callback:
            log_callback("error", "Embedding service is not configured")
        return {"status": "error", "reason": "embedding_service_not_configured"}
    
    # Get documents to backfill
    try:
        if document_ids and len(document_ids) > 0:
            # Backfill specific documents by ID
            if log_callback:
                log_callback("progress", f"Querying Neo4j for {len(document_ids)} document IDs...")
            cypher = """
            MATCH (d:Document)
            WHERE d.id IN $doc_ids
            RETURN d.id AS id, d.key AS key, d.name AS name, 
                   COALESCE(d.vector_db_id, null) AS vector_db_id
            ORDER BY d.name
            """
            documents = neo4j_service.run_cypher(cypher, {"doc_ids": document_ids})
            found_count = len(documents) if documents else 0
            
            # If no documents found by ID, try by key as fallback
            if found_count == 0:
                if log_callback:
                    log_callback("warning", f"No documents found by ID, trying by key...")
                cypher = """
                MATCH (d:Document)
                WHERE d.key IN $doc_ids
                RETURN d.id AS id, d.key AS key, d.name AS name, 
                       COALESCE(d.vector_db_id, null) AS vector_db_id
                ORDER BY d.name
                """
                documents = neo4j_service.run_cypher(cypher, {"doc_ids": document_ids})
                found_count = len(documents) if documents else 0
            
            if log_callback:
                log_callback("progress", f"Found {found_count} documents in Neo4j (queried {len(document_ids)} IDs)")
                if found_count == 0:
                    log_callback("error", f"No documents found in Neo4j. Please verify the document IDs are correct.")
        elif username and username != "all":
            # Use list_files to filter by owner
            user_evidence_list = evidence_storage.list_files(owner=username)
            user_doc_names = set()
            for evidence in user_evidence_list:
                original_filename = evidence.get("original_filename", "")
                if original_filename:
                    user_doc_names.add(original_filename)
            
            if not user_doc_names:
                if log_callback:
                    log_callback("complete", f"No documents found for user {username}")
                return {"status": "complete", "processed": 0, "message": f"No documents found for user {username}"}
            
            # Query Neo4j for documents that match user's evidence files
            try:
                doc_names_list = list(user_doc_names)
                cypher = """
                MATCH (d:Document)
                WHERE d.name IN $doc_names
                RETURN d.id AS id, d.key AS key, d.name AS name, 
                       COALESCE(d.vector_db_id, null) AS vector_db_id
                ORDER BY d.name
                """
                documents = neo4j_service.run_cypher(cypher, {"doc_names": doc_names_list})
            except Exception as e:
                if log_callback:
                    log_callback("error", f"Error querying Neo4j: {str(e)}")
                return {"status": "error", "reason": str(e)}
        else:
            # Get all documents
            try:
                cypher = """
                MATCH (d:Document)
                RETURN d.id AS id, d.key AS key, d.name AS name, 
                       COALESCE(d.vector_db_id, null) AS vector_db_id
                ORDER BY d.name
                """
                documents = neo4j_service.run_cypher(cypher)
            except Exception as e:
                if log_callback:
                    log_callback("error", f"Error querying Neo4j: {str(e)}")
                return {"status": "error", "reason": str(e)}
    except Exception as e:
        if log_callback:
            log_callback("error", f"Error querying Neo4j: {str(e)}")
        return {"status": "error", "reason": str(e)}
    
    if not documents or len(documents) == 0:
        message = "No matching documents found in Neo4j"
        if document_ids:
            message += f" for the {len(document_ids)} selected document ID(s)"
        elif username:
            message += f" for user {username}"
        if log_callback:
            log_callback("complete", message)
        return {"status": "complete", "processed": 0, "message": message}
    
    stats = {
        "total": len(documents),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "already_embedded": 0,
        "file_not_found": 0,
        "extraction_failed": 0,
        "embedding_failed": 0,
        "extraction_errors": [],  # Store detailed error messages
        "file_not_found_errors": [],  # Store files that weren't found
    }
    
    if log_callback:
        log_callback("progress", f"Processing {stats['total']} documents for user {username}...")
    
    for i, doc in enumerate(documents, 1):
        doc_id = doc.get("id")
        doc_key = doc.get("key")
        doc_name = doc.get("name")
        vector_db_id = doc.get("vector_db_id")
        
        if not doc_id or not doc_name:
            stats["skipped"] += 1
            continue
        
        # Check if already embedded
        if skip_existing and vector_db_id:
            try:
                existing_doc = vector_db_service.get_document(vector_db_id)
                if existing_doc:
                    stats["already_embedded"] += 1
                    if log_callback:
                        log_callback("progress", f"Skipping {doc_name} - already has embedding")
                    continue
            except Exception as e:
                # If we can't verify, continue processing
                if log_callback:
                    log_callback("warning", f"Could not verify existing embedding for {doc_name}, will process: {str(e)}")
        
        # Find the file
        file_path = find_evidence_file(doc_name)
        if not file_path:
            stats["file_not_found"] += 1
            error_msg = f"{doc_name} (document ID: {doc_id})"
            stats["file_not_found_errors"].append(error_msg)
            if log_callback:
                log_callback("warning", f"File not found for document: {doc_name} (ID: {doc_id})")
            continue
        
        # Extract text
        text = None
        extraction_error = None
        try:
            text = extract_text_from_file(file_path)
            if not text:
                extraction_error = "Text extraction returned empty result"
        except Exception as e:
            extraction_error = str(e)
            if log_callback:
                log_callback("error", f"Exception during text extraction for {doc_name}: {str(e)}")
        
        if not text:
            stats["extraction_failed"] += 1
            error_msg = f"{doc_name}: {extraction_error or 'Unknown extraction error'}"
            stats["extraction_errors"].append(error_msg)
            if log_callback:
                log_callback("warning", f"Could not extract text from {doc_name}: {extraction_error or 'Unknown error'}")
            continue
        
        if dry_run:
            stats["processed"] += 1
            if log_callback:
                log_callback("progress", f"[DRY RUN] Would process: {doc_name}")
            continue
        
        # Generate embedding
        try:
            embedding = embedding_service.generate_embedding(text)
            if not embedding:
                stats["embedding_failed"] += 1
                continue
        except Exception as e:
            stats["embedding_failed"] += 1
            if log_callback:
                log_callback("error", f"Failed to generate embedding for {doc_name}: {str(e)}")
            continue
        
        # Store in vector DB
        try:
            vector_db_id = vector_db_service.add_document(
                doc_id=doc_id,
                text=text,
                embedding=embedding,
                metadata={
                    "filename": doc_name,
                    "doc_key": doc_key,
                    "source_type": "backfill",
                    "owner": username,
                }
            )
            
            # Update Neo4j document node
            neo4j_service.run_cypher(
                "MATCH (d:Document {id: $doc_id}) SET d.vector_db_id = $vector_db_id",
                {"doc_id": doc_id, "vector_db_id": vector_db_id}
            )
            
            stats["processed"] += 1
            if log_callback and i % 10 == 0:
                log_callback("progress", f"Processed {i}/{stats['total']} documents...")
        except Exception as e:
            stats["failed"] += 1
            if log_callback:
                log_callback("error", f"Failed to store embedding for {doc_name}: {str(e)}")
    
    if log_callback:
        log_callback("complete", f"Backfill complete: {stats['processed']} processed, {stats['already_embedded']} already embedded, {stats['failed']} failed")
    
    return {"status": "complete", "stats": stats}


@router.post("", response_model=BackfillResponse)
async def backfill_embeddings(
    request: BackfillRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Backfill embeddings for documents.
    
    If username is provided, only backfill documents for that user.
    If username is None, backfill all documents.
    
    Args:
        request: Backfill request with optional username filter
        background_tasks: FastAPI background tasks
        user: Current authenticated user
    """
    # Determine which user to backfill for
    target_username = request.username or user.get("username")
    current_username = user.get("username", "unknown")
    
    # Log the operation
    system_log_service.log(
        log_type=LogType.DOCUMENT_INGESTION,
        origin=LogOrigin.FRONTEND,
        action=f"Backfill Embeddings Request: {target_username or 'all users'}",
        details={
            "target_username": target_username,
            "requested_by": current_username,
            "skip_existing": request.skip_existing,
            "dry_run": request.dry_run,
        },
        user=current_username,
        success=True,
    )
    
    # For now, run synchronously (can be made async later)
    # In production, you might want to use a proper task queue
    try:
        def log_callback(level, message):
            system_log_service.log(
                log_type=LogType.DOCUMENT_INGESTION,
                origin=LogOrigin.BACKEND,
                action=f"Backfill Progress: {message}",
                details={
                    "target_username": target_username,
                    "level": level,
                },
                user=current_username,
                success=level != "error",
            )
        
        result = backfill_documents_for_user(
            username=target_username,
            document_ids=request.document_ids,
            skip_existing=request.skip_existing,
            dry_run=request.dry_run,
            log_callback=log_callback,
        )
        
        # Include stats in message for better feedback
        stats = result.get("stats", {})
        if stats:
            message = result.get("message", "Backfill completed")
            if stats.get("processed", 0) > 0 or stats.get("already_embedded", 0) > 0:
                message += f" - Processed: {stats.get('processed', 0)}, Already embedded: {stats.get('already_embedded', 0)}, Failed: {stats.get('failed', 0)}"
            if stats.get("file_not_found", 0) > 0:
                file_not_found_errors = stats.get("file_not_found_errors", [])
                if file_not_found_errors:
                    message += f", Files not found: {stats.get('file_not_found', 0)}"
                    if len(file_not_found_errors) == 1:
                        message += f" ({file_not_found_errors[0]})"
                    else:
                        message += f" (e.g., {file_not_found_errors[0]})"
                else:
                    message += f", Files not found: {stats.get('file_not_found', 0)}"
            if stats.get("extraction_failed", 0) > 0:
                extraction_errors = stats.get("extraction_errors", [])
                if extraction_errors:
                    # Include first few error details
                    error_details = extraction_errors[:3]  # Show first 3 errors
                    message += f", Extraction failed: {stats.get('extraction_failed', 0)}"
                    if len(extraction_errors) == 1:
                        message += f" ({extraction_errors[0]})"
                    else:
                        message += f" (e.g., {error_details[0]})"
                else:
                    message += f", Extraction failed: {stats.get('extraction_failed', 0)}"
        else:
            message = result.get("message", "Backfill completed")
        
        return BackfillResponse(
            status=result.get("status", "complete"),
            message=message,
        )
    except Exception as e:
        system_log_service.log(
            log_type=LogType.DOCUMENT_INGESTION,
            origin=LogOrigin.BACKEND,
            action="Backfill Embeddings Failed",
            details={
                "target_username": target_username,
                "error": str(e),
            },
            user=current_username,
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))

