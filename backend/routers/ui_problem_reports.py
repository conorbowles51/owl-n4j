"""Report a problem on phone screens: case members file and read reports for their case (07 section 9)."""
from uuid import UUID
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from postgres.session import get_db
from postgres.models.user import User
from routers.users import get_current_db_user
from services import ui_problem_reports as reports
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access

router = APIRouter(prefix='/api/cases/{case_id}/ui-problem-reports', tags=['ui-problem-reports'])


def _access(db, case_id, user):
    try:
        check_case_access(db, case_id, user)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail='Case not found') from None
    except CaseAccessDenied:
        raise HTTPException(status_code=403, detail='You do not have access to this case') from None


@router.post('', status_code=201)
def file_report(case_id: UUID, body: dict = Body(...), user: User = Depends(get_current_db_user),
                db: Session = Depends(get_db)):
    """Anyone who can open the case can report a problem on it. Structured fields only, plus optional text."""
    _access(db, case_id, user)
    try:
        report = reports.create(db, case_id=case_id, user=user, body=body)
    except reports.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {'id': str(report.id), 'reference': reports.reference(report)}


@router.get('')
def list_reports(case_id: UUID, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Reports on this case, newest first: case members with access and admins."""
    from postgres.models.ui_problem_report import UiProblemReport as R
    _access(db, case_id, user)
    rows = db.query(R).filter(R.case_id == case_id).order_by(R.created_at.desc()).limit(500).all()
    total = db.query(R).filter(R.case_id == case_id).count()
    return {'reports': [reports.view(r) for r in rows], 'total': total, 'shown': len(rows)}
