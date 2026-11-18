"""Who overlaps with whom, and the go-between graph (lx-overlapviews-a): every pair of people in the case against
every kind of overlap, read through the Corroborate store. Reading needs case view. Levels come from saved leads
only; nothing here weighs a pair."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import require_case_view
from services.corroborate import overlaps

router = APIRouter(prefix="/api/cases", tags=["corroborate"])


@router.get("/{case_id}/corroborate/overlaps", dependencies=[Depends(require_case_view)])
def read_overlaps(case_id: UUID, fresh: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The grid (people, pairs, kinds with their records), Worth a look, the go-between panels and the graph."""
    return overlaps.cached_build(db, case_id, fresh=fresh)
