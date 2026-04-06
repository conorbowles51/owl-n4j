"""
Cellebrite Router

Analytics endpoints for the Cellebrite Multi-Phone View:
- List ingested phone reports
- Cross-phone graph (shared contacts across devices)
- Multi-device timeline
- Communication network analysis
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from services.neo4j_service import neo4j_service
from services.case_service import get_case_if_allowed, CaseNotFound, CaseAccessDenied
from postgres.session import get_db
from postgres.models.user import User
from routers.users import get_current_db_user

router = APIRouter(prefix="/api/cellebrite", tags=["cellebrite"])


def _require_case_access(case_id: str, user: User, db: Session):
    """Verify user has access to the case."""
    try:
        get_case_if_allowed(db, case_id, user)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/reports")
async def get_reports(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List all ingested Cellebrite PhoneReport nodes for a case."""
    _require_case_access(case_id, current_user, db)
    reports = neo4j_service.get_cellebrite_reports(case_id)
    return {"reports": reports}


@router.get("/cross-phone-graph")
async def get_cross_phone_graph(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get cross-phone graph showing shared contacts across devices."""
    _require_case_access(case_id, current_user, db)
    graph = neo4j_service.get_cellebrite_cross_phone_graph(case_id)
    return graph


@router.get("/timeline")
async def get_timeline(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None, description="Comma-separated report keys to filter"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get multi-device event timeline."""
    _require_case_access(case_id, current_user, db)

    keys = [k.strip() for k in report_keys.split(",")] if report_keys else None
    types = [t.strip() for t in event_types.split(",")] if event_types else None

    result = neo4j_service.get_cellebrite_timeline(
        case_id=case_id,
        report_keys=keys,
        start_date=start_date,
        end_date=end_date,
        event_types=types,
        limit=limit,
        offset=offset,
    )
    return result


@router.get("/communication-network")
async def get_communication_network(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get communication network analysis (contact frequency, shared contacts)."""
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.get_cellebrite_communication_network(case_id)
    return result
