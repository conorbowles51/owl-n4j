"""Recover empty legacy BBVA imports with the current recognised layout."""
from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from services.financial.pdf_candidates import PdfMappingError, _digest


def refresh_available(session, document, proposal):
    metadata = document.metadata_ or {}
    original, request = metadata.get('statement_import_original'), metadata.get('statement_import_request')
    if (document.status != 'admitted' or not original or not request or
            _digest(original) != metadata.get('statement_import_original_sha256') or
            _digest(request) != metadata.get('statement_import_request_sha256') or
            original.get('revision') == proposal['revision']):
        return False
    choice = next((choice for choice in proposal.get('statement_choices', []) if choice['id'] == proposal.get('statement_id')), {})
    if choice.get('layout_id') != 'bbva-mexico-cash-management':
        return False
    if session.scalar(select(FinancialTransaction.id).where(FinancialTransaction.source_document_id == document.id).limit(1)):
        return False
    if metadata.get('statement_details_review', {}).get('balances'):
        return False
    from services.financial.import_batches import initial_request
    initial = {row['id']: row for row in initial_request(original)['rows']}
    # Some legacy versions selected every unmatched line. That default alone is
    # not a manual correction; all other changed values must remain protected.
    for row in request['rows']:
        baseline = initial.get(row['id'])
        if baseline is None or any(value != baseline.get(key) for key, value in row.items()
                if key != 'excluded' and not (key in ('reason', 'manual_page') and not value)):
            return False
    if any(record.get('correction') for record in metadata.get('statement_incomplete_records', [])):
        return False
    return bool(proposal.get('can_import_balances')) and not proposal.get('reading_failure')


def refresh_legacy_import(*, session_factory, case_id, source_id, expected_revision, actor, resolve_path):
    from services.financial.statement_import import read_statement_import, confirm_statement_import, StatementImportRequest
    from services.financial.import_batches import initial_request
    from services.financial.duplicate_decisions import duplicate_revision
    from services.financial.statement_details import saved_details, saved_currency
    with session_factory() as session:
        source = session.scalar(select(FinancialSourceDocument).where(
            FinancialSourceDocument.id == source_id, FinancialSourceDocument.case_id == case_id))
        if source is None:
            raise PdfMappingError('Statement not found in this case.', 404)
        if source.status == 'superseded' and source.superseded_by_id:
            replacement = session.get(FinancialSourceDocument, source.superseded_by_id)
            request = (replacement.metadata_ or {}).get('statement_import_request', {}) if replacement else {}
            if (replacement and replacement.case_id == case_id and request.get('replaces_source_document_id') == str(source.id)
                    and request.get('replacement_revision') == expected_revision):
                # The original confirmation is idempotent, including a lost response.
                return confirm_statement_import(session_factory=session_factory, case_id=case_id,
                    evidence_file_id=source.evidence_file_id, request=StatementImportRequest.model_validate(request), actor=actor, resolve_path=resolve_path)
        if duplicate_revision(session, source) != expected_revision:
            raise PdfMappingError('This import changed. Reload the statement before updating it.', 409)
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=source.evidence_file_id,
            currency=saved_currency(source), statement_id=source.metadata_.get('statement_import_statement_id'))
        if not refresh_available(session, source, proposal):
            raise PdfMappingError('This import has saved payment corrections or needs a source comparison. Its records have been kept.', 409)
        raw = initial_request(proposal)
        original_details = source.metadata_['statement_import_original']['metadata']
        for key, value in saved_details(source).items():
            if value and value != original_details.get(key, ''):
                raw[key] = value
        raw.update(replaces_source_document_id=str(source.id), replacement_revision=expected_revision,
            details_reason='Updated BBVA statement reading replaces unmatched text previously saved as incomplete records.')
        file_id = source.evidence_file_id
    return confirm_statement_import(session_factory=session_factory, case_id=case_id, evidence_file_id=file_id,
        request=StatementImportRequest.model_validate(raw), actor=actor, resolve_path=resolve_path)
