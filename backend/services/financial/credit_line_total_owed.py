"""Checking line of credit periods whose movement table prints the principal balance only (Navy Federal).

The statement's line of credit section prints a summary (Outstanding Principal Balance, Outstanding
Interest Charge, Outstanding Fees, Total Outstanding Balance, Credit Limit, Available Credit) and a
movement table with the columns Date, Transaction Detail, Amount, Fee(s), Interest, Principal, Balance.
Its Balance column (Beginning Balance, each line, Ending Balance) is the principal alone: an interest
charge does not move it and a payment moves it only by its principal part. The general reader therefore
holds the period ('principal_only_balance'), correctly, because the amount owed at the opening is not
printed in the period.

This reading records the period in amounts owed, the way the ledger keeps a credit line (a charge raises
the balance, a payment lowers it), only when every printed figure agrees, to the cent:

* the summary prints each of its four balances once, and principal + interest + fees = the total owed;
* every movement line is one of: a payment (its amount equals its printed fee, interest and principal
  parts, each printed as reducing), an advance (its amount equals its printed principal part, nothing
  else), or a charge (an interest or fee amount alone, no principal part); a line printed over two lines
  (the posting date, then 'Effective Date' with the amounts) is one movement;
* the Balance column chains: Beginning Balance, then each line's principal part, gives each printed
  balance, and the last is the Ending Balance and the summary's principal balance;
* a printed fee total for the period equals the fee charges read;
* the closing amount owed is the printed Total Outstanding Balance; the opening amount owed is that
  less the movements, it is not below the opening principal, and it equals the amount owed printed by
  the statement before it in the same document (its Total Outstanding Balance; where that one cell is
  unread, its Credit Limit less its Available Credit, a relation this statement must also print).

The opening is cited to this period's printed Beginning Balance line with its basis (``balance_basis``)
and every figure it rests on (``balance_derivation``), never recorded as what that line prints. Lines
carry no running balance (the printed one is the principal, not the amount owed). Anything else returns
None and the general reader's held reading stands. Identity (id, account, holder, dates) never changes.

Switch: LOUPE_FINANCIAL_CREDIT_LINE_TOTAL_OWED (default on; 0/false/off/no turns it off).
"""
import os
import re
from datetime import date, timedelta

ENABLED = os.environ.get('LOUPE_FINANCIAL_CREDIT_LINE_TOTAL_OWED', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
OPENING_BASIS = 'credit_line_total_owed_less_movements'
CLOSING_BASIS = 'credit_line_total_outstanding_balance'
HOLD_REASON = 'principal_only_balance'
# Why the last call refused (a step name, for diagnosis only; never part of a reading).
LAST_REFUSAL = {}

HEADING = ('DATE', 'TRANSACTION DETAIL', 'AMOUNT', 'FEES', 'INTEREST', 'PRINCIPAL', 'BALANCE')
COLUMNS = ('amount', 'fee', 'interest', 'principal', 'balance')
SUMMARY = {'OUTSTANDING PRINCIPAL BALANCE': 'principal', 'OUTSTANDING INTEREST CHARGE': 'interest',
           'OUTSTANDING FEES': 'fees', 'TOTAL OUTSTANDING BALANCE': 'total', 'CREDIT LIMIT': 'limit',
           'AVAILABLE CREDIT': 'available'}
_MONEY = re.compile(r'^\$?(\d{1,3}(?:,\d{3})*|\d+)\.(\d{2})\s?(-)?$')
_DATED = re.compile(r'^(\d{2})-(\d{2})(?:\s+(.*))?$')
_EFFECTIVE = re.compile(r'^EFFECTIVE DATE (\d{2})-(\d{2})-(\d{2})$')
# A value's right edge lies within this share of the page width of its heading's right edge (a printed
# trailing ' -' moves it right by about 0.6%).
ALIGN = 0.02


def _refuse(step, row=None):
    LAST_REFUSAL.clear()
    LAST_REFUSAL.update(step=step, row=row)
    return None


def _norm(value):
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9$.,\- ]', '', (value or '').upper())).strip()


def _money(value):
    """Signed minor units of a printed amount ('3,225.69', '$36.84', '38.23 -'), or None."""
    match = _MONEY.match((value or '').strip())
    if not match:
        return None
    minor = int(match[1].replace(',', '')) * 100 + int(match[2])
    return -minor if match[3] else minor


def _rect(cell):
    rect = (cell.get('locator') or {}).get('rect')
    return rect if isinstance(rect, list) and len(rect) == 4 else None


def _heading_edges(row):
    """{column: right edge} when the row is the movement table's heading, else None."""
    cells = row['source_cells']
    names = [re.sub(r'[^A-Z ]', '', c['expected_text'].upper()).strip() for c in cells]
    names = [re.sub(r'\s+', ' ', n) for n in names]
    if tuple(names) != HEADING or any(_rect(c) is None for c in cells):
        return None
    return {column: _rect(cell)[2] for column, cell in zip(COLUMNS, cells[2:])}


def _date_in(month, day, start, end):
    found = set()
    for year in {start.year, end.year}:
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        if start <= value <= end:
            found.add(value)
    return found.pop() if len(found) == 1 else None


def _summary(rows):
    """{name: (minor, row)} for the summary labels printed once each with a money value after them."""
    found, twice = {}, set()
    for row in rows:
        cells = row['source_cells']
        for index, cell in enumerate(cells):
            name = SUMMARY.get(_norm(cell['expected_text']))
            if name is None:
                continue
            value = _money(cells[index + 1]['expected_text']) if index + 1 < len(cells) else None
            if name in found:
                twice.add(name)
            found[name] = (value, row)
    for name in twice:
        found[name] = (None, found[name][1])
    return found


def _owed_printed(statement):
    """The amount owed a statement of this layout prints at its close: its Total Outstanding Balance, or,
    where that cell is unread, its Credit Limit less its Available Credit. None when neither is printed."""
    summary = _summary(statement.get('_rows') or [])
    total = (summary.get('total') or (None,))[0]
    if total is not None:
        return total, 'total_outstanding_balance'
    limit, available = (summary.get('limit') or (None,))[0], (summary.get('available') or (None,))[0]
    if limit is not None and available is not None and 'total' in summary and limit >= available:
        return limit - available, 'credit_limit_less_available_credit'
    return None, None


def _movements(rows, start, end):
    """(opening principal row, closing principal row, movements, fee total) read from the table lines, or a
    refusal step name."""
    edges, width = None, None
    opening = closing = None
    moves, fee_total, pending = [], None, None
    for index, row in enumerate(rows):
        found = _heading_edges(row)
        if found is not None:
            if pending is not None:
                return 'dangling_dated_line'
            edges = found
            width = max(_rect(c)[2] for c in row['source_cells'])
            continue
        if edges is None:
            continue
        cells = row['source_cells']
        first = _norm(cells[0]['expected_text']) if cells else ''
        if first.startswith('TOTAL FEES FOR THIS PERIOD') and len(cells) == 2:
            fee_total = _money(cells[1]['expected_text'])
            if fee_total is None:
                return 'fee_total_unread'
            continue
        texts, values = [], {}
        for cell in cells:
            value = _money(cell['expected_text'])
            if value is None:
                texts.append(cell['expected_text'].strip())
                continue
            rect = _rect(cell)
            if rect is None:
                return 'no_position'
            column = min(COLUMNS, key=lambda c: abs(edges[c] - rect[2]))
            if abs(edges[column] - rect[2]) > ALIGN * width or column in values:
                return 'value_outside_columns'
            values[column] = value
        text = ' '.join(texts)
        if pending is not None:
            effective = _EFFECTIVE.match(_norm(text))
            if effective is None or not values:
                return 'two_line_entry_unread'
            pending['values'], pending['effective'] = values, effective
            pending['rows'].append(row)
            moves.append(pending)
            pending = None
            continue
        if not values and _EFFECTIVE.match(_norm(text)):
            continue
        dated = _DATED.match(text)
        if dated is None:
            if values:
                return 'undated_money_line'
            continue
        when = _date_in(int(dated[1]), int(dated[2]), start, end)
        label = (dated[3] or '').strip()
        if when is None or not label:
            return 'date_outside_period'
        folded = _norm(label)
        if folded in ('BEGINNING BALANCE', 'ENDING BALANCE'):
            if set(values) != {'balance'}:
                return 'balance_line_unread'
            if folded == 'BEGINNING BALANCE':
                if opening is not None or moves:
                    return 'beginning_balance_twice'
                opening = (values['balance'], row)
            else:
                if closing is not None:
                    return 'ending_balance_twice'
                closing = (values['balance'], row)
            continue
        if opening is None or closing is not None:
            return 'movement_outside_table'
        move = dict(date=when, description=label, rows=[row], values=values, effective=None)
        if not values:
            pending = move
            continue
        moves.append(move)
    if pending is not None:
        return 'dangling_dated_line'
    if opening is None or closing is None:
        return 'table_bounds'
    return opening, closing, moves, fee_total


def _effect(values):
    """(direction, amount, effect on the amount owed, principal change) of one line, or None."""
    amount = values.get('amount')
    parts = {k: values[k] for k in ('fee', 'interest', 'principal') if k in values}
    if 'balance' not in values:
        return None
    if amount is None:
        # A charge: one interest or fee amount, raising what is owed; the principal does not move.
        if len(parts) != 1 or 'principal' in parts or next(iter(parts.values())) <= 0:
            return None
        value = next(iter(parts.values()))
        return 'debit', value, value, 0
    if amount <= 0 or not parts:
        return None
    if all(v < 0 for v in parts.values()) and -sum(parts.values()) == amount:
        return 'credit', amount, -amount, parts.get('principal', 0)
    if set(parts) == {'principal'} and parts['principal'] == amount:
        return 'debit', amount, amount, amount
    return None


def recover_rows(statement, reading, currency):
    """The rows of a held period of this layout in amounts owed, or None (the held reading stands)."""
    if not ENABLED:
        return _refuse('switch_off')
    engine = statement.get('engine') or {}
    if engine.get('proved') or engine.get('reason') != HOLD_REASON:
        return _refuse('not_principal_only')
    if statement.get('balance_convention') != 'liability_owed':
        return _refuse('not_amounts_owed')
    if not currency or (statement.get('currency') and currency != statement['currency']):
        return _refuse('currency')
    try:
        start, end = date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end'])
    except (KeyError, TypeError, ValueError):
        return _refuse('period')
    rows = [dict(r, fields=dict(r['fields']), issues=list(r['issues'])) for r in statement.get('_rows') or []
            if not r.get('engine_hold')]
    summary = _summary(rows)
    if any(name not in summary or summary[name][0] is None for name in ('principal', 'interest', 'fees', 'total')):
        return _refuse('summary_unread')
    principal, interest, fees, total = (summary[n][0] for n in ('principal', 'interest', 'fees', 'total'))
    if min(principal, interest, fees) < 0 or principal + interest + fees != total:
        return _refuse('summary_does_not_add_up')
    if 'limit' in summary or 'available' in summary:
        limit, available = (summary.get('limit') or (None,))[0], (summary.get('available') or (None,))[0]
        if limit is None or available is None or limit - available != total:
            return _refuse('available_credit_differs')
    read = _movements(rows, start, end)
    if isinstance(read, str):
        return _refuse(read)
    (opening_principal, opening_row), (closing_principal, closing_row), moves, fee_total = read
    if closing_principal != principal:
        return _refuse('principal_differs')
    balance, net, fees_charged = opening_principal, 0, 0
    for move in moves:
        effect = _effect(move['values'])
        if effect is None:
            return _refuse('line_unexplained', move['rows'][0]['id'])
        direction, amount, owed, principal_change = effect
        balance += principal_change
        if balance != move['values']['balance']:
            return _refuse('principal_chain', move['rows'][0]['id'])
        if direction == 'debit' and principal_change == 0 and 'fee' in move['values']:
            fees_charged += amount
        net += owed
        move.update(direction=direction, amount=amount)
    if balance != closing_principal:
        return _refuse('principal_chain_end')
    if fee_total is not None and fee_total != fees_charged:
        return _refuse('fee_total_differs')
    opening_owed = total - net
    if opening_owed < opening_principal:
        return _refuse('opening_below_principal')
    previous = [other for other in reading if other is not statement and other.get('period_end')
                and other['period_end'] == (start - timedelta(days=1)).isoformat()]
    printed = [(other, _owed_printed(other)) for other in previous]
    printed = [(other, value, basis) for other, (value, basis) in printed if value is not None]
    if len(printed) != 1:
        return _refuse('previous_statement')
    before, before_owed, before_basis = printed[0]
    if before_owed != opening_owed:
        return _refuse('previous_amount_owed_differs')

    by_id = {row['id']: row for row in rows}
    read_ids = {row['id'] for move in moves for row in move['rows']}
    if any(row['kind'] in ('transaction', 'unresolved') and row['id'] not in read_ids for row in rows):
        # A line the general reader read as money (or could not read) that this reading does not explain.
        return _refuse('other_money_line')
    for row in rows:
        if row['kind'] in ('balance', 'transaction', 'unresolved', 'statement_total', 'zero_line'):
            row.update(kind='header', excluded=True, fields={}, issues=[])
    by_id[opening_row['id']].update(kind='balance', excluded=True, fields=dict(
        description='Opening Balance', balance=str(opening_owed), balance_column=str(
            opening_row['source_cells'][-1]['column_index']),
        balance_basis=OPENING_BASIS, balance_derivation=dict(
            printed_beginning_principal_minor=str(opening_principal),
            closing_total_outstanding_minor=str(total), movements_minor=str(net),
            interest_and_fees_owed_at_opening_minor=str(opening_owed - opening_principal),
            previous_statement_id=before['id'], previous_amount_owed_minor=str(before_owed),
            previous_amount_owed_basis=before_basis)))
    total_row = summary['total'][1]
    by_id[total_row['id']].update(kind='balance', excluded=True, fields=dict(
        description='Closing Balance', balance=str(total), balance_column=str(
            total_row['source_cells'][1]['column_index']), balance_basis=CLOSING_BASIS))
    for move in moves:
        item = by_id[move['rows'][0]['id']]
        fields = dict(description=move['description'], counterparty='', date=move['date'].isoformat(),
                      direction=move['direction'], amount_minor=str(move['amount']), date_column='0',
                      description_column='0')
        fields[move['direction']] = str(move['amount'])
        if move['effective'] is not None:
            e = move['effective']
            fields['value_date'] = date(2000 + int(e[3]), int(e[1]), int(e[2])).isoformat()
        for extra in move['rows'][1:]:
            by_id[extra['id']]['fields']['parent_transaction_id'] = item['id']
            item.setdefault('continuation_sources', []).append(dict(
                page_number=extra['page_number'], table_index=extra['table_index'], row_index=extra['row_index'],
                source_cells=extra['source_cells']))
        item.update(kind='transaction', excluded=False, fields=fields, issues=[])
    LAST_REFUSAL.clear()
    return rows


def recover_held(statement, reading, sources, currency):
    """``recover_rows`` for one period the general reader held as printing its principal balance only."""
    return recover_rows(statement, reading, currency)
