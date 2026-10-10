"""Withdraw, or restore, a row the investigator entered on a saved statement.

A row the investigator added by hand, or a printed row she corrected, can be
withdrawn when it turns out to be wrong (for example a re-entry of a charge
that is already on the statement). Nothing is deleted:

* a held row (not yet in Transactions) keeps every value; it is marked
  ``withdrawn`` with who, when and why, and every change is appended to its
  ``withdrawal_history``. A withdrawn added row is left out of the statement;
  a withdrawn correction leaves the printed row on its original reading. The
  statement's retained records are then checked again with the ordinary
  held-record rule (``complete_currency_records``), in the same commit, so a
  correct row that was held because of the withdrawn one can enter;
* a row already in Transactions is set aside through the adjudication chain
  (``quarantine_case_row``), and restored by releasing it.

Restoring reverses either step and is recorded the same way.
"""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument
from services.financial.pdf_candidates import PdfMappingError

WITHDRAW_REASON = 'Withdrawn by the investigator.'


class RecordWithdrawal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    record_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=0)
    reason: str = Field(default='', max_length=2000)


def entered_by_investigator(record):
    """A manual addition, or a printed row that carries a correction."""
    return record['original'].get('kind') == 'manual_entry' or bool(record.get('correction'))


def is_open(record):
    """Still to deal with: not in Transactions and not a withdrawn addition."""
    return not record.get('resolved_transaction_id') and not (
        record.get('withdrawn') and record['original'].get('kind') == 'manual_entry')


def change(*, session_factory, case_id, source_id, request, actor, restore=False):
    from services.financial.runs import ingestion_run
    from services.financial.reconcile import reconcile_period
    with session_factory() as session:
        exists = session.scalar(select(FinancialSourceDocument.id).where(FinancialSourceDocument.id == source_id,
            FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted'))
        if exists is None:
            raise PdfMappingError('This imported statement is no longer available.', 404)
    operation = 'restore_statement_record' if restore else 'withdraw_statement_record'
    with ingestion_run(case_id=case_id, actor=SimpleNamespace(id=actor.user_id, email=actor.email),
            session_factory=session_factory, config=dict(operation=operation, source_document_id=str(source_id),
                record_id=request.record_id)) as run:
        with session_factory() as session:
            from postgres.models.case import Case
            session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
            from services.financial.statement_details import _load
            document, period, _account = _load(session, case_id, source_id, lock=True)
            metadata = deepcopy(document.metadata_)
            record = next((item for item in metadata.get('statement_incomplete_records', [])
                           if item['id'] == request.record_id), None)
            if record is None:
                raise PdfMappingError('The record was not found on this statement.', 404)
            if not entered_by_investigator(record):
                raise PdfMappingError('Only a row you added or corrected can be withdrawn. '
                                      'Correct this printed row instead.', 422)
            reason = request.reason.strip() or WITHDRAW_REASON
            if record.get('resolved_transaction_id'):
                session.rollback()
                return _adjudicate(session, case_id, record, actor, reason, restore)
            if bool(record.get('withdrawn')) != restore:
                # Already in the requested state: a replay changes nothing.
                return _result(record, metadata, admitted=0, changed=False)
            if record.get('version', 0) != request.version:
                raise PdfMappingError('Another investigator changed this record. Reload it before withdrawing it.', 409)
            entry = dict(action='restored' if restore else 'withdrawn', by=str(actor.user_id), name=actor.name,
                         email=actor.email, at=datetime.now(timezone.utc).isoformat(), reason=reason)
            record.setdefault('withdrawal_history', []).append(entry)
            if restore:
                record.pop('withdrawn', None)
                if record['original'].get('kind') != 'manual_entry':
                    record['missing_fields'] = []
            else:
                record['withdrawn'] = entry
            record['version'] = record.get('version', 0) + 1
            pending_before = sum(not item.get('resolved_transaction_id') for item in metadata['statement_incomplete_records'])
            admission = None
            if period:
                from services.financial.statement_currency_edit import complete_currency_records
                admission = complete_currency_records(session, document=document, period=period,
                    metadata=metadata, currency=period.currency, actor=actor)
            document.metadata_ = metadata
            if period:
                if admission is None:
                    from services.financial.saved_statement_admission import refresh_saved_assessment
                    admission = refresh_saved_assessment(session, document, period)
                    metadata = document.metadata_
                reconcile_period(session, period)
                if admission and admission['can_import']:
                    from services.financial.account_history import record_admission_snapshot
                    record_admission_snapshot(session, document, period)
            session.commit()
            admitted = pending_before - sum(not item.get('resolved_transaction_id') for item in metadata['statement_incomplete_records'])
            if admitted: run.transaction_admitted(admitted)
            return _result(record, metadata, admitted=admitted, changed=True, admission=admission)


def _result(record, metadata, *, admitted, changed, admission=None):
    admission = admission or metadata.get('statement_admission') or {}
    return dict(record_id=record['id'], withdrawn=bool(record.get('withdrawn')), changed=changed,
        version=record.get('version', 0), admitted=admitted, statement_status=admission.get('status'),
        statement_reconciles=bool(admission.get('can_import')),
        held=[dict(id=item['id'], reason=item['hold_reason']) for item in metadata.get('statement_incomplete_records', [])
              if not item.get('resolved_transaction_id') and item.get('hold_reason')])


def _adjudicate(session, case_id, record, actor, reason, restore):
    """A row already in Transactions: set it aside (or let it back in) through
    the adjudication chain, which keeps the row and records the decision."""
    from services.financial.quarantine_row import quarantine_case_row, release_case_row
    write = release_case_row if restore else quarantine_case_row
    result = write(session, case_id=case_id, transaction_id=UUID(record['resolved_transaction_id']),
                   actor=actor, reason=reason)
    outcome = getattr(result.outcome, 'value', result.outcome)
    if outcome in ('refused', 'write_failed', 'not_found'):
        raise PdfMappingError(result.reason or 'The row could not be changed. Nothing was changed.', 409)
    return dict(record_id=record['id'], transaction_id=record['resolved_transaction_id'],
                withdrawn=not restore, changed=outcome not in ('unchanged',), set_aside=outcome,
                adjudication_id=result.adjudication_id, admitted=0, held=[])
