"""
Backfill Router - endpoints for backfilling document embeddings.
"""

import uuid
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user
from services.neo4j_service import neo4j_service
from services.vector_db_service import vector_db_service
from services.embedding_service import embedding_service
from config import EVIDENCE_DATA_ROOT


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


from postgres.models.evidence import EvidenceFile
from postgres.session import get_background_session
from services.evidence_db_storage import EvidenceDBStorage
from sqlalchemy import select
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
EVIDENCE_ROOT_DIR = EVIDENCE_DATA_ROOT


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
    include_vector_db: bool = True
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
        elif suffix in ['.html', '.htm']:
            try:
                import re as _re
                from lxml import html as lxml_html
                from lxml import etree

                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
                if not raw or not raw.strip():
                    raise Exception("File is empty or contains only whitespace")

                try:
                    doc = lxml_html.fromstring(raw)
                    to_remove = list(doc.iter("script", "style", "noscript", "head"))
                    to_remove.extend(doc.iter(etree.Comment))
                    for el in to_remove:
                        if el.getparent() is not None:
                            el.getparent().remove(el)
                    text = doc.text_content()
                except Exception:
                    # Fallback: strip tags with regex
                    text = _re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=_re.DOTALL | _re.IGNORECASE)
                    text = _re.sub(r"<style[^>]*>.*?</style>", "", text, flags=_re.DOTALL | _re.IGNORECASE)
                    text = _re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=_re.DOTALL | _re.IGNORECASE)
                    text = _re.sub(r"<[^>]+>", " ", text)

                text = _re.sub(r"[ \t]+", " ", text)
                text = _re.sub(r"\n\s*\n+", "\n\n", text)
                text = text.strip()
                if not text:
                    raise Exception("HTML file contains no text content")
                return text
            except Exception as e:
                raise Exception(f"Error reading HTML file: {str(e)}")
        elif suffix == '.md':
            try:
                import re as _re

                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
                if not raw or not raw.strip():
                    raise Exception("File is empty or contains only whitespace")

                try:
                    from markdown_it import MarkdownIt
                    md_parser = MarkdownIt()
                    html_output = md_parser.render(raw)
                    text = _re.sub(r"<[^>]+>", "", html_output)
                except ImportError:
                    # Fallback: strip common markdown syntax
                    text = raw
                    text = _re.sub(r"^#{1,6}\s+", "", text, flags=_re.MULTILINE)
                    text = _re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
                    text = _re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
                    text = _re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
                    text = _re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
                    text = _re.sub(r"`([^`]+)`", r"\1", text)
                    text = _re.sub(r"```[^\n]*\n", "", text)

                text = _re.sub(r"[ \t]+", " ", text)
                text = _re.sub(r"\n\s*\n+", "\n\n", text)
                text = text.strip()
                if not text:
                    raise Exception("Markdown file contains no text content")
                return text
            except Exception as e:
                raise Exception(f"Error reading Markdown file: {str(e)}")
        elif suffix in ['.txt', '.csv', '.json', '.xml']:
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


def find_evidence_file(doc_name: str, case_id: Optional[str]) -> Optional[Path]:
    """The file on disk for a document of a case: the one visible evidence file of that case with this name.

    Never another case's file, and never a guess between same-named files: a name several files of the case share,
    or a document without a case, finds nothing (the caller reports it as not found)."""
    try:
        case_uuid = uuid.UUID(str(case_id))
    except (TypeError, ValueError):
        return None
    with get_background_session() as db:
        found = EvidenceDBStorage.find_all_by_filename(db, doc_name, case_uuid)
        if len(found) > 1:
            return None
        if found and found[0].stored_path:
            stored_path = Path(found[0].stored_path)
            if stored_path.exists():
                return stored_path

    # A file in the case's own folder that has no evidence row: only when exactly one file there has the name.
    case_dir = EVIDENCE_ROOT_DIR / str(case_uuid)
    if case_dir.is_dir():
        matches = [p for p in case_dir.rglob(doc_name) if p.is_file()]
        if len(matches) == 1:
            return matches[0]
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
                   COALESCE(d.vector_db_id, null) AS vector_db_id,
                   COALESCE(d.case_id, '') AS case_id
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
                       COALESCE(d.vector_db_id, null) AS vector_db_id,
                       COALESCE(d.case_id, '') AS case_id
                ORDER BY d.name
                """
                documents = neo4j_service.run_cypher(cypher, {"doc_ids": document_ids})
                found_count = len(documents) if documents else 0
            
            if log_callback:
                log_callback("progress", f"Found {found_count} documents in Neo4j (queried {len(document_ids)} IDs)")
                if found_count == 0:
                    log_callback("error", f"No documents found in Neo4j. Please verify the document IDs are correct.")
        elif username and username != "all":
            with get_background_session() as db:
                user_evidence_list = list(
                    db.scalars(
                        select(EvidenceFile).where(EvidenceFile.owner == username)
                    ).all()
                )
            user_doc_names = set()
            for evidence in user_evidence_list:
                original_filename = evidence.original_filename
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
                       COALESCE(d.vector_db_id, null) AS vector_db_id,
                       COALESCE(d.case_id, '') AS case_id
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
                       COALESCE(d.vector_db_id, null) AS vector_db_id,
                       COALESCE(d.case_id, '') AS case_id
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
        doc_case_id = doc.get("case_id", "")
        vector_db_id = doc.get("vector_db_id")
        
        if not doc_id or not doc_name:
            stats["skipped"] += 1
            continue
        
        # Check if already embedded (check chunks collection)
        if skip_existing and vector_db_id:
            try:
                # Check if chunks exist for this document
                chunk_results = vector_db_service.chunk_collection.get(where={"doc_id": doc_id})
                if chunk_results and chunk_results.get("ids"):
                    stats["already_embedded"] += 1
                    if log_callback:
                        log_callback("progress", f"Skipping {doc_name} - already has chunk embeddings")
                    continue
            except Exception as e:
                if log_callback:
                    log_callback("warning", f"Could not verify existing embedding for {doc_name}, will process: {str(e)}")
        
        # Find the file
        file_path = find_evidence_file(doc_name, doc_case_id)
        if not file_path:
            stats["file_not_found"] += 1
            error_msg = f"{doc_name} (document ID: {doc_id})"
            stats["file_not_found_errors"].append(error_msg)
            if log_callback:
                log_callback("warning", f"File not found for document: {doc_name} (ID: {doc_id}); none, or several, of the case's files have this name")
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
            from postgres.models.cost_record import CostJobType
            from services.ai_costs_service import ai_cost_context
            with ai_cost_context(job_type=CostJobType.INGESTION, case_id=_uuid_or_none(doc_case_id),
                                 description="Document search index"):
                embedding = embedding_service.generate_embedding(text)
            if not embedding:
                stats["embedding_failed"] += 1
                continue
        except Exception as e:
            stats["embedding_failed"] += 1
            if log_callback:
                log_callback("error", f"Failed to generate embedding for {doc_name}: {str(e)}")
            continue
        
        # Store as a chunk in vector DB
        try:
            chunk_id = f"{doc_id}_chunk_0"
            vector_db_service.add_chunk(
                chunk_id=chunk_id,
                text=text[:10000],
                embedding=embedding,
                metadata={
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "doc_key": doc_key,
                    "case_id": doc_case_id,
                    "chunk_index": 0,
                    "source_type": "backfill",
                    "owner": username,
                }
            )

            # Update Neo4j document node
            neo4j_service.run_cypher(
                "MATCH (d:Document {id: $doc_id}) SET d.vector_db_id = $doc_id",
                {"doc_id": doc_id}
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
def backfill_embeddings(
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
def backfill_chunks(
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

        def run_chunk_backfill():
            """Run chunk backfill in background thread."""
            try:
                result = backfill_chunk_embeddings(
                    dry_run=request.dry_run,
                    skip_existing=request.skip_existing,
                    case_id=request.case_id,
                    log_callback=log_callback,
                )
                stats = result.get("stats", {})
                system_log_service.log(
                    log_type=LogType.DOCUMENT_INGESTION,
                    origin=LogOrigin.BACKEND,
                    action=f"Chunk Backfill Complete: {stats.get('processed', 0)} docs, "
                           f"{stats.get('total_chunks_created', 0)} chunks created",
                    details={"stats": stats},
                    user=current_username,
                    success=True,
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

        # Run in background to avoid frontend timeout
        background_tasks.add_task(run_chunk_backfill)

        return BackfillResponse(
            status="started",
            message=f"Chunk backfill {'(dry run) ' if request.dry_run else ''}"
                    f"started in background for case_id={request.case_id or 'all'}. "
                    f"Check system logs for progress.",
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
def backfill_entity_metadata(
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
def backfill_document_summaries_endpoint(
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
def backfill_case_ids_endpoint(
    request: CaseIdBackfillRequest,
    user: dict = Depends(get_current_user),
):
    """
    Backfill case_id for documents and entities in Neo4j and ChromaDB.

    Neo4j Documents: Resolves case_id from evidence storage records or file path.
    Neo4j Entities: Inherits case_id from connected Document nodes.
    ChromaDB Documents/Chunks/Entities: Updates metadata with resolved case_id.

    No LLM calls. No re-embedding. Pure metadata updates.
    """
    current_username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.DOCUMENT_INGESTION,
        origin=LogOrigin.FRONTEND,
        action=f"Case ID Backfill Request: include_entities={request.include_entities}, include_vector_db={request.include_vector_db}",
        details={
            "include_entities": request.include_entities,
            "include_vector_db": request.include_vector_db,
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
            include_vector_db=request.include_vector_db,
            log_callback=log_callback,
        )

        stats = result.get("stats", {})
        doc_stats = stats.get("documents", {})
        entity_stats = stats.get("entities", {})
        vdoc_stats = stats.get("vector_documents", {})
        vchunk_stats = stats.get("vector_chunks", {})
        vent_stats = stats.get("vector_entities", {})

        parts = [
            f"Case ID backfill {'(dry run) ' if request.dry_run else ''}complete:",
            f"Neo4j: {doc_stats.get('updated', 0)} docs",
        ]
        if request.include_entities:
            parts.append(f"{entity_stats.get('updated', 0)} entities")
        if request.include_vector_db:
            parts.append(
                f"ChromaDB: {vdoc_stats.get('updated', 0)} docs, "
                f"{vchunk_stats.get('updated', 0)} chunks, "
                f"{vent_stats.get('updated', 0)} entities"
            )

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


STATUS_PAGE_SIZE = 5000


def _iter_metadatas(collection, page_size: int | None = None, with_ids: bool = False):
    """Every metadata of a Chroma collection (with its id when asked), read page by page (limit/offset)."""
    page_size = page_size or STATUS_PAGE_SIZE
    offset = 0
    while True:
        page = collection.get(include=["metadatas"], limit=page_size, offset=offset)
        ids = page.get("ids") or []
        metadatas = page.get("metadatas") or []
        for i in range(len(ids)):
            metadata = metadatas[i] if i < len(metadatas) else None
            yield (ids[i], metadata) if with_ids else metadata
        if len(ids) < page_size:
            return
        offset += len(ids)


@router.get("/status", response_model=BackfillStatusResponse)
def get_backfill_status(
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

        # Count documents that have chunks. Paged: one unpaged get of a large collection fails
        # ("too many SQL variables"), and a failed read must not show as 0.
        docs_with_chunks = set()
        total_chunks = 0
        chunks_with_case_id = 0
        for metadata in _iter_metadatas(vector_db_service.chunk_collection):
            total_chunks += 1
            if metadata and metadata.get("doc_id"):
                docs_with_chunks.add(metadata["doc_id"])
            if metadata and metadata.get("case_id"):
                chunks_with_case_id += 1
        docs_with_chunk_count = len(docs_with_chunks)

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

        # Check ChromaDB entity metadata for case_id (paged, as above)
        total_entities_chromadb = 0
        entities_with_case_id = 0
        entity_ids: set[str] = set()
        for entity_id, metadata in _iter_metadatas(vector_db_service.entity_collection, with_ids=True):
            total_entities_chromadb += 1
            entity_ids.add(entity_id)
            if metadata and metadata.get("case_id"):
                entities_with_case_id += 1
        # Missing = the entities the engine embeds (entity_vectors.engine_entity_labels) with no vector; payments,
        # statement periods, phone nodes and file Documents are never embedded and are not counted.
        from services.entity_vectors import engine_entity_labels
        engine_keys = engine_entity_labels(include_phones=True)
        embeddable = set(engine_entity_labels())
        missing_embeddings = len(embeddable - entity_ids)
        orphaned_embeddings = len(entity_ids - set(engine_keys))

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
                "missing_embeddings": missing_embeddings,
                "orphaned_embeddings": orphaned_embeddings,
                "neo4j_with_case_id": entities_neo4j_with_case_id,
                "neo4j_missing_case_id": total_entities_neo4j - entities_neo4j_with_case_id,
            },
            chunks={
                "total": total_chunks,
                "with_case_id": chunks_with_case_id,
                "missing_case_id": total_chunks - chunks_with_case_id,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

