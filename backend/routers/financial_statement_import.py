"""Automatic statement review; permissions remain scoped to the selected case."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import read_statement_import
from services.financial.statement_file_status import statement_file_status

logger = logging.getLogger(__name__)
_require_access = case_access_dependency(lambda request, payload: ('case', 'view'))
router = APIRouter(prefix='/api/financial/statement-import', tags=['financial'],
                   dependencies=[Depends(get_current_db_user), Depends(_require_access)])


@router.get('/files')
def files(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    return statement_file_status(db, case_id=case_id)


@router.get('/{evidence_file_id}')
def preview(evidence_file_id: UUID, case_id: UUID = Query(...),
            currency: str | None = Query(None, pattern=r'^[A-Z]{3}$'),
            statement_id: str | None = Query(None, pattern=r'^[a-f0-9]{64}$'), db: Session = Depends(get_db)):
    try:
        return read_statement_import(db, case_id=case_id, evidence_file_id=evidence_file_id, currency=currency, statement_id=statement_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Automatic statement review failed')
        raise HTTPException(status_code=500, detail='The statement could not be prepared for review. Your evidence has not changed.')

from sqlalchemy.orm import sessionmaker
from routers.evidence import _resolve_stored_path
from services.financial.quarantine_row import actor_from_user
from services.financial.statement_import import StatementImportRequest, confirm_statement_import


@router.post('/{evidence_file_id}/confirm', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def confirm(evidence_file_id: UUID, body: StatementImportRequest, case_id: UUID = Query(...),
            user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return confirm_statement_import(session_factory=sessionmaker(bind=db.get_bind()),
            case_id=case_id, evidence_file_id=evidence_file_id, request=body,
            actor=actor_from_user(user), resolve_path=_resolve_stored_path)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Statement import could not be confirmed')
        raise HTTPException(status_code=500, detail='Import could not be confirmed. Retry the same review to check its outcome without adding duplicates.')

from pydantic import BaseModel, ConfigDict
from services.financial.statement_reprocessing import create_statement_version
from services.evidence_processing_service import process_db_files


class ReprocessRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID


@router.post('/{evidence_file_id}/reprocess', dependencies=[Depends(case_access_dependency(lambda request, payload: ('evidence', 'upload')))])
async def reprocess(evidence_file_id: UUID, body: ReprocessRequest, case_id: UUID = Query(...),
                    user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        version = create_statement_version(db, case_id=case_id, evidence_file_id=evidence_file_id,
            request_id=body.request_id, actor=actor_from_user(user), resolve_path=_resolve_stored_path)
        if version.engine_job_id and version.status in ('processing', 'processed'):
            return dict(case_id=str(case_id), evidence_file_id=str(version.id), job_id=version.engine_job_id)
        result = await process_db_files(db, case_id=case_id, file_ids=[version.id],
            force_reprocess=True, preparation_mode='pdf_review', requested_by_user_id=user.id)
        if len(result.get('job_ids', [])) != 1:
            raise PdfMappingError('The new version could not be queued. Retry this reprocessing request.', 409)
        return dict(case_id=str(case_id), evidence_file_id=str(version.id), job_id=result['job_ids'][0])
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Statement reprocessing failed')
        raise HTTPException(status_code=500, detail='Reprocessing could not be confirmed. Previous readings are preserved; retry the same request.')
