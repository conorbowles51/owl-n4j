"""Held copies of statements the case already saved: set aside as linked duplicates when the ledger agrees.

A held statement whose printed account (last six digits) and period the case already saved is not read
again (recovery_readers.copy_of_saved): a new reading could save it into a second ledger account and count
its money twice. Such a copy no longer waits for a person when its own reading agrees with the saved ledger
for that account and period:

* every payment of the copy has its own counterpart among the saved period's admitted payments, and the
  other way round (date, amount, direction; one for one), with at least one payment;
* its printed opening and closing balance, where its reading has them, equal the saved period's;
* its currency, where read, equals the saved period's;
* its reading has no unread line, and no payment without a date, amount or direction;
* exactly one saved period of the case agrees with it.

It is then set aside automatically as a linked duplicate of the saved statement, through the same
reversible decision the pre-admission duplicate check records (pending_statement_duplicates): status
ignored, basis ``saved_ledger_copy``, linked to the saved statement, the reason shown. A person restores it
with the ordinary duplicate "restore" action, which is final for it. Nothing is deleted, nothing is saved,
and the saved statement is not changed: it is only read.

A copy that does not agree stays held, and its batch item records what differs (``saved_copy_check``): the
payments only in the copy or only in the saved statement, a different balance or currency. It may be a
different statement of the same account number or carry rows the saved one lacks; a person compares them.

Only a copy nobody worked on is decided: no saved review, no batch draft, no duplicate decision a person
recorded, not imported. Fail closed: anything that cannot be read or compared leaves the copy held.

Switch: LOUPE_FINANCIAL_SAVED_COPY_SET_ASIDE (default on). Off: copies stay held as before; a set-aside
recorded earlier remains an ordinary System duplicate decision that a person can restore.
"""
import os
from collections import Counter
from datetime import date

from sqlalchemy import select

ENABLED = os.environ.get('LOUPE_FINANCIAL_SAVED_COPY_SET_ASIDE', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
BASIS = 'saved_ledger_copy'
LABEL = 'Duplicate - Ignored by system'
REASON = ('The case already saved this account and period, and this copy\'s payments match the saved statement one '
          'for one (date, amount, direction), with the same printed balances. It is set aside as a linked duplicate; '
          'the saved statement counts once. Restore it to review it again.')
MATCHED_FIELDS = ['account_reference_last_six', 'period_start', 'period_end', 'payments_one_for_one',
                  'printed_balances']


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _same_account(saved, read):
    from services.financial.recovery_readers import _same_account as same
    return same(saved, read)


def _day(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def copy_facts(proposal, request, summary=None):
    """What the copy's own reading says: account digits, dates, currency, payments, printed balances, holds."""
    summary = summary or {}
    facts = dict(account=_digits(request.get('account_number') or summary.get('account')),
                 start=_day(request.get('period_start') or summary.get('period_start')),
                 end=_day(request.get('period_end') or summary.get('period_end')),
                 currency=request.get('currency') or proposal.get('currency') or '', payments=Counter(), holds=[])
    edits = {row.get('id'): row for row in request.get('rows') or []}
    for row in proposal.get('rows') or []:
        edit = edits.get(row.get('id'), {})
        if edit.get('excluded', row.get('excluded')):
            continue
        if row.get('kind') in ('unresolved', 'unclassified'):
            facts['holds'].append('unread_rows')
            continue
        if row.get('kind') != 'transaction':
            continue
        fields = row.get('fields') or {}
        day = fields.get('date') or fields.get('booking_date') or ''
        amount, direction = _int(fields.get('amount_minor')), fields.get('direction')
        if not _day(day) or amount is None or direction not in ('debit', 'credit'):
            facts['holds'].append('incomplete_payment')
            continue
        facts['payments'][(day, amount, direction)] += 1
    checks = next((check for check in summary.get('checks') or []
                   if isinstance(check, dict) and check.get('kind') == 'closing_balance'), {})
    facts['opening'], facts['closing'] = _int(checks.get('opening_minor')), _int(checks.get('printed_minor'))
    return facts


def saved_periods(session, case_id, facts, own=()):
    """Admitted periods of the case on the copy's dates whose account matches its last six digits."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod
    if not facts['account'] or not facts['start'] or not facts['end']:
        return []
    rows = session.execute(select(FinancialStatementPeriod, FinancialAccount, FinancialSourceDocument, EvidenceFile)
        .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
        .join(FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id)
        .join(EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id)
        .where(FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.status == 'admitted',
               FinancialStatementPeriod.period_start == facts['start'],
               FinancialStatementPeriod.period_end == facts['end'])).all()
    result = []
    for period, account, document, file in rows:
        if (document.metadata_ or {}).get('financial_import_removal'):
            continue
        key = (document.metadata_ or {}).get('statement_import_statement_id') or ''
        if (str(file.id), key) in own:
            continue
        if any(_same_account(_digits(value), facts['account'])
               for value in (account.identifier_normalised, account.identifier_as_printed)):
            result.append((period, document, file, key))
    return result


def _ledger(session, period):
    from postgres.models.financial import FinancialTransaction
    return Counter((str(row.transaction_date or row.ordering_date), int(row.amount_minor), row.direction)
                   for row in session.scalars(select(FinancialTransaction).where(
                       FinancialTransaction.statement_period_id == period.id))
                   if row.ledger_status == 'admitted' and row.superseded_by_id is None)


def _differences(facts, period, ledger):
    out = []
    only_copy, only_saved = facts['payments'] - ledger, ledger - facts['payments']
    if only_copy or only_saved:
        out.append(dict(field='payments', copy=sum(facts['payments'].values()), saved=sum(ledger.values()),
                        only_in_copy=sum(only_copy.values()), only_in_saved=sum(only_saved.values())))
    for name, value, saved in (('opening', facts['opening'], period.opening_balance_minor),
                               ('closing', facts['closing'], period.closing_balance_minor)):
        if value is not None and saved != value:
            out.append(dict(field=name, copy=str(value), saved=None if saved is None else str(saved)))
    if facts['currency'] and period.currency and facts['currency'] != period.currency:
        out.append(dict(field='currency', copy=facts['currency'], saved=period.currency))
    return out


def _link(document, file, key, period):
    from services.financial.pending_statement_duplicates import _own_link
    original = (document.metadata_ or {}).get('statement_import_original') or {}
    link = _own_link(file, {**original, 'statement_id': key or original.get('statement_id')}, str(document.id))
    return dict(link, statement_period_id=str(period.id))


def compare(session, case_id, proposal, request, summary=None, own=()):
    """{'outcome': 'match'|'differs'|'not_comparable'|'no_saved', ...}. Read only."""
    facts = copy_facts(proposal, request, summary)
    candidates = saved_periods(session, case_id, facts, own)
    if not candidates:
        return dict(outcome='no_saved')
    compared = []
    for period, document, file, key in candidates:
        ledger = _ledger(session, period)
        compared.append((_differences(facts, period, ledger), period, document, file, key, ledger))
    agreeing = [entry for entry in compared if not entry[0]]
    holds = sorted(set(facts['holds']))
    if not sum(facts['payments'].values()):
        holds.append('no_payments')
    if holds or len(agreeing) != 1:
        best = min(compared, key=lambda entry: (len(entry[0]), str(entry[1].id)))
        differences = [dict(field=hold) for hold in holds] + best[0]
        if len(agreeing) > 1:
            differences.append(dict(field='several_saved_statements', saved=len(agreeing)))
        return dict(outcome='not_comparable' if holds else 'differs', saved=_link(best[2], best[3], best[4], best[1]),
                    saved_statements=len(candidates), differences=differences)
    _, period, document, file, key, ledger = agreeing[0]
    return dict(outcome='match', saved=_link(document, file, key, period), saved_statements=len(candidates),
                payments=sum(ledger.values()), opening=facts['opening'] is not None,
                closing=facts['closing'] is not None, differences=[])


def still_agrees(session, case_id, file, proposal, request, decision):
    """A stored set-aside stays only while the copy and the same saved statement still agree. Read only."""
    if not ENABLED or decision.get('basis') != BASIS:
        return False
    from services.financial.import_batches import assess
    try:
        _, summary = assess({**proposal, 'duplicate_disposition': None}, request)
    except Exception:
        return False
    result = compare(session, case_id, proposal, request, summary, own={(str(file.id), proposal.get('statement_id') or '')})
    retained = decision.get('retained') or {}
    return result['outcome'] == 'match' and result['saved'].get('source_document_id') == retained.get('source_document_id')


def _person_work(file, item, statement_key):
    from services.financial.recovery_readers import _person_disposition
    from services.financial.pending_statement_duplicates import METADATA_KEY
    metadata = file.metadata_ or {}
    if item.review_request or (metadata.get('financial_review_progress') or {}).get(statement_key):
        return True
    stored = (metadata.get(METADATA_KEY) or {}).get(statement_key)
    return bool(stored and _person_disposition(stored))


def settle_item(session, case_id, item, *, cache=None, apply=True):
    """Decide one held item (a copy of a saved account and period). Returns the outcome; writes when ``apply``.

    The caller holds the case lock. Outcomes: 'set_aside', 'differs', 'not_comparable', 'no_saved', 'skipped'.
    """
    from postgres.models.evidence import EvidenceFile
    from services.financial.file_visibility import financial_file_visibility
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.pending_statement_duplicates import _persist, _raw, _requires_review_comparison
    from services.financial.statement_import import read_statement_import
    from services.financial.import_batches import assess
    if not ENABLED or item.status != 'attention':
        return dict(outcome='skipped', why='switch_or_status')
    key = item.statement_key or ''
    query = select(EvidenceFile).where(EvidenceFile.id == item.file_id, EvidenceFile.case_id == case_id)
    if apply:
        query = query.with_for_update().execution_options(populate_existing=True)
    file = session.scalar(query)
    if file is None:
        return dict(outcome='skipped', why='unavailable')
    visibility = financial_file_visibility(file)
    if visibility['financial_removed'] or visibility['financial_imports_removed']:
        return dict(outcome='skipped', why='removed')
    if _person_work(file, item, key):
        return dict(outcome='skipped', why='person_work')
    try:
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
            currency=(item.summary or {}).get('currency') or None, statement_id=key or None, _cache=cache,
            _include_duplicate_disposition=False)
    except PdfMappingError:
        return dict(outcome='skipped', why='unreadable')
    if (proposal.get('current_import') or proposal.get('saved_review') or _requires_review_comparison(proposal)
            or proposal.get('not_payment_statement') or proposal.get('document_review')):
        return dict(outcome='skipped', why='not_a_held_copy')
    # Decided on the current reading (what any save would use); the decision is bound to it (its signature),
    # so a later reading makes it stale and the copy is held again.
    request = _raw(proposal)
    try:
        _, summary = assess({**proposal, 'duplicate_disposition': None}, request)
    except Exception:
        return dict(outcome='skipped', why='not_assessable')
    result = compare(session, case_id, proposal, request, summary, own={(str(file.id), key)})
    if result['outcome'] == 'no_saved':
        return result
    if not apply:
        return {**result, 'outcome': 'set_aside' if result['outcome'] == 'match' else result['outcome']}
    check = {name: value for name, value in result.items() if name != 'outcome'} | dict(outcome=result['outcome'])
    if result['outcome'] != 'match':
        if (item.summary or {}).get('saved_copy_check') != check:
            item.summary = {**(item.summary or {}), 'saved_copy_check': check}
            session.flush()
        return result
    saved = result['saved']
    retained = {name: saved[name] for name in ('evidence_file_id', 'statement_id', 'source_document_id', 'filename',
                                               'page_number')}
    decision = _persist(file, proposal, request, dict(status='ignored', label=LABEL, basis=BASIS, retained=retained,
        reason=REASON, saved_ledger_match=dict(statement_period_id=saved['statement_period_id'],
            payments=result['payments'], opening=result['opening'], closing=result['closing'])),
        None, matched_fields=MATCHED_FIELDS)
    item.status = 'duplicate_ignored'
    item.summary = {**(item.summary or {}), 'duplicate_disposition': decision, 'can_import': False, 'problems': [],
                    'problem_count': 0, 'saved_copy_check': check}
    session.flush()
    return {**result, 'outcome': 'set_aside'}
