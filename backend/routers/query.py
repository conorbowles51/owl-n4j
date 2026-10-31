"""
Query Router - read-only Cypher for the graph's Query panel and the administrators' console.

Two modes, both read only (READ session and transaction: the database refuses any write, whatever the text):

* Case mode (``case_id`` given): any person who can view the case. The query must pass the case-scope grammar
  in ``services.agent.cypher_safety`` (every node and relationship bound to ``$case_id``); the server supplies
  ``$case_id`` and a client value for it is refused. This is what the graph's Query panel uses.
* Console mode (no ``case_id``): reads across every case, so administrators only.

Every query has a database time limit and a row limit. The response states the limit and whether the answer
was cut (``truncated``); ``total`` is the row count when the answer is whole and null when it was cut.
"""

import re
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.user import GlobalRole, User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services.agent.cypher_safety import UnsafeCypherError, run_case_cypher
from services.agent.json_utils import to_jsonable
from services.neo4j_service import neo4j_service
from services.system_log_service import system_log_service, LogType, LogOrigin

router = APIRouter(prefix="/api/query", tags=["query"])

ROW_LIMIT = 500
TIMEOUT_SECONDS = 30


class CypherRequest(BaseModel):
    """Request model for Cypher query execution."""

    query: str
    params: Optional[Dict[str, Any]] = None
    case_id: Optional[str] = None


class CypherResponse(BaseModel):
    """Response model for Cypher query results."""

    success: bool
    results: List[Dict[str, Any]]
    columns: List[str] = []
    count: int
    row_limit: int = ROW_LIMIT
    truncated: bool = False
    total: Optional[int] = None
    error: Optional[str] = None


# LOAD CSV and apoc.load.* are reads that fetch files or URLs from the database server, so they are refused here.
_FETCHES = re.compile(r"\bLOAD\s+CSV\b|\bapoc\s*\.\s*load\s*\.", re.IGNORECASE)
READ_ONLY_REFUSAL = "This console is read only: the database refused the query because it would change data."
TIMEOUT_REFUSAL = f"The query ran longer than {TIMEOUT_SECONDS} seconds and was stopped. Narrow it and try again."


def _is_write_refusal(error: Exception) -> bool:
    # Neo4j 5 answers every write in a READ transaction (plain Cypher, CALL apoc.*, schema changes) with this code.
    return getattr(error, "code", None) == "Neo.ClientError.Statement.AccessMode"


def _is_timeout(error: Exception) -> bool:
    return "TransactionTimedOut" in str(getattr(error, "code", "") or "")


def _is_admin(user: User) -> bool:
    return user.global_role in (GlobalRole.admin, GlobalRole.super_admin)


def _refused(error: str, rows_limit: int = ROW_LIMIT) -> CypherResponse:
    return CypherResponse(success=False, results=[], count=0, row_limit=rows_limit, error=error)


@router.post("", response_model=CypherResponse)
def execute_cypher(
    request: CypherRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Execute a read-only Cypher query: case-scoped for case viewers, unscoped for administrators."""
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    query = request.query.strip()
    username = current_user.email
    case_id = (request.case_id or "").strip() or None

    if case_id is not None:
        case_uuid = authorize_case(db, case_id, current_user, ("case", "view"))
        case_id = str(case_uuid)
        if request.params and "case_id" in request.params:
            raise HTTPException(status_code=400, detail="$case_id is supplied by the server; do not send it.")
    elif not _is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Choose a case: queries across every case are for administrators only.",
        )

    if _FETCHES.search(query):
        error = "LOAD CSV and apoc.load are not allowed: they fetch files or addresses from the database server."
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Cypher Query Blocked (File or Network Read)",
            details={"query_preview": query[:100], "case_id": case_id},
            user=username,
            success=False,
            error=error,
        )
        return _refused(error)

    try:
        if case_id is not None:
            rows, truncated = run_case_cypher(
                query,
                case_id=case_id,
                params=request.params,
                max_rows=ROW_LIMIT,
                timeout_seconds=TIMEOUT_SECONDS,
            )
        else:
            raw, truncated = neo4j_service.run_cypher_read_bounded(
                query, request.params, max_rows=ROW_LIMIT, timeout_seconds=TIMEOUT_SECONDS
            )
            rows = [to_jsonable(row) for row in raw]
    except UnsafeCypherError as e:
        error = (
            f"{e}. Queries in a case must bind every node and relationship to the case, "
            "for example MATCH (n {case_id: $case_id}) RETURN n.name LIMIT 25."
        )
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Cypher Query Blocked (Not Case-Scoped)",
            details={"query_preview": query[:200], "case_id": case_id, "reason": str(e)},
            user=username,
            success=False,
            error=error,
        )
        return _refused(error)
    except Exception as e:
        if _is_write_refusal(e):
            action, error = "Cypher Query Blocked (Write Operation)", READ_ONLY_REFUSAL
        elif _is_timeout(e):
            action, error = "Cypher Query Stopped (Time Limit)", TIMEOUT_REFUSAL
        else:
            action, error = "Execute Cypher Query Failed", str(e)
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=action,
            details={"query_preview": query[:200], "case_id": case_id, "error": str(e)[:300]},
            user=username,
            success=False,
            error=error,
        )
        return _refused(error)

    columns: List[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    system_log_service.log(
        log_type=LogType.GRAPH_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Execute Cypher Query",
        details={
            "query_preview": query[:200],
            "query_length": len(query),
            "case_id": case_id,
            "results_count": len(rows),
            "truncated": truncated,
            "has_params": bool(request.params),
        },
        user=username,
        success=True,
    )
    return CypherResponse(
        success=True,
        results=rows,
        columns=columns,
        count=len(rows),
        row_limit=ROW_LIMIT,
        truncated=truncated,
        total=None if truncated else len(rows),
    )
