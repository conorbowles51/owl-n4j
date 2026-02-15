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

# PDF extraction - use pypdf directly to avoid complex import dependencies
# The pdf_ingestion module has dependencies on the full ingestion pipeline,
# but we only need the text extraction functionality here
PDF_EXTRACTION_AVAILABLE = False
extract_text_from_pdf = None

try:
    import pypdf
    
    def extract_text_from_pdf_simple(path: Path) -> str:
        """Extract text from PDF using pypdf directly."""
        reader = pypdf.PdfReader(str(path))
        chunks = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                chunks.append(f"--- Page {i + 1} ---\n{page_text}")
        return "\n\n".join(chunks)
    
    extract_text_from_pdf = extract_text_from_pdf_simple
    PDF_EXTRACTION_AVAILABLE = True
    print(f"[Backfill] PDF extraction available (using pypdf)")
except ImportError as e:
    PDF_EXTRACTION_AVAILABLE = False
    print(f"[Backfill] WARNING: pypdf not available: {e}")
    print(f"[Backfill] PDF extraction will not be available. Install pypdf: pip install pypdf")
except Exception as e:
    PDF_EXTRACTION_AVAILABLE = False
    print(f"[Backfill] WARNING: Failed to initialize PDF extraction: {e}")
    import traceback
    traceback.print_exc()

router = APIRouter(prefix="/api/backfill", tags=["backfill"])


class BackfillRequest(BaseModel):
    """Request model for backfill endpoint."""
    username: Optional[str] = None  # If None, backfill all documents
    document_ids: Optional[List[str]] = None  # Specific document IDs to backfill
    skip_existing: bool = True
    dry_run: bool = False


class ChunkBackfillRequest(BaseModel):
    """Request model for chunk backfill endpoint."""
    case_id: Optional[str] = None
    skip_existing: bool = True
    dry_run: bool = False


class EntityMetadataBackfillRequest(BaseModel):
    """Request model for entity metadata backfill endpoint."""
    dry_run: bool = False


class DocumentSummaryBackfillRequest(BaseModel):
    """Request model for document summary backfill endpoint."""
    case_id: Optional[str] = None
    skip_existing: bool = True
    dry_run: bool = False


class CaseIdBackfillRequest(BaseModel):
    """Request model for case_id backfill endpoint."""
    include_entities: bool = True
    dry_run: bool = False


class BackfillResponse(BaseModel):
    """Response model for backfill endpoint."""
    status: str
    message: str
    task_id: Optional[str] = None


class BackfillStatusResponse(BaseModel):
    """Response model for gap analysis / status endpoint."""
    documents: dict
    entities: dict
    chunks: dict


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


@router.post("/chunks", response_model=BackfillResponse)
async def backfill_chunks(
    request: ChunkBackfillRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Backfill chunk-level embeddings for existing documents.

    Reads original files from disk, re-chunks them (pure text splitting, no LLM cost),
    and embeds each chunk into the ChromaDB chunks collection.

    This is much cheaper than re-ingestion since no entity extraction is needed.
    """
    current_username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.DOCUMENT_INGESTION,
        origin=LogOrigin.FRONTEND,
        action=f"Chunk Backfill Request: case_id={request.case_id or 'all'}",
        details={
            "case_id": request.case_id,
            "skip_existing": request.skip_existing,
            "dry_run": request.dry_run,
            "requested_by": current_username,
        },
        user=current_username,
        success=True,
    )

    try:
        # Import the backfill function
        from scripts.backfill_chunk_embeddings import backfill_chunk_embeddings

        def log_callback(level, message):
            system_log_service.log(
                log_type=LogType.DOCUMENT_INGESTION,
                origin=LogOrigin.BACKEND,
                action=f"Chunk Backfill Progress: {message}",
                details={
                    "case_id": request.case_id,
                    "level": level,
                },
                user=current_username,
                success=level != "error",
            )

        result = backfill_chunk_embeddings(
            dry_run=request.dry_run,
            skip_existing=request.skip_existing,
            case_id=request.case_id,
            log_callback=log_callback,
        )

        stats = result.get("stats", {})
        message = (
            f"Chunk backfill {'(dry run) ' if request.dry_run else ''}"
            f"complete: {stats.get('processed', 0)} documents processed, "
            f"{stats.get('total_chunks_created', 0)} chunks created, "
            f"{stats.get('already_has_chunks', 0)} already had chunks, "
            f"{stats.get('file_not_found', 0)} files not found"
        )

        return BackfillResponse(
            status=result.get("status", "complete"),
            message=message,
        )
    except Exception as e:
        system_log_service.log(
            log_type=LogType.DOCUMENT_INGESTION,
            origin=LogOrigin.BACKEND,
            action="Chunk Backfill Failed",
            details={"error": str(e)},
            user=current_username,
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entity-metadata", response_model=BackfillResponse)
async def backfill_entity_metadata(
    request: EntityMetadataBackfillRequest,
    user: dict = Depends(get_current_user),
):
    """
    Backfill entity metadata (case_id) in ChromaDB.

    Updates entity embeddings in ChromaDB to include case_id metadata from Neo4j.
    No re-embedding needed — purely a metadata update.
    """
    current_username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.DOCUMENT_INGESTION,
        origin=LogOrigin.FRONTEND,
        action="Entity Metadata Backfill Request",
        details={
            "dry_run": request.dry_run,
            "requested_by": current_username,
        },
        user=current_username,
        success=True,
    )

    try:
        from scripts.backfill_entity_metadata import backfill_entity_metadata as run_backfill

        def log_callback(level, message):
            system_log_service.log(
                log_type=LogType.DOCUMENT_INGESTION,
                origin=LogOrigin.BACKEND,
                action=f"Entity Metadata Backfill Progress: {message}",
                details={"level": level},
                user=current_username,
                success=level != "error",
            )

        result = run_backfill(
            dry_run=request.dry_run,
            log_callback=log_callback,
        )

        stats = result.get("stats", {})
        message = (
            f"Entity metadata backfill {'(dry run) ' if request.dry_run else ''}"
            f"complete: {stats.get('updated', 0)} updated, "
            f"{stats.get('already_has_case_id', 0)} already had case_id, "
            f"{stats.get('no_case_id_in_neo4j', 0)} missing in Neo4j"
        )

        return BackfillResponse(
            status=result.get("status", "complete"),
            message=message,
        )
    except Exception as e:
        system_log_service.log(
            log_type=LogType.DOCUMENT_INGESTION,
            origin=LogOrigin.BACKEND,
            action="Entity Metadata Backfill Failed",
            details={"error": str(e)},
            user=current_username,
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/document-summaries", response_model=BackfillResponse)
async def backfill_document_summaries_endpoint(
    request: DocumentSummaryBackfillRequest,
    user: dict = Depends(get_current_user),
):
    """
    Backfill AI summaries for documents that don't have one.

    Reads original files from disk, sends first 5000 chars to LLM,
    and stores the resulting summary on the Document node.

    NOTE: This uses LLM calls and has a per-document cost.
    """
    current_username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.DOCUMENT_INGESTION,
        origin=LogOrigin.FRONTEND,
        action=f"Document Summary Backfill Request: case_id={request.case_id or 'all'}",
        details={
            "case_id": request.case_id,
            "skip_existing": request.skip_existing,
            "dry_run": request.dry_run,
            "requested_by": current_username,
        },
        user=current_username,
        success=True,
    )

    try:
        from scripts.backfill_document_summaries import backfill_document_summaries

        def log_callback(level, message):
            system_log_service.log(
                log_type=LogType.DOCUMENT_INGESTION,
                origin=LogOrigin.BACKEND,
                action=f"Document Summary Backfill Progress: {message}",
                details={
                    "case_id": request.case_id,
                    "level": level,
                },
                user=current_username,
                success=level != "error",
            )

        result = backfill_document_summaries(
            dry_run=request.dry_run,
            skip_existing=request.skip_existing,
            case_id=request.case_id,
            log_callback=log_callback,
        )

        stats = result.get("stats", {})
        message = (
            f"Document summary backfill {'(dry run) ' if request.dry_run else ''}"
            f"complete: {stats.get('processed', 0)} summaries generated, "
            f"{stats.get('already_has_summary', 0)} already had summaries, "
            f"{stats.get('file_not_found', 0)} files not found, "
            f"{stats.get('llm_failed', 0)} LLM failures"
        )

        return BackfillResponse(
            status=result.get("status", "complete"),
            message=message,
        )
    except Exception as e:
        system_log_service.log(
            log_type=LogType.DOCUMENT_INGESTION,
            origin=LogOrigin.BACKEND,
            action="Document Summary Backfill Failed",
            details={"error": str(e)},
            user=current_username,
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/case-ids", response_model=BackfillResponse)
async def backfill_case_ids_endpoint(
    request: CaseIdBackfillRequest,
    user: dict = Depends(get_current_user),
):
    """
    Backfill case_id for documents and entities in Neo4j.

    Documents: Resolves case_id from evidence storage records or file path.
    Entities: Inherits case_id from connected Document nodes.

    No LLM calls. No re-embedding. Pure metadata update in Neo4j.
    """
    current_username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.DOCUMENT_INGESTION,
        origin=LogOrigin.FRONTEND,
        action=f"Case ID Backfill Request: include_entities={request.include_entities}",
        details={
            "include_entities": request.include_entities,
            "dry_run": request.dry_run,
            "requested_by": current_username,
        },
        user=current_username,
        success=True,
    )

    try:
        from scripts.backfill_case_ids import backfill_case_ids

        def log_callback(level, message):
            system_log_service.log(
                log_type=LogType.DOCUMENT_INGESTION,
                origin=LogOrigin.BACKEND,
                action=f"Case ID Backfill Progress: {message}",
                details={"level": level},
                user=current_username,
                success=level != "error",
            )

        result = backfill_case_ids(
            dry_run=request.dry_run,
            include_entities=request.include_entities,
            log_callback=log_callback,
        )

        stats = result.get("stats", {})
        doc_stats = stats.get("documents", {})
        entity_stats = stats.get("entities", {})

        parts = [
            f"Case ID backfill {'(dry run) ' if request.dry_run else ''}complete:",
            f"{doc_stats.get('updated', 0)} documents updated",
            f"{doc_stats.get('not_resolved', 0)} documents unresolved",
        ]
        if request.include_entities:
            parts.append(f"{entity_stats.get('updated', 0)} entities updated")
            parts.append(f"{entity_stats.get('not_resolved', 0)} entities unresolved")

        message = ", ".join(parts)

        return BackfillResponse(
            status=result.get("status", "complete"),
            message=message,
        )
    except Exception as e:
        system_log_service.log(
            log_type=LogType.DOCUMENT_INGESTION,
            origin=LogOrigin.BACKEND,
            action="Case ID Backfill Failed",
            details={"error": str(e)},
            user=current_username,
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=BackfillStatusResponse)
async def get_backfill_status(
    user: dict = Depends(get_current_user),
):
    """
    Get gap analysis showing what data needs backfilling.

    Returns counts of:
    - Documents with/without chunk embeddings and summaries
    - Entities with/without case_id metadata in ChromaDB
    - Total chunks in the chunks collection
    """
    try:
        # Document stats (total + summary + case_id counts)
        doc_cypher = """
        MATCH (d:Document)
        RETURN count(d) AS total,
               count(CASE WHEN d.summary IS NOT NULL AND d.summary <> '' THEN 1 END) AS with_summary,
               count(CASE WHEN d.case_id IS NOT NULL AND d.case_id <> '' THEN 1 END) AS with_case_id
        """
        doc_result = neo4j_service.run_cypher(doc_cypher)
        total_docs = doc_result[0]["total"] if doc_result else 0
        docs_with_summary = doc_result[0]["with_summary"] if doc_result else 0
        docs_with_case_id = doc_result[0]["with_case_id"] if doc_result else 0

        # Count documents that have chunks
        try:
            chunk_collection = vector_db_service.chunk_collection
            all_chunks = chunk_collection.get(include=["metadatas"])
            chunk_ids = all_chunks.get("ids", [])
            chunk_metadatas = all_chunks.get("metadatas", [])

            # Count unique doc_ids that have chunks
            docs_with_chunks = set()
            for metadata in chunk_metadatas:
                if metadata and metadata.get("doc_id"):
                    docs_with_chunks.add(metadata["doc_id"])

            total_chunks = len(chunk_ids)
            docs_with_chunk_count = len(docs_with_chunks)
        except Exception:
            total_chunks = 0
            docs_with_chunk_count = 0

        # Entity stats (including case_id in Neo4j)
        entity_cypher = """
        MATCH (e)
        WHERE NOT e:Document
        RETURN count(e) AS total,
               count(CASE WHEN e.case_id IS NOT NULL AND e.case_id <> '' THEN 1 END) AS with_case_id
        """
        entity_result = neo4j_service.run_cypher(entity_cypher)
        total_entities_neo4j = entity_result[0]["total"] if entity_result else 0
        entities_neo4j_with_case_id = entity_result[0]["with_case_id"] if entity_result else 0

        # Check ChromaDB entity metadata for case_id
        try:
            entity_collection = vector_db_service.entity_collection
            all_entities = entity_collection.get(include=["metadatas"])
            entity_ids = all_entities.get("ids", [])
            entity_metadatas = all_entities.get("metadatas", [])

            total_entities_chromadb = len(entity_ids)
            entities_with_case_id = sum(
                1 for m in entity_metadatas if m and m.get("case_id")
            )
        except Exception:
            total_entities_chromadb = 0
            entities_with_case_id = 0

        return BackfillStatusResponse(
            documents={
                "total": total_docs,
                "with_chunks": docs_with_chunk_count,
                "missing_chunks": total_docs - docs_with_chunk_count,
                "with_summary": docs_with_summary,
                "missing_summary": total_docs - docs_with_summary,
                "with_case_id": docs_with_case_id,
                "missing_case_id": total_docs - docs_with_case_id,
            },
            entities={
                "total_neo4j": total_entities_neo4j,
                "total_chromadb": total_entities_chromadb,
                "with_case_id_metadata": entities_with_case_id,
                "missing_case_id": total_entities_chromadb - entities_with_case_id,
                "missing_embeddings": total_entities_neo4j - total_entities_chromadb,
                "neo4j_with_case_id": entities_neo4j_with_case_id,
                "neo4j_missing_case_id": total_entities_neo4j - entities_neo4j_with_case_id,
            },
            chunks={
                "total": total_chunks,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

