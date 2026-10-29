"""Admin: per case, how many payments name the other side (services.financial.party_coverage), every case."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import require_admin

router = APIRouter(prefix="/api/admin/party-coverage", tags=["admin-party-coverage"])


@router.get("")
def party_coverage(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    from services.financial.party_coverage import cases_for_admin
    return cases_for_admin(db)
