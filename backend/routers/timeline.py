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
    start_datetime: Optional[str] = Query(
        None,
        description=(
            "Filter events on or after this UTC instant "
            "(YYYY-MM-DDTHH:MM:SS). Carries time-of-day and takes "
            "precedence over start_date. Stored event props are UTC, "
            "so callers must convert any local boundary to UTC first."
        ),
    ),
    end_datetime: Optional[str] = Query(
        None,
        description=(
            "Filter events on or before this UTC instant "
            "(YYYY-MM-DDTHH:MM:SS). Carries time-of-day and takes "
            "precedence over end_date."
        ),
    ),
    case_id: str = Query(
        ...,
        description="REQUIRED: Filter to events in this case"
    ),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=5000,
        description=(
            "Max events per page. When omitted, returns the entire "
            "matching set in one shot (legacy behaviour). New callers "
            "should always pass this — case-wide returns can hit "
            "tens of MB on busy cases (OPDMD28: 29.5 MB / 9.7s)."
        ),
    ),
    cursor: Optional[str] = Query(
        None,
        description=(
            "Opaque continuation token from a previous response's "
            "`next_cursor`. Engages keyset pagination so deep pages "
            "don't re-read earlier rows. Filter parameters MUST match "
            "the request that produced the cursor — changing them "
            "mid-pagination yields undefined ordering."
        ),
    ),
):
    """
    Get timeline events sorted chronologically (date asc, time asc, key asc) for a specific case.

    Returns events (Transaction, Payment, Communication, etc.) that have dates,
    along with their connected entities. Response shape:

        {
            "events":      [...],   # zero or more event rows
            "count":       N,       # rows in THIS response (preferred)
            "total":       N,       # legacy alias for count — same value;
                                    # name kept for backwards compat with
                                    # callers that wire to "total" before
                                    # pagination shipped. Note this is NOT
                                    # the dataset cardinality.
            "next_cursor": str|None # token for the next page, or null
                                    # if no more pages exist
        }
    """
    # Parse comma-separated types if provided
    event_types = None
    if types:
        event_types = [t.strip() for t in types.split(",") if t.strip()]

    return neo4j_service.get_timeline_events(
        event_types=event_types,
        start_date=start_date,
        end_date=end_date,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        case_id=case_id,
        limit=limit,
        cursor=cursor,
    )


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