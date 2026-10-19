"""Recover empty legacy imports without overwriting investigator corrections."""
from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from services.financial.pdf_candidates import PdfMappingError, _digest


def refresh_currency_conflict(document, proposal):
    """A reader default cannot reverse an investigator's denomination choice."""
    metadata = document.metadata_ or {}
    review = metadata.get('statement_details_review') or {}
    saved = review.get('currency')
    reading = proposal.get('currency')
    original = (metadata.get('statement_import_request') or {}).get('currency')
    changed = bool(saved and saved != original) or any(
        entry.get('before', {}).get('currency') != entry.get('after', {}).get('currency')
        for entry in metadata.get('statement_details_history', [])
        if entry.get('before', {}).get('currency') and entry.get('after', {}).get('currency'))
    if saved and reading and saved != reading and changed:
        return dict(saved_currency=saved, reading_currency=reading,
            message=f'The saved statement currency was corrected to {saved}, but this reading uses {reading}. '
                f'Check this reading in saved {saved} before replacing the import. Saved amounts and currency have not changed.')
    return None


def refresh_available(session, document, proposal):
    metadata = document.metadata_ or {}
    original, request = metadata.get('statement_import_original'), metadata.get('statement_import_request')
    if (document.status != 'admitted' or not original or not request or
            _digest(original) != metadata.get('statement_import_original_sha256') or
            _digest(request) != metadata.get('statement_import_request_sha256') or
            original.get('revision') == proposal['revision']):
        return False
    if session.scalar(select(FinancialTransaction.id).where(FinancialTransaction.source_document_id == document.id).limit(1)):
        return False
    review = metadata.get('statement_details_review')
    if review and _digest(review) != metadata.get('statement_details_review_sha256'):
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
    if proposal.get('reading_failure') or proposal.get('assignment_only') or proposal.get('document_review'):
        return False
    # A newer reading must produce actual payments or printed statement balances.
    # Merely having more extracted text must never count as a successful recovery.
    from services.financial.statement_import import StatementImportRequest, check_import_request
    try:
        refreshed = StatementImportRequest.model_validate(refresh_request(document, proposal))
        check_import_request(proposal, refreshed)
    except (ValueError, PdfMappingError):
        return False
    usable = refresh_payment_count(document, proposal)
    return usable > 0 or bool(proposal.get('can_import_balances'))


def refresh_payment_count(document, proposal):
    from services.financial.statement_import import StatementImportRequest
    from services.financial.import_issues import incomplete_records
    request = StatementImportRequest.model_validate(refresh_request(document, proposal))
    return sum(not row.excluded for row in request.rows) - len(incomplete_records(proposal, request))


def refresh_assessment(document, proposal):
    """Assess the exact replacement rows with the investigator's saved controls.

    A readable replacement is not permission to admit its payments. The final
    writer rechecks this same request; source-only balance observations remain
    distinct from payment admission and confirmed no activity.
    """
    from services.financial.statement_import import StatementImportRequest
    from services.financial.statement_admission import assess_admission
    request = StatementImportRequest.model_validate(refresh_request(document, proposal))
    return assess_admission(proposal, request), any(not row.excluded for row in request.rows)


def refresh_request(document, proposal):
    """Carry saved account details and page-cited balances into the new reading."""
    from services.financial.import_batches import initial_request
    from services.financial.statement_details import saved_details, saved_currency
    from services.financial.currency_correction import rescale_minor
    if conflict := refresh_currency_conflict(document, proposal):
        raise PdfMappingError(conflict['message'], 409)
    raw = initial_request(proposal)
    original_details = document.metadata_['statement_import_original']['metadata']
    for key, value in saved_details(document).items():
        if value != original_details.get(key, ''):
            raw[key] = value
    originals = {row['id']: row for row in proposal['rows']}
    for role, edit in document.metadata_.get('statement_details_review', {}).get('balances', {}).items():
        if role not in ('opening', 'closing'):
            continue
        # Do not duplicate the extracted control, and preserve an explicit clear.
        for row in raw['rows']:
            original = originals.get(row['id'])
            if original is None:
                continue
            if original['kind'] == 'balance' and original['fields'].get('description', '').lower() == role + ' balance':
                row['balance_minor'] = None
        if edit.get('amount_minor') is not None:
            amount = edit['amount_minor']
            prior_currency = saved_currency(document)
            if prior_currency and prior_currency != proposal['currency']:
                # A legacy denomination may be corrected by the new reading.
                # Preserve the printed number, not its old minor-unit integer.
                amount = rescale_minor(amount, prior_currency, proposal['currency'])
            raw['rows'].append(dict(id=f'manual:{role}-balance', excluded=True, manual_page=edit['page'],
                date='', description=f'{role.title()} Balance', counterparty='', amount_minor='0', direction=None,
                balance_minor=amount, reason='Preserved the investigator’s saved balance and source page.'))
    return raw


def refresh_legacy_import(*, session_factory, case_id, source_id, expected_revision, actor, resolve_path,
        currency=None, expected_reading_revision=None, compared_review_revision=None):
    from services.financial.statement_import import read_statement_import, confirm_statement_import, StatementImportRequest
    from services.financial.duplicate_decisions import duplicate_revision
    from services.financial.statement_details import saved_currency
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
            currency=currency or saved_currency(source), statement_id=source.metadata_.get('statement_import_statement_id'))
        if conflict := refresh_currency_conflict(source, proposal):
            raise PdfMappingError(conflict['message'], 409)
        if expected_reading_revision and proposal['revision'] != expected_reading_revision:
            raise PdfMappingError('The statement reading changed. Reload it before saving its payments.', 409)
        if compared_review_revision:
            saved = proposal.get('saved_review')
            if not saved or saved['review_revision'] != compared_review_revision:
                raise PdfMappingError('The saved draft changed. Compare its latest values before saving payments.', 409)
            if not refresh_available(session, source, {**proposal, 'saved_review': None}):
                raise PdfMappingError('Saved payment corrections need an individual source comparison. No payments were changed.', 409)
            # The explicit comparison replaces only the unfinished draft. Its
            # prior values remain in history even if the later import fails.
            from services.financial.statement_progress import save_progress
            from services.financial.statement_import import StatementReviewDraft
            proposal['saved_review'] = save_progress(session, case_id=case_id, evidence_file_id=source.evidence_file_id,
                request=StatementReviewDraft.model_validate(refresh_request(source, proposal)),
                expected_review_revision=compared_review_revision, actor=actor)
        if not refresh_available(session, source, proposal):
            raise PdfMappingError('This import has saved payment corrections or needs a source comparison. Its records have been kept.', 409)
        raw = refresh_request(source, proposal)
        raw.update(replaces_source_document_id=str(source.id), replacement_revision=expected_revision,
            details_reason='Updated statement reading replaces incomplete records. Previous reading retained in history.')
        file_id = source.evidence_file_id
    return confirm_statement_import(session_factory=session_factory, case_id=case_id, evidence_file_id=file_id,
        request=StatementImportRequest.model_validate(raw), actor=actor, resolve_path=resolve_path)
