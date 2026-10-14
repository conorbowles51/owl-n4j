"""Source proof of a quiet period from the statement's own printed totals.

Mexican statements (Santander, Kapital, Monex, Scotiabank) print, for each
account section, the bank's own deposit and withdrawal totals beside the
opening and closing balances. A section proves it had no activity only when
the page itself shows all of:

- exactly one opening and one closing balance, both readable and equal;
- a printed deposit total and a printed withdrawal total, each read exactly as
  zero (for Scotiabank, every amount of its printed activity chart);
- no payment candidate, dated line or movement line inside the section
  (checked by the family's own guard);
- the printed statement period.

Equal balances alone never establish no activity, and an unread or missing
total is never treated as zero. Anything short of the full proof returns a
held result naming what was missing; the investigator's confirmation is then
still required. Admission binds the proof to the exact rows it cites (see
``statement_admission.source_proves_no_activity``): editing a cited balance,
total, period date or the currency moves the basis to the investigator.
"""
from services.financial.import_issues import calendar_date

METHOD = 'printed-zero-totals-v1'
BASIS = 'printed_zero_totals'


def held(family, reason, message, **extra):
    return dict(verified=False, method=METHOD, family=family, reason=reason, message=message, **extra)


def _cite(row):
    return dict(row_id=row['id'], page_number=row.get('page_number'),
        text=' '.join(c.get('expected_text', '').strip() for c in row.get('source_cells') or []).strip()[:300])


def zero_totals_evidence(rows, statement, currency, *, family, guard=None, zero_cells=None, printed_currency=None):
    """Decide whether a proposed section's printed controls prove no activity.

    ``rows`` are the section proposal's rows. ``guard`` is called only after
    the printed controls agree; it returns None or a ``(reason, message)``
    pair describing source text that could be an unread payment. For layouts
    whose zero amounts are printed outside the proposal rows (Scotiabank's
    activity chart), ``zero_cells`` lists those printed cells, already checked
    as explicit zeros by the reader, in place of the two total rows.
    The review currency must equal the currency printed for the section (the
    statement's own ``currency``, or ``printed_currency`` for layouts that
    print it only in the header).
    Returns None when the section has payment candidates (not a quiet question).
    """
    if statement.get('assignment_only'):
        return None
    if any(not row['excluded'] for row in rows):
        return None
    balances = [row for row in rows if row['kind'] == 'balance']
    openings = [row for row in balances if row['fields'].get('description') == 'Opening Balance']
    closings = [row for row in balances if row['fields'].get('description') == 'Closing Balance']
    totals = {direction: [row for row in rows if row['kind'] == 'statement_total'
        and not row['fields'].get('total_scope') and row['fields'].get('total_direction') == direction]
        for direction in ('credit', 'debit')}
    if (len(openings) != 1 or len(closings) != 1 or len(balances) != 2
            or (zero_cells is None and any(len(found) != 1 for found in totals.values()))
            or (zero_cells is not None and (any(totals.values()) or not zero_cells))):
        return held(family, 'controls_missing', 'The opening balance, closing balance and printed deposit and withdrawal totals of this account section were not all read exactly once. Check the page before confirming that it contains no transactions.')
    opening, closing = openings[0], closings[0]
    zero_rows = [] if zero_cells is not None else [totals['credit'][0], totals['debit'][0]]
    page = opening.get('page_number')
    controls = [opening, closing, *zero_rows]
    if any(row['issues'] or row['fields'].get('balance') in (None, '') for row in controls):
        return held(family, 'control_unreadable', 'A printed balance or total of this account section could not be read. Check the page before confirming that it contains no transactions.', page_number=page)
    if any(row['fields']['balance'] != '0' for row in zero_rows):
        return held(family, 'totals_not_zero', 'The printed deposit or withdrawal total is not zero, so money moved in this period. Check the page for transactions that were not read.', page_number=page)
    if opening['fields']['balance'] != closing['fields']['balance']:
        return held(family, 'endpoints_differ', 'The opening and closing balances differ, so money moved in this period. Check the page for transactions that were not read.', page_number=page)
    if not calendar_date(statement.get('period_start') or '') or not calendar_date(statement.get('period_end') or ''):
        return held(family, 'period_dates', 'The printed statement period was not read. Check the page before confirming that it contains no transactions.', page_number=page)
    printed_currency = statement.get('currency') or printed_currency
    if not printed_currency or currency != printed_currency:
        return held(family, 'currency_differs', 'The currency of this review differs from the currency printed for this account section. Check the currency before confirming that it contains no transactions.', page_number=page)
    problem = guard() if guard else None
    if problem:
        return held(family, problem[0], problem[1], page_number=page)
    return dict(verified=True, method=METHOD, basis=BASIS, family=family, reason='printed_zero_totals',
        message='The statement prints zero deposits and zero withdrawals for this account section, and its opening and closing balances are equal.',
        page_number=page, opening_row_id=opening['id'], closing_row_id=closing['id'],
        zero_total_row_ids=[row['id'] for row in zero_rows],
        balance_minor=opening['fields']['balance'], currency=currency,
        period_start=statement.get('period_start'), period_end=statement.get('period_end'),
        cited=[_cite(row) for row in controls] + [dict(page_number=(c.get('locator') or {}).get('page'),
            text=c.get('expected_text', '').strip()[:300], locator=c.get('locator')) for c in zero_cells or []])


LINE_METHOD = 'printed-no-transactions-line-v1'
LINE_BASIS = 'printed_no_transactions'


def printed_line_evidence(rows, statement, currency, sources, *, family):
    """Source proof of a quiet period from a line the statement prints inside the section ('No Transactions
    This Period'), found by the general reader between the section's equal opening and closing balances.

    Verified only when, again on the proposal: nothing but excluded rows was read, exactly one opening and
    one closing balance row are read and equal, the cited line still reads as a no-activity phrase, the
    printed period is read and the review currency is the currency read for the section. Admission binds
    the proof to the two balance rows (``statement_admission.source_proves_no_activity``). Returns None
    when the reader did not prove the period from such a line (not this proof's question).
    """
    from services.financial.statement_engine import NO_TRANSACTIONS
    from services.financial.statement_engine_vocabulary import fold
    engine = statement.get('engine') or {}
    cited = engine.get('no_transactions_row')
    if engine.get('basis') != LINE_BASIS or not engine.get('proved') or not cited or len(cited) != 3:
        return None
    if statement.get('assignment_only') or any(not row['excluded'] for row in rows):
        return None

    def refuse(reason, message):
        return dict(verified=False, method=LINE_METHOD, family=family, reason=reason, message=message)
    balances = [row for row in rows if row['kind'] == 'balance']
    openings = [row for row in balances if row['fields'].get('description') == 'Opening Balance']
    closings = [row for row in balances if row['fields'].get('description') == 'Closing Balance']
    if len(openings) != 1 or len(closings) != 1 or len(balances) != 2:
        return refuse('controls_missing', 'The opening and closing balances of this account section were not each read exactly once. Check the page before confirming that it contains no transactions.')
    opening, closing = openings[0], closings[0]
    if any(row['issues'] or row['fields'].get('balance') in (None, '') for row in (opening, closing)):
        return refuse('control_unreadable', 'A printed balance of this account section could not be read. Check the page before confirming that it contains no transactions.')
    if opening['fields']['balance'] != closing['fields']['balance']:
        return refuse('endpoints_differ', 'The opening and closing balances differ, so money moved in this period. Check the page for transactions that were not read.')
    page, table, index = cited
    source = next((s for s in sources if s['page_number'] == page and s['table_index'] == table), None)
    line = next((r for r in (source or {}).get('rows', []) if r['row_index'] == index), None)
    text = ' '.join(c.get('expected_text', '').strip() for c in (line or {}).get('cells', [])).strip()
    if not line or ' '.join(fold(text).split()) not in NO_TRANSACTIONS:
        return refuse('line_missing', 'The line saying that nothing moved in this account section could not be found again. Check the page before confirming that it contains no transactions.')
    if not calendar_date(statement.get('period_start') or '') or not calendar_date(statement.get('period_end') or ''):
        return refuse('period_dates', 'The printed statement period was not read. Check the page before confirming that it contains no transactions.')
    if not statement.get('currency') or currency != statement['currency']:
        return refuse('currency_differs', 'The currency of this review differs from the currency read for this account section. Check the currency before confirming that it contains no transactions.')
    return dict(verified=True, method=LINE_METHOD, basis=LINE_BASIS, family=family, reason=LINE_BASIS,
                message='The statement prints that this account section had no transactions in the period, and its opening and closing balances are equal.',
                page_number=page, opening_row_id=opening['id'], closing_row_id=closing['id'], zero_total_row_ids=[],
                balance_minor=opening['fields']['balance'], currency=currency,
                period_start=statement.get('period_start'), period_end=statement.get('period_end'),
                cited=[_cite(opening), _cite(closing), dict(page_number=page, text=text[:300],
                                                             locator=(line['cells'][0].get('locator') if line['cells'] else None))])
