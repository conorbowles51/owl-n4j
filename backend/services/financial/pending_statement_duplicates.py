"""Reversible per-period duplicate decisions before ledger admission.

No evidence, review, source or payment is removed. A case lock serializes the
choice of retained source with imports. Metadata equality nominates candidates;
matching actual financial readings (or source bytes) establishes a copy.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_import_overlap import scope, same_statement, comparison_sources

POLICY = 'pending-statement-duplicate-v1'
METADATA_KEY = 'financial_duplicate_dispositions'
MATCHED_FIELDS = ['bank', 'full_account_number', 'account_holder', 'period_start', 'period_end', 'currency', 'account_type']


def _initial(proposal):
    from services.financial.import_batches import initial_request
    return initial_request(proposal)


def _raw(proposal, request=None):
    return request if request is not None else (proposal.get('saved_review') or {}).get('request') or _initial(proposal)


def _review_shape(proposal, request):
    """Source addresses and request IDs differ across copies; user values do not."""
    originals = {row['id']: row for row in proposal.get('rows', [])}
    rows = []
    for row in request.get('rows', []):
        original = originals.get(row.get('id'), {})
        kind = original.get('kind', 'manual')
        value = {key: row.get(key) or None for key in (
            'date', 'date_values', 'date_unprinted', 'description', 'counterparty',
            'balance_minor', 'reason', 'counterparty_link', 'manual_page', 'counterparty_entity_id', 'counterparty_account_id',
            'source_page_number', 'source_row_id', 'manual_placement', 'source_order_anchor')}
        value.update(kind=kind, excluded=bool(row.get('excluded')))
        if kind not in ('balance', 'statement_total', 'total', 'header'):
            value.update(amount_minor=row.get('amount_minor') or '0', direction=row.get('direction'))
        rows.append(value)
    return dict(scope=scope({**request, 'account_type': proposal.get('metadata', {}).get('account_type') or ''}),
        rows=rows, notes={key: request.get(key) or None for key in (
            'details_reason', 'balance_exception_reason', 'coverage_review_reason', 'no_activity_confirmed')})


def review_signature(proposal, request=None):
    return _digest(dict(policy=POLICY, reading=proposal['revision'], review=_review_shape(proposal, _raw(proposal, request)),
        saved_review=_review_shape(proposal, proposal['saved_review']['request']) if (proposal.get('saved_review') or {}).get('request') else None))


def _financial_reading(proposal):
    rows = []
    useful = False
    for row in proposal.get('rows', []):
        fields = row.get('fields') or {}
        if row.get('kind') not in ('transaction', 'balance', 'statement_total', 'total', 'unresolved', 'unclassified'):
            continue
        value = {key: fields.get(key) for key in (
            'date', 'booking_date', 'value_date', 'date_basis', 'description', 'counterparty',
            'amount_minor', 'direction', 'balance', 'total_direction', 'total_scope', 'count',
            'printed_transaction_count', 'reference', 'bank_reference')}
        value.update(kind=row.get('kind'), excluded=bool(row.get('excluded')))
        rows.append(value)
        useful = useful or (row.get('kind') == 'transaction' and bool(fields.get('amount_minor'))
                            and fields.get('direction') in ('debit', 'credit'))
        useful = useful or (row.get('kind') == 'balance' and fields.get('balance') is not None)
    usable = bool(useful and not proposal.get('reading_failure') and not proposal.get('assignment_only')
        and not any(row.get('kind') in ('unresolved', 'unclassified') for row in proposal.get('rows', [])))
    return _digest(dict(rows=rows, convention=proposal.get('metadata', {}).get('balance_convention'))), usable


def _own_link(file, proposal, source_id=None):
    return dict(evidence_file_id=str(file.id), statement_id=proposal.get('statement_id'),
        source_document_id=source_id, filename=file.original_filename,
        page_number=min(proposal.get('statement_page_numbers') or proposal.get('page_numbers') or [1]))


def _stored(file, statement_id):
    return (file.metadata_ or {}).get(METADATA_KEY, {}).get(statement_id or '')


def _requires_review_comparison(proposal):
    recovery = proposal.get('review_recovery') or {}
    return bool(recovery.get('required') and not recovery.get('acknowledged'))


def _target_available(session, case_id, decision):
    retained = decision.get('retained') or {}
    try:
        file_id = UUID(retained['evidence_file_id'])
    except (KeyError, ValueError, TypeError):
        return False
    target = session.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id, EvidenceFile.case_id == case_id))
    if target is None or (target.metadata_ or {}).get('financial_file_visibility', {}).get('removed') or (target.metadata_ or {}).get('financial_import_removal'):
        return False
    source_id = retained.get('source_document_id')
    if source_id:
        source = session.get(FinancialSourceDocument, UUID(source_id))
        return bool(source and source.case_id == case_id and source.status == 'admitted'
                    and not (source.metadata_ or {}).get('financial_import_removal'))
    other = _stored(target, retained.get('statement_id'))
    if other and other.get('status') == 'ignored':
        return False
    if decision.get('retained_reading_revision'):
        from services.financial.statement_import import read_statement_import
        try:
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=target.id,
                statement_id=retained.get('statement_id'), currency=(decision.get('scope') or {}).get('currency'),
                _include_period_checks=False, _include_duplicate_disposition=False)
        except PdfMappingError:
            return False
        if proposal['revision'] != decision['retained_reading_revision'] or _requires_review_comparison(proposal):
            return False
    return True


def read_duplicate_disposition(session, file, proposal, request=None):
    """Cheap read projection; stale decisions cannot continue suppressing work."""
    previous = _stored(file, proposal.get('statement_id'))
    if not previous:
        return None
    result = deepcopy(previous)
    result.pop('history', None)
    valid = previous.get('signature') == review_signature(proposal, request)
    if previous.get('status') in ('ignored', 'restored'):
        from services.financial.pending_duplicate_projection import capture_projection_guard
        valid = valid and previous.get('projection_guard') == capture_projection_guard(session, file, proposal.get('statement_id'), previous)
    if previous.get('status') == 'ignored':
        valid = valid and not _requires_review_comparison(proposal) and _target_available(session, file.case_id, previous)
    result['current'] = valid
    if not valid:
        result.update(status='needs_comparison', label='Compare this statement',
            reason='The reading, saved review or retained source changed. Check these statements again.')
    return result


def _persist(file, proposal, request, decision, actor):
    from sqlalchemy.orm import object_session
    from services.financial.pending_duplicate_projection import capture_projection_guard
    previous = _stored(file, proposal.get('statement_id'))
    value = dict(policy=POLICY, reading_revision=proposal['revision'], signature=review_signature(proposal, request),
        scope=scope({**request, 'account_type': proposal.get('metadata', {}).get('account_type') or ''}),
        matched_fields=MATCHED_FIELDS if decision.get('retained') else [], **decision)
    value['projection_guard'] = capture_projection_guard(object_session(file), file, proposal.get('statement_id'), decision)
    revision = _digest(value)
    if previous and previous.get('revision') == revision:
        return {key: deepcopy(value) for key, value in previous.items() if key != 'history'} | {'current': True}
    value.update(revision=revision, at=datetime.now(timezone.utc).isoformat(),
        actor=dict(user_id=str(actor.user_id), name=actor.name) if actor else dict(name='System'))
    history = deepcopy((previous or {}).get('history', []))
    if previous:
        history.append({key: deepcopy(item) for key, item in previous.items() if key != 'history'})
    value['history'] = history
    metadata = deepcopy(file.metadata_ or {})
    metadata.setdefault(METADATA_KEY, {})[proposal.get('statement_id') or ''] = value
    file.metadata_ = metadata
    return {key: deepcopy(item) for key, item in value.items() if key != 'history'} | {'current': True}


def _candidate(session, case_id, entry, cache):
    file = session.get(EvidenceFile, UUID(entry['file_id']))
    if file is None or file.case_id != case_id:
        return None
    if entry.get('source_document_id'):
        source = session.get(FinancialSourceDocument, UUID(entry['source_document_id']))
        metadata = (source.metadata_ or {}) if source else {}
        proposal, request = metadata.get('statement_import_original'), metadata.get('statement_import_request')
        if not proposal or not request or source.status != 'admitted':
            return None
        if (_digest(proposal) != metadata.get('statement_import_original_sha256') or
                _digest(request) != metadata.get('statement_import_request_sha256')):
            return None
        return file, proposal, request
    from services.financial.statement_import import read_statement_import
    try:
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
            currency=entry['scope']['currency'], statement_id=entry.get('statement_id'),
            _cache=cache, _include_period_checks=False, _include_duplicate_disposition=False)
    except PdfMappingError:
        return None
    if _requires_review_comparison(proposal):
        return None
    # Batch drafts can precede the shared Save progress record.
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    drafts = list(session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == file.id,
        Item.statement_key == (entry.get('statement_id') or ''),
        Item.status.in_(('ready', 'attention', 'pending_import', 'duplicate_ignored')))))
    requests = [item.review_request for item in drafts if item.review_request]
    if requests and any(_review_shape(proposal, request) != _review_shape(proposal, requests[0]) for request in requests[1:]):
        return None
    request = requests[0] if requests else _raw(proposal)
    if request.get('expected_revision') != proposal['revision']:
        return None
    return file, proposal, request


def apply_duplicate_disposition(session, *, case_id, file, proposal, request=None, actor=None, sources=None):
    """Caller holds Case then EvidenceFile locks; flushes/commit belong to caller.

    Invoke after preparing all periods in a file, and immediately before import.
    Only a current ignored result removes a period from available imports.
    """
    request = _raw(proposal, request)
    previous = read_duplicate_disposition(session, file, proposal, request)
    if previous and previous['current'] and (previous['status'] == 'restored' or
            (previous['status'] == 'ignored' and previous.get('basis') == 'investigator_decision')):
        return previous
    own = scope({**request, 'account_type': proposal.get('metadata', {}).get('account_type') or ''})
    current = proposal.get('current_import') or {}
    if current.get('evidence_file_id') == str(file.id):
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=None,
            retained=_own_link(file, proposal, current.get('source_document_id')), reason='This statement already has a saved import.'), actor)
    if _requires_review_comparison(proposal):
        return _persist(file, proposal, request, dict(status='needs_comparison', label='Compare this statement', basis=None,
            retained=None, reason='Compare the earlier saved reviews with this reading before deciding whether it is a duplicate. Saved corrections remain available.'), actor)
    if not own or not own.get('full_reference') or not own.get('holder'):
        return _persist(file, proposal, request, dict(status='not_duplicate', label='No confirmed duplicate', basis=None,
            retained=None, reason='Complete bank, full account, holder, currency and exact dates are required.'), actor)
    sources = sources if sources is not None else comparison_sources(session, case_id)[0]
    candidates = [entry for entry in sources.get((own['identity'], own['currency']), [])
        if same_statement(own, entry.get('scope')) and not (entry['file_id'] == str(file.id)
            and (entry.get('statement_id') or '') == (proposal.get('statement_id') or ''))]
    # Explicit internal reread lineage is already governed by replacement rules.
    families = getattr(sources, 'families', {}) or {}
    root = families.get(str(file.id), str(file.id))
    candidates = [entry for entry in candidates if families.get(entry['file_id'], entry['file_id']) != root]
    if not candidates:
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=None,
            retained=_own_link(file, proposal), reason='No separate statement with the same full identity and period was found.'), actor)
    own_reading, own_usable = _financial_reading(proposal)
    own_shape = _review_shape(proposal, request)
    own_edited = own_shape != _review_shape(proposal, _initial(proposal))
    saved_request = (proposal.get('saved_review') or {}).get('request')
    conflicting_saved_review = bool(saved_request and _review_shape(proposal, saved_request) != own_shape)
    # Individual review and batch review are independent saved work surfaces.
    # An automatic check from either surface must preserve the other's edits.
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    own_drafts = session.scalars(select(Item.review_request).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == file.id,
        Item.statement_key == (proposal.get('statement_id') or ''),
        Item.status.notin_(('removed', 'superseded_reading')), Item.review_request.is_not(None)))
    conflicting_saved_review = conflicting_saved_review or any(
        _review_shape(proposal, draft) != own_shape for draft in own_drafts if draft)
    peers, conflicts = [], []
    cache = {}
    for entry in candidates:
        loaded = _candidate(session, case_id, entry, cache)
        if loaded is None:
            conflicts.append(entry)
            continue
        other_file, other_proposal, other_request = loaded
        # A corrected candidate identity must still match its current reading/review.
        other_scope = scope({**other_request, 'account_type': other_proposal.get('metadata', {}).get('account_type') or ''})
        if not same_statement(own, other_scope):
            continue
        fingerprint, usable = _financial_reading(other_proposal)
        same_bytes = file.sha256 == other_file.sha256
        same_reading = own_reading == fingerprint
        own_changes_preserved = not conflicting_saved_review and (not own_edited or own_shape == _review_shape(other_proposal, other_request))
        if (not own_changes_preserved or (not same_bytes and not (same_reading and own_usable and usable))
                or (same_bytes and own_usable and usable and not same_reading)):
            conflicts.append(entry)
            continue
        reviewed = bool((other_proposal.get('saved_review') or {}).get('request')) or bool(other_request.get('coverage_review_reason'))
        peers.append((entry, other_file, reviewed, 'identical_bytes' if same_bytes else 'identical_financial_reading', other_proposal['revision']))
    # Never hide a revised/conflicting copy merely because another copy matches.
    if request.get('coverage_review_reason', '').strip():
        conflicts = candidates
    if conflicts:
        first = sorted(conflicts, key=lambda item: (item['status'] != 'imported', item['file_id'], item.get('statement_id') or ''))[0]
        retained = dict(evidence_file_id=first['file_id'], statement_id=first.get('statement_id'),
            source_document_id=first.get('source_document_id'), filename=first['filename'], page_number=first.get('page_number', 1))
        return _persist(file, proposal, request, dict(status='needs_comparison', label='Compare this statement', basis=None,
            retained=retained, reason='The matching period contains different readings, saved edits or unavailable comparison evidence.'), actor)
    own_rank = (1, not bool(proposal.get('saved_review')), str(file.created_at), str(file.id), proposal.get('statement_id') or '')
    ranked = sorted(peers, key=lambda item: (item[0]['status'] != 'imported', not item[2], str(item[1].created_at), item[0]['file_id'], item[0].get('statement_id') or ''))
    if not ranked:
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=None,
            retained=_own_link(file, proposal), reason='No confirmed duplicate remained after comparing the current identities.'), actor)
    entry, other_file, reviewed, basis, retained_reading_revision = ranked[0]
    rank = (entry['status'] != 'imported', not reviewed, str(other_file.created_at), entry['file_id'], entry.get('statement_id') or '')
    if own_rank <= rank:
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=basis,
            retained=_own_link(file, proposal), reason='This is the retained source for matching copies of this period.'), actor)
    retained = dict(evidence_file_id=entry['file_id'], statement_id=entry.get('statement_id'),
        source_document_id=entry.get('source_document_id'), filename=entry['filename'], page_number=entry.get('page_number', 1))
    return _persist(file, proposal, request, dict(status='ignored', label='Duplicate - Ignored by system', basis=basis,
        retained=retained, retained_reading_revision=retained_reading_revision, reason='The full statement identity and financial reading match the retained source. Evidence and saved reviews remain available.'), actor)


def decide_duplicate_disposition(session, *, case_id, evidence_file_id, action, expected_reading_revision,
        statement_id=None, currency=None, expected_decision_revision=None, reason='', actor=None):
    if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
        raise PdfMappingError('Case not found.', 404)
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    from services.financial.statement_import import read_statement_import
    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
        statement_id=statement_id, currency=currency, _include_period_checks=False,
        _include_duplicate_disposition=False)
    if proposal['revision'] != expected_reading_revision:
        raise PdfMappingError('The statement reading changed. Reopen this period before comparing copies.', 409)
    if action == 'ignore':
        if proposal.get('current_import'):
            raise PdfMappingError('This statement already has an import. Review its saved records before excluding them.', 409)
        if _requires_review_comparison(proposal):
            raise PdfMappingError('Save your compared review before deciding to leave this copy unimported.', 409)
        request = _raw(proposal)
        from services.financial.statement_import_overlap import coverage_review
        review = coverage_review(session, case_id=case_id, file_id=file.id, request=request)
        candidates = [c for c in review['candidates'] if c.get('matching_statement')]
        if not candidates:
            raise PdfMappingError('No matching statement remains. Reopen this review to check its current status.', 409)
        retained = sorted(candidates, key=lambda c: (c['status'] != 'imported', c['file_id']))[0]
        link = dict(evidence_file_id=retained['file_id'], statement_id=retained.get('statement_id'),
            source_document_id=retained.get('source_document_id'), filename=retained['filename'],
            page_number=retained.get('page_number', 1))
        result = _persist(file, proposal, request, dict(status='ignored', label='Duplicate - Left unimported by investigator',
            basis='investigator_decision', retained=link,
            reason=reason.strip() or 'Investigator chose not to import this matching statement. Evidence and saved corrections are retained.'), actor)
    elif action == 'restore':
        previous = read_duplicate_disposition(session, file, proposal)
        history = (_stored(file, proposal.get('statement_id')) or {}).get('history', [])
        replayed_restore = bool(previous and previous['status'] == 'restored' and history
            and history[-1].get('status') == 'ignored' and history[-1].get('revision') == expected_decision_revision)
        if not previous or not previous.get('current') or (previous.get('revision') != expected_decision_revision and not replayed_restore):
            raise PdfMappingError('The duplicate decision changed. Reopen this statement before restoring it.', 409)
        if previous['status'] == 'restored':
            result = previous
        elif previous['status'] != 'ignored':
            raise PdfMappingError('Only an ignored duplicate can be restored to review.', 409)
        else:
            result = _persist(file, proposal, _raw(proposal), dict(status='restored', label='Restored for review',
                basis=previous.get('basis'), retained=previous.get('retained'),
                reason=reason.strip() or 'Restored by the investigator for comparison.'), actor)
    else:
        result = apply_duplicate_disposition(session, case_id=case_id, file=file, proposal=proposal, actor=actor)
    session.commit()
    return dict(case_id=str(case_id), evidence_file_id=str(file.id), statement_id=proposal.get('statement_id'),
        duplicate_disposition=result)


def ignored_receipt(case_id, file, decision):
    return dict(case_id=str(case_id), evidence_file_id=str(file.id), outcome='duplicate_ignored', ignored=True,
        applied=True, created=False, source_document_id=None, account_id=None,
        transaction_count=0, record_count=0, incomplete_count=0, issues=[], duplicate_disposition=decision)


def prepare_batch_dispositions(session, batch, file_id, *, cache=None):
    """Recheck only this file's exact matching periods, preserving saved imports.

    Preparation already holds the case lock. Comparing peers also handles a
    batch whose upload order differs from the stable retained-source ordering.
    """
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.statement_import import read_statement_import
    from services.financial.statement_import_overlap import summary_request
    cache = cache if cache is not None else {}
    items = list(session.scalars(select(Item).where(Item.batch_id == batch.id,
        Item.status.in_(('ready', 'attention', 'duplicate_ignored'))).order_by(Item.file_id, Item.statement_key)))
    scopes = [scope({**(item.review_request or summary_request(item.summary)),
        'account_type': item.summary.get('account_type', '')}) for item in items if item.file_id == file_id]
    for item in items:
        descriptor = scope({**(item.review_request or summary_request(item.summary)),
            'account_type': item.summary.get('account_type', '')})
        if item.file_id != file_id and not any(same_statement(descriptor, own) for own in scopes):
            continue
        file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == item.file_id,
            EvidenceFile.case_id == batch.case_id).with_for_update().execution_options(populate_existing=True))
        if file is None:
            continue
        try:
            proposal = read_statement_import(session, case_id=batch.case_id, evidence_file_id=file.id,
                currency=item.summary.get('currency') or None, statement_id=item.statement_key or None,
                _cache=cache, _include_period_checks=False, _include_duplicate_disposition=False)
        except PdfMappingError:
            continue  # Existing reading failure remains visible in the batch.
        decision = apply_duplicate_disposition(session, case_id=batch.case_id, file=file,
            proposal=proposal, request=item.review_request)
        item.summary = {**item.summary, 'duplicate_disposition': decision}
        if decision['status'] == 'ignored':
            item.status = 'duplicate_ignored'
            item.summary = {**item.summary, 'can_import': False, 'problems': [], 'problem_count': 0}
        elif item.status == 'duplicate_ignored':
            from services.financial.import_batches import assess
            state, summary = assess(proposal, item.review_request)
            item.status = state
            item.summary = {**item.summary, **summary, 'duplicate_disposition': decision}
        session.flush()
