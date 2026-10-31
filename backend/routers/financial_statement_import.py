from typing import Annotated
"""Automatic statement review; permissions remain scoped to the selected case."""
import logging
from datetime import date
from typing import Literal
from uuid import UUID
from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import read_statement_import
from services.financial.currency_correction import CurrencyCode
from services.financial.imported_records import CompleteImportedRecord
from services.financial.manual_statement_payment import ManualStatementPayment
from services.financial.record_withdrawal import RecordWithdrawal
from services.financial.statement_check_request import StatementCheckRequest, check_statement_request
from services.financial.statement_file_status import statement_file_status
from services.financial.payment_document_review import (
    PaymentMatchRequest, PaymentDocumentReviewRequest, matching_payments,
    read_payment_document, save_payment_document,
)

logger = logging.getLogger(__name__)
_require_access = case_access_dependency(lambda request, payload: ('case', 'view'))
from services.financial.view_cache import cached_view, not_kept

router = APIRouter(prefix='/api/financial/statement-import', tags=['financial'],
                   dependencies=[Depends(get_current_db_user), Depends(_require_access)])

from services.financial import bulk_statement_details


def _batch_added(db, case_id, batch_id):
    """Who started this batch, when, and from where (activity trail when it has it). Never fails the read."""
    try:
        from services.activity_trail import batch_sources
        from postgres.models.financial_import_batches import FinancialImportBatch
        batch = db.get(FinancialImportBatch, batch_id)
        if batch is None or batch.case_id != case_id:
            return None
        actor = batch.actor or {}
        return dict(by=None if actor.get('auto_read') else actor.get('name'), automatic=bool(actor.get('auto_read')),
                    at=batch.created_at.isoformat() if batch.created_at else None,
                    sent_from=batch_sources(db, case_id=case_id, batch_ids=[batch_id]).get(str(batch_id)))
    except Exception:
        logger.exception('Batch provenance unavailable')
        return None


def _record_send(db, *, case_id, user, how, file_ids=(), batch_id=None, extra=None):
    """Activity trail: a person put files in Financial (who, from where, which screen, which files)."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from services import activity_trail
    try:
        ids = [UUID(str(i)) for i in file_ids]
        files = list(db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_(ids)))) if ids else []
    except Exception:
        files = []
    activity_trail.record('financial_send', db=db, commit=True, user=user, case_id=case_id,
        details=dict(how=how, batch_id=str(batch_id) if batch_id else None, file_count=len(file_ids),
                     files=activity_trail.file_entries(files), **(extra or {})))


@router.post('/account-details/statements')
def account_detail_selection(body: bulk_statement_details.Selection, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return bulk_statement_details.list_statements(db, case_id=case_id, selection=body)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/account-details/{action}', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def bulk_account_details(action: Literal['preview', 'save'], body: bulk_statement_details.BulkEdit,
        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        if action == 'preview':
            return bulk_statement_details.preview(db, case_id=case_id, request=body)
        return bulk_statement_details.save(db, case_id=case_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Bulk statement account correction failed')
        raise HTTPException(status_code=500, detail='The account details could not be saved. Retry with the same selection to check the result; completed saves will not be repeated.')

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
@cached_view('statement-import-files')
def files(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    # The register's own cache stays: it checks this case's rows of every table the view reads (measured on six
    # cases), whereas the view checks three of them whole (no case_id), so another case's import makes the view
    # compute again and the register's cache then answers as before.
    return statement_file_status(db, case_id=case_id)


from services.financial.statement_details import StatementDetailsRequest, read_statement_details, update_statement_details


@router.get('/sources/{source_id}/details')
def statement_details(source_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
        include_positions: bool = Query(False)):
    try:
        return read_statement_details(db, case_id=case_id, source_id=source_id, include_positions=include_positions)
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


from pydantic import BaseModel, ConfigDict
from services.financial import account_type_change


class _AccountTypePreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_type: Literal['credit_card', 'checking', 'savings']


@router.get('/account-types')
@cached_view('statement-import-account-types')
def account_types(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return account_type_change.account_type_review(db, case_id=case_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get('/accounts/{account_id}/type')
def account_type(account_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return account_type_change.account_type_state(db, case_id=case_id, account_id=account_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/accounts/{account_id}/type/preview')
def preview_account_type(account_id: UUID, body: _AccountTypePreview, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return account_type_change.preview_account_type(db, case_id=case_id, account_id=account_id, account_type=body.account_type)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/accounts/{account_id}/type', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def save_account_type(account_id: UUID, body: account_type_change.AccountTypeRequest, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return account_type_change.save_account_type(db, case_id=case_id, account_id=account_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Account type could not be saved')
        raise HTTPException(status_code=500, detail='The account type could not be saved. Nothing was changed.')


@router.post('/accounts/{account_id}/type/flip-rows', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def flip_account_rows(account_id: UUID, body: account_type_change.FlipRowsRequest, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return account_type_change.flip_flagged_rows(db, case_id=case_id, account_id=account_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Flagged rows could not be flipped')
        raise HTTPException(status_code=500, detail='The rows could not be flipped. Nothing was changed.')


from services.financial import account_details_correction


@router.get('/accounts/{account_id}/details')
def account_details(account_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return account_details_correction.account_details_state(db, case_id=case_id, account_id=account_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/accounts/{account_id}/details/preview')
def preview_account_details(account_id: UUID, body: account_details_correction.AccountDetailsRequest,
        case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return account_details_correction.preview_account_details(db, case_id=case_id, account_id=account_id, request=body)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/accounts/{account_id}/details', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def save_account_details(account_id: UUID, body: account_details_correction.AccountDetailsRequest, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return account_details_correction.save_account_details(db, case_id=case_id, account_id=account_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Account details could not be corrected')
        raise HTTPException(status_code=500, detail='The account could not be corrected. Nothing was changed.')


@router.post('/accounts/{account_id}/details/confirm', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def confirm_account_details(account_id: UUID, body: account_details_correction.ConfirmAccountDetailsRequest,
        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return account_details_correction.confirm_account_details(db, case_id=case_id, account_id=account_id,
                                                                  request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/accounts/{account_id}/details/undo', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def undo_account_details(account_id: UUID, body: account_details_correction.UndoAccountDetailsRequest, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return account_details_correction.undo_account_details(db, case_id=case_id, account_id=account_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Account correction could not be undone')
        raise HTTPException(status_code=500, detail='The correction could not be undone. Nothing was changed.')


@router.get('/incomplete-records')
def incomplete_records(account_ids: Annotated[list[UUID] | None, Query()] = None, account_holders: Annotated[list[str] | None, Query()] = None, case_id: UUID = Query(...), account_id: UUID | None = Query(None),
        source_document_id: UUID | None = None, evidence_file_id: Annotated[list[UUID] | None, Query()] = None,
        start_date: date | None = Query(None), end_date: date | None = Query(None),
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    from services.financial.imported_records import imported_records
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail='The end date must be on or after the start date.')
    return imported_records(db, case_id=case_id, account_id=account_id, account_ids=account_ids, account_holders=account_holders,
        start_date=start_date, end_date=end_date, offset=offset, limit=limit, source_document_id=source_document_id,
        evidence_file_ids=evidence_file_id)


@router.get('/deployment-recovery')
def deployment_recovery_status(case_id: UUID = Query(...), offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    from services.financial.deployment_recovery import status
    return status(db, case_id, offset=offset, limit=limit)


@router.post('/deployment-recovery/{action}', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def deployment_recovery_control(action: Literal['pause', 'resume'], case_id: UUID = Query(...),
        db: Session = Depends(get_db)):
    from services.financial.deployment_recovery import control
    try:
        return control(db, case_id, action)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/deployment-recovery/items/{item_id}/retry', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def retry_deployment_recovery_item(item_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.deployment_recovery import retry_item
    try:
        return retry_item(db, case_id, item_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
    holder: str | None = Field(default=None, max_length=255)
    period_start: str = Field(default='', max_length=32)
    period_end: str = Field(default='', max_length=32)


class DuplicateDispositionRequest(_Contract):
    action: Literal['check', 'restore', 'ignore'] = 'check'
    expected_reading_revision: _Digest
    statement_id: _Digest | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    expected_decision_revision: _Digest | None = None
    reason: str = Field(default='', max_length=4096)


@router.post('/{evidence_file_id}/duplicate-disposition', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def duplicate_disposition(evidence_file_id: UUID, body: DuplicateDispositionRequest,
        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.pending_statement_duplicates import decide_duplicate_disposition
    try:
        return decide_duplicate_disposition(db, case_id=case_id, evidence_file_id=evidence_file_id,
            actor=actor_from_user(user), **body.model_dump())
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Statement duplicate decision failed')
        raise HTTPException(status_code=500, detail='The duplicate decision could not be confirmed. Reopen the statement to check its saved result.')


class NotPaymentStatementRequest(_Contract):
    action: Literal['restore', 'set_aside']
    statement_id: _Digest | None = None
    reason: str = Field(default='', max_length=4096)


@router.post('/{evidence_file_id}/not-payment-statement', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def not_payment_statement(evidence_file_id: UUID, body: NotPaymentStatementRequest,
        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Put a fund statement set aside as not a payment statement back for review, or set it aside again."""
    from services.financial.not_payment_statements import decide
    try:
        return decide(db, case_id=case_id, evidence_file_id=evidence_file_id, actor=actor_from_user(user),
                      **body.model_dump())
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Not-a-payment-statement decision failed')
        raise HTTPException(status_code=500, detail='The decision could not be confirmed. Reopen the statement to check it.')


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
                    **coverage_review(db, case_id=case_id, file_id=evidence_file_id, request={**body.model_dump(mode='json'),
                        'holder': body.holder if body.holder is not None else proposal['metadata'].get('holder', ''),
                        'account_type': proposal['metadata'].get('account_type') or ''}))
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
@router.post('/{evidence_file_id:uuid}/confirm-result')
def confirm_result(evidence_file_id: UUID, body: StatementImportRequest, case_id: UUID = Query(...),
                   db: Session = Depends(get_db)):
    from services.financial.statement_import_receipt import saved_receipt
    try:
        return saved_receipt(db, case_id=case_id, evidence_file_id=evidence_file_id, request=body)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/{evidence_file_id:uuid}/queue-import', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def queue_statement_import(evidence_file_id: UUID, body: StatementImportRequest, case_id: UUID = Query(...),
                           user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.standalone_import_jobs import queue_statement
    try:
        return queue_statement(db, case_id=case_id, evidence_file_id=evidence_file_id,
            request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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


@router.post('/sources/{source_id}/manual-payment', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def add_manual_statement_payment(source_id: UUID, body: ManualStatementPayment, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.manual_statement_payment import append_payment
    try:
        return append_payment(session_factory=sessionmaker(bind=db.get_bind()), case_id=case_id,
            source_id=source_id, request=body, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/sources/{source_id}/admit-ready-records', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def admit_ready_imported_records(source_id: UUID, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.imported_records import admit_ready_records
    try:
        return admit_ready_records(session_factory=sessionmaker(bind=db.get_bind()), case_id=case_id,
            source_id=source_id, actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Ready imported records could not be added')
        raise HTTPException(status_code=500, detail='The records could not be added. They remain retained; retry to check again.')


def _change_record(source_id, body, case_id, user, db, restore):
    from services.financial.record_withdrawal import change
    try:
        return change(session_factory=sessionmaker(bind=db.get_bind()), case_id=case_id, source_id=source_id,
            request=body, actor=actor_from_user(user), restore=restore)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Statement record withdrawal failed')
        raise HTTPException(status_code=500, detail='The row could not be changed. Nothing was changed; retry to check again.')


@router.post('/sources/{source_id}/withdraw-record', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def withdraw_statement_record(source_id: UUID, body: RecordWithdrawal, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Withdraw a row the investigator added or corrected (kept, reversible)."""
    return _change_record(source_id, body, case_id, user, db, restore=False)


@router.post('/sources/{source_id}/restore-record', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def restore_statement_record(source_id: UUID, body: RecordWithdrawal, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Restore a withdrawn row."""
    return _change_record(source_id, body, case_id, user, db, restore=True)


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


class FinancialSourceSelection(EvidenceSelectionRequest):
    include_other_formats: bool = False


class FinancialSourceChoice(EvidencePreparationRequest):
    evidence_file_id: UUID


class FinancialSourcesRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    files: list[FinancialSourceChoice] = Field(min_length=1, max_length=10000)


@router.post('/selection/resolve')
def resolve_selection(body: FinancialSourceSelection, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    try:
        return resolve_financial_selection(db, case_id=case_id, file_ids=body.file_ids, folder_ids=body.folder_ids,
            include_other_formats=body.include_other_formats)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/selection/include', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def include_sources(body: FinancialSourcesRequest, case_id: UUID = Query(...),
                    user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.evidence_intake import include_financial_sources
    try:
        result = include_financial_sources(db, case_id=case_id, selections=body.files, actor=actor_from_user(user))
        _record_send(db, case_id=case_id, user=user, how='include_other_formats',
                     file_ids=[f.evidence_file_id for f in body.files])
        return result
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        logger.exception('Financial source selection failed')
        raise HTTPException(status_code=500, detail='The selection could not be confirmed. Retry to check the same files; source evidence is retained.')


@router.post('/{evidence_file_id}/prepare-existing', dependencies=[
    Depends(case_access_dependency(lambda request, payload: ('case', 'edit'))),
    Depends(case_access_dependency(lambda request, payload: ('evidence', 'upload')))])
async def prepare_existing(evidence_file_id: UUID, body: EvidencePreparationRequest, case_id: UUID = Query(...),
                           user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        result = await prepare_existing_financial_file(db, case_id=case_id, evidence_file_id=evidence_file_id,
            expected_revision=body.expected_revision, actor=actor_from_user(user), resolve_path=_resolve_stored_path,
            process_files=process_db_files)
        await run_in_threadpool(_record_send, db, case_id=case_id, user=user, how='prepare_existing',
                                file_ids=[evidence_file_id])
        return result
    except PdfMappingError as exc:
        await run_in_threadpool(db.rollback)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        await run_in_threadpool(db.rollback)
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
        user_id = user.id  # read before the version's commit expires the user row (a load on the event loop after)
        def _create_version():
            version = create_statement_version(db, case_id=case_id, evidence_file_id=evidence_file_id,
                request_id=body.request_id, reading_mode=body.reading_mode,
                actor=actor_from_user(user), resolve_path=_resolve_stored_path)
            return version.id, version.engine_job_id, version.status
        # The database work runs in the thread pool; process_db_files does the same for its own.
        version_id, engine_job_id, version_status = await run_in_threadpool(_create_version)
        if engine_job_id and version_status in ('processing', 'processed'):
            return dict(case_id=str(case_id), evidence_file_id=str(version_id), job_id=engine_job_id)
        result = await process_db_files(db, case_id=case_id, file_ids=[version_id],
            force_reprocess=True, preparation_mode='pdf_review', requested_by_user_id=user_id)
        if len(result.get('job_ids', [])) != 1:
            raise PdfMappingError('The new version could not be queued. Retry this reprocessing request.', 409)
        return dict(case_id=str(case_id), evidence_file_id=str(version_id), job_id=result['job_ids'][0])
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        logger.exception('Statement reprocessing failed')
        raise HTTPException(status_code=500, detail='Reprocessing could not be confirmed. Previous readings are preserved; retry the same request.')

# Batches retain their own file/period list and reuse the single-statement writer.
from services.financial import import_batches


class CreateFinancialBatch(EvidenceSelectionRequest):
    request_id: UUID
    # Files already in an unfinished batch continue it unless this is set.
    start_new: bool = False


class FinancialBatchPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_ids: list[UUID] = Field(min_length=1, max_length=10000)


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
    request_id: UUID | None = None


@router.post('/batches/{batch_id}/currency', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def set_batch_statement_currency(batch_id: UUID, body: SelectedStatementCurrency, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return import_batches.set_selected_currency(db, case_id=case_id, batch_id=batch_id,
            selections=body.statements, currency=body.currency, actor=actor_from_user(user), request_id=body.request_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


from services.financial import layout_memory


class LayoutMemoryConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_id: UUID
    statement_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    field: Literal['holder', 'institution', 'currency']
    value: str = Field(min_length=1, max_length=128)
    key: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_id: UUID | None = None


class LayoutMemoryWithdrawal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=1, max_length=500)


@router.get('/batches/{batch_id}/layout-memory')
def batch_layout_memory_groups(batch_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Held general-reader periods grouped by layout, account and missing identity fact."""
    try:
        return layout_memory.memory_groups(db, case_id=case_id, batch_id=batch_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get('/layout-memory/confirmations')
def case_layout_memory(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    return layout_memory.case_confirmations(db, case_id=case_id)


@router.post('/layout-memory/confirm', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def confirm_layout_memory(body: LayoutMemoryConfirmation, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return layout_memory.confirm(db, case_id=case_id, file_id=body.file_id, statement_id=body.statement_id,
            field=body.field, value=body.value, expected_key=body.key, actor=actor_from_user(user), request_id=body.request_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/layout-memory/{confirmation_id}/withdraw', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def withdraw_layout_memory(confirmation_id: UUID, body: LayoutMemoryWithdrawal, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return layout_memory.withdraw(db, case_id=case_id, confirmation_id=confirmation_id, reason=body.reason,
            actor=actor_from_user(user))
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/batches', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit'))), Depends(case_access_dependency(lambda request,payload: ('evidence','upload')))])
def create_financial_batch(body: CreateFinancialBatch, case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        identifier=import_batches.create_batch(db,case_id=case_id,request_id=body.request_id,file_ids=body.file_ids,folder_ids=body.folder_ids,actor=actor_from_user(user),start_new=body.start_new)
        batch = db.get(import_batches.Batch, identifier)
        _record_send(db, case_id=case_id, user=user, how='batch', batch_id=identifier,
            file_ids=[f['source_id'] for f in (batch.files if batch is not None else [])] or body.file_ids,
            extra=dict(continued=identifier != body.request_id, folder_ids=[str(f) for f in body.folder_ids]))
        return dict(id=str(identifier),case_id=str(case_id),continued=identifier!=body.request_id)
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


@router.post('/batches/preview')
def preview_financial_batch(body: FinancialBatchPreview, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Before a batch starts: open batches holding these files, and files that are copies. Read only."""
    from services.financial.batch_selection_preview import selection_preview
    try:
        return selection_preview(db, case_id=case_id, file_ids=body.file_ids)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get('/review/queue')
def financial_review_queue(case_id: UUID = Query(...), file_id: list[UUID] = Query([]),
        limit: int | None = Query(None, ge=0, le=5000), offset: int = Query(0, ge=0),
        page_list: Literal['waiting', 'ready', 'filled', 'reader_fix', 'rechecking', 'copies', 'unreadable'] = Query('waiting'),
        issue: str | None = Query(None, max_length=64), fresh: bool | None = Query(None),
        db: Session = Depends(get_db)):
    """The case's statements that need a decision now, from stored readings. Read only; nothing is re-read.

    ``limit``/``offset``/``page_list``/``issue`` page the lists (``totals`` and
    ``page`` say how much there is). A paged read (``limit``) or ``fresh=0``
    may be answered from a queue built moments ago while the current one is
    built (``refreshing``); ``fresh=1``, and an unpaged read (the views that
    predate paging), wait for the current one.
    """
    from services.financial.review_queue import case_review_queue
    from services.financial.request_timing import stage
    with stage('review_queue'):
        return case_review_queue(db, case_id=case_id, file_ids=file_id, limit=limit, offset=offset,
                                 page_list=page_list, issue=issue,
                                 stale_ok=fresh is False or (fresh is None and limit is not None))


@router.get('/review/status')
def financial_review_status(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """The per-case status line (counts of the same queue)."""
    from services.financial.review_queue import case_status
    return case_status(db, case_id=case_id)


@router.post('/review/read-unread', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit'))), Depends(case_access_dependency(lambda request,payload: ('evidence','upload')))])
def financial_read_unread(case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Read the case's statement files that were never read or prepared (one explicit action)."""
    from services.financial.auto_read import read_unread
    try:
        result = read_unread(db, case_id=case_id, actor=actor_from_user(user))
        _record_send(db, case_id=case_id, user=user, how='read_unread',
                     extra=dict(result={k: v for k, v in (result or {}).items() if isinstance(v, (int, str, bool))}))
        return result
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


class QueueSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item_ids: list[UUID] = Field(min_length=1, max_length=500)
    request_id: UUID


@router.post('/review/save', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def save_from_review_queue(body: QueueSave, case_id: UUID = Query(...), user=Depends(get_current_db_user),
        db: Session = Depends(get_db)):
    """Save ready statements from the queue, across batches, with the batch save's admission checks."""
    from services.financial.queue_save import save_statements
    from services.financial.request_timing import stage
    try:
        with stage('review_queue_save'):
            return save_statements(db, case_id=case_id, item_ids=body.item_ids, actor=actor_from_user(user),
                                   request_id=body.request_id)
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


class QueueFill(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_ids: list[UUID] = Field(default_factory=list, max_length=10000)


@router.post('/review/fill', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def fill_from_review_queue(body: QueueFill, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Before a queue save: save the details the system filled with certainty (confirmed proposals) as System."""
    from services.financial.queue_save import fill_from_queue
    from services.financial.request_timing import stage
    with stage('review_queue_fill'):
        return fill_from_queue(db, case_id=case_id, file_ids=body.file_ids)


class ProposalGroupConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    group_id: str = Field(min_length=64, max_length=64)
    file_ids: list[UUID] = Field(default_factory=list, max_length=10000)


@router.post('/review/proposal-groups/confirm', dependencies=[Depends(case_access_dependency(lambda request, payload: ('case', 'edit')))])
def confirm_review_proposal_group(body: ProposalGroupConfirm, case_id: UUID = Query(...),
        user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Confirm one account's proposed value for all its waiting statements at once (fills empty fields only)."""
    from services.financial.review_queue import confirm_proposal_group
    try:
        return confirm_proposal_group(db, case_id=case_id, group_id=body.group_id, actor=actor_from_user(user),
                                      file_ids=body.file_ids)
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get('/review/save-result')
def review_queue_save_result(case_id: UUID = Query(...), operation_id: list[UUID] = Query([]),
        db: Session = Depends(get_db)):
    """Progress of a queue save: its import receipts added together."""
    from services.financial.queue_save import save_result
    return save_result(db, case_id=case_id, operation_ids=operation_id[:200])


@router.get('/review/cases')
def financial_review_cases(user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """Cases this user can view that hold statement batches. Counts load per case from /review/status."""
    from sqlalchemy import select, func
    from postgres.models.case import Case
    from postgres.models.financial_import_batches import FinancialImportBatch
    from services.case_service import check_case_access, CaseAccessDenied, CaseNotFound
    rows = db.execute(select(Case.id, Case.title, func.max(FinancialImportBatch.updated_at))
        .join(FinancialImportBatch, FinancialImportBatch.case_id == Case.id)
        .where(FinancialImportBatch.status != 'removed', Case.archived.is_not(True))
        .group_by(Case.id, Case.title).order_by(func.max(FinancialImportBatch.updated_at).desc()).limit(200)).all()
    cases = []
    for case_id, title, updated in rows:
        try:
            check_case_access(db, case_id, user, required_permission=('case', 'view'))
        except (CaseAccessDenied, CaseNotFound):
            continue
        cases.append(dict(case_id=str(case_id), title=title, last_batch_activity=updated.isoformat() if updated else None))
    return dict(cases=cases)


@router.get('/batches/list')
@cached_view('batches-list')
def list_financial_batches(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.batch_review_summary import statement_summary
    from sqlalchemy import select
    from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
    batches=list(db.scalars(select(FinancialImportBatch).where(FinancialImportBatch.case_id==case_id, FinancialImportBatch.status != 'removed').order_by(FinancialImportBatch.created_at.desc(), FinancialImportBatch.id.desc()).limit(100)))
    references = import_batches.available_batch_references(db, case_id, [f for b in batches for f in b.files])
    files_by_batch = {b.id: import_batches.project_batch_files(b.files, references) for b in batches}
    by_batch = {b.id: [] for b in batches}
    superseded = {}
    if by_batch:
        from services.financial.batch_import_history import project_individual_receipts
        from services.financial.batch_supersession import superseded_batches
        items = list(db.scalars(select(FinancialImportBatchItem).where(FinancialImportBatchItem.batch_id.in_(by_batch), FinancialImportBatchItem.status != 'removed')))
        superseded = superseded_batches(db, case_id, batches, items)
        for item in import_batches.project_list_items(db, case_id, project_individual_receipts(db, case_id, items)):
            by_batch[item.batch_id].append(item)
    def counts(batch):
        items = by_batch[batch.id]
        checks = sum(bool(i.summary.get('problem_count', 0)) for i in items if i.status in ('ready', 'attention'))
        ready = sum(import_batches.import_available(i) for i in items)
        complete = bool(items) and all(f['status'] == 'checked' for f in files_by_batch[batch.id]) and all(i.status in ('imported', 'skipped', 'assigned', 'duplicate_ignored', 'superseded_reading') for i in items)
        return dict(completed=complete, available_statements=ready, statements_with_checks=checks,
                    statement_summary=statement_summary(items))
    from services.activity_trail import batch_sources
    try:
        sources = batch_sources(db, case_id=case_id, batch_ids=[b.id for b in batches])
    except Exception:
        logger.exception('Batch send sources unavailable; the list is shown without them')
        sources = {}
        # Shown as it stands, not kept by the view cache: the next call reads the sources again.
        not_kept()
    return dict(case_id=str(case_id),batches=[dict(id=str(b.id),status=b.status,created_at=b.created_at.isoformat(),file_count=len(b.files), **counts(b),
        created_by=(b.actor or {}).get('name', ''), filenames=[f['filename'] for f in b.files[:3]],
        automatic=bool((b.actor or {}).get('auto_read')), sent_from=sources.get(str(b.id)),
        superseded=bool(superseded.get(b.id)),
        checked_files=sum(f['status'] == 'checked' for f in files_by_batch[b.id]),
        failed_files=sum(f['status'] == 'error' for f in files_by_batch[b.id])) for b in batches])


@router.get('/batches/{batch_id}')
def get_financial_batch(batch_id: UUID, case_id: UUID = Query(...), offset: int = Query(0,ge=0), limit: int = Query(100,ge=1,le=500),only_problems: bool = Query(False),review_group: str | None = Query(None),db: Session = Depends(get_db)):
    try:
        view = import_batches.batch_status(db,case_id=case_id,batch_id=batch_id,offset=offset,limit=limit,only_problems=only_problems,review_group=review_group)
        return {**view, 'added': _batch_added(db, case_id, batch_id)} if isinstance(view, dict) else view
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


@router.get('/batches/{batch_id}/operations/{request_id}')
def check_financial_import_operation(batch_id: UUID, request_id: UUID,
        case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.import_operations import check_operation
    try:
        return check_operation(db, case_id=case_id, batch_id=batch_id, request_id=request_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
def save_financial_batch_review(batch_id: UUID,item_id: UUID,body: SaveFinancialBatchReview,case_id: UUID = Query(...),db: Session = Depends(get_db),user=Depends(get_current_db_user)):
    try:
        return import_batches.save_review(db,case_id=case_id,batch_id=batch_id,item_id=item_id,request=body.request,expected_review_revision=body.expected_review_revision,actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback();raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


@router.post('/batches/{batch_id}/items/{item_id}/page-image-offer/accept', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def accept_financial_page_image_offer(batch_id: UUID, item_id: UUID, case_id: UUID = Query(...), offer_id: str = Query(...),
        db: Session = Depends(get_db),
        user=Depends(get_current_db_user)):
    """'Use this reading': the reading from the page images on offer, saved as the person's own review."""
    from services.financial import vision_reader
    try:
        return vision_reader.accept_offer(db, case_id=case_id, batch_id=batch_id, item_id=item_id, offer_id=offer_id, actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback();raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


@router.post('/batches/{batch_id}/items/{item_id}/page-image-offer/decline', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def decline_financial_page_image_offer(batch_id: UUID, item_id: UUID, case_id: UUID = Query(...), offer_id: str = Query(...),
        db: Session = Depends(get_db),
        user=Depends(get_current_db_user)):
    """'Keep mine': the offer is set aside; the person's work is not touched."""
    from services.financial import vision_reader
    try:
        return vision_reader.decline_offer(db, case_id=case_id, batch_id=batch_id, item_id=item_id, offer_id=offer_id, actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback();raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


class ConfirmFinancialBatchPage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_review_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.get('/batches/{batch_id}/items/{item_id}/page-proposals')
def financial_batch_page_proposals(batch_id: UUID, item_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial import page_row_proposals
    try:
        return page_row_proposals.read_item_page_proposals(db, case_id=case_id, batch_id=batch_id, item_id=item_id)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        db.rollback()


@router.post('/batches/{batch_id}/items/{item_id}/pages/{page_number}/confirm', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def confirm_financial_batch_page(batch_id: UUID, item_id: UUID, page_number: int, body: ConfirmFinancialBatchPage,
        case_id: UUID = Query(...), user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial import page_row_proposals
    try:
        return page_row_proposals.confirm_item_page(db, case_id=case_id, batch_id=batch_id, item_id=item_id,
            page_number=page_number, digest=body.digest, expected_review_revision=body.expected_review_revision,
            actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback(); raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
        if item.status == 'superseded_reading':
            raise PdfMappingError('This reading was replaced by a newer one. Return to the batch to open its current statements. Your earlier review remains in history.',409)
        # Opening one review may re-read that statement; other sources stay stored.
        item=import_batches.checked_batch_items(db,case_id,[item],reading='targets')[0]
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
                           direction: Literal["next", "previous"] = Query("next"), review_group: str | None = Query(None), db: Session=Depends(get_db)):
    try:
        return import_batches.next_problem(db, case_id=case_id, batch_id=batch_id, item_id=item_id, direction=direction, review_group=review_group)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get('/batches/{batch_id}/items/{item_id}/next-statement')
def next_financial_statement(batch_id: UUID, item_id: UUID, case_id: UUID = Query(...),
        direction: Literal['next', 'previous'] = Query('next'), review_group: str | None = Query(None), db: Session = Depends(get_db)):
    try:
        return import_batches.next_statement(db, case_id=case_id, batch_id=batch_id, item_id=item_id, direction=direction, review_group=review_group)
    except PdfMappingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post('/batches/{batch_id}/files/{source_id}/retry', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit'))),Depends(case_access_dependency(lambda request,payload: ('evidence','upload')))])
async def retry_financial_batch_file(batch_id: UUID,source_id: UUID,case_id: UUID=Query(...),db: Session=Depends(get_db)):
    try:
        from services.financial.reading_job_retry import retry_file_checked
        return await retry_file_checked(db,case_id=case_id,batch_id=batch_id,source_id=source_id)
    except PdfMappingError as exc:
        await run_in_threadpool(db.rollback);raise HTTPException(status_code=exc.status_code,detail=str(exc)) from exc


class ReadAfreshFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    batch_id: UUID
    source_id: UUID
    expected_revision: str = Field(min_length=1, max_length=64)


class ReadAfreshRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    files: list[ReadAfreshFile] = Field(min_length=1, max_length=1000)


@router.post('/review/read-afresh', dependencies=[
    Depends(case_access_dependency(lambda request,payload: ('case','edit'))),
    Depends(case_access_dependency(lambda request,payload: ('evidence','upload')))])
def read_retained_sources_afresh(body: ReadAfreshRequest, case_id: UUID=Query(...),
        user=Depends(get_current_db_user), db: Session=Depends(get_db)):
    """Explicitly read the listed retained PDFs afresh; each is verified as a single request would be."""
    return import_batches.recover_retained_sources(db, case_id=case_id,
        files=[file.model_dump() for file in body.files], actor=actor_from_user(user))


class CheckAgainFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    batch_id: UUID
    file_id: UUID


class CheckAgainRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    files: list[CheckAgainFile] = Field(min_length=1, max_length=2000)


@router.post('/review/check-again', dependencies=[Depends(case_access_dependency(lambda request,payload: ('case','edit')))])
def check_files_again(body: CheckAgainRequest, case_id: UUID=Query(...), db: Session=Depends(get_db)):
    """Prepare the listed files again from their saved readings with the current reader; reviews are kept."""
    return import_batches.refresh_files(db, case_id=case_id, files=[file.model_dump() for file in body.files])


@router.post('/batches/{batch_id}/files/{source_id}/recover-source', dependencies=[
    Depends(case_access_dependency(lambda request,payload: ('case','edit'))),
    Depends(case_access_dependency(lambda request,payload: ('evidence','upload')))])
def recover_retained_batch_source(batch_id: UUID, source_id: UUID, body: EvidencePreparationRequest,
        case_id: UUID=Query(...), user=Depends(get_current_db_user), db: Session=Depends(get_db)):
    try:
        return import_batches.recover_retained_source(db, case_id=case_id, batch_id=batch_id,
            source_id=source_id, expected_revision=body.expected_revision, actor=actor_from_user(user))
    except PdfMappingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
