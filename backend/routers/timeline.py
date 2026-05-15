"""
Timeline Router - endpoints for timeline visualization data.
"""

from typing import List, Optional
from fastapi import APIRouter, Query

from services import neo4j_service

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("")
async def get_timeline(
    types: Optional[str] = Query(
        None,
        description="Comma-separated event types to include (e.g., 'Transaction,Payment')"
    ),
    start_date: Optional[str] = Query(
        None,
        description="Filter events on or after this date (YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None,
        description="Filter events on or before this date (YYYY-MM-DD)"
    ),
    case_id: str = Query(
        ...,
        description="REQUIRED: Filter to events in this case"
    ),
    limit: int = Query(500, ge=1, le=2000, description="Maximum events to return"),
    cursor: Optional[str] = Query(None, description="Opaque cursor from a previous response"),
):
    """
    Get timeline events sorted chronologically for a specific case.

    Returns events (Transaction, Payment, Communication, etc.) that have dates,
    along with their connected entities.
    """
    # Parse comma-separated types if provided
    event_types = None
    if types:
        event_types = [t.strip() for t in types.split(",") if t.strip()]
    
    page = neo4j_service.get_timeline_page(
        event_types=event_types,
        start_date=start_date,
        end_date=end_date,
        case_id=case_id,
        limit=limit,
        cursor=cursor,
    )

    return page


@router.get("/types")
async def get_event_types():
    """
    Get available event types that can appear on the timeline.
    
    Returns types and counts for events that have dates.
    """
    # This could be dynamic based on what's in the DB,
    # but for now return the standard event types
    return {
        "event_types": [
            "Transaction",
            "Transfer", 
            "Payment",
            "Communication",
            "Email",
            "PhoneCall",
            "Meeting",
        ]
    }
