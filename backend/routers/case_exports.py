"""Whole-case export: request, watch, cancel, download. Case owners and super admins only."""
from __future__ import annotations

import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.case_export import CaseExport
from postgres.models.enums import CaseMembershipRole
from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services import activity_trail
from services.case_service import get_membership, is_super_admin

router = APIRouter(prefix="/api/cases/{case_id}/exports", tags=["case-exports"])

HOLDS = ("A complete copy of the case: evidence files, financial and phone records, the graph, stored readings, labels "
         "with their authors and status, notes, and the activity trail. It includes privileged material and any saved "
         "passwords and card numbers held in phone records. Handle it as you would the case itself.")
OWNER_PRIVATE_NOTE = ("Chats and agent conversations belong to the person who had them: your export carries your own, "
                      "and the package counts the others it leaves out. A super admin's export carries them all.")
LEFT_OUT = ("Left out: who can open the case (the new owner gives access), the engine's working copies, generated PDFs "
            "and previews, which are drawn again, and uploads still in progress.")
KEPT = "A package is kept for 7 days, then removed."


def _allowed(db: Session, case_id: UUID, user: User) -> Case:
    """Owner or super admin. Anyone else who is not a member sees no case at all, as everywhere else."""
    case = db.get(Case, case_id)
    member = get_membership(db, case_id, user.id) if case else None
    if case is None or (member is None and not is_super_admin(user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    if is_super_admin(user) or case.owner_user_id == user.id or (
            member is not None and member.membership_role == CaseMembershipRole.owner):
        return case
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the case owner or a super admin can export a case")


def _view(row: CaseExport) -> dict:
    summary = row.summary or {}
    return dict(id=str(row.id), status=row.status, phase=row.phase, done=row.done, total=row.total, error=row.error,
                whole=row.whole, requested_by=row.requested_by_name, created_at=row.created_at.isoformat(),
                finished_at=row.finished_at.isoformat() if row.finished_at else None,
                expires_at=row.expires_at.isoformat() if row.expires_at else None, size_bytes=row.size_bytes,
                sha256=row.sha256, rows=summary.get("rows"), tables=summary.get("tables"),
                evidence_files=summary.get("evidence_files"), graph=summary.get("graph"), vectors=summary.get("vectors"),
                missing_from_disk=summary.get("missing_from_disk"),
                differ_from_recorded_hash=summary.get("differ_from_recorded_hash"),
                rows_private_to_others_left_out=summary.get("rows_private_to_others_left_out"))


@router.get("")
def list_exports(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    _allowed(db, case_id, user)
    rows = db.query(CaseExport).filter(CaseExport.case_id == case_id).order_by(CaseExport.created_at.desc()).limit(10).all()
    return dict(exports=[_view(r) for r in rows], holds=HOLDS, private_note=OWNER_PRIVATE_NOTE, left_out=LEFT_OUT, kept=KEPT,
                carries_all_private=is_super_admin(user))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def request_export(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    from services.caseport.jobs import ACTIVE
    case = _allowed(db, case_id, user)
    if db.query(CaseExport.id).filter(CaseExport.case_id == case_id, CaseExport.status.in_(ACTIVE)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An export of this case is already running")
    whole = is_super_admin(user)
    row = CaseExport(case_id=case_id, requested_by_user_id=user.id, requested_by_email=user.email,
                     requested_by_name=user.name, whole=whole)
    db.add(row)
    db.flush()
    activity_trail.record("case_export_requested", db=db, user=user, case_id=case_id,
                          details=dict(export_id=str(row.id), title=case.title, carries_rows_private_to_others=whole))
    db.commit()
    db.refresh(row)
    return _view(row)


def _row(db, case_id, export_id) -> CaseExport:
    row = db.get(CaseExport, export_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found")
    return row


@router.post("/{export_id}/cancel")
def cancel_export(case_id: UUID, export_id: UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    _allowed(db, case_id, user)
    row = _row(db, case_id, export_id)
    if row.status == "queued":
        row.status = "cancelled"
    elif row.status == "running":
        row.status = "cancelling"
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "This export is not running")
    activity_trail.record("case_export_cancelled", db=db, user=user, case_id=case_id, details=dict(export_id=str(row.id)))
    db.commit()
    return _view(row)


@router.get("/{export_id}/download")
def download_export(case_id: UUID, export_id: UUID, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    case = _allowed(db, case_id, user)
    row = _row(db, case_id, export_id)
    if row.status != "complete" or not row.path or not os.path.isfile(row.path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This package is not available")
    activity_trail.record("case_export_downloaded", db=db, commit=True, user=user, case_id=case_id,
                          details=dict(export_id=str(row.id), sha256=row.sha256, size_bytes=row.size_bytes))
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "-" for ch in case.title)[:60].strip() or "case"
    return FileResponse(row.path, media_type="application/x-tar", filename=f"{safe}.loupecase.tar")


@router.delete("/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_export(case_id: UUID, export_id: UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    from services.caseport.jobs import remove_files
    _allowed(db, case_id, user)
    row = _row(db, case_id, export_id)
    if row.status in ("queued", "running", "cancelling"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the export first")
    if row.path:
        remove_files(row.path)
    row.status, row.path = "removed", None
    activity_trail.record("case_export_removed", db=db, user=user, case_id=case_id, details=dict(export_id=str(row.id)))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
