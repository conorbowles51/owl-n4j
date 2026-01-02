"""
Database Router - endpoints for vector database management.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.vector_db_service import vector_db_service
from services.neo4j_service import neo4j_service
from services.evidence_storage import evidence_storage
from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user

router = APIRouter(prefix="/api/database", tags=["database"])


class DocumentResponse(BaseModel):
    """Response model for a document."""
    id: str
    text: str
    metadata: dict


class DocumentsListResponse(BaseModel):
    """Response model for documents list."""
    documents: List[DocumentResponse]
    total: int


class RetrievalHistoryEntry(BaseModel):
    """Model for a retrieval history entry."""
    query: str
    timestamp: str
    distance: Optional[float] = None


class DocumentStatusResponse(BaseModel):
    """Response model for document status."""
    id: str
    key: str
    name: str
    has_embedding: bool
    vector_db_id: Optional[str] = None
    owner: Optional[str] = None
    case_id: Optional[str] = None
    file_path: Optional[str] = None


class DocumentsStatusResponse(BaseModel):
    """Response model for documents status list."""
    documents: List[DocumentStatusResponse]
    total: int
    backfilled: int
    not_backfilled: int


@router.get("/documents/status", response_model=DocumentsStatusResponse)
async def list_documents_status(
    user: dict = Depends(get_current_user),
):
    """
    List all documents with their backfill status.
    
    Shows documents from Neo4j and whether they have embeddings in the vector DB.
    
    Args:
        user: Current authenticated user
    """
    try:
        # Get all documents from Neo4j
        cypher = """
        MATCH (d:Document)
        RETURN d.id AS id, d.key AS key, d.name AS name, 
               COALESCE(d.vector_db_id, null) AS vector_db_id
        ORDER BY d.name
        """
        neo4j_docs = neo4j_service.run_cypher(cypher)
        
        # Get evidence records to find owner and file paths
        all_evidence = evidence_storage.get_all()
        evidence_by_filename = {}
        for evidence in all_evidence:
            filename = evidence.get("original_filename", "")
            if filename:
                evidence_by_filename[filename] = evidence
        
        documents = []
        backfilled_count = 0
        not_backfilled_count = 0
        
        for doc in neo4j_docs:
            doc_id = doc.get("id")
            doc_key = doc.get("key")
            doc_name = doc.get("name")
            vector_db_id = doc.get("vector_db_id")
            
            if not doc_id or not doc_name:
                continue
            
            has_embedding = vector_db_id is not None and vector_db_id != ""
            
            # Check if embedding actually exists in vector DB
            if has_embedding:
                try:
                    vector_doc = vector_db_service.get_document(vector_db_id)
                    if not vector_doc:
                        has_embedding = False
                        vector_db_id = None
                except:
                    has_embedding = False
                    vector_db_id = None
            
            # Find evidence record for this document
            evidence = evidence_by_filename.get(doc_name)
            owner = evidence.get("owner") if evidence else None
            case_id = evidence.get("case_id") if evidence else None
            file_path = evidence.get("stored_path") if evidence else None
            
            documents.append({
                "id": doc_id,
                "key": doc_key,
                "name": doc_name,
                "has_embedding": has_embedding,
                "vector_db_id": vector_db_id,
                "owner": owner,
                "case_id": case_id,
                "file_path": file_path,
            })
            
            if has_embedding:
                backfilled_count += 1
            else:
                not_backfilled_count += 1
        
        return DocumentsStatusResponse(
            documents=documents,
            total=len(documents),
            backfilled=backfilled_count,
            not_backfilled=not_backfilled_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents", response_model=DocumentsListResponse)
async def list_documents(
    user: dict = Depends(get_current_user),
):
    """
    List all documents in the vector database.
    
    Args:
        user: Current authenticated user
    """
    try:
        # Get all documents from ChromaDB
        # ChromaDB doesn't have a direct "get all" method, so we'll use a workaround
        # We'll query with a dummy embedding to get all documents
        # Or we can use the collection's get method
        
        # Get all document IDs from the collection
        # ChromaDB's get() method can retrieve all documents if we don't specify IDs
        collection = vector_db_service.collection
        
        # Get all documents (this is a workaround - ChromaDB doesn't have a direct "list all")
        # We'll use peek() to get a sample, but for full list we need to track IDs
        # For now, let's get all by querying with a very generic embedding
        # Actually, ChromaDB's get() with no parameters should return all
        
        try:
            # Get all documents from ChromaDB collection
            # ChromaDB's get() method returns all documents when called without parameters
            all_data = collection.get()
            
            documents = []
            if all_data and all_data.get("ids") and len(all_data["ids"]) > 0:
                ids = all_data["ids"]
                texts = all_data.get("documents", [])
                metadatas = all_data.get("metadatas", [])
                
                for i in range(len(ids)):
                    doc_id = ids[i]
                    text = texts[i] if i < len(texts) else ""
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    
                    documents.append({
                        "id": doc_id,
                        "text": text,
                        "metadata": metadata or {},
                    })
        except Exception as e:
            # If get() doesn't work, return empty list
            print(f"Warning: Could not retrieve all documents: {e}")
            documents = []
        
        # Log the operation
        system_log_service.log(
            log_type=LogType.SYSTEM,
            origin=LogOrigin.FRONTEND,
            action="List Vector Database Documents",
            details={
                "count": len(documents),
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return DocumentsListResponse(
            documents=documents,
            total=len(documents),
        )
    except Exception as e:
        system_log_service.log(
            log_type=LogType.SYSTEM,
            origin=LogOrigin.BACKEND,
            action="List Vector Database Documents Failed",
            details={
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/retrieval-history")
async def get_retrieval_history(
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Get retrieval history for a specific document.
    
    Args:
        doc_id: Document ID
        user: Current authenticated user
    """
    try:
        # For now, we'll get retrieval history from system logs
        # Filter logs for AI assistant queries that retrieved this document
        logs = system_log_service.get_logs(
            log_type=LogType.AI_ASSISTANT,
            limit=1000,  # Get more logs to find relevant ones
        )
        
        history = []
        for log in logs.get("logs", []):
            details = log.get("details", {})
            debug_log = details.get("debug_log", {})
            
            # Check if this document was retrieved in this query
            # Look in hybrid_filtering, vector_search results, etc.
            vector_results = debug_log.get("vector_search", {}).get("results", [])
            for result in vector_results:
                if result.get("id") == doc_id:
                    history.append({
                        "query": details.get("question", "Unknown query"),
                        "timestamp": log.get("timestamp"),
                        "distance": result.get("distance"),
                    })
                    break
        
        # Sort by timestamp (most recent first)
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {"history": history[:50]}  # Limit to 50 most recent
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Get a specific document by ID.
    
    Args:
        doc_id: Document ID
        user: Current authenticated user
    """
    try:
        doc = vector_db_service.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {
            "id": doc_id,
            "text": doc.get("text", ""),
            "metadata": doc.get("metadata", {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

