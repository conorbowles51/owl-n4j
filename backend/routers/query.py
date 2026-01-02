"""
Query Router - endpoints for direct Cypher queries (advanced users).
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.neo4j_service import neo4j_service
from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user

router = APIRouter(prefix="/api/query", tags=["query"])


class CypherRequest(BaseModel):
    """Request model for Cypher query execution."""

    query: str
    params: Optional[Dict[str, Any]] = None


class CypherResponse(BaseModel):
    """Response model for Cypher query results."""

    success: bool
    results: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None


@router.post("", response_model=CypherResponse)
async def execute_cypher(request: CypherRequest, user: dict = Depends(get_current_user)):
    """
    Execute a Cypher query.

    Note: Only read queries are allowed (no DELETE, CREATE, etc.)

    Args:
        request: Cypher query and optional parameters
        user: Current authenticated user
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    query = request.query.strip()

    # Safety check - block write operations
    query_upper = query.upper()
    blocked_keywords = ["DELETE", "REMOVE", "SET", "CREATE", "MERGE", "DROP", "DETACH"]

    for keyword in blocked_keywords:
        if keyword in query_upper:
            # Log blocked operation
            system_log_service.log(
                log_type=LogType.GRAPH_OPERATION,
                origin=LogOrigin.FRONTEND,
                action="Cypher Query Blocked (Write Operation)",
                details={
                    "query_preview": query[:100],
                    "blocked_keyword": keyword,
                },
                user=user.get("username", "unknown"),
                success=False,
                error=f"Write operations are not allowed. Blocked keyword: {keyword}",
            )
            
            return CypherResponse(
                success=False,
                results=[],
                count=0,
                error=f"Write operations are not allowed. Blocked keyword: {keyword}",
            )

    try:
        results = neo4j_service.run_cypher(query, request.params)
        
        # Log the query execution (for search/filter operations)
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Execute Cypher Query",
            details={
                "query_preview": query[:200],
                "query_length": len(query),
                "results_count": len(results),
                "has_params": request.params is not None and len(request.params) > 0,
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return CypherResponse(
            success=True,
            results=results,
            count=len(results),
        )
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Execute Cypher Query Failed",
            details={
                "query_preview": query[:200],
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        
        return CypherResponse(
            success=False,
            results=[],
            count=0,
            error=str(e),
        )
