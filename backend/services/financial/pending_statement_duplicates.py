"""Reversible per-period duplicate decisions before ledger admission.

No evidence, review, source or payment is removed. A case lock serializes the
choice of retained source with imports. Metadata equality nominates candidates;
matching actual financial readings (or source bytes) establishes a copy.
"""
import os
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_import_overlap import scope, same_statement, same_printed_period, comparison_sources

POLICY = 'pending-statement-duplicate-v1'
# A copy is also another file printing the same account reference, currency and
# dates with the same payments, whatever product type or bank wording its reader
# gave it (r15-hold-gaps: such a copy was saved again into another ledger
# account). Off: only the bank identity and product type nominate copies.
PRINTED_FACTS_COPIES = os.environ.get('LOUPE_FINANCIAL_PRINTED_FACTS_COPIES', '1') != '0'
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
    descriptor = scope({**request, 'account_type': proposal.get('metadata', {}).get('account_type') or ''})
    if request.get('period_start_unprinted'):
        descriptor = {key: request.get(key) for key in ('period_start_unprinted', 'period_start', 'period_end',
            'currency', 'holder', 'institution', 'account_number')}
    return dict(scope=descriptor,
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


def statement_content(proposal):
    """The money of one reading, however its text was read.

    Two productions of one printed statement (another scan, another producer's
    text layer, a reprint inside the same file) can read descriptions,
    references or the holder differently. Their money cannot differ: every
    included payment (amount, direction, date) and every printed balance must
    be equal. Returns (fingerprint, number of payments).
    """
    payments = sorted((str(row['fields'].get('amount_minor') or ''), row['fields'].get('direction') or '',
        row['fields'].get('date') or row['fields'].get('booking_date') or '')
        for row in proposal.get('rows', []) if row.get('kind') == 'transaction' and not row.get('excluded'))
    balances = sorted(str(row['fields']['balance']) for row in proposal.get('rows', [])
        if row.get('kind') == 'balance' and row['fields'].get('balance') is not None)
    return _digest(dict(payments=payments, balances=balances,
        convention=proposal.get('metadata', {}).get('balance_convention'))), len(payments)


def _own_link(file, proposal, source_id=None):
    return dict(evidence_file_id=str(file.id), statement_id=proposal.get('statement_id'),
        source_document_id=source_id, filename=file.original_filename,
        page_number=min(proposal.get('statement_page_numbers') or proposal.get('page_numbers') or [1]))


def _stored(file, statement_id):
    return (file.metadata_ or {}).get(METADATA_KEY, {}).get(statement_id or '')


def _requires_review_comparison(proposal):
    recovery = proposal.get('review_recovery') or {}
    return bool(recovery.get('required') and not recovery.get('acknowledged'))


def _target_available(session, case_id, decision, cache=None):
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
    # A reprint inside one file is a copy of its first printing whatever that
    # printing's own outcome; its money reaches the ledger once either way.
    if other and other.get('status') == 'ignored' and not decision.get('printed_copy'):
        return False
    if decision.get('retained_reading_revision'):
        from services.financial.statement_import import read_statement_import
        try:
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=target.id,
                statement_id=retained.get('statement_id'), currency=(decision.get('scope') or {}).get('currency'),
                _cache=cache, _include_period_checks=False, _include_duplicate_disposition=False)
        except PdfMappingError:
            return False
        if proposal['revision'] != decision['retained_reading_revision'] or _requires_review_comparison(proposal):
            return False
    return True


def read_duplicate_disposition(session, file, proposal, request=None, *, cache=None):
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
        valid = valid and not _requires_review_comparison(proposal) and _target_available(session, file.case_id, previous, cache)
    result['current'] = valid
    if not valid:
        result.update(status='needs_comparison', label='Compare this statement',
            reason='The reading, saved review or retained source changed. Check these statements again.')
    return result


def _persist(file, proposal, request, decision, actor, matched_fields=None):
    from sqlalchemy.orm import object_session
    from services.financial.pending_duplicate_projection import capture_projection_guard
    previous = _stored(file, proposal.get('statement_id'))
    if matched_fields is None:
        source = 'source_pages' if decision.get('basis') == 'identical_pages' else 'source_sha256'
        matched_fields = (([source, 'source_section', 'reviewed_values'] if request.get('period_start_unprinted') else [source, 'period_start', 'period_end', 'currency'])
            if decision.get('basis') in ('identical_bytes', 'identical_pages') else MATCHED_FIELDS) if decision.get('retained') else []
    value = dict(policy=POLICY, reading_revision=proposal['revision'], signature=review_signature(proposal, request),
        scope=scope({**request, 'account_type': proposal.get('metadata', {}).get('account_type') or ''}),
        matched_fields=matched_fields, **decision)
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


def _printed_copy_fields(own, other):
    """What two copies of one printed statement share besides their money."""
    fields = ['account_reference', 'period_start', 'period_end', 'currency', 'account_type', 'payments_and_balances']
    if own.get('identity') == (other or {}).get('identity'):
        fields.insert(0, 'bank')
    if own.get('holder') and own['holder'] == (other or {}).get('holder'):
        fields.insert(2, 'account_holder')
    return fields


def _same_source_section(left, right):
    for key in ('statement_row_addresses', 'statement_source_regions'):
        if (left.get(key) or right.get(key)) and left.get(key) != right.get(key):
            return False
    def addresses(proposal):
        pages = proposal.get('statement_page_numbers') or proposal.get('page_numbers')
        if pages:
            return tuple(sorted(set(pages)))
        return tuple(sorted({row['page_number'] for row in proposal.get('rows', []) if row.get('page_number')}))
    own, other = addresses(left), addresses(right)
    return bool(own and own == other)


def _same_content_scope(left, right):
    """Masked identity is comparable only alongside verified identical bytes."""
    return bool(left and right and all(left.get(key) == right.get(key) for key in (
        'identity', 'account_reference', 'holder', 'currency', 'start', 'end', 'account_type')))


def _section_pages(proposal):
    """The pages this statement is read from, as its file's statement list records them."""
    choice = next((c for c in proposal.get('statement_choices') or [] if c.get('id') == proposal.get('statement_id')), None)
    pages = (choice or {}).get('page_numbers') or proposal.get('statement_page_numbers') or proposal.get('page_numbers')
    return frozenset(page for page in pages or [] if isinstance(page, int))


def _shares_pages(proposal, pages):
    """Another statement of the same reading is printed on one of these pages."""
    return any(c.get('id') != proposal.get('statement_id') and pages & set(c.get('page_numbers') or [])
               for c in proposal.get('statement_choices') or [])


def _page_copy(left, right):
    """Two readings of the same pages of one document (bytes or rendered pages identical).

    The same pages are the same printed statement whatever either reader made
    of them. Where a page also carries another statement, the pages alone do
    not say which statement is which; then both readings must place it in the
    same regions of those pages.
    """
    pages = _section_pages(left)
    if not pages or pages != _section_pages(right):
        return False
    if _shares_pages(left, pages) or _shares_pages(right, pages):
        return _same_source_section(left, right)
    return True


def _money_conflicts(left, right):
    """Two readings whose money cannot both be right: different payments, or a printed
    balance read in both with different values. One reading capturing more printed
    balance rows than the other is not a conflict."""
    def payments(proposal):
        return sorted((str(row['fields'].get('amount_minor') or ''), row['fields'].get('direction') or '',
            row['fields'].get('date') or row['fields'].get('booking_date') or '')
            for row in proposal.get('rows', []) if row.get('kind') == 'transaction' and not row.get('excluded'))
    def balances(proposal):
        return Counter(str(row['fields']['balance']) for row in proposal.get('rows', [])
                       if row.get('kind') == 'balance' and row['fields'].get('balance') is not None)
    if payments(left) != payments(right):
        return True
    if (left.get('metadata') or {}).get('balance_convention') != (right.get('metadata') or {}).get('balance_convention'):
        return True
    a, b = balances(left), balances(right)
    return not (a <= b or b <= a)


def _printed_key(descriptor):
    """The printed account reference, currency and dates of a statement scope, without the
    reader's bank wording or product type; None when no reference with digits was read."""
    from services.financial.statement_import_overlap import _printed_reference
    reference = _printed_reference(descriptor)
    if not descriptor or not reference or not any(ch.isdigit() for ch in reference):
        return None
    return (reference, descriptor.get('currency'), descriptor.get('start'), descriptor.get('end'))


def _edited(proposal, request):
    """An investigator's work on this reading: a saved review or values changed from the reading."""
    return bool((proposal.get('saved_review') or {}).get('request')) or \
        _review_shape(proposal, request) != _review_shape(proposal, _initial(proposal))


def _proved(proposal, request):
    """The reading proves this statement by itself: saved, or ready to save without a check."""
    if (proposal.get('current_import') or {}).get('source_document_id'):
        return True
    from services.financial.import_batches import assess
    try:
        state, _ = assess({**proposal, 'duplicate_disposition': None}, request)
    except Exception:  # a reading that cannot even be assessed proves nothing
        return False
    return state == 'ready'


def _unprinted_start_disposition(session, case_id, file, proposal, request, actor):
    """Unknown dates cannot establish equality; identical bytes and sections can.

    Consult admitted receipts under the caller's case lock, including periods
    omitted by date-based coverage. Never merge neighbouring sections or hide
    a corrected reading. Pending copies are checked again at admission.
    """
    # The same bytes, or the same rendered pages (page_identity): one document.
    from services.financial.page_identity import same_document_files
    peers = same_document_files(session, case_id, file)
    if not peers:
        return None
    documents = session.scalars(select(FinancialSourceDocument).join(
        EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id, EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_([UUID(peer) for peer in peers]),
        FinancialSourceDocument.status == 'admitted'))
    matches = []
    for document in documents:
        metadata = document.metadata_ or {}
        if metadata.get('financial_import_removal'):
            continue
        original = metadata.get('statement_import_original') or {}
        if not _same_source_section(proposal, original):
            continue
        entry = dict(file_id=str(document.evidence_file_id), source_document_id=str(document.id))
        loaded = _candidate(session, case_id, entry, {})
        if loaded is None:
            raise PdfMappingError('A saved copy of this source section could not be verified. Open its saved records before importing this copy.', 409)
        peer, original, saved_request = loaded
        same_values = _review_shape(proposal, request) == _review_shape(original, saved_request)
        # scope() intentionally excludes incomplete periods. Compare identity
        # explicitly so two unknown scopes never imply account equality.
        same_identity = all(request.get(key) == saved_request.get(key) for key in (
            'currency', 'holder', 'account_number', 'institution'))
        matches.append((document, peer, original, same_values and same_identity))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[3], str(item[0].id)))
    document, peer, original, identical = matches[0]
    return _persist(file, proposal, request, dict(
        status='ignored' if identical else 'needs_comparison',
        label='Duplicate - Ignored by system' if identical else 'Compare this statement',
        basis=peers.get(str(peer.id), 'identical_bytes'), retained=_own_link(peer, original, str(document.id)),
        retained_reading_revision=original['revision'],
        reason=('These identical source pages already have the same saved review. No additional payments are needed.'
                if identical else 'These source pages already have saved payments with different review values. Open the saved records to compare or correct them before importing this copy.')), actor)


def apply_duplicate_disposition(session, *, case_id, file, proposal, request=None, actor=None, sources=None):
    """Caller holds Case then EvidenceFile locks; flushes/commit belong to caller.

    Invoke after preparing all periods in a file, and immediately before import.
    Only a current ignored result removes a period from available imports.
    """
    request = _raw(proposal, request)
    previous = read_duplicate_disposition(session, file, proposal, request)
    if request.get('period_start_unprinted'):
        partial = _unprinted_start_disposition(session, case_id, file, proposal, request, actor)
        if partial is not None:
            return partial
    if previous and previous['current'] and (previous['status'] == 'restored' or
            (previous['status'] == 'ignored' and previous.get('basis') == 'investigator_decision')):
        return previous
    if previous and previous['current'] and previous['status'] == 'ignored':
        # A held copy set aside because the saved ledger of its account and period agrees with it
        # (saved_copies): kept while that still holds; otherwise compared again below.
        from services.financial.saved_copies import BASIS, still_agrees
        if previous.get('basis') == BASIS and still_agrees(session, case_id, file, proposal, request, previous):
            return previous
    own = scope({**request, 'account_type': proposal.get('metadata', {}).get('account_type') or ''})
    current = proposal.get('current_import') or {}
    if current.get('excluded_as_duplicate') and current.get('duplicate_disposition'):
        # A saved copy set aside after admission: its document decision governs.
        return deepcopy(current['duplicate_disposition'])
    if current.get('evidence_file_id') == str(file.id):
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=None,
            retained=_own_link(file, proposal, current.get('source_document_id')), reason='This statement already has a saved import.'), actor)
    if _requires_review_comparison(proposal):
        return _persist(file, proposal, request, dict(status='needs_comparison', label='Compare this statement', basis=None,
            retained=None, reason='Compare the earlier saved reviews with this reading before deciding whether it is a duplicate. Saved corrections remain available.'), actor)
    printed = proposal.get('printed_copies') or {}
    if printed.get('printing', 1) > 1:
        # A reprint inside this file: the first printing carries the period.
        retained = dict(evidence_file_id=str(file.id), statement_id=printed['first'], source_document_id=None,
            filename=file.original_filename, page_number=printed.get('first_page', 1))
        own_edited = _review_shape(proposal, request) != _review_shape(proposal, _initial(proposal))
        if printed['identical'] and printed.get('first_revision') and not own_edited and not proposal.get('saved_review'):
            return _persist(file, proposal, request, dict(status='ignored', label='Duplicate - Ignored by system',
                basis='identical_financial_reading', printed_copy=True, retained=retained,
                retained_reading_revision=printed['first_revision'],
                reason='This statement is printed again in the same PDF with the same payments and balances. The first printing is used. Evidence and saved reviews remain available.'),
                actor, matched_fields=['source_file', 'account_reference', 'period_start', 'period_end', 'payments_and_balances'])
        return _persist(file, proposal, request, dict(status='needs_comparison', label='Compare this statement', basis=None,
            retained=retained, reason='This statement is printed again in the same PDF and the copies differ or were edited. Compare both printings before importing either.'), actor)
    # The same bytes or the same rendered pages (page_identity) are one
    # document: its statements on the same pages are one printed statement,
    # however either file was read (another reader, bank wording, product).
    from services.financial.page_identity import same_document_files
    documents = same_document_files(session, case_id, file)
    if not own and not documents:
        return _persist(file, proposal, request, dict(status='not_duplicate', label='No confirmed duplicate', basis=None,
            retained=None, reason='Complete bank, full account, holder, currency and exact dates are required.'), actor)
    sources = sources() if callable(sources) else sources if sources is not None else comparison_sources(session, case_id)[0]
    content_peers = set(documents)
    def own_period(entry):
        return entry['file_id'] == str(file.id) and (entry.get('statement_id') or '') == (proposal.get('statement_id') or '')
    candidates = []
    if own:
        candidates = [entry for entry in sources.get((own['identity'], own['currency']), [])
            if (same_statement(own, entry.get('scope')) or same_printed_period(own, entry.get('scope'))
                or (entry['file_id'] in content_peers and _same_content_scope(own, entry.get('scope'))))
            and not own_period(entry)]
        # Another production can read the bank name differently, which files the
        # same printed reference and period under another identity. Only identical
        # payments and balances can make it a copy; otherwise it is left alone.
        candidates += [entry for (identity, currency), entries in sources.items()
            if identity != own['identity'] and currency == own['currency']
            for entry in entries if same_printed_period(own, entry.get('scope')) and not own_period(entry)]
    # r15-hold-gaps: another file printing the same account reference, currency
    # and dates, whatever bank wording and product type its reader gave it (so
    # whatever ledger account it was or would be filed in). A copy only with the
    # same money (below); otherwise two products sharing a printed reference.
    printed_only = set()
    own_printed = _printed_key(own) if own and PRINTED_FACTS_COPIES else None
    if own_printed:
        listed = {(entry['file_id'], entry.get('statement_id') or '') for entry in candidates}
        for entries in sources.values():
            for entry in entries:
                key = (entry['file_id'], entry.get('statement_id') or '')
                if (entry['file_id'] != str(file.id) and key not in listed and not own_period(entry)
                        and _printed_key(entry.get('scope')) == own_printed):
                    candidates.append(entry)
                    listed.add(key)
                    printed_only.add(key)
    # Metadata nominated these; a candidate among them that cannot be compared
    # holds this statement for comparison, as before.
    nominated = {(entry['file_id'], entry.get('statement_id') or '') for entry in candidates}
    # Every statement of the same document is compared by its pages, whatever
    # scope its reading gave it. Those only it nominated are skipped when they
    # cannot be compared or are not on the same pages.
    page_only = set()
    for entries in sources.values():
        for entry in entries:
            key = (entry['file_id'], entry.get('statement_id') or '')
            if entry['file_id'] in documents and key not in nominated and not own_period(entry):
                candidates.append(entry)
                nominated.add(key)
                page_only.add(key)
    # Explicit internal reread lineage is already governed by replacement rules.
    families = getattr(sources, 'families', {}) or {}
    root = families.get(str(file.id), str(file.id))
    candidates = [entry for entry in candidates if families.get(entry['file_id'], entry['file_id']) != root]
    if not candidates:
        if not own:
            return _persist(file, proposal, request, dict(status='not_duplicate', label='No confirmed duplicate', basis=None,
                retained=None, reason='Complete bank, full account, holder, currency and exact dates are required.'), actor)
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=None,
            retained=_own_link(file, proposal), reason='No separate statement with the same full identity and period was found.'), actor)
    own_reading, own_usable = _financial_reading(proposal)
    own_content, own_payments = statement_content(proposal)
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
    # Within one document, how many statements of each reading print each
    # account reference and period (the same printed statement must be unique).
    printed_counts = Counter((entry['file_id'], _printed_key(entry.get('scope'))) for entries in sources.values()
                             for entry in entries if entry['file_id'] in documents or entry['file_id'] == str(file.id))
    own_key = _printed_key(own)
    proved_cache = []
    def own_proved():
        if not proved_cache:
            proved_cache.append(_proved(proposal, request))
        return proved_cache[0]
    for entry in candidates:
        key = (entry['file_id'], entry.get('statement_id') or '')
        loaded = _candidate(session, case_id, entry, cache)
        if loaded is None:
            if key not in page_only:
                conflicts.append(entry)
            continue
        other_file, other_proposal, other_request = loaded
        reviewed = bool((other_proposal.get('saved_review') or {}).get('request')) or bool(other_request.get('coverage_review_reason'))
        same_pages = by_pages = entry['file_id'] in documents and _page_copy(proposal, other_proposal)
        if entry['file_id'] in documents and not same_pages and own_key:
            # Two readers can group one printed statement's pages differently.
            # In the same document, the one statement each reading prints for
            # this account reference and period, on shared pages, is that statement.
            other_key = _printed_key(scope({**other_request, 'account_type': ''}))
            same_pages = bool(other_key == own_key and printed_counts[(entry['file_id'], own_key)] == 1
                and printed_counts[(str(file.id), own_key)] <= 1
                and _section_pages(proposal) & _section_pages(other_proposal))
        if same_pages:
            # One printed statement of one document. The better proved reading is kept and the other set aside, whatever
            # their readings say; only two different investigator edits of it
            # need a person to compare them.
            other_edited = _edited(other_proposal, other_request)
            if (conflicting_saved_review or (own_edited and other_edited)) and own_shape != _review_shape(other_proposal, other_request):
                conflicts.append(entry)
                continue
            other_proved = _proved(other_proposal, other_request)
            if other_proved and own_proved() and _money_conflicts(proposal, other_proposal):
                # Both readings reconcile, yet their money differs: one reader
                # misread while still reconciling. A person compares them.
                conflicts.append(entry)
                continue
            basis = documents[entry['file_id']]
            peers.append((entry, other_file, reviewed, basis, other_proposal['revision'],
                ['page_images' if basis == 'identical_pages' else 'source_sha256',
                 *(['source_pages'] if by_pages else ['account_reference', 'period_start', 'period_end', 'currency'])],
                other_edited, other_proved))
            continue
        if key in page_only:
            continue  # Nominated by its document only, and not on the same pages.
        if key in printed_only:
            # The same printed reference, currency and dates in another file,
            # read as another product or bank (r15-hold-gaps). The same payments
            # (at least one), balance convention and printed balances (one
            # reading's a subset of the other's) make it the same printed
            # statement; anything else is another statement, left alone.
            _, usable = _financial_reading(other_proposal)
            if not (own_usable and usable and own_payments and not _money_conflicts(proposal, other_proposal)):
                continue
            if conflicting_saved_review or (own_edited and own_shape != _review_shape(other_proposal, other_request)):
                conflicts.append(entry)
                continue
            peers.append((entry, other_file, reviewed, 'identical_financial_reading', other_proposal['revision'],
                ['account_reference', 'period_start', 'period_end', 'currency', 'payments_and_balances'],
                _edited(other_proposal, other_request), _proved(other_proposal, other_request)))
            continue
        # A corrected candidate identity must still match its current reading/review.
        other_scope = scope({**other_request, 'account_type': other_proposal.get('metadata', {}).get('account_type') or ''})
        same_bytes = bool(file.sha256 and file.sha256 == other_file.sha256)
        strong_identity = same_statement(own, other_scope)
        printed_copy = same_printed_period(own, other_scope)
        other_bank = bool(other_scope and other_scope.get('identity') != own['identity'])
        if not strong_identity and not printed_copy and not (same_bytes and _same_content_scope(own, other_scope)):
            continue
        fingerprint, usable = _financial_reading(other_proposal)
        same_reading = own_reading == fingerprint
        # Decision (r1-reproduced): equal money is a copy even when descriptions
        # or the holder were read differently. Reverse: require same_reading.
        same_money = same_reading or statement_content(other_proposal)[0] == own_content
        if other_bank and not (same_money and own_usable and usable and own_payments):
            if (PRINTED_FACTS_COPIES and printed_copy and entry['status'] == 'imported' and own_payments
                    and statement_content(other_proposal)[1]):
                # The same printed account reference, product, currency and
                # dates is already saved in the case, read with other money (two
                # readers of one statement): never saved again automatically; a
                # person compares the pair (r15-hold-gaps, live case).
                conflicts.append(entry)
            continue  # A differently named bank is a copy only with equal payments.
        own_changes_preserved = not conflicting_saved_review and (not own_edited or own_shape == _review_shape(other_proposal, other_request))
        # Identical bytes are a copy of the same section only; a different
        # file is a copy when the same printed statement carries equal money.
        byte_copy = same_bytes and (strong_identity or (own_usable and usable and same_reading
            and _same_source_section(proposal, other_proposal)))
        money_copy = not same_bytes and (strong_identity or printed_copy) and same_money and own_usable and usable
        if (not own_changes_preserved or not (byte_copy or money_copy)
                or (same_bytes and own_usable and usable and not same_reading)):
            conflicts.append(entry)
            continue
        peers.append((entry, other_file, reviewed, 'identical_bytes' if byte_copy else 'identical_financial_reading', other_proposal['revision'],
            None if byte_copy or strong_identity else _printed_copy_fields(own, other_scope),
            _edited(other_proposal, other_request), _proved(other_proposal, other_request)))
    # Never hide a revised/conflicting copy merely because another copy matches.
    if request.get('coverage_review_reason', '').strip():
        conflicts = candidates
    if conflicts:
        first = sorted(conflicts, key=lambda item: (item['status'] != 'imported', item['file_id'], item.get('statement_id') or ''))[0]
        retained = dict(evidence_file_id=first['file_id'], statement_id=first.get('statement_id'),
            source_document_id=first.get('source_document_id'), filename=first['filename'], page_number=first.get('page_number', 1))
        return _persist(file, proposal, request, dict(status='needs_comparison', label='Compare this statement', basis=None,
            retained=retained, reason='The matching period contains different readings, saved edits or unavailable comparison evidence.'), actor)
    # Keep the first verified retained reading stable. File creation timestamps
    # can tie, and UUID ordering must not nominate a second retained copy when
    # it is prepared after its peer. Before them: a saved statement, then an
    # investigator's work, then the reading that proves the statement by itself
    # (r10-copies: the better proved copy is the one admitted).
    def peer_rank(item):
        entry, peer, reviewed, _, _, _, edited, proved = item
        retained = (_stored(peer, entry.get('statement_id')) or {}).get('status') == 'retained'
        return (entry['status'] != 'imported', not reviewed, not edited, not proved, not retained,
            str(peer.created_at), entry['file_id'], entry.get('statement_id') or '')
    if not peers:
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=None,
            retained=_own_link(file, proposal), reason='No confirmed duplicate remained after comparing the current identities.'), actor)
    own_rank = (1, not bool(proposal.get('saved_review')), not own_edited, not own_proved(),
        not bool(previous and previous.get('status') == 'retained'),
        str(file.created_at), str(file.id), proposal.get('statement_id') or '')
    ranked = sorted(peers, key=peer_rank)
    entry, other_file, reviewed, basis, retained_reading_revision, matched, _, _ = ranked[0]
    rank = peer_rank(ranked[0])
    if own_rank <= rank:
        return _persist(file, proposal, request, dict(status='retained', label='Retained statement', basis=basis,
            retained=_own_link(file, proposal), reason='This is the retained source for matching copies of this period.'), actor,
            matched_fields=matched)
    retained = dict(evidence_file_id=entry['file_id'], statement_id=entry.get('statement_id'),
        source_document_id=entry.get('source_document_id'), filename=entry['filename'], page_number=entry.get('page_number', 1))
    reason = ('Every page of this file is identical to the retained file, so this is the same statement. The retained '
              'reading is used once. Evidence and saved reviews remain available.') if basis == 'identical_pages' else \
        'The statement content and period match the retained source. Evidence and saved reviews remain available.'
    return _persist(file, proposal, request, dict(status='ignored', label='Duplicate - Ignored by system', basis=basis,
        retained=retained, retained_reading_revision=retained_reading_revision, reason=reason), actor,
        matched_fields=matched)


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
    response = dict(case_id=str(case_id), evidence_file_id=str(file.id), statement_id=proposal.get('statement_id'),
        duplicate_disposition=result)
    # Batch lists reuse stored readiness; bring this period's batch items current.
    from services.financial.import_batches import refresh_file_readiness
    refresh_file_readiness(session, case_id=case_id, file_id=file.id, statement_key=proposal.get('statement_id') or '')
    return response


def ignored_receipt(case_id, file, decision):
    return dict(case_id=str(case_id), evidence_file_id=str(file.id), outcome='duplicate_ignored', ignored=True,
        applied=True, created=False, source_document_id=None, account_id=None,
        transaction_count=0, record_count=0, incomplete_count=0, issues=[], duplicate_disposition=decision)


def prepare_batch_dispositions(session, batch, file_id, *, cache=None, review_lock=None):
    """Recheck only this file's exact matching periods, preserving saved imports.

    Preparation already holds the case lock. Comparing peers also handles a
    batch whose upload order differs from the stable retained-source ordering.
    A worker review passes its `review_lock`: the case may then be released
    between items, after which each item is re-read before it is decided.
    """
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.statement_import import read_statement_import
    from services.financial.statement_import_overlap import summary_request
    cache = cache if cache is not None else {}
    eligible = ('ready', 'attention', 'duplicate_ignored')
    items = list(session.scalars(select(Item).where(Item.batch_id == batch.id,
        Item.status.in_(eligible)).order_by(Item.file_id, Item.statement_key)))
    scopes = [scope({**(item.review_request or summary_request(item.summary)),
        'account_type': item.summary.get('account_type', '')}) for item in items if item.file_id == file_id]
    # Loading the case's comparison sources reads every pending item and file
    # (seconds on a large case), and this loop held the case lock while doing
    # it once per matching period. Reuse one snapshot until a decision here
    # changes something it was built from: this item's status, review or
    # summary (other than its own copy of the decision), or the file's metadata.
    snapshot = {}
    def sources():
        if 'value' not in snapshot:
            snapshot['value'] = comparison_sources(session, batch.case_id)[0]
        return snapshot['value']
    def inputs(item, file):
        return (item.status, deepcopy(item.review_request), deepcopy(file.metadata_),
                {key: deepcopy(value) for key, value in (item.summary or {}).items() if key != 'duplicate_disposition'})
    # Statements of a file holding the same document (same bytes or pages) are
    # rechecked whatever their reading says.
    from services.financial.page_identity import same_document_files
    prepared = session.get(EvidenceFile, file_id)
    same_document = {UUID(peer) for peer in same_document_files(session, batch.case_id, prepared)} if prepared else set()
    def matches(item):
        descriptor = scope({**(item.review_request or summary_request(item.summary)),
            'account_type': item.summary.get('account_type', '')})
        return item.file_id == file_id or item.file_id in same_document or any(
            same_statement(descriptor, own) or same_printed_period(descriptor, own) for own in scopes)
    def current(item):
        # The case was released at a statement boundary (a sliced worker
        # review): another save may have claimed, edited or removed this item.
        snapshot.clear()
        return session.scalar(select(Item).where(Item.id == item.id, Item.status.in_(eligible)))
    for item in items:
        if review_lock is not None and review_lock.yield_case():
            item = current(item)
            if item is None:
                continue
        if not matches(item):
            continue
        if review_lock is not None and review_lock.warm(item.file_id, item.summary.get('currency') or None):
            item = current(item)
            if item is None or not matches(item):
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
        before = inputs(item, file)
        decision = apply_duplicate_disposition(session, case_id=batch.case_id, file=file,
            proposal=proposal, request=item.review_request, sources=sources)
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
        if inputs(item, file) != before:
            snapshot.clear()
