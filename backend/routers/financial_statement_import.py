from typing import Annotated
"""Automatic statement review; permissions remain scoped to the selected case."""
import logging
from datetime import date
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import read_statement_import
from services.financial.currency_correction import CurrencyCode
from services.financial.imported_records import CompleteImportedRecord
from services.financial.statement_check_request import StatementCheckRequest, check_statement_request
from services.financial.statement_file_status import statement_file_status
from services.financial.payment_document_review import (
    PaymentMatchRequest, PaymentDocumentReviewRequest, matching_payments,
    read_payment_document, save_payment_document,
)

logger = logging.getLogger(__name__)
_require_access = case_access_dependency(lambda request, payload: ('case', 'view'))
router = APIRouter(prefix='/api/financial/statement-import', tags=['financial'],
                   dependencies=[Depends(get_current_db_user), Depends(_require_access)])

from services.financial.saved_statement_recovery import (
    StatementRecoveryRequest, read_recovery, preview_recovery, save_recovery,
)


@router.get('/sources/{source_id}/recovery')
def saved_statement_recovery(source_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return read_recovery(db, case_id=case_id, source_id=source_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/sources/{source_id}/recovery/{action}', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def review_saved_statement_recovery(source_id: UUID, action: Literal['preview', 'save'], body: StatementRecoveryRequest,
        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        if action == 'preview':
            return preview_recovery(db, case_id=case_id, source_id=source_id, request=body)
        return save_recovery(db, case_id=case_id, source_id=source_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Saved statement recovery failed')
        raise HTTPException(status_code=500, detail='The sections could not be saved. Previous records are unchanged; your assignments remain available to retry.')


@router.get('/files')
def files(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    return statement_file_status(db, case_id=case_id)


from services.financial.statement_details import StatementDetailsRequest, read_statement_details, update_statement_details


@router.get('/sources/{source_id}/details')
def statement_details(source_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return read_statement_details(db, case_id=case_id, source_id=source_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.put('/sources/{source_id}/details', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def save_statement_details(source_id: UUID, body: StatementDetailsRequest, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return update_statement_details(db, case_id=case_id, source_id=source_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Statement details could not be saved')
        raise HTTPException(status_code=500, detail='The changes could not be saved. Your previous values are unchanged.')


@router.get('/incomplete-records')
def incomplete_records(account_ids: Annotated[list[UUID] | None, Query()] = None, account_holders: Annotated[list[str] | None, Query()] = None, case_id: UUID = Query(...), account_id: UUID | None = Query(None),
        source_document_id: UUID | None = None,
        start_date: date | None = Query(None), end_date: date | None = Query(None),
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    from services.financial.imported_records import imported_records
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail='The end date must be on or after the start date.')
    return imported_records(db, case_id=case_id, account_id=account_id, account_ids=account_ids, account_holders=account_holders,
        start_date=start_date, end_date=end_date, offset=offset, limit=limit, source_document_id=source_document_id)


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
from services.financial.statement_import import StatementImportRequest, StatementReviewDraft, confirm_statement_import
from services.financial.pdf_candidates import _Contract, _Digest
from pydantic import Field


class StatementCoverageRequest(_Contract):
    expected_revision: _Digest
    statement_id: _Digest | None = None
    replaces_source_document_id: UUID | None = None
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    institution: str = Field(default='', max_length=128)
    account_number: str = Field(default='', max_length=128)
    period_start: str = Field(default='', max_length=32)
    period_end: str = Field(default='', max_length=32)


class RefreshStoredReadingRequest(_Contract):
    compared_review_revision: _Digest | None = None
    expected_revision: _Digest
    expected_reading_revision: _Digest | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')


@router.post('/sources/{source_id}/refresh-reading', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def refresh_stored_reading(source_id: UUID, body: RefreshStoredReadingRequest, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.legacy_statement_refresh import refresh_legacy_import
    try:
        return refresh_legacy_import(session_factory=sessionmaker(bind=db.get_bind()), case_id=case_id,
            source_id=source_id, expected_revision=body.expected_revision, actor=actor_from_user(user), resolve_path=_resolve_stored_path,
            expected_reading_revision=body.expected_reading_revision, currency=body.currency,
            compared_review_revision=body.compared_review_revision)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Stored statement reading could not be updated')
        raise HTTPException(status_code=500, detail='The update could not be confirmed. Retry to check its result without importing twice.')


@router.post('/{evidence_file_id}/coverage-check')
def check_import_coverage(evidence_file_id: UUID, body: StatementCoverageRequest, case_id: UUID = Query(...),
                          db: Session = Depends(get_db)):
    from services.financial.statement_import_overlap import coverage_review
    try:
        proposal = read_statement_import(db, case_id=case_id, evidence_file_id=evidence_file_id,
            currency=body.currency, statement_id=body.statement_id, _include_period_checks=False)
        if proposal['revision'] != body.expected_revision:
            raise PdfMappingError('The statement reading changed. Reopen it before comparing dates.', 409)
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id),
                    **coverage_review(db, case_id=case_id, file_id=evidence_file_id, request=body.model_dump(mode='json')))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/{evidence_file_id}/checks')
def review_checks(evidence_file_id: UUID, body: StatementCheckRequest, case_id: UUID = Query(...),
                  db: Session = Depends(get_db)):
    try:
        proposal = read_statement_import(db, case_id=case_id, evidence_file_id=evidence_file_id,
                                        currency=body.currency, statement_id=body.statement_id, _include_period_checks=False)
        return check_statement_request(proposal, body)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/{evidence_file_id}/payment-document/matches')
def payment_matches(evidence_file_id: UUID, body: PaymentMatchRequest, case_id: UUID = Query(...),
                    document_id: str | None = Query(None, pattern=r'^[a-f0-9]{64}$'), db: Session = Depends(get_db)):
    try:
        proposal = read_payment_document(db, case_id=case_id, evidence_file_id=evidence_file_id, document_id=document_id)
        return matching_payments(db, case_id=case_id, request=body, direction='credit' if proposal['kind'] == 'deposit_receipt' else None)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/{evidence_file_id}/payment-document/save', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def save_payment_review(evidence_file_id: UUID, body: PaymentDocumentReviewRequest, case_id: UUID = Query(...),
                        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.workspace_entry_service import WorkspaceEntryValidationError
    try:
        return save_payment_document(db, case_id=case_id, evidence_file_id=evidence_file_id,
            request=body, user=user, resolve_path=_resolve_stored_path)
    except (PdfMappingError, WorkspaceEntryValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=getattr(exc, 'status_code', 422), detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Payment document review could not be saved')
        raise HTTPException(status_code=500, detail='The review could not be confirmed. Retry the same save to check its outcome without creating another note.')


# Match a file UUID in the router itself so named operations such as
# /removals/confirm cannot be captured as a single-statement import.
@router.post('/{evidence_file_id:uuid}/confirm', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
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


@router.post('/sources/{source_id}/complete-record', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def complete_imported_record(source_id: UUID, body: CompleteImportedRecord, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.imported_records import complete_record
    try:
        return complete_record(session_factory=sessionmaker(bind=db.get_bind()), case_id=case_id,
            source_id=source_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Imported record correction failed')
        raise HTTPException(status_code=500, detail='The correction could not be saved. Your original record is retained; retry the same correction.')

from pydantic import BaseModel, ConfigDict
from pydantic import Field
from services.financial.statement_progress import save_progress
from services.financial.review_recovery import previous_review_detail, acknowledge_recovery
from services.financial.statement_row_assignment import RowAssignmentRequest, reassign_rows


@router.post('/{evidence_file_id}/row-assignment/preview', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def preview_row_assignment(evidence_file_id: UUID, body: RowAssignmentRequest, case_id: UUID = Query(...),
                           user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return reassign_rows(db, case_id=case_id, evidence_file_id=evidence_file_id,
            body=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        db.rollback()  # Preview never persists a review or assignment.


@router.post('/{evidence_file_id}/row-assignment/apply', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def apply_row_assignment(evidence_file_id: UUID, body: RowAssignmentRequest, case_id: UUID = Query(...),
                         user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return reassign_rows(db, case_id=case_id, evidence_file_id=evidence_file_id,
            body=body, actor=actor_from_user(user), apply=True)
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Statement rows could not be reassigned')
        raise HTTPException(status_code=500, detail='The move could not be confirmed. Reopen the statements to check the saved result before trying again.')


@router.get('/{evidence_file_id}/previous-reviews/{review_id}')
def previous_statement_review(evidence_file_id: UUID, review_id: str, case_id: UUID = Query(...),
                              offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                              db: Session = Depends(get_db)):
    try:
        return previous_review_detail(db, case_id=case_id, evidence_file_id=evidence_file_id,
            review_id=review_id, offset=offset, limit=limit)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


class ReviewComparisonRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.post('/{evidence_file_id}/previous-reviews/compare', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def compare_previous_reviews(evidence_file_id: UUID, body: ReviewComparisonRequest, case_id: UUID = Query(...),
                             user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return acknowledge_recovery(db, case_id=case_id, evidence_file_id=evidence_file_id,
            expected_revision=body.expected_revision, actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
from services.financial.file_visibility import set_financial_file_visibility
from services.financial.evidence_intake import resolve_financial_selection, prepare_existing_financial_file
from services.financial.statement_reprocessing import create_statement_version
from services.evidence_processing_service import process_db_files


class FileVisibilityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    removed: bool = Field(strict=True)
    expected_revision: str = Field(min_length=1, max_length=64)


class StatementProgressRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_review_revision: str = Field(min_length=1, max_length=64)
    request: StatementReviewDraft


@router.put('/{evidence_file_id}/progress', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def save_statement_progress(evidence_file_id: UUID, body: StatementProgressRequest, case_id: UUID = Query(...),
                            user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return save_progress(db, case_id=case_id, evidence_file_id=evidence_file_id,
            request=body.request, expected_review_revision=body.expected_review_revision, actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Statement progress could not be saved')
        raise HTTPException(status_code=500, detail='Progress could not be saved. Your edits remain in this review. Try saving again.')


class EvidenceSelectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    folder_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class EvidencePreparationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(min_length=1, max_length=64)


@router.post('/selection/resolve')
def resolve_selection(body: EvidenceSelectionRequest, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return resolve_financial_selection(db, case_id=case_id, file_ids=body.file_ids, folder_ids=body.folder_ids)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/{evidence_file_id}/prepare-existing', dependencies=[
    Depends(case_access_dependency(lambda request, payload: ('case', 'edit'))),
    Depends(case_access_dependency(lambda request, payload: ('evidence', 'upload')))])
async def prepare_existing(evidence_file_id: UUID, body: EvidencePreparationRequest, case_id: UUID = Query(...),
                           user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return await prepare_existing_financial_file(db, case_id=case_id, evidence_file_id=evidence_file_id,
            expected_revision=body.expected_revision, actor=actor_from_user(user), resolve_path=_resolve_stored_path,
            process_files=process_db_files)
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Existing evidence could not be sent to Financial')
        raise HTTPException(status_code=500, detail='The financial reading could not be confirmed. Refresh files before trying again; existing evidence results are retained.')


@router.post('/{evidence_file_id}/visibility', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def visibility(evidence_file_id: UUID, body: FileVisibilityRequest, case_id: UUID = Query(...),
               user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return set_financial_file_visibility(db, case_id=case_id, evidence_file_id=evidence_file_id,
            removed=body.removed, expected_revision=body.expected_revision, actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Financial file-list change failed')
        raise HTTPException(status_code=500, detail='The file-list change could not be confirmed. Refresh files to check the result. The original remains in Evidence.')


class ReprocessRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    reading_mode: Literal['automatic', 'page_images'] = 'automatic'


@router.post('/{evidence_file_id}/reprocess', dependencies=[Depends(case_access_dependency(lambda request, payload: ('evidence', 'upload')))])
async def reprocess(evidence_file_id: UUID, body: ReprocessRequest, case_id: UUID = Query(...),
                    user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        version = create_statement_version(db, case_id=case_id, evidence_file_id=evidence_file_id,
            request_id=body.request_id, reading_mode=body.reading_mode,
            actor=actor_from_user(user), resolve_path=_resolve_stored_path)
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

# Batches retain their own file/period list and reuse the single-statement writer.
from services.financial import import_batches


class CreateFinancialBatch(EvidenceSelectionRequest):
    request_id: UUID


class ConfirmFinancialBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_ready_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_id: UUID | None = None


class FinancialBatchCurrency(BaseModel):
    model_config = ConfigDict(extra='forbid')
    currency: str = Field(pattern=r'^[A-Z]{3}$')


class SelectedCurrencyStatement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class SelectedStatementCurrency(BaseModel):
    model_config = ConfigDict(extra='forbid')
    currency: CurrencyCode
    statements: list[SelectedCurrencyStatement] = Field(min_length=1, max_length=10000)


@router.post('/batches/{batch_id}/currency', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def set_batch_statement_currency(batch_id: UUID, body: SelectedStatementCurrency, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return import_batches.set_selected_currency(db, case_id=case_id, batch_id=batch_id,
            selections=body.statements, currency=body.currency, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/batches', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit'))), Depends(case_access_dependency(lambda request,payload: ('evidence','upload')))])
def create_financial_batch(body: CreateFinancialBatch, case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        identifier=import_batches.create_batch(db,case_id=case_id,request_id=body.request_id,file_ids=body.file_ids,folder_ids=body.folder_ids,actor=actor_from_user(user))
        return dict(id=str(identifier),case_id=str(case_id))
    except PdfMappingError as exc:
        db.rollback();raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


class FinancialRemovalSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    batch_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    file_ids: list[UUID] = Field(default_factory=list, max_length=10000)


class ConfirmFinancialRemoval(FinancialRemovalSelection):
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.post('/removals/preview', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def preview_financial_removal(body: FinancialRemovalSelection, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.import_removal import preview_removal
    try:
        return preview_removal(db, case_id=case_id, **body.model_dump())
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/removals/confirm', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def confirm_financial_removal(body: ConfirmFinancialRemoval, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.import_removal import remove_imports
    try:
        return remove_imports(db, case_id=case_id, actor=actor_from_user(user), **body.model_dump())
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get('/batches/list')
def list_financial_batches(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from sqlalchemy import select
    from postgres.models.financial_import_batches import FinancialImportBatch
    batches=db.scalars(select(FinancialImportBatch).where(FinancialImportBatch.case_id==case_id, FinancialImportBatch.status != 'removed').order_by(FinancialImportBatch.created_at.desc()).limit(100))
    return dict(case_id=str(case_id),batches=[dict(id=str(b.id),status=b.status,created_at=b.created_at.isoformat(),file_count=len(b.files),
        created_by=(b.actor or {}).get('name', ''), filenames=[f['filename'] for f in b.files[:3]],
        checked_files=sum(f['status'] == 'checked' for f in b.files),
        failed_files=sum(f['status'] == 'error' for f in b.files)) for b in batches])


@router.get('/batches/{batch_id}')
def get_financial_batch(batch_id: UUID, case_id: UUID = Query(...), offset: int = Query(0,ge=0), limit: int = Query(100,ge=1,le=500),only_problems: bool = Query(False),db: Session = Depends(get_db)):
    try:
        return import_batches.batch_status(db,case_id=case_id,batch_id=batch_id,offset=offset,limit=limit,only_problems=only_problems)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


@router.post('/batches/{batch_id}/control/{action}', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def control_financial_batch(batch_id: UUID, action: str, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return import_batches.control_batch(db, case_id=case_id, batch_id=batch_id, action=action)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/batches/{batch_id}/confirm', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def confirm_financial_batch(batch_id: UUID,body: ConfirmFinancialBatch,case_id: UUID = Query(...),user=Depends(get_current_db_user),db: Session = Depends(get_db)):
    try:
        return import_batches.queue_import(db,case_id=case_id,batch_id=batch_id,expected_revision=body.expected_ready_revision,actor=actor_from_user(user),request_id=body.request_id)
    except PdfMappingError as exc:
        db.rollback();raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


@router.get('/batches/{batch_id}/imported-transactions')
def imported_financial_batch_scope(batch_id: UUID, case_id: UUID = Query(...), operation_id: UUID | None = Query(None), db: Session = Depends(get_db)):
    from services.financial.batch_transaction_scope import imported_batch_scope
    try:
        return imported_batch_scope(db, case_id=case_id, batch_id=batch_id, operation_id=operation_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/batches/{batch_id}/refresh-statements', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def refresh_financial_batch_statements(batch_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return import_batches.refresh_statement_list(db, case_id=case_id, batch_id=batch_id)
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


class SaveFinancialBatchReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_review_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    request: StatementReviewDraft


@router.post('/batches/{batch_id}/items/{item_id}/confirm', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def confirm_financial_batch_review(batch_id: UUID, item_id: UUID, body: SaveFinancialBatchReview,
        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return import_batches.confirm_review(session_factory=sessionmaker(bind=db.get_bind()), case_id=case_id,
            batch_id=batch_id, item_id=item_id, request=body.request,
            expected_review_revision=body.expected_review_revision, actor=actor_from_user(user), resolve_path=_resolve_stored_path)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.put('/batches/{batch_id}/items/{item_id}',  dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def save_financial_batch_review(batch_id: UUID,item_id: UUID,body: SaveFinancialBatchReview,case_id: UUID = Query(...),db: Session = Depends(get_db)):
    try:
        return import_batches.save_review(db,case_id=case_id,batch_id=batch_id,item_id=item_id,request=body.request,expected_review_revision=body.expected_review_revision)
    except PdfMappingError as exc:
        db.rollback();raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


@router.post('/batches/{batch_id}/files/{source_id}/currency', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def financial_batch_currency(batch_id: UUID,source_id: UUID,body: FinancialBatchCurrency,case_id: UUID=Query(...),db: Session=Depends(get_db)):
    from services.financial.money import MoneyError
    try:
        import_batches.choose_currency(db,case_id=case_id,batch_id=batch_id,source_id=source_id,currency=body.currency)
        return dict(saved=True)
    except (PdfMappingError,MoneyError) as exc:
        db.rollback();raise HTTPException(status_code=getattr(exc,'status_code',422),detail=str(exc)) from exc

@router.get('/batches/{batch_id}/items/{item_id}')
def get_financial_batch_item(batch_id: UUID,item_id: UUID,case_id: UUID=Query(...),db: Session=Depends(get_db)):
    from sqlalchemy import select
    from postgres.models.financial_import_batches import FinancialImportBatchItem
    try:
        import_batches.batch_for(db,case_id,batch_id)
        item=db.scalar(select(FinancialImportBatchItem).where(FinancialImportBatchItem.batch_id==batch_id,FinancialImportBatchItem.id==item_id))
        if item is None: raise PdfMappingError('Statement not found in this batch.',404)
        item=import_batches.checked_batch_items(db,case_id,[item])[0]
        return dict(id=str(item.id),file_id=str(item.file_id),statement_id=item.statement_key or None,status=item.status,review_request=item.review_request,review_revision=item.review_revision,**item.summary)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


class BatchImportChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['skip','restore']
    reason: str = Field(min_length=1, max_length=2000)
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.post('/batches/{batch_id}/items/{item_id}/import-choice', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def choose_batch_import(batch_id: UUID, item_id: UUID, body: BatchImportChoice,
                        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return import_batches.leave_unimported(db, case_id=case_id, batch_id=batch_id, item_id=item_id,
            action=body.action, reason=body.reason, expected_revision=body.expected_revision, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


@router.get('/batches/{batch_id}/items/{item_id}/next-problem')
def next_financial_problem(batch_id: UUID, item_id: UUID, case_id: UUID=Query(...),
                           direction: Literal["next", "previous"] = Query("next"), db: Session=Depends(get_db)):
    try:
        return import_batches.next_problem(db, case_id=case_id, batch_id=batch_id, item_id=item_id, direction=direction)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/batches/{batch_id}/files/{source_id}/retry', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit'))),Depends(case_access_dependency(lambda request,payload: ('evidence','upload')))])
def retry_financial_batch_file(batch_id: UUID,source_id: UUID,case_id: UUID=Query(...),db: Session=Depends(get_db)):
    try:
        import_batches.retry_file(db,case_id=case_id,batch_id=batch_id,source_id=source_id)
        return dict(queued=True)
    except PdfMappingError as exc:
        db.rollback();raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc
