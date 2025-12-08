"""
Query Router - endpoints for direct Cypher queries (advanced users).
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.neo4j_service import neo4j_service

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
async def execute_cypher(request: CypherRequest):
    """
    Execute a Cypher query.

    Note: Only read queries are allowed (no DELETE, CREATE, etc.)

    Args:
        request: Cypher query and optional parameters
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    query = request.query.strip()

    # Safety check - block write operations
    query_upper = query.upper()
    blocked_keywords = ["DELETE", "REMOVE", "SET", "CREATE", "MERGE", "DROP", "DETACH"]

    for keyword in blocked_keywords:
        if keyword in query_upper:
            return CypherResponse(
                success=False,
                results=[],
                count=0,
                error=f"Write operations are not allowed. Blocked keyword: {keyword}",
            )

    try:
        results = neo4j_service.run_cypher(query, request.params)
        return CypherResponse(
            success=True,
            results=results,
            count=len(results),
        )
    except Exception as e:
        return CypherResponse(
            success=False,
            results=[],
            count=0,
            error=str(e),
        )
