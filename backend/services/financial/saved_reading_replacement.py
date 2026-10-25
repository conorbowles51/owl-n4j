"""Replace a saved statement period that the current reader proves wrong.

A statement saved on an earlier reading can carry money the printed statement
does not: a payment the old reader missed, a misread balance. When the current
reader reads that same period again and its reading *proves* (it would be
saved automatically as a fresh, untouched statement), the saved period is
replaced by that reading, linked and reversible. One period at a time, never a
whole file: the file's other saved periods are not looked at.

A saved period is replaced only when all of these hold:

* it is an admitted statement review with one statement period (account,
  currency, printed dates) and its file's bytes are still the evidence;
* no person typed or corrected its payments: no payment row a person added,
  no payment value changed from its reading, no saved payment corrected or
  completed afterwards, no recorded row decision (``TYPED``). Statement
  details a person saved (holder, dates, balances) do not stop it: that version
  is kept, linked, restorable, and the new statement says so;
* exactly one statement of the file's current reading is that period: the same
  currency, the same printed dates, the same account reference, filed in the
  same ledger account (the writer's own account rule, and account merges);
* that reading proves under today's admission exactly as a fresh untouched
  statement would: ready with no check at all (``import_batches.assess`` on
  the reading without the saved copy, which applies the printed totals and
  running balances, opening + payments = closing, identity, missing pages,
  printed copies and copies saved from other files), no coverage hold against
  any other saved statement, and a reconciled admission;
* and its money differs from what is saved (payments by amount, direction and
  date; opening and closing balances).

Mechanism: the new reading is admitted through the strict import writer
(``statement_import.confirm_statement_import``), the path every import takes,
as a replacement of the saved copy (``replaces_source_document_id``). Under
the writer's locks this module proves it again on the writer's own reading;
the old copy is then set aside with the reversible duplicate decision
(``duplicate_decisions.decide_duplicate``, match ``reader_replacement``): it
becomes ``superseded``, linked to the new copy, its payments ``superseded``
with a row record, and an adjudication by "system: reader replacement" keeps
the before and after. Both in the writer's one transaction, so the period's
money counts once at every instant. Nothing is deleted: old rows,
corrections, citations and the investigator's saved review stay on the old
copy. The graph follows through the writer's own follow-up request.

Restore (``restore_replacement``) is the exact reversal, in one transaction:
the old copy and its recorded payments count again and the new copy is set
aside, linked to it. A restored period is never replaced again automatically.

Switch: ``LOUPE_FINANCIAL_REPLACE_SAVED_READING`` (default on; ``0`` off).
Off, nothing is replaced and the writer refuses a reader replacement; restoring
an earlier replacement stays available.
"""
from __future__ import annotations

import os
import re
import uuid
from collections import Counter
from datetime import date

from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import (
    AdjudicationEvent, FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction,
)
from services.financial.decisions import Actor
from services.financial.pdf_candidates import PdfMappingError, _digest

ENABLED = os.environ.get('LOUPE_FINANCIAL_REPLACE_SAVED_READING', '1').strip().lower() not in ('0', 'false', 'off', 'no')
ACTOR = Actor(name='system: reader replacement', email='reader-replacement@system.local')
BASIS = 'system_reader_replacement'
RESTORED_BASIS = 'reader_replacement_restored'
METADATA_KEY = 'reader_replacement'
REASON = ('The current reader read this statement period again and its reading balances under every admission check; '
          'it differs from the saved copy. The saved copy is kept, linked and restorable.')
RESTORE_REASON = 'Restored on request: the earlier saved copy counts again; the replacing reading is kept, linked.'
NOTICE = 'Loupe replaced this saved statement with a reading that balances; your earlier version is kept (Restore).'
NOTICE_SYSTEM = 'Loupe replaced this saved statement with a reading that balances; the earlier version is kept (Restore).'

# Why a saved period is left as it is. Codes are reported (counts); messages explain.
REFUSED = {
    'disabled': 'Replacing saved statements is switched off.',
    'not_admitted': 'The saved copy no longer counts.',
    'not_statement_review': 'Not a saved statement review.',
    'removed': 'The saved copy was removed from the import.',
    'source_changed': 'The evidence file no longer matches the saved copy.',
    'no_single_period': 'The saved copy does not hold exactly one dated statement period with a currency.',
    'typed_payments': 'A person typed or changed payments of this saved statement.',
    'corrected_payments': 'Payments of this saved statement were corrected or completed after it was saved.',
    'row_decisions': 'A person recorded decisions on payments of this saved statement.',
    'other_copies_linked': 'Another copy linked to this saved statement still counts.',
    'restored_by_request': 'A replacement of this statement was restored on request; it is left as decided.',
    'no_reading': 'The file has no current reading of this period.',
    'no_matching_period': 'No statement of the current reading has this currency, account and printed dates.',
    'several_matching_periods': 'More than one statement of the current reading matches this period.',
    'other_account': 'The current reading would file this period in another ledger account.',
    'not_proved': 'The current reading of this period does not balance under every admission check.',
    'coverage': 'Another saved statement overlaps this account and period.',
    'same': 'The current reading has the same payments and balances as the saved copy.',
    'unreadable': 'The current reading could not be built.',
}


class ReplacementError(PdfMappingError):
    pass


def enabled():
    return ENABLED


def _calendar(value):
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _digits(value):
    return re.sub(r'\D', '', value or '')


def _row_date(fields, row):
    """The ledger date the writer records for this reviewed row (transaction, else posted)."""
    from services.financial.statement_import import _reading_dates
    if row.get('date_unprinted'):
        return None
    try:
        dates = _reading_dates(fields or {}, row['date'], row.get('date_values'))
    except (ValueError, TypeError, KeyError):
        return row.get('date') or None
    when = dates.get('transaction_date') or dates.get('posted_date')
    return when.isoformat() if when else None


def fresh_money(proposal, raw):
    """What the writer would put in the ledger for this request: payments and the period's balances."""
    from services.financial.import_issues import incomplete_records, usable_balance
    from services.financial.statement_import import StatementImportRequest
    request = StatementImportRequest.model_validate(raw)
    originals = {row['id']: row for row in proposal['rows']}
    incomplete = {record['id'] for record in incomplete_records(proposal, request)}
    convention = proposal['metadata'].get('balance_convention')
    sign = -1 if convention == 'liability_owed' else 1
    rows = Counter()
    for row in request.rows:
        if row.excluded or row.id in incomplete:
            continue
        rows[(int(row.amount_minor), row.direction,
              _row_date((originals.get(row.id) or {}).get('fields'), row.model_dump(mode='json')))] += 1

    def balance(test):
        found = [row for row in request.rows if row.excluded and row.id in originals
                 and originals[row.id]['kind'] == 'balance' and test(originals[row.id]['fields'].get('description', '').strip().lower())
                 and usable_balance(row.balance_minor, convention)]
        return sign * int(found[0].balance_minor) if len(found) == 1 else None
    return dict(rows=rows, opening=balance(lambda text: 'opening' in text),
                closing=balance(lambda text: text == 'closing balance'))


def saved_money(session, document, period):
    rows = Counter()
    for row in session.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == document.id, FinancialTransaction.ledger_status == 'admitted')):
        when = None if (row.provenance or {}).get('date_basis') == 'statement_end_ordering_only' else (
            row.transaction_date or row.posted_date)
        rows[(int(row.amount_minor), row.direction, when.isoformat() if when else None)] += 1
    return dict(rows=rows, opening=period.opening_balance_minor, closing=period.closing_balance_minor)


def _typed(session, document):
    """Refusal code when a person typed, changed, corrected or decided payments of this saved copy."""
    from services.financial.import_batches import initial_request
    metadata = document.metadata_ or {}
    original, request = metadata.get('statement_import_original'), metadata.get('statement_import_request')
    if not original or not request:
        return 'typed_payments'
    baseline = {row['id']: row for row in initial_request(original)['rows']}
    kinds = {row['id']: row.get('kind') for row in original.get('rows', [])}
    for row in request.get('rows', []):
        initial = baseline.get(row['id'])
        if initial is None:
            # A row the reading never had: a payment or balance a person typed.
            return 'typed_payments'
        if row.get('excluded') and initial.get('excluded') and kinds.get(row['id']) == 'balance':
            continue  # a printed balance kept outside the payments; its value is a statement detail
        if bool(row.get('excluded')) != bool(initial.get('excluded')):
            return 'typed_payments'
        if row.get('excluded') and initial.get('excluded'):
            continue  # a line left outside the payments on both sides
        # Every field of a payment row: amount, direction, dates, description, counterparty, its link, page, reason.
        if any(_given(row.get(key)) != _given(initial.get(key)) for key in set(row) | set(initial) if key != 'id'):
            return 'typed_payments'
    return _rows_changed(session, document)


def _given(value):
    """A request field as given: an absent field and its empty default are the same decision."""
    return None if value in (None, '', {}, [], False) else value


def _rows_changed(session, document):
    """Refusal code when saved payments of this copy were corrected, completed or decided after it was saved."""
    metadata = document.metadata_ or {}
    if any(record.get('correction') or record.get('resolved_transaction_id')
           for record in metadata.get('statement_incomplete_records', [])):
        return 'corrected_payments'
    rows = list(session.execute(select(FinancialTransaction.id, FinancialTransaction.ledger_status,
                                       FinancialTransaction.superseded_by_id).where(
        FinancialTransaction.source_document_id == document.id)))
    if any(status != 'admitted' or superseded for _, status, superseded in rows):
        return 'corrected_payments'
    if rows and session.scalar(select(func.count()).select_from(AdjudicationEvent).where(
            AdjudicationEvent.case_id == document.case_id, AdjudicationEvent.subject_type == 'transaction',
            AdjudicationEvent.subject_id.in_([row[0] for row in rows]))):
        return 'row_decisions'
    return None


def _latest_event(session, document):
    return session.scalar(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id == document.case_id, AdjudicationEvent.subject_type == 'source_document',
        AdjudicationEvent.subject_id == document.id).order_by(AdjudicationEvent.subject_sequence.desc()).limit(1))


def _restored_before(session, document):
    """Whether this saved copy came back from a reader replacement a person (or --restore) undid."""
    return session.scalar(select(AdjudicationEvent.id).where(
        AdjudicationEvent.case_id == document.case_id, AdjudicationEvent.subject_type == 'source_document',
        AdjudicationEvent.subject_id == document.id,
        AdjudicationEvent.after['basis'].as_string() == RESTORED_BASIS).limit(1)) is not None


def investigator_work(session, document):
    """Whether a person saved work on this copy (statement details, or the review it was saved from)."""
    metadata = document.metadata_ or {}
    if metadata.get('statement_details_review') or metadata.get('statement_details_history'):
        return True
    file = session.get(EvidenceFile, document.evidence_file_id)
    progress = ((file.metadata_ or {}).get('financial_review_progress') or {}).get(
        metadata.get('statement_import_statement_id') or '') if file else None
    saved_by = ((progress or {}).get('saved_by') or {}).get('name') or ''
    from services.financial.field_proposals import SYSTEM_NAME
    return bool(progress and saved_by and saved_by != SYSTEM_NAME and not saved_by.startswith('system'))


def _saved_state(session, document):
    """(refusal code, period) for a saved copy, before any reading."""
    if document.status != 'admitted':
        return 'not_admitted', None
    if document.document_type != 'statement_review':
        return 'not_statement_review', None
    metadata = document.metadata_ or {}
    if metadata.get('financial_import_removal'):
        return 'removed', None
    file = session.get(EvidenceFile, document.evidence_file_id)
    if file is None or file.case_id != document.case_id or file.sha256 != document.sha256_at_ingestion:
        return 'source_changed', None
    periods = list(session.scalars(select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.source_document_id == document.id)))
    if len(periods) != 1 or not periods[0].currency or periods[0].period_end is None or periods[0].account_id is None:
        return 'no_single_period', None
    if _restored_before(session, document):
        return 'restored_by_request', periods[0]
    code = _typed(session, document)
    if code:
        return code, periods[0]
    if session.scalar(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.superseded_by_id == document.id,
            FinancialSourceDocument.status != 'superseded').limit(1)) is not None:
        return 'other_copies_linked', periods[0]
    return None, periods[0]


def _candidates(document, choices, currency):
    """Statement ids of the current reading that may be this saved period, nearest first."""
    metadata = document.metadata_ or {}
    key = metadata.get('statement_import_statement_id') or None
    ids = [choice['id'] for choice in choices]
    if key and key in ids:
        return [key]
    saved_pages = set((metadata.get('statement_import_original') or {}).get('page_numbers') or [])
    return [choice['id'] for choice in choices if not choice.get('document_kind')
            and (choice.get('currency') or currency) == currency
            and (not saved_pages or saved_pages & set(choice.get('page_numbers') or []))]


def _same_period(raw, period, saved_request, *, same_key=False):
    """Whether a reading is this saved period. ``same_key``: it is the statement the copy was saved from; a
    reading that cannot date it is still that statement (and cannot prove: admission needs its dates)."""
    if raw.get('currency') != period.currency:
        return False
    end, start = _calendar(raw.get('period_end')), _calendar(raw.get('period_start'))
    if same_key and end is None and start is None:
        pass
    elif end != period.period_end or (period.period_start is not None and start != period.period_start):
        return False
    saved_reference = _digits((saved_request or {}).get('account_number'))
    return not saved_reference or _digits(raw.get('account_number')) == saved_reference


def _account_digits(account):
    return _digits(account.identifier_normalised or account.identifier_as_printed)


def target_account(session, document, period, request, proposal):
    """(code, account): the ledger account the writer would file this reading in, when it is this saved
    period's account.

    The same account, one merged with it, or (a reader that now files the
    statement under a better identity, such as one account per currency of a
    multi-currency contract) an account that already exists and holds saved
    statements, of the same bank, printed reference and this period's currency.
    Never a new account.
    """
    from services.financial.account_consolidation import bank_key, expand_account_ids
    from services.financial.statement_import import statement_account_draft
    file = session.get(EvidenceFile, document.evidence_file_id)
    key = statement_account_draft(request, proposal, file).identity().key
    account = session.scalar(select(FinancialAccount).where(
        FinancialAccount.case_id == document.case_id, FinancialAccount.identity_key == key))
    if account is None:
        return 'other_account', None
    if account.id == period.account_id or account.id in set(
            expand_account_ids(session, document.case_id, [period.account_id])):
        return None, account
    saved = session.get(FinancialAccount, period.account_id)
    if (saved is None or bank_key(account.institution_name or '') != bank_key(saved.institution_name or '')
            or not _account_digits(account) or _account_digits(account) != _account_digits(saved)
            or account.currency not in (None, period.currency)):
        return 'other_account', None
    others = session.scalar(select(func.count()).select_from(FinancialStatementPeriod).join(
        FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id).where(
        FinancialStatementPeriod.account_id == account.id, FinancialSourceDocument.status == 'admitted'))
    return (None, account) if others else ('other_account', None)


def build_request(document, proposal):
    """The request a fresh untouched statement is saved with, naming the saved copy it replaces."""
    from services.financial.import_batches import initial_request
    raw = initial_request(proposal)
    raw.update(replaces_source_document_id=str(document.id), details_reason=REASON)
    return raw


def prove(session, document, proposal, raw):
    """Refusal code, or None when this reading proves exactly as a fresh untouched statement would."""
    from services.financial.import_batches import assess
    from services.financial.statement_import import StatementImportRequest
    from services.financial.statement_import_overlap import (coverage_review, duplicate_hold, later_queries_trim_themselves,
                                                             requires_decision)
    fresh = {**proposal, 'current_import': None, 'saved_review': None}
    state, summary = assess(fresh, None)
    admission = summary.get('admission') or {}
    if (state != 'ready' or not summary.get('can_import') or summary.get('problems') or summary.get('problem_count')
            or not admission.get('can_import') or admission.get('blockers') or summary.get('balance_status') != 'matches'):
        return 'not_proved'
    request = StatementImportRequest.model_validate(raw)
    coverage_request = {**request.model_dump(mode='json'), 'account_type': proposal['metadata'].get('account_type') or '',
                        'account_reference_kind': proposal['metadata'].get('account_reference_kind') or ''}
    coverage = coverage_review(session, case_id=document.case_id, file_id=document.evidence_file_id, request=coverage_request)
    coverage = later_queries_trim_themselves(coverage, coverage_request, file_id=document.evidence_file_id,
        statement_id=request.statement_id, summary=dict(statement_form=proposal.get('statement_form')))
    if duplicate_hold(coverage, coverage_request) or requires_decision(coverage, request.model_dump(mode='json')):
        return 'coverage'
    return None


def assess_document(session, document, *, cache=None, reading=None):
    """What replacing this saved copy would do. Reads only.

    ``reading``: (statement id, proposal) the writer read under its locks; the
    proof is then made on exactly that reading. Returns a dict with
    ``outcome`` ('replace', 'same' or 'refused'), ``code``, counts of the saved
    and fresh payments, and for 'replace' the ``request`` to import.
    """
    from services.financial.duplicate_decisions import duplicate_revision
    from services.financial.statement_import import read_statement_import
    result = dict(document_id=str(document.id), evidence_file_id=str(document.evidence_file_id),
                  case_id=str(document.case_id), outcome='refused', code=None)
    code, period = _saved_state(session, document)
    if period is not None:
        result.update(period_id=str(period.id), currency=period.currency)
    if code:
        return {**result, 'code': code}
    saved = saved_money(session, document, period)
    result.update(saved_payments=sum(saved['rows'].values()))
    saved_request = (document.metadata_ or {}).get('statement_import_request') or {}
    try:
        if reading is not None:
            matches = [reading]
        else:
            cache = {} if cache is None else cache
            top = read_statement_import(session, case_id=document.case_id, evidence_file_id=document.evidence_file_id,
                                        currency=period.currency, _cache=cache)
            choices = top.get('statement_choices') or ([dict(id=top['statement_id'], currency=top.get('currency'),
                page_numbers=top.get('page_numbers'))] if top.get('statement_id') or top.get('rows') else [])
            matches = []
            for statement_id in _candidates(document, choices, period.currency):
                proposal = top if statement_id and statement_id == top.get('statement_id') else read_statement_import(
                    session, case_id=document.case_id, evidence_file_id=document.evidence_file_id,
                    currency=period.currency, statement_id=statement_id, _cache=cache)
                if not proposal.get('rows'):
                    continue
                from services.financial.import_batches import initial_request
                same_key = statement_id == (document.metadata_ or {}).get('statement_import_statement_id')
                if _same_period(initial_request(proposal), period, saved_request, same_key=same_key):
                    matches.append((statement_id, proposal))
        if not matches:
            return {**result, 'code': 'no_matching_period'}
        if len(matches) > 1:
            return {**result, 'code': 'several_matching_periods'}
        statement_id, proposal = matches[0]
        current = proposal.get('current_import') or {}
        if current.get('source_document_id') not in (None, str(document.id)):
            # The writer would replace another saved copy, not this one.
            return {**result, 'code': 'no_matching_period'}
        raw = build_request(document, proposal)
        raw['replacement_revision'] = duplicate_revision(session, document)
        if not _same_period(raw, period, saved_request, same_key=statement_id == (
                (document.metadata_ or {}).get('statement_import_statement_id'))):
            return {**result, 'code': 'no_matching_period'}
        fresh = fresh_money(proposal, raw)
        result.update(statement_id=statement_id, fresh_payments=sum(fresh['rows'].values()))
        if fresh == saved:
            return {**result, 'outcome': 'same', 'code': 'same'}
        from services.financial.statement_import import StatementImportRequest
        code, account = target_account(session, document, period, StatementImportRequest.model_validate(raw), proposal)
        if code:
            return {**result, 'code': code}
        result['account_moved'] = account.id != period.account_id
        code = prove(session, document, proposal, raw)
        if code:
            return {**result, 'code': code}
    except (PdfMappingError, ValueError) as error:
        return {**result, 'code': 'unreadable', 'message': str(error)[:200]}
    differs = [name for name in ('opening', 'closing') if fresh[name] != saved[name]]
    if fresh['rows'] != saved['rows']:
        differs.insert(0, 'payments')
    return {**result, 'outcome': 'replace', 'code': None, 'request': raw, 'differs': differs,
            'investigator_work': investigator_work(session, document),
            'missing_payments': sum((fresh['rows'] - saved['rows']).values()),
            'extra_payments': sum((saved['rows'] - fresh['rows']).values())}


def plan(session, *, case_ids=None, document_ids=None):
    """Assess saved copies (all saved statement reviews of the cases, or the given copies). Reads only."""
    query = select(FinancialSourceDocument).where(FinancialSourceDocument.status == 'admitted',
                                                  FinancialSourceDocument.document_type == 'statement_review')
    if document_ids is not None:
        query = query.where(FinancialSourceDocument.id.in_([uuid.UUID(str(d)) for d in document_ids]))
    if case_ids is not None:
        query = query.where(FinancialSourceDocument.case_id.in_([uuid.UUID(str(c)) for c in case_ids]))
    documents = list(session.scalars(query.order_by(FinancialSourceDocument.case_id,
                                                    FinancialSourceDocument.evidence_file_id, FinancialSourceDocument.id)))
    results, caches = [], {}
    for document in documents:
        cache = caches.setdefault(document.evidence_file_id, {})
        if len(caches) > 2:
            for key in list(caches)[:-1]:
                caches.pop(key)
        results.append(assess_document(session, document, cache=cache))
    return results


# Writer hook -----------------------------------------------------------------

def is_replacement(actor):
    # The system actor only: never a signed-in account, whatever it is called.
    return (getattr(actor, 'user_id', None) is None and getattr(actor, 'email', None) == ACTOR.email
            and getattr(actor, 'name', None) == ACTOR.name)


def writer_refusal(session, existing, proposal, request):
    """Called by the strict writer under its locks: the message refusing this reader replacement, or None."""
    if not ENABLED:
        return REFUSED['disabled']
    if str(request.replaces_source_document_id or '') != str(existing.id):
        return 'The saved copy named for replacement is not the current one.'
    if existing.evidence_file_id is None or str(existing.evidence_file_id) != str(proposal.get('evidence_file_id')):
        return 'A reader replacement replaces a saved copy of the same file only.'
    verdict = assess_document(session, existing, reading=(request.statement_id, proposal))
    if verdict['outcome'] != 'replace':
        return REFUSED.get(verdict['code']) or 'The current reading does not replace this saved copy.'
    from services.financial.statement_import import StatementImportRequest
    expected = StatementImportRequest.model_validate(verdict['request']).model_dump(mode='json')
    if _digest(expected) != _digest(request.model_dump(mode='json')):
        return 'The request differs from the current reading. Nothing was replaced.'
    return None


def writer_metadata(session, existing):
    return {METADATA_KEY: dict(policy='reader-replacement-v1', replaced_source_document_id=str(existing.id),
                               investigator_work=investigator_work(session, existing))}


def set_aside_replaced(session, *, case_id, existing, document, run_id=None):
    """Within the writer's transaction: the replaced copy is set aside, linked to the new one (reversible)."""
    from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
    result = decide_duplicate(session, case_id=case_id, document_id=existing.id, action='exclude',
        expected_revision=duplicate_revision(session, existing), primary_id=document.id,
        expected_primary_revision=duplicate_revision(session, document), actor=ACTOR, reason=REASON,
        match='reader_replacement', basis=BASIS, commit=False)
    _log(session, case_id, existing, 'Saved statement period replaced by the current reading, which balances. '
         'The earlier saved copy is kept, linked and restorable.', action='financial_reader_replacement',
         replacement_source_document_id=str(document.id), adjudication_id=result['adjudication_id'])
    return result


def link_refusal(session, document, primary):
    """For ``decide_duplicate(match='reader_replacement')``: why these two copies are not a replacement pair."""
    if document.case_id != primary.case_id or document.evidence_file_id != primary.evidence_file_id:
        return 'A reader replacement links two readings of the same file only.'
    if document.sha256_at_ingestion != primary.sha256_at_ingestion:
        return 'The two readings have different source bytes.'
    if not (_names(primary, document) or _names(document, primary)):
        return 'These two saved copies are not linked by a reader replacement.'
    return None


def _names(replacement, replaced):
    metadata = replacement.metadata_ or {}
    request = metadata.get('statement_import_request') or {}
    return bool(request.get('replaces_source_document_id') == str(replaced.id)
                and (metadata.get(METADATA_KEY) or {}).get('replaced_source_document_id') == str(replaced.id))


def replacement_pair(session, document):
    """(replacement, replaced) for a copy taking part in a reader replacement, or None."""
    metadata = document.metadata_ or {}
    if (metadata.get(METADATA_KEY) or {}).get('replaced_source_document_id'):
        other = session.get(FinancialSourceDocument, uuid.UUID(metadata[METADATA_KEY]['replaced_source_document_id']))
        if other is not None and other.case_id == document.case_id and _names(document, other):
            return document, other
    for other in session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == document.case_id,
            FinancialSourceDocument.evidence_file_id == document.evidence_file_id,
            FinancialSourceDocument.metadata_[METADATA_KEY]['replaced_source_document_id'].as_string() == str(document.id))):
        if _names(other, document):
            return other, document
    return None


def notice(session, document):
    """The notice shown on a statement taking part in a reader replacement, or None."""
    pair = replacement_pair(session, document)
    if pair is None:
        return None
    replacement, replaced = pair
    counting = replacement if replacement.status == 'admitted' else replaced if replaced.status == 'admitted' else None
    if counting is None:
        return None
    work = bool((replacement.metadata_.get(METADATA_KEY) or {}).get('investigator_work'))
    replaced_now = counting.id == replacement.id
    return dict(policy='reader-replacement-v1', status='replaced' if replaced_now else 'restored',
        message=(NOTICE if work else NOTICE_SYSTEM) if replaced_now else
        'The earlier saved version of this statement was restored; the reading that replaced it is kept, linked.',
        counting_source_document_id=str(counting.id),
        replacement_source_document_id=str(replacement.id), replaced_source_document_id=str(replaced.id),
        investigator_work=work, can_restore=True)


def is_replacement_link(session, superseded, retained):
    """Whether ``superseded`` is set aside for ``retained`` by a reader replacement (either direction)."""
    return bool(superseded is not None and retained is not None and superseded.case_id == retained.case_id
                and (_names(retained, superseded) or _names(superseded, retained)))


# Empty legacy imports ("shells") ---------------------------------------------
#
# 2026-10-25 (fin-queue2, lesson 13): early imports saved a whole file as one
# statement nobody could date: no statement of the reading named, no printed
# dates on its period, no payment and no incomplete record (BNB2: 65 such
# saved copies, e.g. "03 ECOTERRA KAPITAL MXN MZO 25", "09 ARRENDO MONEX MXN
# SEPT 2023"). Holding nothing, they still stood as the saved copy of every
# statement of the same bytes (their statement key is empty, which matches any
# key), so the file's real statements, read and balancing today, could never be
# saved and its periods stayed out of the ledger. A shell is not a reading of a
# period, so it is not compared or proved like one: a statement of the same bytes
# is imported as a fresh statement, and the shell is then set aside, linked to
# it, reversibly (decide_duplicate, match ``empty_shell``). Details a person
# saved on the shell (holder, account) stay on it, restorable. Off with the
# replacement switch: shells stand as before.

SHELL_BASIS = 'system_empty_shell_replacement'
SHELL_REASON = ('An earlier import saved this file as one undated statement with no payments. A statement of the same '
                'file was saved with its own dates and payments; this empty copy is kept, linked and restorable.')


def is_shell(session, document):
    """Whether this saved copy is an empty legacy import: no statement named, no dated period, nothing paid."""
    metadata = document.metadata_ or {}
    if (document.document_type != 'statement_review' or metadata.get('statement_import_statement_id')
            or metadata.get('financial_import_removal') or metadata.get('statement_incomplete_records')):
        return False
    periods = list(session.execute(select(FinancialStatementPeriod.period_start, FinancialStatementPeriod.period_end)
                                   .where(FinancialStatementPeriod.source_document_id == document.id)))
    if not periods or any(start is not None or end is not None for start, end in periods):
        return False
    return session.scalar(select(func.count()).select_from(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id)) == 0


def standing_shell(session, document):
    """Whether this copy is a shell that still counts as saved and may give way to a statement of its bytes."""
    from postgres.models.enums import ProofClass
    from services.financial.proof_class import may_produce_ledger_rows
    if not ENABLED or document is None or document.status != 'admitted' or document.superseded_by_id is not None:
        return False
    if not is_shell(session, document):  # first: on a saved statement it stops at its stored key or dates
        return False
    try:
        if not may_produce_ledger_rows(ProofClass(document.proof_class)):
            return False
    except ValueError:
        return False
    # What the set-aside refuses on the shell's side, checked first: the writer never starts an import
    # whose shell could not then be set aside.
    if session.scalar(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.superseded_by_id == document.id).limit(1)) is not None:
        return False
    file = session.get(EvidenceFile, document.evidence_file_id) if document.evidence_file_id else None
    return file is not None and file.sha256 == document.sha256_at_ingestion


def shell_link_refusal(session, document, primary):
    """For ``decide_duplicate(match='empty_shell')``: why ``document`` is not a shell giving way to ``primary``."""
    if document.case_id != primary.case_id or document.sha256_at_ingestion != primary.sha256_at_ingestion:
        return 'An empty import gives way only to a statement of the same file bytes.'
    if not is_shell(session, document):
        return 'The copy to set aside is not an empty import.'
    if is_shell(session, primary):
        return 'The retained copy is itself an empty import.'
    return None


def set_aside_shell(session, *, case_id, shell, document):
    """Within the writer's transaction: the shell is set aside, linked to the statement just admitted."""
    from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
    result = decide_duplicate(session, case_id=case_id, document_id=shell.id, action='exclude',
        expected_revision=duplicate_revision(session, shell), primary_id=document.id,
        expected_primary_revision=duplicate_revision(session, document), actor=ACTOR, reason=SHELL_REASON,
        match='empty_shell', basis=SHELL_BASIS, commit=False)
    _log(session, case_id, shell, 'Empty earlier import set aside: a statement of the same file was saved with its '
         'own dates and payments. The empty copy is kept, linked and restorable.', action='financial_empty_shell_replaced',
         replacement_source_document_id=str(document.id), adjudication_id=result['adjudication_id'])
    return result


def _shell_rows(session, *conditions):
    """(id, proof class) of the saved statement reviews matching ``conditions`` that are shells (``is_shell``),
    in one query reading only the fields it needs: a saved copy's stored reading is large."""
    from sqlalchemy import exists, or_
    D = FinancialSourceDocument
    dated = exists().where(FinancialStatementPeriod.source_document_id == D.id,
                           or_(FinancialStatementPeriod.period_start.is_not(None), FinancialStatementPeriod.period_end.is_not(None)))
    has_period = exists().where(FinancialStatementPeriod.source_document_id == D.id)
    paid = exists().where(FinancialTransaction.source_document_id == D.id)
    rows = session.execute(select(D.id, D.proof_class, D.metadata_['statement_import_statement_id'].as_string(),
                                  D.metadata_['financial_import_removal'].as_string(),
                                  D.metadata_['statement_incomplete_records'].as_string())
        .where(D.document_type == 'statement_review', has_period, ~dated, ~paid, *conditions)).all()
    return [(document_id, proof_class) for document_id, proof_class, key, removal, incomplete in rows
            if not key and not removal and incomplete in (None, '', '[]', 'null')]


def standing_shell_ids(session, case_id):
    """Ids (strings) of the case's shells that still count as saved (``standing_shell``), in two queries:
    the queue asks this on every listing."""
    if not ENABLED:
        return set()
    from postgres.models.enums import ProofClass
    from services.financial.proof_class import may_produce_ledger_rows
    D = FinancialSourceDocument
    found = set()
    for document_id, proof_class in _shell_rows(session, D.case_id == case_id, D.status == 'admitted',
            D.superseded_by_id.is_(None), D.evidence_file_id.in_(select(EvidenceFile.id).where(
                EvidenceFile.id == D.evidence_file_id, EvidenceFile.sha256 == D.sha256_at_ingestion))):
        try:
            if may_produce_ledger_rows(ProofClass(proof_class)):
                found.add(document_id)
        except ValueError:
            continue
    if found:
        # Copies set aside for one of these depend on it: it is not set aside in turn (standing_shell).
        found -= set(session.scalars(select(D.superseded_by_id).where(D.superseded_by_id.in_(found))).all())
    return {str(document_id) for document_id in found}


def shell_document_ids(session, case_id, document_ids):
    """The ids among ``document_ids`` (strings or UUIDs) that are shells, whatever their status."""
    ids = []
    for value in document_ids:
        try:
            ids.append(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            continue
    if not ids:
        return set()
    D = FinancialSourceDocument
    return {str(document_id) for document_id, _ in _shell_rows(session, D.case_id == case_id, D.id.in_(ids))}


# Apply / restore -------------------------------------------------------------

def replace_document(*, session_factory, case_id, document_id, resolve_path):
    """Replace one saved copy if (and only if) the current reading proves it wrong. One transaction.

    Returns the plan entry with the writer's receipt; refused entries are returned unchanged.
    """
    from services.financial.statement_import import StatementImportRequest, confirm_statement_import
    with session_factory() as session:
        document = session.get(FinancialSourceDocument, uuid.UUID(str(document_id)))
        if document is None or str(document.case_id) != str(case_id):
            raise ReplacementError('Saved statement not found in this case.', 404)
        if not ENABLED:
            return dict(document_id=str(document_id), outcome='refused', code='disabled')
        verdict = assess_document(session, document)
        file_id, old_key = document.evidence_file_id, (document.metadata_ or {}).get('statement_import_statement_id') or ''
        session.rollback()
    if verdict['outcome'] != 'replace':
        return verdict
    receipt = confirm_statement_import(session_factory=session_factory, case_id=uuid.UUID(str(case_id)),
        evidence_file_id=file_id, request=StatementImportRequest.model_validate(verdict['request']),
        actor=ACTOR, resolve_path=resolve_path)
    _refresh(session_factory, case_id, file_id, old_key)
    return {**{k: v for k, v in verdict.items() if k != 'request'}, 'applied': True, 'receipt': receipt}


def _refresh(session_factory, case_id, file_id, *keys):
    from services.financial.import_batches import refresh_file_readiness
    for key in dict.fromkeys(keys):
        try:
            with session_factory() as session:
                refresh_file_readiness(session, case_id=uuid.UUID(str(case_id)), file_id=file_id, statement_key=key)
        except Exception:  # Best effort: the readiness sweep brings it current.
            import logging
            logging.getLogger(__name__).exception('Readiness refresh after a reader replacement failed; the sweep will retry')


def _log(session, case_id, document, message, **extra):
    file = session.get(EvidenceFile, document.evidence_file_id)
    session.add(IngestionLog(case_id=case_id, evidence_file_id=document.evidence_file_id,
        filename=file.original_filename if file else None, level='info', message=message,
        extra=dict(source_document_id=str(document.id), **extra)))


def restore_replacement(*, session_factory, case_id, document_id, actor=ACTOR, reason=RESTORE_REASON):
    """Swap which copy of a reader replacement counts: ``document_id`` names the copy that counts NOW (the one
    the person is looking at); it is set aside and the other copy counts again, linked. One transaction.

    Naming a copy that no longer counts changes nothing (a repeated or stale request): ``applied`` is False.
    Refused when the copy to set aside holds payments corrected, completed or decided since it was saved:
    those would stop counting silently.
    """
    from postgres.models.case import Case
    from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
    case_id = uuid.UUID(str(case_id))
    with session_factory() as session:
        try:
            if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
                raise ReplacementError('Case not found.', 404)
            document = session.get(FinancialSourceDocument, uuid.UUID(str(document_id)))
            if document is None or document.case_id != case_id:
                raise ReplacementError('Saved statement not found in this case.', 404)
            pair = replacement_pair(session, document)
            if pair is None:
                raise ReplacementError('This statement was not replaced by a reading.', 409)
            ids = sorted({pair[0].id, pair[1].id}, key=str)
            locked = {d.id: d for d in session.scalars(select(FinancialSourceDocument).where(
                FinancialSourceDocument.id.in_(ids)).order_by(FinancialSourceDocument.id).with_for_update()
                .execution_options(populate_existing=True))}
            replacement, replaced = locked[pair[0].id], locked[pair[1].id]
            if replaced.status == 'superseded' and replaced.superseded_by_id == replacement.id and replacement.status == 'admitted':
                back, aside = replaced, replacement
            elif replacement.status == 'superseded' and replacement.superseded_by_id == replaced.id and replaced.status == 'admitted':
                back, aside = replacement, replaced
            else:
                raise ReplacementError('The two copies changed since the replacement. Review their history first.', 409)
            if aside.id != document.id:
                # The named copy is already set aside: this was done already (or the page is stale).
                session.rollback()
                return dict(applied=False, counting_source_document_id=str(aside.id),
                            set_aside_source_document_id=str(back.id))
            if _rows_changed(session, aside):
                raise ReplacementError('Payments of the statement in use were corrected or decided since it was saved. '
                                       'Restoring the other version would set that work aside; nothing was changed.', 409)
            first = decide_duplicate(session, case_id=case_id, document_id=back.id, action='restore',
                expected_revision=duplicate_revision(session, back), actor=actor, reason=reason,
                match='reader_replacement', basis=RESTORED_BASIS, commit=False)
            second = decide_duplicate(session, case_id=case_id, document_id=aside.id, action='exclude',
                expected_revision=duplicate_revision(session, aside), primary_id=back.id,
                expected_primary_revision=duplicate_revision(session, back), actor=actor, reason=reason,
                match='reader_replacement', basis=RESTORED_BASIS, commit=False)
            _log(session, case_id, back, 'Saved statement period restored: this copy counts again; the other reading '
                 'of the period is kept, linked.', action='financial_reader_replacement_restore',
                 set_aside_source_document_id=str(aside.id), adjudication_ids=[first['adjudication_id'], second['adjudication_id']])
            keys = [(back.metadata_ or {}).get('statement_import_statement_id') or '',
                    (aside.metadata_ or {}).get('statement_import_statement_id') or '']
            file_id = back.evidence_file_id
            result = dict(applied=True, counting_source_document_id=str(back.id), set_aside_source_document_id=str(aside.id),
                          restored_rows=first['changed_rows'], set_aside_rows=second['changed_rows'])
            session.commit()
        except Exception:
            session.rollback()
            raise
    from services.financial.graph_followup import request_follow_up
    request_follow_up(case_id)
    _refresh(session_factory, case_id, file_id, *keys)
    return result
