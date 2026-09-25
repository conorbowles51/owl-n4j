"""Classify a completed reading without mistaking review failures for failed jobs.

This is a recovery decision, never an admission decision. A successful read may
still require reconciliation and a new read never discards saved investigator work.
"""
from decimal import Decimal, InvalidOperation

from services.financial.pdf_candidates import PdfMappingError


def retry_reference_problem(session, *, case_id, source_id, source, prepared=None):
    """A missing original/reset pointer is not a new reading request.

    Only an explicitly linked, case-owned retained version remains navigable.
    Filenames and account labels never substitute for a missing evidence id.
    """
    from uuid import UUID
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from services.financial.file_visibility import financial_file_visibility
    if source is None:
        from services.financial.evidence_intake import has_financial_reading
        metadata = (prepared.metadata_ or {}) if prepared else {}
        foreign = session.scalar(select(EvidenceFile.id).where(EvidenceFile.id == source_id,
            EvidenceFile.case_id != case_id))
        retained = bool(prepared and prepared.case_id == case_id and not foreign and metadata.get('statement_version_request')
            and str(source_id) in (metadata.get('statement_parent_evidence_id'), metadata.get('statement_root_evidence_id'))
            and not financial_file_visibility(prepared)['financial_removed']
            and not financial_file_visibility(prepared)['financial_imports_removed']
            and has_financial_reading(session, prepared))
        message = 'The original evidence is not available in this case. '
        message += ('Its explicitly linked saved reading is retained; open that review to inspect existing work. ' if retained else '')
        message += 'Restore the original in Evidence, or select the correct evidence file to start a new preparation. Saved payments and corrections were not changed.'
        return dict(message=message, review_file_id=str(prepared.id) if retained else None)
    for file in (source, prepared):
        reset = (file.metadata_ or {}).get('financial_import_removal') if file else None
        if not reset:
            continue
        try:
            identifier = UUID(str(reset.get('restart_file_id')))
        except (ValueError, TypeError):
            identifier = None
        restart = session.scalar(select(EvidenceFile).where(EvidenceFile.id == identifier,
            EvidenceFile.case_id == case_id)) if identifier else None
        if (restart is None or restart.sha256 != file.sha256 or not reset.get('id')
                or (restart.metadata_ or {}).get('financial_import_removal', {}).get('id') != reset['id']):
            return dict(message='The source recorded for restarting this removed import is unavailable or no longer matches this evidence. Restore that source in Evidence, or select the correct evidence file for a new preparation. The previous removal and all saved history remain unchanged.',
                review_file_id=None)
    return None


def persist_unavailable_retry(session, *, batch, files, target, problem, commit=True):
    from datetime import datetime, timezone
    from uuid import uuid4
    previous = target.get('recovery') or {}
    receipt = dict(attempt_id=previous.get('attempt_id') or str(uuid4()),
        action='source_unavailable', stage='source_unavailable', message=problem['message'],
        review_file_id=problem['review_file_id'], reading_file_id=problem['review_file_id'],
        fresh_reading=False, updated_at=datetime.now(timezone.utc).isoformat())
    target.update(status='error', error=problem['message'], recovery=receipt)
    batch.files = files
    session.commit() if commit else session.flush()
    return dict(queued=False, status='error', **receipt)


def missing_reading_reason(proposal):
    if proposal.get('reading_failure'):
        return proposal['reading_failure']
    if proposal.get('document_review') or proposal.get('assignment_only') or not proposal.get('currency'):
        return None
    rows = proposal.get('rows') or []
    payments = [row for row in rows if row.get('kind') in ('transaction', 'unresolved')]
    if payments:
        return None
    # Explicit printed nonzero activity with no payments is a reading omission.
    # Equal/unknown balances or an absent amount are not evidence of inactivity.
    for row in rows:
        if row.get('kind') != 'statement_total':
            continue
        fields = row.get('fields') or {}
        for key in ('printed_transaction_count', 'amount_minor', 'balance'):
            value = fields.get(key)
            try:
                amount = Decimal(str(value)) if value is not None else None
                if amount is not None and amount.is_finite() and amount != 0:
                    return 'The printed statement reports activity, but this reading found no payments. A new reading is needed before reconciliation.'
            except InvalidOperation:
                continue
    return None


def inspect_completed_reading(session, *, case_id, file, currency=None, _continue=None):
    from services.financial.evidence_intake import has_financial_reading
    from services.financial.statement_import import read_statement_import
    if not has_financial_reading(session, file):
        return dict(action='read_again', stage='reading_missing',
            message='The completed file has no usable saved text and tables. Prepare a new reading; previous payments and reviews remain unchanged.')
    try:
        cache = {}
        first = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
            currency=currency, _cache=cache)
        choices = first.get('statement_choices') or []
        proposals = []
        for choice in choices:
            if _continue is not None and not _continue():
                return None
            proposals.append(read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
                currency=currency, statement_id=choice['id'], _cache=cache))
        proposals = proposals or [first]
    except PdfMappingError as error:
        return dict(action='review_required', stage='statement_review', message=str(error), review_available=False)
    reasons = [reason for proposal in proposals if (reason := missing_reading_reason(proposal))]
    if reasons:
        return dict(action='read_again', stage='reading_incomplete', message=reasons[0])
    return dict(action='review_required', stage='statement_review', review_available=True,
        message='The file has been read. Open its statement review to resolve the current values or reconciliation checks; retrying the same reading will not change them.')


def reader_inventory(proposals):
    """Retain the observed reader family/revision for selective future recovery."""
    from services.financial.statement_import import VERSION
    result = {}
    for proposal in proposals:
        choices = proposal.get('statement_choices') or []
        selected = next((choice for choice in choices if choice['id'] == proposal.get('statement_id')), None)
        name = selected.get('layout_id') if selected else None
        result[name or 'generic-statement'] = VERSION
    return result
