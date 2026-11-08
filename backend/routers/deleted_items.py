"""Deleted items of a case: list, restore, delete now (services/deleted_items.py; lx-deletebin B, C)."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user

router = APIRouter(prefix="/api/cases/{case_id}/deleted-items", tags=["deleted-items"])


def _view(db, case_id, user):
    from routers.case_access import authorize_case_view
    return authorize_case_view(db, str(case_id), user)


@router.get("")
def list_deleted_items(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Everything deleted in this case that can still be restored: what, by whom, when, days left."""
    from postgres.soft_delete import enabled
    from services import deleted_items
    _view(db, case_id, user)
    if not enabled():
        return dict(enabled=False, items=[], retention_days=None, can_manage=False)
    return deleted_items.list_items(db, case_id, user)


def _run(fn, db, case_id, kind, item_id, user):
    from postgres.soft_delete import enabled
    from services import deleted_items
    _view(db, case_id, user)
    if not enabled():
        raise HTTPException(status_code=404, detail="Deleted items are switched off")
    try:
        return fn(db, case_id, kind, item_id, user)
    except deleted_items.DeletedItemError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/{kind}/{item_id}/restore")
async def restore_deleted_item(case_id: UUID, kind: str, item_id: str, db: Session = Depends(get_db),
                               user: User = Depends(get_current_db_user)):
    """Put a deleted item back exactly as it was (the case owner or an admin)."""
    from services import deleted_items
    return await run_in_threadpool(_run, deleted_items.restore, db, case_id, kind, item_id, user)


@router.post("/{kind}/{item_id}/purge")
async def purge_deleted_item(case_id: UUID, kind: str, item_id: str, db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """Remove a deleted item for good now (the case owner or an admin): its rows, graph and search entries and every
    file no other row uses. Returns the counts."""
    from services import deleted_items
    return await run_in_threadpool(_run, deleted_items.purge, db, case_id, kind, item_id, user)
