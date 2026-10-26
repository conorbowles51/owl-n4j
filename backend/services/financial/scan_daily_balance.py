"""A scanned M&T checking statement held because its scan misread a date or a digit, read from its printed columns.

M&T prints its account activity in three amount columns under one heading
line (``CREDITS (+)``, ``OTHER DEBITS (-)``, ``BALANCE``): a line's amount sits
under the credits or the debits heading, and the last line of each day also
prints the day's balance (sometimes on its second, continuation line). A scan
read by OCR can misread a month's first figure (``41/05/2024`` for 11/05) or
lose one figure of an amount (``?,400.00``). The general reader then reads
the rest of the period as no movement at all, and holds it: no reading of the
columns reconciles.

This reading is used only for such a held period of the M&T layout, and only
when every printed figure agrees:

* each line is dated inside the printed statement period, in printed order;
  a month that is no month (``41``) is the one month of the period whose
  second figure is the one printed;
* each line has exactly one amount, under the credits or the debits heading;
  one figure printed as ``?`` is the one digit the day's printed balance
  fixes (one such figure per printed balance at most);
* every printed daily balance equals the opening plus the lines before it,
  and the last one and the printed ending balance equal the closing;
* the account summary's beginning and ending balances are the period's, and
  its counts and totals of credits (plus interest) and of checks and debits
  equal the lines read.

Anything else returns None and the held reading stands. Nothing is derived
from the totals: they only confirm what was read. Switch
``LOUPE_FINANCIAL_SCAN_DAILY_BALANCE``.
"""
import os
import re
from datetime import date

ENABLED = os.environ.get('LOUPE_FINANCIAL_SCAN_DAILY_BALANCE', '1').strip().lower() not in ('0', 'false', 'off', 'no')
PROFILE = 'mt-bank'
HOLD_REASON = 'not_reconciled'
DATE_BASIS = 'month_figure_fixed_by_printed_period'
AMOUNT_BASIS = 'figure_fixed_by_printed_daily_balance'
LAST_REFUSAL = {}

_MONEY = re.compile(r'^\$?((?:\d{1,3}(?:,\d{3})+|\d+))\.(\d{2})$')
_UNREAD_MONEY = re.compile(r'^\$?([\d?]{1,3}(?:,[\d?]{3})*)\.([\d?]{2})$')
_DATE = re.compile(r'^(\S)(\S)/(\d{2})/(\d{4})(?:\s*\|\s*(.*))?$')


def _refuse(step, row=None):
    LAST_REFUSAL.clear()
    LAST_REFUSAL.update(step=step, row=row)
    return None


def _rect(cell):
    rect = (cell.get('locator') or {}).get('rect')
    return rect if isinstance(rect, list) and len(rect) == 4 else None


def _money(text):
    match = _MONEY.match((text or '').strip())
    return int(match[1].replace(',', '')) * 100 + int(match[2]) if match else None


def _unread_money(text):
    """The digit pattern of an amount with exactly one figure printed as ``?`` (``'?400.00'`` -> ``'?40000'``), or None."""
    text = (text or '').strip()
    match = _UNREAD_MONEY.match(text)
    if not match or text.count('?') != 1:
        return None
    return match[1].replace(',', '') + match[2]


def _fits(pattern, value):
    digits = str(value)
    return (value > 0 and len(digits) == len(pattern) and digits[0] != '0'
            and all(p == '?' or p == d for p, d in zip(pattern, digits)))


def _heading(row):
    """(credit|debit boundary, debit|balance boundary, left edge of the amounts) of the activity heading, or None."""
    names = {re.sub(r'\s+', ' ', c['expected_text'].strip().upper()): c for c in row['source_cells']}
    cells = [names.get(name) for name in ('CREDITS (+)', 'OTHER DEBITS (-)', 'BALANCE')]
    if any(cell is None or _rect(cell) is None for cell in cells):
        return None
    credit, debit, balance = (_rect(cell) for cell in cells)
    if not credit[2] < debit[0] < debit[2] < balance[0]:
        return None
    return (credit[2] + debit[0]) / 2, (debit[2] + balance[0]) / 2, credit[0] - (credit[2] - credit[0])


def _line_date(text, start, end):
    """``(date, basis or None, description)`` of a movement line's leading date, or None when it opens with none."""
    match = _DATE.match(text.strip())
    if not match:
        return None
    first, second, day, year = match[1], match[2], int(match[3]), int(match[4])
    description = (match[5] or '').strip()
    if first.isdigit() and second.isdigit():
        try:
            printed = date(year, int(first + second), day)
        except ValueError:
            printed = None
        if printed is not None:
            return (printed, None, description) if start <= printed <= end else ('outside', None, description)
    if not second.isdigit():
        return ('unread', None, description)
    # The month printed is no month: its first figure was misread. The period fixes it, when only one fits.
    fits = []
    for month in range(1, 13):
        if month % 10 != int(second):
            continue
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        if start <= value <= end:
            fits.append(value)
    return (fits[0], DATE_BASIS, description) if len(fits) == 1 else ('unread', None, description)


def _summary(rows):
    """The account summary line: (beginning, credit count, credits, check count, checks, debit count, debits,
    interest, ending), from its nine printed values, or None."""
    found = []
    for row in rows:
        texts = [c['expected_text'].strip() for c in row['source_cells']]
        if len(texts) != 9:
            continue
        values = [_money(t) if i not in (1, 3, 5) else (int(t) if re.fullmatch(r'\d{1,4}', t) else None)
                  for i, t in enumerate(texts)]
        if all(v is not None for v in values) and all(texts[i].startswith('$') for i in (0, 2, 4, 6, 8)):
            found.append(values)
    return found[0] if len(found) == 1 else None


def scan_rows(statement, currency):
    """The rows of a held M&T period read from its printed columns, or None (the held reading stands)."""
    if not ENABLED:
        return _refuse('switch_off')
    engine = statement.get('engine') or {}
    if engine.get('proved') or engine.get('reason') != HOLD_REASON or statement.get('engine_profile') != PROFILE:
        return _refuse('not_this_hold')
    if statement.get('balance_convention') != 'asset_balance' or not currency or statement.get('currency') != currency:
        return _refuse('convention_or_currency')
    try:
        start, end = date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end'])
    except (KeyError, TypeError, ValueError):
        return _refuse('period')
    rows = [dict(r, fields=dict(r['fields']), issues=list(r['issues'])) for r in statement.get('_rows') or []
            if not r.get('engine_hold')]
    balances = {}
    for row in rows:
        if row['kind'] == 'balance':
            balances.setdefault(row['fields'].get('description'), []).append(row)
    if any(len(balances.get(name, ())) != 1 for name in ('Opening Balance', 'Closing Balance')):
        return _refuse('balances')
    try:
        opening = int(balances['Opening Balance'][0]['fields']['balance'])
        closing = int(balances['Closing Balance'][0]['fields']['balance'])
    except (KeyError, TypeError, ValueError):
        return _refuse('balances')
    summary = _summary(rows)
    if summary is None:
        return _refuse('summary_unread')
    beginning, credit_count, credits, check_count, checks, debit_count, debits, interest, ending = summary
    if (beginning, ending) != (opening, closing) or opening + credits + interest - checks - debits != closing:
        return _refuse('summary_does_not_add_up')

    # The movement lines, page by page, from the activity heading to the ending balance.
    lines, heading, ended, opened = [], None, False, False
    for row in rows:
        if ended:
            break
        cells = row['source_cells']
        texts = [c['expected_text'].strip() for c in cells]
        found = _heading(row)
        if found:
            heading = found
            continue
        if heading is None or not texts:
            continue
        if texts[0].upper().startswith('PAGE ') or re.match(r'^ACCOUNT NUMBER|^M&.? BANK', texts[0].upper()):
            heading = None  # the page ends; the next page repeats its heading
            continue
        if texts[0].upper() == 'ENDING BALANCE':
            if len(texts) != 2 or _money(texts[1]) != closing:
                return _refuse('ending_balance', row['id'])
            ended = True
            continue
        merged = len(texts) > 1 and texts[1].startswith('|')
        first = ' '.join(texts[:2]) if merged else texts[0]
        dated = _line_date(first, start, end) if re.match(r'^\S\S/\d{2}/\d{4}', texts[0]) else None
        credit_edge, balance_edge, left = heading
        amounts = []
        for cell in cells:
            rect = _rect(cell)
            text = cell['expected_text'].strip()
            if rect is None or rect[0] < left or (_money(text) is None and _unread_money(text) is None):
                continue
            column = 'credit' if rect[2] < credit_edge else 'debit' if rect[2] < balance_edge else 'balance'
            amounts.append((column, text, cell))
        words = [c['expected_text'].strip() for c in cells if not any(c is a[2] for a in amounts)]
        if dated is None:
            # A continuation line: its words, and the day's balance when it prints it.
            if not lines or any(column != 'balance' for column, _, _ in amounts) or len(amounts) > 1:
                if any(r['kind'] in ('transaction', 'unresolved') for r in (row,)):
                    return _refuse('undated_money_line', row['id'])
                continue
            lines[-1]['rows'].append(row)
            lines[-1]['words'] += words
            if amounts:
                if lines[-1]['balance'] is not None:
                    return _refuse('two_balances', row['id'])
                lines[-1]['balance'] = _money(amounts[0][1])
            continue
        when, basis, description = dated
        if when in ('outside', 'unread'):
            return _refuse('date_' + when, row['id'])
        if description.upper() == 'BEGINNING BALANCE' and not opened:
            if [column for column, _, _ in amounts] != ['balance'] or _money(amounts[0][1]) != opening:
                return _refuse('beginning_balance', row['id'])
            opened = True
            continue
        moves = [a for a in amounts if a[0] != 'balance']
        printed = [a for a in amounts if a[0] == 'balance']
        if len(moves) != 1 or len(printed) > 1:
            return _refuse('line_amounts', row['id'])
        column, text, cell = moves[0]
        lines.append(dict(rows=[row], date=when, date_basis=basis, direction=column, cell=cell,
                          amount=_money(text), pattern=_unread_money(text) if _money(text) is None else None,
                          words=([description] if description else []) + words[2 if merged else 1:],
                          balance=_money(printed[0][1]) if printed else None))
    if not opened or not ended or not lines:
        return _refuse('activity_unread')
    if any(later['date'] < earlier['date'] for earlier, later in zip(lines, lines[1:])):
        return _refuse('dates_out_of_order')

    # Every printed daily balance, with at most one unread figure between two of them.
    running, pending = opening, []
    for line in lines:
        pending.append(line)
        if line['balance'] is None and line is not lines[-1]:
            continue
        target = line['balance'] if line['balance'] is not None else closing
        unread = [p for p in pending if p['amount'] is None]
        known = sum(p['amount'] * (1 if p['direction'] == 'credit' else -1) for p in pending if p['amount'] is not None)
        if len(unread) > 1:
            return _refuse('several_unread_figures', unread[0]['rows'][0]['id'])
        if unread:
            needed = (target - running - known) * (1 if unread[0]['direction'] == 'credit' else -1)
            if not _fits(unread[0]['pattern'], needed):
                return _refuse('unread_figure_not_fixed', unread[0]['rows'][0]['id'])
            unread[0].update(amount=needed, amount_basis=AMOUNT_BASIS)
            known += needed * (1 if unread[0]['direction'] == 'credit' else -1)
        running += known
        if running != target:
            return _refuse('daily_balance', line['rows'][0]['id'])
        pending = []
    if running != closing:
        return _refuse('closing')
    credit_lines = [line['amount'] for line in lines if line['direction'] == 'credit']
    debit_lines = [line['amount'] for line in lines if line['direction'] == 'debit']
    interest_lines = 1 if interest else 0
    if (len(credit_lines) != credit_count + interest_lines or sum(credit_lines) != credits + interest
            or len(debit_lines) != check_count + debit_count or sum(debit_lines) != checks + debits):
        return _refuse('summary_counts')

    read_ids = {row['id'] for line in lines for row in line['rows']}
    if any(row['kind'] in ('transaction', 'unresolved') and row['id'] not in read_ids for row in rows):
        return _refuse('other_money_line')
    by_id = {row['id']: row for row in rows}
    for row in rows:
        if row['id'] in read_ids:
            row.update(kind='header', excluded=True, fields={}, issues=[])
    for line in lines:
        item = by_id[line['rows'][0]['id']]
        fields = dict(description=' '.join(w for w in line['words'] if w), counterparty='',
                      date=line['date'].isoformat(), direction=line['direction'], amount_minor=str(line['amount']),
                      amount_column=str(line['cell']['column_index']), date_column='0', description_column='0')
        fields[line['direction']] = str(line['amount'])
        if line['date_basis']:
            fields['date_basis'] = line['date_basis']
        if line.get('amount_basis'):
            fields['amount_basis'] = line['amount_basis']
        if line['balance'] is not None:
            fields['balance'] = str(line['balance'])
        for extra in line['rows'][1:]:
            by_id[extra['id']]['fields']['parent_transaction_id'] = item['id']
            item.setdefault('continuation_sources', []).append(dict(
                page_number=extra['page_number'], table_index=extra['table_index'], row_index=extra['row_index'],
                source_cells=extra['source_cells']))
        item.update(kind='transaction', excluded=False, fields=fields, issues=[])
    LAST_REFUSAL.clear()
    return rows


def recover_held(statement, reading, sources, currency):
    """``scan_rows`` for one period the general reader held because no reading of its columns reconciles."""
    return scan_rows(statement, currency)
