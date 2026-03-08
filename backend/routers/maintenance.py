"""
Maintenance Router — Vector DB integrity and housekeeping endpoints.

Provides REST endpoints for auditing, repairing, and purging orphaned
vector database entries to enforce case isolation.
"""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services.maintenance_service import maintenance_service
from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class RepairRequest(BaseModel):
    """Request model for repair endpoint."""
    dry_run: bool = False


class PurgeRequest(BaseModel):
    """Request model for purge orphans endpoint."""
    dry_run: bool = True  # Default to dry run for safety


@router.get("/health")
async def health_check(user: dict = Depends(get_current_user)):
    """
    Quick health check of vector database integrity.

    Returns counts per collection, case_id coverage percentages, and overall status.
    """
    return maintenance_service.health()


@router.post("/audit")
async def run_audit(user: dict = Depends(get_current_user)):
    """
    Full integrity audit across all ChromaDB collections.

    Cross-references case_ids against valid Postgres cases.
    Read-only — no changes are made.
    """
    username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.GRAPH_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Maintenance Audit Requested",
        details={"requested_by": username},
        user=username,
        success=True,
    )

    def log_callback(level, message):
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.BACKEND,
            action=f"Maintenance Audit: {message}",
            details={"level": level},
            user=username,
            success=level != "error",
        )

    result = maintenance_service.audit(log_callback=log_callback)

    system_log_service.log(
        log_type=LogType.GRAPH_OPERATION,
        origin=LogOrigin.BACKEND,
        action=f"Maintenance Audit Complete: {result.get('total_issues', '?')} issues found",
        details={"healthy": result.get("healthy"), "total_issues": result.get("total_issues")},
        user=username,
        success=True,
    )

    return result


@router.post("/repair")
async def run_repair(request: RepairRequest, user: dict = Depends(get_current_user)):
    """
    Repair missing case_id metadata across Neo4j and ChromaDB.

    Runs the backfill script to resolve case_id from evidence storage,
    file paths, and relationship traversal.

    Set dry_run=true to preview changes without applying them.
    """
    username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.GRAPH_OPERATION,
        origin=LogOrigin.FRONTEND,
        action=f"Maintenance Repair Requested (dry_run={request.dry_run})",
        details={"dry_run": request.dry_run, "requested_by": username},
        user=username,
        success=True,
    )

    def log_callback(level, message):
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.BACKEND,
            action=f"Maintenance Repair: {message}",
            details={"level": level},
            user=username,
            success=level != "error",
        )

    result = maintenance_service.repair(dry_run=request.dry_run, log_callback=log_callback)
    return result


@router.post("/purge-orphans")
async def purge_orphans(request: PurgeRequest, user: dict = Depends(get_current_user)):
    """
    Remove vector entries with no valid case association.

    Targets entries where case_id is empty or doesn't match any valid Postgres case.

    IMPORTANT: Defaults to dry_run=true. Set dry_run=false to actually delete orphans.
    Always run a dry_run first to review what will be removed.
    """
    username = user.get("username", "unknown")

    system_log_service.log(
        log_type=LogType.GRAPH_OPERATION,
        origin=LogOrigin.FRONTEND,
        action=f"Maintenance Purge Orphans Requested (dry_run={request.dry_run})",
        details={"dry_run": request.dry_run, "requested_by": username},
        user=username,
        success=True,
    )

    def log_callback(level, message):
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.BACKEND,
            action=f"Maintenance Purge: {message}",
            details={"level": level},
            user=username,
            success=level != "error",
        )

    result = maintenance_service.purge_orphans(
        dry_run=request.dry_run,
        log_callback=log_callback,
    )

    system_log_service.log(
        log_type=LogType.GRAPH_OPERATION,
        origin=LogOrigin.BACKEND,
        action=f"Maintenance Purge Complete: {result.get('total_orphans', '?')} orphans "
               f"{'found (dry run)' if request.dry_run else 'removed'}",
        details={"dry_run": request.dry_run, "total_orphans": result.get("total_orphans")},
        user=username,
        success=True,
    )

    return result
