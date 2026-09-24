"""Append an investigator-read payment without reimporting the saved statement."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from postgres.models.case import Case
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_import import ImportRow
from services.financial.statement_details import _load, _view


class ManualStatementPayment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    row: ImportRow


def append_payment(*, session_factory, case_id, source_id, request, actor):
    from services.financial.runs import ingestion_run
    from services.financial.reconcile import reconcile_period
    row = request.row
    if row.excluded or row.date_unprinted or row.date_values or not row.description.strip():
        raise PdfMappingError('Enter the printed date, description, amount and direction for this payment.', 422)
    if row.id != 'manual:' + str(request.request_id):
        raise PdfMappingError('The manual payment request does not match its draft.', 422)
    fingerprint = _digest(request.model_dump(mode='json'))
    # Validate scope before creating even an audit run for this operation.
    with session_factory() as session:
        _load(session, case_id, source_id)
    with ingestion_run(case_id=case_id, actor=SimpleNamespace(id=actor.user_id, email=actor.email),
            session_factory=session_factory, config=dict(operation='append_statement_payment', source_document_id=str(source_id))) as run:
        with session_factory() as session:
            session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
            document, period, account = _load(session, case_id, source_id, lock=True)
            metadata = deepcopy(document.metadata_)
            additions = metadata.setdefault('statement_manual_additions', {})
            prior = additions.get(str(request.request_id))
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise PdfMappingError('This payment was already saved with different values. Open it to make a correction.', 409)
                retained = next((item for item in metadata.get('statement_incomplete_records', []) if item['id'] == row.id), {})
                transaction_id = retained.get('resolved_transaction_id') or prior.get('transaction_id')
                return dict(transaction_id=transaction_id, created=False, pending_reconciliation=not bool(transaction_id))
            view = _view(document, period, account)
            if view['revision'] != request.expected_revision:
                raise PdfMappingError('The statement details changed. Reload the saved account details before adding this payment; your draft is retained.', 409)
            if row.manual_page not in view['pages']:
                raise PdfMappingError('Choose a PDF page belonging to this statement.', 422)
            if not view['currency']:
                raise PdfMappingError('Set this statement’s currency before adding a payment.', 422)
            original = dict(id=row.id, page_number=row.manual_page, kind='manual_entry', fields={}, source_cells=[])
            retained = dict(id=row.id, fields=row.model_dump(mode='json'), original=original,
                missing_fields=[], version=0, correction_currency=view['currency'])
            metadata.setdefault('statement_incomplete_records', []).append(retained)
            additions[str(request.request_id)] = dict(fingerprint=fingerprint, transaction_id=None,
                row=row.model_dump(mode='json'), currency=view['currency'], actor=str(actor.user_id),
                recorded_at=datetime.now(timezone.utc).isoformat())
            from services.financial.statement_currency_edit import complete_currency_records
            pending_before = sum(not item.get('resolved_transaction_id') for item in metadata['statement_incomplete_records'])
            admission = complete_currency_records(session, document=document, period=period, metadata=metadata,
                currency=view['currency'], actor=actor) if period else None
            transaction_id = retained.get('resolved_transaction_id')
            additions[str(request.request_id)]['transaction_id'] = transaction_id
            document.metadata_ = metadata
            if period:
                reconcile_period(session, period)
                if admission and admission['can_import']:
                    from services.financial.account_history import record_admission_snapshot
                    record_admission_snapshot(session, document, period)
            session.commit()
            admitted = pending_before - sum(not item.get('resolved_transaction_id') for item in metadata['statement_incomplete_records'])
            if admitted: run.transaction_admitted(admitted)
            return dict(transaction_id=transaction_id, created=bool(transaction_id), pending_reconciliation=not bool(transaction_id),
                blockers=(admission or {}).get('blockers', []))
