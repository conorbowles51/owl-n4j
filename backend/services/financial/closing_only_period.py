"""Period dates for card statements that print only their closing date.

A Merrick card statement prints one date, its statement (billing-cycle
closing) date. Its start is not printed. Card billing cycles are contiguous:
a cycle begins the day after the previous cycle closed. So the start of one
statement is established by the source only where the immediately preceding
statement for the same card is present in the case, and that is shown by the
documents themselves:

* the same full card number on both statements;
* the earlier closing date is one billing cycle before this one (27 to 35
  days: monthly cycles vary by a few days with month length), with no other
  statement for the card closing in between;
* the earlier statement's printed New Balance is exactly this statement's
  printed Previous Balance.

Anything less leaves the start empty with a specific reason, so the period
stays held for a person. Nothing here is inferred from transaction dates or
from arithmetic on the rows; the derived start is recorded as derived, with
the cells it rests on, and never as a printed date.
"""
from datetime import date, timedelta

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile

MERRICK = 'merrick-card'
# Monthly billing cycles: shortest is February (28 days) less a few days of
# permitted closing-day variation; a skipped statement would be at least ~55.
CYCLE_DAYS = (27, 35)
_MEMO_LIMIT = 512
_memo = {}

HOLD_MESSAGES = {
    'no_previous_statement': (
        'This statement prints only its closing date. The previous statement for this card, '
        'closing about one month earlier, is not in this case, so the start date cannot be '
        'taken from it. Add the previous statement, or confirm that no start date is printed.'),
    'several_previous_statements': (
        'This statement prints only its closing date. More than one earlier statement for this '
        'card could be the previous one, so the start date was not taken from either. Compare '
        'them, then enter the start date or confirm that no start date is printed.'),
    'balance_unreadable': (
        'This statement prints only its closing date. The previous statement for this card was '
        'found, but its New Balance or this statement\'s Previous Balance could not be read, so '
        'it is not shown to be the immediately preceding statement. Check both balances, then '
        'enter the start date or confirm that no start date is printed.'),
    'balance_mismatch': (
        'This statement prints only its closing date. The previous statement for this card has a '
        'New Balance that differs from this statement\'s Previous Balance, so a statement may be '
        'missing between them. The start date was not taken from it. Compare both statements, '
        'then enter the start date or confirm that no start date is printed.'),
}


def _iso(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _digits(reference):
    digits = ''.join(ch for ch in reference or '' if ch.isdigit())
    return digits if 13 <= len(digits) <= 19 and '*' not in (reference or '') else ''


def _printed_balances(sources, currency):
    """The unique printed Previous and New Balance cells, or None for each.

    A value with any reading issue (including an unread dollar sign) is not
    used. Two readings of the same role are not resolved by choosing one.
    """
    from services.financial.statement_import_card_balances import merrick_summary_balances
    found = {'opening': [], 'closing': []}
    for source in sources:
        controls, _ = merrick_summary_balances(source, currency)
        for row_index, control in controls.items():
            role = control['fields']['description'].split(' ', 1)[0].lower()
            if role not in found:
                continue
            cell = next((c for row in source['rows'] if row['row_index'] == row_index for c in row['cells']
                         if str(c['column_index']) == control['fields']['balance_column']), None)
            found[role].append(dict(
                balance_minor=control['fields'].get('balance') if not control['issues'] else None,
                page_number=source['page_number'], table_index=source['table_index'], row_index=row_index,
                expected_text=cell['expected_text'] if cell else None))
    return {role: values[0] if len(values) == 1 else None for role, values in found.items()}


def _statement_facts(statement, sources, currency, *, file_id, filename):
    if statement.get('layout_id') != MERRICK or statement.get('date_conflict'):
        return None
    closing = _iso(statement.get('statement_date'))
    account = _digits(statement.get('account_reference'))
    if closing is None or not account:
        return None
    addresses = {(s['page_number'], s['table_index']) for s in statement.get('sources', [])}
    own = [s for s in sources if (s['page_number'], s['table_index']) in addresses]
    balances = _printed_balances(own, currency)
    return dict(file_id=str(file_id), filename=filename, statement_id=statement['id'], account=account,
                closing_date=closing.isoformat(), printed_statement_date=statement.get('printed_statement_date', ''),
                opening=balances['opening'], closing=balances['closing'])


def _file_facts(session, case_id, file, currency, cache):
    """Closing-only statements read from one file's stored source tables."""
    text = session.get(EvidenceDocumentText, file.id)
    if text is None:
        return []
    key = (str(file.id), text.content_sha256, str(text.engine_job_id), currency)
    if key in _memo:
        return _memo[key]
    from services.financial.candidate_sources import read_candidate_source
    from services.financial.statement_import_catalog import statement_catalog
    from postgres.models.evidence import EvidenceTableGeometry
    source_key = (str(case_id), str(file.id), text.content_sha256)
    if source_key not in cache:
        pages = list(session.scalars(select(EvidenceTableGeometry).where(
            EvidenceTableGeometry.evidence_file_id == file.id).order_by(EvidenceTableGeometry.page_number)))
        cache[source_key] = [read_candidate_source(session, case_id=case_id, evidence_file_id=file.id,
                                                   page_number=page.page_number, table_index=index)
                             for page in pages for index in range(len(page.payload or []))]
    sources = cache[source_key]
    catalog_key = ('catalog', source_key)
    if catalog_key not in cache:
        cache[catalog_key] = statement_catalog(sources)
    facts = [fact for statement in cache[catalog_key]['statements']
             if (fact := _statement_facts(statement, sources, currency, file_id=file.id,
                                          filename=file.original_filename)) is not None]
    if len(_memo) >= _MEMO_LIMIT:
        _memo.pop(next(iter(_memo)))
    _memo[key] = facts
    return facts


def _case_facts(session, case_id, currency, cache):
    from services.financial.file_visibility import financial_file_visibility
    files = session.scalars(select(EvidenceFile).join(
        EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id).where(
        EvidenceFile.case_id == case_id, EvidenceDocumentText.content.contains('MERRICK BANK'))
        .order_by(EvidenceFile.id))
    facts = []
    for file in files:
        if financial_file_visibility(file)['financial_removed']:
            continue
        try:
            facts.extend(_file_facts(session, case_id, file, currency, cache))
        except Exception:  # An unreadable neighbour establishes nothing.
            continue
    return facts


def closing_only_period_dates(session, *, case_id, file, selected, sources, currency, cache):
    """Return the period dates this statement's source establishes, with provenance.

    ``period_end`` is the printed closing date. ``period_start`` is filled
    only when the previous statement establishes it; otherwise
    ``period_start_hold`` says why not.
    """
    if not selected or selected.get('layout_id') != MERRICK or selected.get('date_conflict'):
        return None
    closing = _iso(selected.get('statement_date'))
    if closing is None:
        return None
    result = dict(period_end=closing.isoformat(), period_end_basis='printed_statement_date',
                  period_start='', period_start_basis='', period_start_evidence=None, period_start_hold=None)

    def hold(code, **detail):
        result['period_start_hold'] = dict(code=code, message=HOLD_MESSAGES[code], **detail)
        return result

    account = _digits(selected.get('account_reference'))
    if not account:
        return hold('no_previous_statement')
    this = _statement_facts(selected, sources, currency, file_id=file.id, filename=file.original_filename)
    # Other readings and exact copies of this statement close on the same
    # date, so only strictly earlier closings can be its predecessor.
    neighbours = [fact for fact in _case_facts(session, case_id, currency, cache) if fact['account'] == account
                  and not (fact['file_id'] == str(file.id) and fact['statement_id'] == selected['id'])]
    earlier = [fact for fact in neighbours if _iso(fact['closing_date']) < closing]
    window = [fact for fact in earlier
              if CYCLE_DAYS[0] <= (closing - _iso(fact['closing_date'])).days <= CYCLE_DAYS[1]]
    if not window:
        return hold('no_previous_statement')
    previous_dates = {fact['closing_date'] for fact in window}
    latest = max(_iso(fact['closing_date']) for fact in earlier)
    if len(previous_dates) != 1 or latest.isoformat() not in previous_dates:
        return hold('several_previous_statements', candidates=sorted(previous_dates | {latest.isoformat()}))
    opening = (this or {}).get('opening')
    closings = {(fact['closing'] or {}).get('balance_minor') for fact in window}
    if not opening or opening['balance_minor'] is None or None in closings:
        return hold('balance_unreadable')
    if closings != {opening['balance_minor']}:
        return hold('balance_mismatch')
    previous = sorted(window, key=lambda fact: (fact['file_id'], fact['statement_id']))[0]
    start = _iso(previous['closing_date']) + timedelta(days=1)
    result.update(period_start=start.isoformat(), period_start_basis='previous_statement_closing_date',
        period_start_evidence=dict(
            previous_closing_date=previous['closing_date'],
            previous_printed_statement_date=previous['printed_statement_date'],
            previous_evidence_file_id=previous['file_id'], previous_filename=previous['filename'],
            previous_statement_id=previous['statement_id'], previous_new_balance=previous['closing'],
            this_previous_balance=opening, copies=len(window)))
    return result
