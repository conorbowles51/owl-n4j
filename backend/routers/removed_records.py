"""Removed analyst work in a case, and undoing a removal (followups m11032229063349)."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user

router = APIRouter(prefix="/api/cases/{case_id}/removed-records", tags=["removed-records"])

CASE_KINDS = ("dossier_assessment", "dossier_interview", "dossier_media", "dossier_link", "dossier_evidence_link")


def _access(db, case_id, user, action):
    from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access
    try:
        check_case_access(db, case_id, user, required_permission=("case", action))
    except CaseNotFound:
        raise HTTPException(status_code=404, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(status_code=403, detail=f"Access denied - case.{action} permission required")


@router.get("")
def list_removed(case_id: UUID, dossier_id: UUID | None = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)):
    """Removals in this case (or one dossier) that can be undone, latest first."""
    from services import removed_records
    _access(db, case_id, user, "view")
    return removed_records.list_removed(db, case_id=case_id, kinds=CASE_KINDS, dossier_id=dossier_id)


@router.post("/{removed_id}/restore")
def restore_removed(case_id: UUID, removed_id: UUID, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """Put a removed assessment, interview, media item or link back exactly as it was."""
    from services import removed_records
    _access(db, case_id, user, "edit")
    try:
        record = removed_records.load(db, removed_id)
        if record.case_id != case_id or record.kind not in CASE_KINDS:
            raise removed_records.RemovedRecordError("That removal was not found.", 404)
        out = removed_records.restore(db, record, user=user)
    except removed_records.RemovedRecordError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    db.commit()
    return out
