"""Santander Mexico "ESTADO DE CUENTA INTEGRAL" (older, scanned) cheque sections the general reader holds.

The older Santander statement prints one cheque account: a cover (CUENTA DE CHEQUES: SALDO INICIAL,
+ DEPOSITOS, - RETIROS, = SALDO ACTUAL), then DETALLE DE MOVIMIENTOS CUENTA DE CHEQUES with the
previous period's final balance and one line per movement (date, seven-digit folio, description,
deposit or withdrawal, running balance), ending in a TOTAL line. Scans of it are read with noisy
separators ("8, 123,157.74", "104,00"), amounts split over two cells, letters for digits in dates
("O1-NOV-2022") and, on some pages, no positions at all, so the general reader cannot place the
amount columns and holds the period (correctly).

This reader proves such a section from the printed running balance alone, never from positions:

* every amount is read digit for digit (the last two digits are the cents, as printed);
* each movement's printed amount must equal the difference between its printed running balance
  and the previous one, exactly; that difference also gives the direction (a column, where one is
  read, must agree). A cell split into several pieces is taken only when exactly one way of joining
  them satisfies this;
* the chain starts at the printed SALDO FINAL DEL PERIODO ANTERIOR, which must equal the cover's
  printed SALDO INICIAL, and ends at the last running balance, which must equal a closing printed
  elsewhere (the cover's SALDO ACTUAL, its Saldo final, or the TOTAL line's balance). An unread
  movement breaks the chain, so a section read this way is complete;
* each movement's date is printed (letters read for digits are corrected only where unambiguous,
  a month only when exactly one month is one letter away), lies in the printed period and never
  goes back in time.

Anything else returns None: the general reader's held reading stands. It runs only for a period the
general reader does not prove, of a document printing exactly one such cheque section, and never
changes the period's identity (id, account, holder, currency, dates).

Switch: LOUPE_FINANCIAL_SANTANDER_INTEGRAL_RECOVERY (default on; 0/false/off/no turns it off).
"""
import os
import re
from datetime import date

from services.financial.statement_import_bbva import MONTHS, norm

ENABLED = os.environ.get('LOUPE_FINANCIAL_SANTANDER_INTEGRAL_RECOVERY', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
LAYOUT_BASIS = 'santander_integral_running_balance'
# Why the last call refused (a step number, for diagnosis only; never part of a reading).
LAST_REFUSAL = {}


def _refuse(step, row=None):
    LAST_REFUSAL.clear()
    LAST_REFUSAL.update(step=step, row=row)
    return None

_DETAIL = re.compile(r'DETALLE DE MOVIMIENTOS CUENTA DE CHEQUES')
_DATE = re.compile(r'^\s*([0-9OQDIL]{2})\s*[-.~_ ]+\s*([A-Z0-9]{3})\s*[-.~_ ]*\s*(\d{4})\b')
_FOLIO = re.compile(r'^[\s|/()\[\]\'.,:;~_-]*(\d{7})\b')
# Digits with the separators a scan reads between them; the last two digits are the cents.
_MONEY = re.compile(r'^[\s$"\'“”‘’]*\d[\d\s,.]*[.,\s]\s?\d{2}[\s?.\'"]*$')
_MONEY_PIECE = re.compile(r'^[\s$"\'“”‘’.,]*\d[\d\s,.]*[\s?.\'"]*$')
_DIGIT_FOR = {'O': '0', 'Q': '0', 'D': '0', 'I': '1', 'L': '1'}
_LETTER_FOR = {'0': 'O', '1': 'I', '5': 'S', '8': 'B', '6': 'G', '2': 'Z'}


def _money(value):
    """Minor units of a printed amount read with noisy separators, or None."""
    if not _MONEY.match(value):
        return None
    digits = re.sub(r'\D', '', value)
    return int(digits) if len(digits) >= 3 else None


def _day(value):
    digits = ''.join(_DIGIT_FOR.get(ch, ch) for ch in value)
    return int(digits) if digits.isdigit() else None


def _month(value, allowed):
    """The printed month: exact, or the only month one letter away from the text read, among the
    period's months; None when ambiguous."""
    token = ''.join(_LETTER_FOR.get(ch, ch) for ch in value)
    if token in MONTHS:
        return MONTHS[token] if MONTHS[token] in allowed else None
    near = [number for name, number in MONTHS.items() if sum(a != b for a, b in zip(name, token)) == 1]
    return near[0] if len(near) == 1 and near[0] in allowed else None


def _printed_date(text, start, end, allowed):
    match = _DATE.match(norm(text))
    if not match:
        return None, None
    day, month, year = _day(match[1]), _month(match[2], allowed), int(match[3])
    if day is None or month is None:
        return None, match
    try:
        value = date(year, month, day)
    except ValueError:
        return None, match
    return value, match


def _ordered_rows(sources):
    """(source, row) in printed order: pages in order; on a page, tables by their top, rows as stored."""
    def top(source):
        tops = [(c.get('locator') or {}).get('rect') for r in source['rows'] for c in r['cells']]
        tops = [rect[1] for rect in tops if isinstance(rect, list) and len(rect) == 4]
        return min(tops) if tops else 0
    ordered = []
    for page in sorted({s['page_number'] for s in sources}):
        for source in sorted((s for s in sources if s['page_number'] == page), key=lambda s: (top(s), s['table_index'])):
            ordered.extend((source, row) for row in source['rows'])
    return ordered


def _row_text(row):
    return ' '.join(c['expected_text'].strip() for c in row['cells']).strip()


def _amount_pieces(cells):
    """The trailing cells of a line that print only money pieces (digits and separators)."""
    pieces = []
    for cell in reversed(cells):
        value = cell['expected_text'].strip()
        if '\n' in value or not _MONEY_PIECE.match(value):
            break
        pieces.insert(0, cell)
    return pieces


def _solutions(pieces, previous):
    """Every (amount, balance, direction, amount cells, balance cell) that reads the trailing pieces as an
    amount followed by a running balance and satisfies the chain from ``previous``."""
    found = []
    for split in range(1, len(pieces)):
        balance_cells = pieces[split:]
        balance = _money(' '.join(c['expected_text'].strip() for c in balance_cells))
        if balance is None or len(balance_cells) > 3:
            continue
        for start in range(max(0, split - 3), split):
            amount_cells = pieces[start:split]
            amount = _money(' '.join(c['expected_text'].strip() for c in amount_cells))
            if not amount:
                continue
            if balance - previous == amount:
                found.append((amount, balance, 'credit', amount_cells, balance_cells))
            elif previous - balance == amount:
                found.append((amount, balance, 'debit', amount_cells, balance_cells))
    return found


def _labelled(rows, label, stop=r'[A-Z]{3}'):
    """Money printed after a cover label (cells after it, up to the next cell with words)."""
    values = []
    for _, row in rows:
        cells = row['cells']
        for index, cell in enumerate(cells):
            if not re.search(label, norm(cell['expected_text'])):
                continue
            pieces = []
            for following in cells[index + 1:]:
                if re.search(stop, norm(following['expected_text'])):
                    break
                pieces.append(following['expected_text'].strip())
            value = _money(' '.join(pieces))
            if value is not None:
                values.append((value, row, cells[index + 1] if index + 1 < len(cells) else cell))
    return values


def _column_names(row):
    """{name: rect} of a movement column heading row, where positions were read."""
    names = {}
    for cell in row['cells']:
        rect = (cell.get('locator') or {}).get('rect')
        name = norm(cell['expected_text']).strip('_— -')
        for key in ('DEPOSITOS', 'RETIROS', 'SALDO'):
            if name.endswith(key) and isinstance(rect, list) and len(rect) == 4:
                names[key] = rect
    return names if len(names) == 3 else None


def _column_of(cells, columns):
    """The movement column the amount cells are printed in, by their right edge, or None (no positions)."""
    if not columns:
        return None
    rects = [(c.get('locator') or {}).get('rect') for c in cells]
    if not rects or not all(isinstance(r, list) and len(r) == 4 for r in rects):
        return None
    right = max(r[2] for r in rects)
    return min(('DEPOSITOS', 'RETIROS', 'SALDO'), key=lambda name: abs(columns[name][2] - right))


def _header(source, row, page):
    return dict(id=f"{page}:{source['table_index']}:{row['row_index']}", page_number=page,
                table_index=source['table_index'], row_index=row['row_index'],
                source_revision=source.get('source_revision'), source_cells=row['cells'],
                fields={}, issues=[], excluded=True, kind='header')


def recover_rows(statement, sources, currency):
    """The proved rows of a held period of this layout, or None (the general reader's reading stands)."""
    if not ENABLED or not currency or (statement.get('currency') and currency != statement['currency']):
        return _refuse(1)
    try:
        start, end = date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end'])
    except (KeyError, TypeError, ValueError):
        return _refuse(2)
    account = re.sub(r'\D', '', statement.get('account_reference') or '')
    if len(account) < 8 or (end - start).days > 62:
        return _refuse(3)
    addresses = {(s['page_number'], s['table_index']) for s in statement.get('sources') or []}
    selected = [s for s in sources if (s['page_number'], s['table_index']) in addresses]
    ordered = _ordered_rows(selected)
    content = '\n'.join(norm(_row_text(row)) for _, row in ordered)
    if 'CUENTA INTEGRAL' not in content or 'SANTANDER' not in content:
        return _refuse(4)
    anchors = [i for i, (_, row) in enumerate(ordered) if _DETAIL.search(norm(_row_text(row)))]
    if len(anchors) != 1:
        return _refuse(5)
    cover, section = ordered[:anchors[0]], ordered[anchors[0]:]
    # The section names this statement's account, and the cover lists no other product.
    if account not in re.sub(r'\D', '', ' '.join(_row_text(row) for _, row in section[:2])):
        return _refuse(6)
    if len({m for m in re.findall(r'\d{2}\s?[-.~]\s?\d{8}\s?[-.~]\s?\d', '\n'.join(_row_text(r) for _, r in cover))
            if re.sub(r'\D', '', m) != account}):
        return _refuse(7)
    allowed = {start.month, end.month}
    rows, by_id = [], {}
    for source, row in ordered:
        item = _header(source, row, source['page_number'])
        rows.append(item)
        by_id[id(row)] = item
    opening = closing_total = None
    previous = previous_day = None
    columns = None
    movements = []
    ended = False
    for source, row in section[1:]:
        joined = norm(_row_text(row))
        if ended:
            continue
        found = _column_names(row) if 'FECHA' in joined and 'SALDO' in joined else None
        if 'FECHA' in joined and 'SALDO' in joined and 'ANTERIOR' not in joined:
            columns = found
            continue
        if 'INFORMACION FISCAL' in joined or 'INFORMACION FISGAL' in joined:
            ended = True
            continue
        if joined.startswith('TOTAL'):
            pieces = _amount_pieces(row['cells'])
            if pieces:
                closing_total = (_money(pieces[-1]['expected_text'].strip()), row, pieces[-1])
            ended = True
            continue
        if 'SALDO FINAL DEL PER' in joined and 'ANTERIOR' in joined:
            if opening is not None or movements:
                return _refuse(8)
            pieces = _amount_pieces(row['cells'])
            value = _money(' '.join(c['expected_text'].strip() for c in pieces)) if pieces else None
            if value is None:
                return _refuse(9)
            opening = (value, row, pieces[-1])
            previous = value
            continue
        pieces = _amount_pieces(row['cells'])
        prefix = norm(' '.join(c['expected_text'].strip() for c in row['cells'][:len(row['cells']) - len(pieces)]))
        day, match = _printed_date(prefix, start, end, allowed)
        if match is None:
            # A continuation line of a movement's description (no printed date): never money.
            continue
        if opening is None or day is None or not start <= day <= end or (previous_day and day < previous_day):
            return _refuse(10, row)
        rest = prefix[match.end():]
        folio = _FOLIO.match(rest)
        if not folio:
            return _refuse(11, row)
        solutions = _solutions(pieces, previous)
        if len({(a, b, d) for a, b, d, _, _ in solutions}) != 1:
            return _refuse(12, row)
        amount, balance, direction, amount_cells, _ = solutions[0]
        column = _column_of(amount_cells, columns)
        if column is not None and column != {'credit': 'DEPOSITOS', 'debit': 'RETIROS'}[direction]:
            return _refuse(13, row)
        description = re.sub(r'\s+', ' ', rest[folio.end():]).strip(" |'")
        movements.append((row, dict(description=description, bank_reference=folio[1], date=day.isoformat(),
                                    direction=direction, amount_minor=str(amount), balance=str(balance))))
        previous, previous_day = balance, day
    if opening is None or not movements or not ended:
        return _refuse(14)
    # The chain's ends agree with balances printed elsewhere on the statement.
    initial = [value for value, _, _ in _labelled(cover, r'SALDO[ ._]*INICIAL')]
    if opening[0] not in initial:
        return _refuse(15)
    closings = [(value, row, cell) for value, row, cell in _labelled(cover, r'= SALDO ACTUAL|SALDO ACTUAL')]
    if closing_total and closing_total[0] is not None:
        closings.append(closing_total)
    agreeing = [entry for entry in closings if entry[0] == previous]
    if not agreeing:
        return _refuse(16)
    value, row, cell = opening
    by_id[id(row)].update(kind='balance', fields=dict(description='Opening Balance', balance=str(value),
                          balance_column=str(cell.get('column_index', '')), balance_basis=LAYOUT_BASIS))
    for row, fields in movements:
        by_id[id(row)].update(kind='transaction', excluded=False, fields=dict(fields, balance_basis=LAYOUT_BASIS))
    value, row, cell = agreeing[0]
    target = by_id[id(row)]
    if target['kind'] != 'header':
        return _refuse(17)
    target.update(kind='balance', fields=dict(description='Closing Balance', balance=str(value),
                  balance_column=str(cell.get('column_index', '')), balance_basis=LAYOUT_BASIS))
    return rows


def recover_held(statement, reading, sources, currency):
    """``recover_rows`` for one held period of the general reader's ``reading`` of the document, only when
    no other period it reads shares a page with it: a second reading of the same pages (a fragment of the
    same section) is never left beside a recovered one."""
    if not ENABLED or statement['engine'].get('proved'):
        return None
    pages = {s['page_number'] for s in statement.get('sources') or []}
    if any(other is not statement and pages & {s['page_number'] for s in other.get('sources') or []}
           for other in reading):
        return _refuse(18)
    return recover_rows(statement, sources, currency)
