"""Rows of a page whose reading failed, proposed from the stored reading and confirmed per page.

A held statement can lack payments the reader set aside: a line it could not
classify (kept as a header), or a payment whose amount columns it could not
settle (``unresolved``). Their printed cells are still in the stored reading.
This module proposes each such line as a payment, from its own cells only,
every value cited to the cell it came from:

* the date: the line's leading date cell, read in the statement's period;
* the amount and the running balance after it: the line's two printed money
  cells (exactly two, so the reading cannot pick between columns);
* the direction: the one the printed balances prove. The previous printed
  balance (the opening, or the balance after the line before) and the line's
  own printed balance after differ by exactly the printed amount, or the line
  is not proved. Three printed facts must agree, never a guess.

A page is confirmable with one action only when every proposed line on it is
proved this way, every payment already read on it agrees with the same chain,
the balance leaving the page is confirmed by the next printed step (the next
line chains from it, or it equals the printed closing), and every printed
total of the statement agrees with the rows once its confirmable pages are
applied. A line that breaks the chain, or lacks a readable field, is shown on
its own and needs its own edit. Nothing is saved here: ``apply_page`` returns
the edited review request, and the caller saves it as the confirming person's
review (``import_batches.save_review``), so the machine reading stays in the
proposal and only the confirmed values are used for totals and money flows.

Switch: ``LOUPE_FINANCIAL_PAGE_ROW_PROPOSALS`` (default OFF: ``1`` turns it on). Measured on the real
statement set (bench r14s-whole, r15-batch-work): no held statement has a page whose lines can be proved this
way, because every one also prints money-shaped lines outside any chain (summary blocks, interest and holdings
tables) that a confirmation must not skip. Off, no page proposal is offered anywhere, which is the behaviour
before this module existed. Turn it on when a reader leaves held statements whose pages it can prove.
"""
import hashlib
import json
import os
import re
from datetime import date, timedelta

PROOF = 'printed_balance_chain'
MONTHS = {**{m: i + 1 for i, m in enumerate(('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct',
                                             'nov', 'dic'))},
          **{m: i + 1 for i, m in enumerate(('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct',
                                             'nov', 'dec'))}, 'set': 9}
_LEADING_DATE = re.compile(r'^\s*(\d{1,2})(?:[/.\- ](\d{1,2})|[/.\- ]?([A-Za-z]{3}))(?:[/.\- ](\d{4}|\d{2}))?(?![\dA-Za-z])')
_MONEY = re.compile(r'^[\s$+\-(]*\d[\d,. ]*[.,]\d{2}\s*\)?\s*$')
# Any figure shaped like money, however damaged (``1,234.5?``, ``9,773,293 60``): a line carrying one that the
# chain does not account for could hide a payment between two proved balances.
_MONEY_SHAPED = re.compile(r'\d[.,]?\s?\d{2}\b|\d[.,]\d')
# The window around the printed period a line's date may fall in (late-posted card charges print before it).
EARLY, LATE = timedelta(days=45), timedelta(days=10)


def enabled():
    return os.environ.get('LOUPE_FINANCIAL_PAGE_ROW_PROPOSALS', '0') == '1'


def _iso(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def read_line_date(text, period_start, period_end):
    """The one calendar date a line's leading date token can be in the printed period, or None."""
    match = _LEADING_DATE.match(text or '')
    start, end = _iso(period_start), _iso(period_end)
    if not match or not end:
        return None
    day, month_number, month_name, year_text = match.groups()
    month_text = month_number or month_name
    month = int(month_text) if month_text.isdigit() else MONTHS.get(month_text.lower())
    if not month:
        return None
    low, high = (start or end - timedelta(days=62)) - EARLY, end + LATE
    years = ([int(year_text) + (2000 if len(year_text) == 2 else 0)] if year_text
             else sorted({low.year, high.year}))
    def readings(d, m):
        out = set()
        for year in years:
            try:
                out.add(date(year, m, d))
            except ValueError:
                pass
        return out
    day_first = readings(int(day), month)
    month_first = readings(month, int(day)) if month_text.isdigit() and int(day) != month else set()
    near = {v for v in day_first | month_first if low <= v <= high}
    if month_first and day_first:
        # Both orders are calendar dates: only a reading inside the printed period, with the other order far
        # outside it, is taken. Anything closer proposes nothing (the person enters the date).
        inside = {v for v in near if (start or end) <= v <= end}
        return inside.pop().isoformat() if len(inside) == 1 and len(near) == 1 else None
    return near.pop().isoformat() if len(near) == 1 else None


def _money(text, currency):
    from services.financial.suspect_amounts import read_amount, TextOrigin
    from services.financial.money import MoneyError
    if not _MONEY.match(text or ''):
        return None
    try:
        reading = read_amount(text, currency, TextOrigin.unknown).to_json()
    except MoneyError:
        return None
    return reading.get('minor_units') if reading.get('suspicion') == 'none' else None


def _candidate_kind(row):
    if row['id'].endswith(':engine_hold') or row['kind'] in ('balance', 'statement_total', 'manual_entry'):
        return None
    if row['kind'] == 'unresolved':
        return 'unsettled'
    if row['excluded'] and row['kind'] in ('header', 'text', 'unclassified', 'page_header', 'footer'):
        return 'set_aside'
    return None


def read_line(row, currency, period_start, period_end):
    """The payment one stored line prints, cell by cell: ``(values, missing)``."""
    cells = [c for c in row.get('source_cells') or [] if (c.get('expected_text') or '').strip()]
    values, missing, used = {}, [], set()
    for index, cell in enumerate(cells):
        when = read_line_date(cell['expected_text'], period_start, period_end)
        if when:
            values['date'] = dict(value=when, cell=cell['locator'], text=cell['expected_text'])
            used.add(index)
            break
    money = [(i, _money(c['expected_text'], currency)) for i, c in enumerate(cells) if i not in used]
    money = [(i, v) for i, v in money if v is not None]
    if len(money) == 2 and money[0][1] > 0:
        (ai, amount), (bi, balance) = money
        values['amount'] = dict(value=amount, cell=cells[ai]['locator'], text=cells[ai]['expected_text'])
        values['balance_after'] = dict(value=balance, cell=cells[bi]['locator'], text=cells[bi]['expected_text'])
        used |= {ai, bi}
    words = []
    for i, cell in enumerate(cells):
        if i in used and i not in [k for k, _ in money]:
            text = _LEADING_DATE.sub('', cell['expected_text'], count=1)
        elif i in used:
            continue
        else:
            text = cell['expected_text']
        if not _MONEY.match(text or '') and text.strip():
            words.append(text.strip())
    if words:
        values['description'] = ' '.join(words)[:4096]
    for name in ('date', 'amount', 'balance_after', 'description'):
        if name not in values:
            missing.append(name)
    return values, missing


def _signed(direction, amount, convention):
    up = 'debit' if convention == 'liability_owed' else 'credit'
    return amount if direction == up else -amount


def _direction(delta, convention):
    up, down = ('debit', 'credit') if convention == 'liability_owed' else ('credit', 'debit')
    return up if delta > 0 else down


def _int(value):
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def page_proposals(proposal, request=None):
    """Every statement page's proposed lines and whether one confirmation can accept them.

    ``{'pages': [...], 'opening': int|None, 'closing': int|None, 'totals': 'agree'|'disagree'|'unchecked'|'none',
    'blocked': reason or None}``; each page ``{'page_number', 'confirmable', 'reason', 'digest', 'lines': [...]}``,
    each line ``{'row_id', 'source', 'values', 'missing', 'chained', 'direction'}``. Empty pages list when the
    switch is off or nothing was set aside.
    """
    from services.financial.import_batches import initial_request
    result = dict(pages=[], opening=None, closing=None, totals='none', blocked=None)
    if not enabled():
        return result
    raw = request or initial_request(proposal)
    edits = {r['id']: r for r in raw['rows']}
    currency = raw.get('currency') or proposal.get('currency') or ''
    if not re.fullmatch(r'[A-Z]{3}', currency):
        result['blocked'] = 'currency'
        return result
    convention = (proposal.get('metadata') or {}).get('balance_convention')
    start, end = raw.get('period_start'), raw.get('period_end')
    statement_pages = set(proposal.get('statement_page_numbers') or proposal.get('page_numbers') or [])
    openings, closings, totals, sequence, unaccounted = [], [], [], [], 0
    for row in proposal.get('rows') or []:
        if row.get('page_number') not in statement_pages:
            continue
        edit = edits.get(row['id'], {})
        description = row['fields'].get('description')
        if row['kind'] == 'balance' and description in ('Opening Balance', 'Closing Balance'):
            value = _int(edit.get('balance_minor', row['fields'].get('balance')))
            (openings if description == 'Opening Balance' else closings).append(value)
            continue
        if row['kind'] == 'statement_total' and row['fields'].get('total_direction') in ('credit', 'debit'):
            totals.append((row['fields']['total_direction'], _int(row['fields'].get('balance'))))
            continue
        kind = _candidate_kind(row)
        untouched = edit.get('excluded', row['excluded']) == row['excluded'] and edit.get('amount_minor') in (None, '', '0')
        if kind and untouched:
            values, missing = read_line(row, currency, start, end)
            # A set-aside line is proposed only when it starts with a date and prints money: summary blocks
            # and headers do not, and a payment line of these layouts always does.
            if kind == 'unsettled' or 'date' in values:
                sequence.append(dict(row_id=row['id'], page_number=row['page_number'], source=kind, values=values,
                                     missing=missing))
            elif any(_MONEY_SHAPED.search(c.get('expected_text') or '') for c in row.get('source_cells') or []):
                unaccounted += 1
            continue
        # Every row the review includes is a payment of the chain, whatever the reader first called it (a
        # set-aside line a person or an earlier page confirmation entered counts exactly like a read one).
        if not edit.get('excluded', row['excluded']) and not row['id'].endswith(':engine_hold'):
            sequence.append(dict(row_id=row['id'], page_number=row['page_number'], source='read',
                                 amount=_int(edit.get('amount_minor')), direction=edit.get('direction'),
                                 balance=_int(edit.get('balance_minor'))))
    opening = openings[0] if openings and openings[0] is not None else None
    closing = closings[-1] if closings and closings[-1] is not None else None
    result.update(opening=opening, closing=closing, unaccounted_lines=unaccounted)
    lines = [s for s in sequence if s['source'] != 'read']
    if not lines:
        return result
    # Walk the printed balances from the opening. ``previous`` is the last balance the chain proved.
    previous, last = opening, None
    for step in sequence:
        if step['source'] == 'read':
            amount, direction = step['amount'], step['direction']
            if previous is not None and amount and direction in ('credit', 'debit'):
                expected = previous + _signed(direction, amount, convention)
                step['agrees'] = step['balance'] is None or step['balance'] == expected
                previous = step['balance'] if step['balance'] is not None else expected
            else:
                # Not verifiable from the chain: never counted as agreeing. Its printed balance, when read,
                # is where the chain continues from.
                step['agrees'] = False
                previous = step['balance']
            proved = step['agrees']
        else:
            values = step['values']
            amount = values.get('amount', {}).get('value')
            after = values.get('balance_after', {}).get('value')
            chained = (previous is not None and amount is not None and after is not None
                       and abs(after - previous) == amount and amount > 0)
            step['chained'] = chained
            step['direction'] = _direction(after - previous, convention) if chained else None
            previous = after
            proved = chained
        if last is not None:
            last['confirmed_by_next'] = proved
        last = step
    # The balance leaving the last step must be the printed closing.
    closes = closing is not None and previous == closing
    if last is not None:
        last['confirmed_by_next'] = closes
    applied = {}
    for step in lines:
        if step['chained'] and not step['missing']:
            applied[step['row_id']] = step
    if totals:
        sums = {'credit': 0, 'debit': 0}
        complete = all(s['chained'] and not s['missing'] for s in lines) and all(
            s.get('agrees', True) for s in sequence if s['source'] == 'read')
        for step in sequence:
            if step['source'] == 'read' and step['direction'] in sums and step['amount']:
                sums[step['direction']] += step['amount']
            elif step['row_id'] in applied:
                sums[step['direction']] += step['values']['amount']['value']
        if not complete:
            result['totals'] = 'unchecked'
        else:
            agree = all(value is not None and sums[d] == value for d, value in totals)
            result['totals'] = 'agree' if agree else 'disagree'
    pages = {}
    for step in sequence:
        pages.setdefault(step['page_number'], []).append(step)
    for number in sorted(pages):
        steps = pages[number]
        page_lines = [s for s in steps if s['source'] != 'read']
        if not page_lines:
            continue
        reason = None
        if opening is None:
            reason = 'opening_not_read'
        elif unaccounted:
            reason = 'unread_money_line'
        elif any(s['missing'] for s in page_lines):
            reason = 'line_incomplete'
        elif not all(s['chained'] for s in page_lines):
            reason = 'chain_broken'
        elif not all(s.get('agrees', True) for s in steps if s['source'] == 'read'):
            reason = 'read_row_disagrees'
        elif not steps[-1].get('confirmed_by_next'):
            reason = 'page_end_unconfirmed'
        elif result['totals'] == 'disagree':
            reason = 'printed_total_disagrees'
        elif result['totals'] == 'unchecked':
            reason = 'printed_total_unchecked'
        public = [dict(row_id=s['row_id'], source=s['source'], values=s['values'], missing=s['missing'],
                       chained=s['chained'], direction=s['direction']) for s in page_lines]
        pages[number] = dict(page_number=number, confirmable=reason is None, reason=reason, lines=public,
                             digest=hashlib.sha256(json.dumps(public, sort_keys=True, default=str).encode()).hexdigest())
        result['pages'].append(pages[number])
    return result


def apply_page(proposal, request, page_number, digest):
    """The review request with one confirmable page's proposed lines entered, or ValueError. Saves nothing."""
    proposals = page_proposals(proposal, request)
    page = next((p for p in proposals['pages'] if p['page_number'] == page_number), None)
    if page is None or not page['confirmable']:
        raise ValueError('This page has no proposal that can be confirmed in one step. Check its lines one by one.')
    if page['digest'] != digest:
        raise ValueError('The proposed lines of this page changed. Reload the statement before confirming.')
    rows = {r['id']: dict(r) for r in request['rows']}
    for line in page['lines']:
        row = rows[line['row_id']]
        values = line['values']
        row.update(excluded=False, date=values['date']['value'], amount_minor=str(values['amount']['value']),
                   direction=line['direction'], balance_minor=str(values['balance_after']['value']),
                   description=row.get('description') or values['description'], reason='')
    return dict(request, rows=[rows[r['id']] for r in request['rows']])


def _item_state(session, case_id, batch_id, item_id):
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial import import_batches
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.statement_import import read_statement_import
    from services.financial.statement_progress import review_progress
    from services.financial.effective_statement_review import batch_review_revision
    batch = import_batches.batch_for(session, case_id, batch_id)
    item = session.scalar(select(Item).where(Item.id == item_id, Item.batch_id == batch.id))
    if item is None or item.status == 'removed':
        raise PdfMappingError('Statement not found in this batch.', 404)
    file = session.get(EvidenceFile, item.file_id)
    saved = review_progress(file, item.statement_key)
    stored = item.review_request or (saved or {}).get('request')
    currency = (stored or {}).get('currency') or (item.summary or {}).get('currency') or None
    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id, currency=currency,
                                     statement_id=item.statement_key or None)
    request = (stored if stored and stored.get('expected_revision') == proposal['revision']
               else import_batches.initial_request(proposal))
    return item, proposal, request, batch_review_revision(item.review_request, saved)


def read_item_page_proposals(session, *, case_id, batch_id, item_id):
    """A held batch statement's page proposals, for review. Read only."""
    item, proposal, request, review_revision = _item_state(session, case_id, batch_id, item_id)
    result = page_proposals(proposal, request)
    return dict(result, item_id=str(item.id), expected_revision=proposal['revision'],
                expected_review_revision=review_revision, proof=PROOF, applied=False)


def confirm_item_page(session, *, case_id, batch_id, item_id, page_number, digest, expected_review_revision, actor):
    """Enter one confirmable page's lines as the confirming person's saved review. Never saves without a person.

    The page is proposed again from the stored reading at the moment of confirmation; the confirmation applies
    only if its lines are exactly the ones the person saw (``digest``). The save is the ordinary batch review
    save (``import_batches.save_review``): its revision check, its re-assessment, its history.
    """
    from services.financial import import_batches
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.statement_import import StatementReviewDraft
    if actor is None or not getattr(actor, 'user_id', None):
        raise PdfMappingError('A page of proposed lines is entered only when a person confirms it.', 403)
    item, proposal, request, review_revision = _item_state(session, case_id, batch_id, item_id)
    if review_revision != expected_review_revision:
        raise PdfMappingError('Another user saved changes to this review. Reopen it before confirming the page.', 409)
    page = next((p for p in page_proposals(proposal, request)['pages'] if p['page_number'] == page_number), None)
    try:
        edited = apply_page(proposal, request, page_number, digest)
    except ValueError as exc:
        raise PdfMappingError(str(exc), 409) from exc
    draft = StatementReviewDraft.model_validate(edited)
    result = import_batches.save_review(session, case_id=case_id, batch_id=batch_id, item_id=item_id, request=draft,
                                        expected_review_revision=expected_review_revision, actor=actor)
    return dict(result, page_number=page_number, lines=len(page['lines']))
