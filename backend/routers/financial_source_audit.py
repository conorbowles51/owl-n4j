"""Case-authorized read-only source/provenance inspection."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial.pdf_candidates import PdfMappingError
from services.financial.source_audit import list_source_audit, source_audit_detail

router = APIRouter(prefix='/api/financial/source-audit', tags=['financial'], dependencies=[
    Depends(get_current_db_user), Depends(case_access_dependency(lambda request, payload: ('case', 'view')))])


@router.get('')
def source_audit(case_id: UUID = Query(...), offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=50), visibility: Literal['all', 'visible', 'hidden'] = 'all',
        db: Session = Depends(get_db)):
    return list_source_audit(db, case_id=case_id, offset=offset, limit=limit, visibility=visibility)


@router.get('/{file_id}')
def source_detail(file_id: UUID, case_id: UUID = Query(...), text_offset: int = Query(0, ge=0),
        text_limit: int = Query(4000, ge=1, le=8000), db: Session = Depends(get_db)):
    try:
        return source_audit_detail(db, case_id=case_id, file_id=file_id, text_offset=text_offset, text_limit=text_limit)
    except PdfMappingError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
