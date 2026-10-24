"""Count each movement of an account once where online movement queries overlap (Neil, 2026-10-24).

A Santander online movement query ("Consulta de Movimientos") covers whatever
dates the person asked the bank for, so two queries of one account, or a query
and a statement already saved for that account, can print the same days. Saving
both whole would count those days' movements twice. The ruling: trim the
overlapping days from the query, so only its other dates are admitted, but only
where the documents themselves prove the overlap is the same money:

* the overlapping days are covered by a statement ALREADY SAVED for the same
  ledger account (same bank, account, currency), never by one still waiting
  (a waiting statement may never be saved, and its days would then be counted
  nowhere);
* every movement the query prints on those days equals, one for one, a movement
  that saved statement holds on the same days: date, amount, direction and
  running balance, nothing more and nothing less on either side;
* the saved statement covers the start or the end of the query (or both), never
  a stretch in its middle; where saved statements cover every printed day with
  exactly its movements, the query is wholly counted already and is kept out of
  the ledger (held, not saveable) with that reason;
* after the trim every remaining check still agrees: the opening is the running
  balance printed after the last trimmed movement before the kept dates, every
  kept running balance follows from it, and the closing (the printed one, or
  the running balance printed on the last kept movement when the end is
  trimmed) is reached. The printed credit and debit totals are proved on the
  whole query first; the kept part is checked against its own sums.

Anything else keeps the query held for overlap with the reason. Nothing is
deleted: a trimmed movement stays in the reading, excluded, citing the saved
statement that counts it (``covered_by``), and the derived opening, closing and
totals record the printed figures they replace. The trim is part of the
reading's revision, so a change in the saved statements it rests on makes any
prepared save of it stale (the import writer re-reads it under the case lock).
A query a person has already reviewed, or one already saved whole, is left as
it is. Switch: ``TRIM_OVERLAPS``.
"""
from copy import deepcopy
from datetime import date, timedelta

from sqlalchemy import select

# Neil, 2026-10-24: trim overlapping movement queries. Reverse: False (overlapping queries are held for a
# person to compare, as before).
TRIM_OVERLAPS = True
VERSION = 'overlap-trim-v1'
OPENING_BASIS = 'running_balance_before_kept_dates'
CLOSING_BASIS = 'running_balance_on_last_kept_movement'
TOTAL_BASIS = 'printed_total_less_covered_movements'

HOLD_MESSAGES = {
    'movements_differ': ('A saved statement of this account covers some of these dates, but its movements on those '
                         'dates are not exactly the ones this query prints (date, amount, direction and running '
                         'balance). Compare the two before saving.'),
    'covered_in_middle': ('A saved statement of this account covers dates in the middle of this query only, so the '
                          'query cannot be trimmed to one continuous period. Compare the two before saving.'),
    'fully_covered': ('Another statement covers every date of this query: saved statements of this account already '
                      'hold each of its movements, so saving it would count them twice. It is kept, not saved.'),
    'checks_differ': ('After leaving out the dates a saved statement covers, the remaining movements do not agree '
                      'with the balances and totals. Compare the two before saving.'),
    'balance_missing': ('A saved statement of this account covers some of these dates, but a running balance is '
                        'missing on one side, so the overlap cannot be proved to be the same movements. Compare the '
                        'two before saving.'),
}


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _signed(row):
    amount = int(row['fields']['amount_minor'])
    return amount if row['fields']['direction'] == 'credit' else -amount


def _control(rows, kind, description=None, direction=None):
    found = [r for r in rows if r['kind'] == kind and r['excluded']
             and (description is None or r['fields'].get('description') == description)
             and (direction is None or r['fields'].get('total_direction') == direction)]
    return found[0] if len(found) == 1 else None


def _movements(rows):
    """The query's movements, or None when any is not fully read (the trim needs every value)."""
    found = []
    for row in rows:
        if row['kind'] == 'unresolved' and not row['excluded']:
            return None
        if row['kind'] != 'transaction':
            continue
        fields = row['fields']
        if (row['excluded'] or row.get('issues') or not _day(fields.get('date'))
                or fields.get('direction') not in ('credit', 'debit')
                or not str(fields.get('amount_minor') or '').isdigit() or fields.get('balance') in (None, '')):
            return None
        found.append(row)
    return found


def _key(fields_date, amount, direction, balance):
    return (str(fields_date)[:10], int(amount), direction, int(balance))


def saved_neighbours(session, *, case_id, identity, currency, start, end, file, exclude_document_id=None):
    """Saved statements of the same ledger account whose saved period shares a date with ``start``..``end``.

    Exact copies of this file (same bytes, or the same original) are left out:
    a copy repeats this statement and is compared as a copy, never trimmed
    against. Each neighbour carries its admitted movements.
    """
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import (FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod,
                                           FinancialTransaction)
    from services.financial.source_lineage import lineage_id
    rows = session.execute(select(
        FinancialStatementPeriod.period_start, FinancialStatementPeriod.period_end,
        FinancialSourceDocument.id, FinancialSourceDocument.evidence_file_id)
        .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
        .join(FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id)
        .where(FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.case_id == case_id,
               FinancialAccount.case_id == case_id, FinancialAccount.identity_key == identity,
               FinancialStatementPeriod.currency == currency, FinancialSourceDocument.status == 'admitted',
               FinancialStatementPeriod.period_start <= end, FinancialStatementPeriod.period_end >= start)).all()
    own = lineage_id(file)
    found = []
    for period_start, period_end, document_id, evidence_file_id in rows:
        if exclude_document_id and str(document_id) == str(exclude_document_id):
            continue
        other = session.get(EvidenceFile, evidence_file_id)
        if other is not None and (other.sha256 == file.sha256 or lineage_id(other) == own):
            continue
        movements = session.execute(select(
            FinancialTransaction.transaction_date, FinancialTransaction.posted_date, FinancialTransaction.amount_minor,
            FinancialTransaction.direction, FinancialTransaction.running_balance_minor)
            .where(FinancialTransaction.source_document_id == document_id,
                   FinancialTransaction.ledger_status == 'admitted')).all()
        found.append(dict(source_document_id=str(document_id), evidence_file_id=str(evidence_file_id),
                          period_start=period_start, period_end=period_end,
                          movements=[(t_date or posted, amount, direction, balance)
                                     for t_date, posted, amount, direction, balance in movements]))
    return found


def plan_trim(rows, *, start, end, neighbours):
    """The trim the saved neighbours establish for a query's rows: None, ('held', code) or ('trim', plan).

    Pure: ``rows`` are the query's reading, ``start``/``end`` its printed dates,
    ``neighbours`` saved statements as :func:`saved_neighbours` returns them.
    """
    if not neighbours:
        return None
    movements = _movements(rows)
    if movements is None:
        return None
    cut_start, cut_end, covers = start, end, []
    for n in neighbours:
        low, high = max(start, n['period_start']), min(end, n['period_end'])
        if n['period_start'] <= start and n['period_end'] >= end:
            # Every printed date is saved already (exact copies of this file are compared as copies, never
            # here): proved the same money below, the query is wholly counted and stays out of the ledger.
            cut_start, cut_end = end + timedelta(days=1), start
        elif n['period_start'] <= start:
            cut_start = max(cut_start, high + timedelta(days=1))
        elif n['period_end'] >= end:
            cut_end = min(cut_end, low - timedelta(days=1))
        else:
            return ('held', 'covered_in_middle')
        ours = [r for r in movements if low <= _day(r['fields']['date']) <= high]
        theirs = [m for m in n['movements'] if m[0] is not None and low <= m[0] <= high]
        if any(m[3] is None for m in theirs):
            return ('held', 'balance_missing')
        if sorted(_key(r['fields']['date'], r['fields']['amount_minor'], r['fields']['direction'], r['fields']['balance'])
                  for r in ours) != sorted(_key(m[0].isoformat(), m[1], m[2], m[3]) for m in theirs):
            return ('held', 'movements_differ')
        covers.append(dict(source_document_id=n['source_document_id'], evidence_file_id=n['evidence_file_id'],
                           period_start=n['period_start'].isoformat(), period_end=n['period_end'].isoformat(),
                           overlap_start=low.isoformat(), overlap_end=high.isoformat(), movements=len(ours)))
    if cut_start > cut_end:
        return ('held', 'fully_covered')
    dated = [(_day(r['fields']['date']), r) for r in movements]
    before = [r for d, r in dated if d < cut_start]
    kept = [r for d, r in dated if cut_start <= d <= cut_end]
    after = [r for d, r in dated if d > cut_end]
    # The printed order is oldest first: the trimmed movements are the first and the last lines.
    if movements != before + kept + after:
        return ('held', 'checks_differ')
    opening = _control(rows, 'balance', 'Opening Balance')
    closing = _control(rows, 'balance', 'Closing Balance')
    credit = _control(rows, 'statement_total', direction='credit')
    debit = _control(rows, 'statement_total', direction='debit')
    if not opening or opening['fields'].get('balance') in (None, '') or not closing \
            or closing['fields'].get('balance') in (None, ''):
        return ('held', 'checks_differ')
    # The whole query first: derived opening, every printed running balance, printed closing and totals.
    running = int(opening['fields']['balance'])
    for row in movements:
        running += _signed(row)
        if running != int(row['fields']['balance']):
            return ('held', 'checks_differ')
    if running != int(closing['fields']['balance']):
        return ('held', 'checks_differ')
    for control, direction in ((credit, 'credit'), (debit, 'debit')):
        if control is not None and (control['fields'].get('balance') in (None, '') or int(control['fields']['balance'])
                                    != sum(int(r['fields']['amount_minor']) for r in movements
                                           if r['fields']['direction'] == direction)):
            return ('held', 'checks_differ')
    new_opening = int(before[-1]['fields']['balance']) if before else int(opening['fields']['balance'])
    new_closing = (int(kept[-1]['fields']['balance']) if kept else new_opening) if after else int(closing['fields']['balance'])
    running = new_opening
    for row in kept:
        running += _signed(row)
    if running != new_closing:
        return ('held', 'checks_differ')
    return ('trim', dict(period_start=cut_start.isoformat(), period_end=cut_end.isoformat(),
                         printed_period_start=start.isoformat(), printed_period_end=end.isoformat(),
                         covers=covers, before=[r['id'] for r in before], after=[r['id'] for r in after],
                         opening_minor=str(new_opening), closing_minor=str(new_closing),
                         kept_credit_minor=str(sum(int(r['fields']['amount_minor']) for r in kept
                                                   if r['fields']['direction'] == 'credit')),
                         kept_debit_minor=str(sum(int(r['fields']['amount_minor']) for r in kept
                                                  if r['fields']['direction'] == 'debit'))))


def apply_trim(rows, plan):
    """Rows with the trim applied: covered movements excluded and cited, derived controls recorded."""
    rows = deepcopy(rows)
    covered = set(plan['before']) | set(plan['after'])
    for row in rows:
        fields = row['fields']
        if row['id'] in covered:
            day = fields['date']
            cover = next(c for c in plan['covers'] if c['overlap_start'] <= day <= c['overlap_end'])
            row['excluded'] = True
            fields['covered_by'] = {k: cover[k] for k in ('source_document_id', 'evidence_file_id',
                                                          'period_start', 'period_end')}
            row['covered_reason'] = (f"Counted once: the saved statement of this account for {cover['period_start']} "
                                     f"to {cover['period_end']} holds this movement.")
        elif row['kind'] == 'balance' and row['excluded'] and fields.get('description') == 'Opening Balance' \
                and plan['before']:
            fields.update(balance_derivation=dict(trimmed_from=fields.get('balance'), basis_before=fields.get('balance_basis'),
                                                  derivation_before=fields.get('balance_derivation'),
                                                  after_movement_id=plan['before'][-1]),
                          balance=plan['opening_minor'], balance_basis=OPENING_BASIS)
        elif row['kind'] == 'balance' and row['excluded'] and fields.get('description') == 'Closing Balance' \
                and plan['after']:
            fields.update(balance_derivation=dict(printed_closing_minor=fields.get('balance'),
                                                  first_trimmed_movement_id=plan['after'][0]),
                          balance=plan['closing_minor'], balance_basis=CLOSING_BASIS)
        elif row['kind'] == 'statement_total' and row['excluded'] and covered \
                and fields.get('total_direction') in ('credit', 'debit'):
            fields.update(printed_total_minor=fields.get('balance'), total_basis=TOTAL_BASIS,
                          balance=plan['kept_credit_minor' if fields['total_direction'] == 'credit' else 'kept_debit_minor'])
    return rows


def overlap_trim(session, *, case_id, file, selected, rows, metadata, currency, statement_id, current):
    """(rows, trim) for a movement query whose dates a saved statement of its account partly covers.

    ``trim`` is None when nothing applies, else a dict recorded on the reading:
    ``status`` 'trimmed' (with the kept dates and what covers the rest) or
    'held' (with the reason the overlap could not be proved).
    """
    from services.financial.statement_import_santander_query import FORM
    if not TRIM_OVERLAPS or not selected or selected.get('form') != FORM or not currency:
        return rows, None
    from services.financial.statement_progress import review_progress
    progress = review_progress(file, statement_id)
    if progress and (progress.get('saved_by') or {}).get('name') != 'System':
        return rows, None  # A person's review of this query stands as it is.
    start, end = _day(metadata.get('period_start')), _day(metadata.get('period_end'))
    if not start or not end or start > end:
        return rows, None
    if current is not None:
        # Already saved: re-derive only the trim it was saved with; one saved whole stays whole.
        saved = (current.metadata_ or {}).get('statement_import_request') or {}
        if (saved.get('period_start'), saved.get('period_end')) == (start.isoformat(), end.isoformat()):
            return rows, None
    from services.financial.statement_import_overlap import scope
    own = scope(dict(institution=metadata.get('institution'), account_number=metadata.get('account_number'),
                     currency=currency, period_start=start.isoformat(), period_end=end.isoformat(),
                     account_reference_kind=metadata.get('account_reference_kind') or None))
    if own is None or not own.get('full_reference'):
        return rows, None
    neighbours = saved_neighbours(session, case_id=case_id, identity=own['identity'], currency=currency,
                                  start=start, end=end, file=file,
                                  exclude_document_id=current.id if current is not None else None)
    planned = plan_trim(rows, start=start, end=end, neighbours=neighbours)
    if planned is None:
        return rows, None
    if planned[0] == 'held':
        return rows, dict(version=VERSION, status='held', code=planned[1], message=HOLD_MESSAGES[planned[1]])
    plan = planned[1]
    return apply_trim(rows, plan), dict(version=VERSION, status='trimmed', **plan)
