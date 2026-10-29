"""Admin: held statements the reader got nothing out of (services.financial.reader_gaps), every case."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from postgres.models.user import User
from routers.users import require_admin

router = APIRouter(prefix="/api/admin/reader-gaps", tags=["admin-reader-gaps"])


@router.get("")
def reader_gaps(_: User = Depends(require_admin)):
    from services.financial.reader_gaps import summary_for_admin
    return summary_for_admin()
