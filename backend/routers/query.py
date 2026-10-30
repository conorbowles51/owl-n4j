"""
Query Router - endpoints for direct Cypher queries (advanced users).
"""

import re
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.neo4j_service import neo4j_service
from services.system_log_service import system_log_service, LogType, LogOrigin
from postgres.models.user import User
from routers.users import require_admin

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


# The console reads across every case (it is not scoped to one), so it is for administrators only.
# No screen calls it; case screens use their own case-scoped endpoints.
#
# Reads only: the query runs in a READ session and transaction, so the database itself refuses any write,
# whatever words the query uses (CALL of a writing procedure included). A keyword list is not the guard.
# LOAD CSV and apoc.load.* are reads that fetch files or URLs from the database server, so they are refused here.
_FETCHES = re.compile(r"\bLOAD\s+CSV\b|\bapoc\s*\.\s*load\s*\.", re.IGNORECASE)
READ_ONLY_REFUSAL = "This console is read only: the database refused the query because it would change data."


def _is_write_refusal(error: Exception) -> bool:
    # Neo4j 5 answers every write in a READ transaction (plain Cypher, CALL apoc.*, schema changes) with this code.
    return getattr(error, "code", None) == "Neo.ClientError.Statement.AccessMode"


@router.post("", response_model=CypherResponse)
async def execute_cypher(request: CypherRequest, current_user: User = Depends(require_admin)):
    """
    Execute a read-only Cypher query (administrators only).

    Args:
        request: Cypher query and optional parameters
        current_user: Signed-in administrator
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    query = request.query.strip()
    user = {"username": current_user.email}

    if _FETCHES.search(query):
        error = "LOAD CSV and apoc.load are not allowed: they fetch files or addresses from the database server."
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Cypher Query Blocked (File or Network Read)",
            details={"query_preview": query[:100]},
            user=user["username"],
            success=False,
            error=error,
        )
        return CypherResponse(success=False, results=[], count=0, error=error)

    try:
        results = neo4j_service.run_cypher_read(query, request.params)
        
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
        if _is_write_refusal(e):
            system_log_service.log(
                log_type=LogType.GRAPH_OPERATION,
                origin=LogOrigin.FRONTEND,
                action="Cypher Query Blocked (Write Operation)",
                details={"query_preview": query[:100], "error": str(e)[:300]},
                user=user["username"],
                success=False,
                error=READ_ONLY_REFUSAL,
            )
            return CypherResponse(success=False, results=[], count=0, error=READ_ONLY_REFUSAL)
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
