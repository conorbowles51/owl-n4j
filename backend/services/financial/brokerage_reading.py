"""Read trades and holdings off a brokerage statement, exactly as printed. Pure: no database, no model.

A Mexican casa de bolsa statement (Intercam, Kapital: one statement system) prints its cash ledger as a movement
table whose every line carries the security leg beside the cash:

    Ope  Liq  Folio  Descripción  Emisora  Serie  Cupón  Títulos  Precio  Plazo  Tasa  Monto  Comisión  Premio
    Impuestos  NETO

The money ledger keeps the cash (NETO, on the settlement day ``Liq``) and stores the whole printed line in the row's
provenance (``statement_import_original.source_cells``). :func:`trade_from_cash_row` reads the security leg back out
of those same printed cells: instrument (Emisora + Serie, as printed), quantity (Títulos), price, the operation day
(``Ope``, the trade date) and the settlement day, and the printed money columns. It never changes the cash row.

The same statement prints its holdings in ``POSICIÓN DE VALORES`` (per instrument: the previous and the closing
quantity, price and valuation) and its open repurchase agreements in ``REPORTOS VIGENTES``.
:func:`holdings_from_tables` reads them from the page tables the statement import already reads.

Nothing is guessed. A value the printed line does not carry is ``None`` and says so (``not_printed``); a line whose
shape is not the movement table's yields no trade. No time of execution is printed by these formats, so none is
stored; a format that prints one stores it as printed (``execution_time``).

An investment-fund statement (BBVA "FONDOS DE INVERSIÓN") is a second format: no cash ledger (it is set aside from
the money ledger as a fund statement), one movement table per fund (``Detalle de Movimientos Realizados Fondo``:
operation and settlement dates, operation, units, price per unit, amount, closing units and pesos) and a holdings
table (``Mes Anterior`` / ``Mes Actual``). :func:`fund_statement_rows` reads both from the statement's text.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

READER_MOVEMENTS = 'casa_de_bolsa_movements_v1'
READER_HOLDINGS = 'casa_de_bolsa_holdings_v1'
READER_FUNDS = 'fund_statement_v1'

_MONEY = r'\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?'
_QTY = r'\d{1,3}(?:,\d{3})*'
# One movement line, joined from its printed cells with the table rule ``)`` and the OCR doubt mark ``?`` removed.
_MOVEMENT = re.compile(
    r'^(?P<ope>\d{1,2})\s+(?P<liq>\d{1,2})\s+(?P<folio>\d{1,12})\s+(?P<text>\S.*?)\s+(?P<cupon>\S{1,8})\s+'
    r'(?:(?P<titulos>' + _QTY + r')\s+)?(?P<precio>\d+\.\d{6,10})'
    r'(?:\s+(?P<plazo>\d{1,5})\s+(?P<tasa>\d+\.\d{4,8}))?'
    r'(?P<money>(?:\s+' + _MONEY + r')+)(?P<rest>(?:\s+\S+)*)\s*$')
# A cash row whose stored description is all that was kept (no printed cells): the security part of the line.
_DESCRIPTION = re.compile(
    r'^(?P<folio>\d{1,12})\s+(?P<text>\S.*?)\s+(?P<cupon>\d{1,4})\s+(?:(?P<titulos>' + _QTY + r')\s+)?'
    r'(?P<precio>\d+\.\d{6,10})(?:\s+(?P<plazo>\d{1,5})\s+(?P<tasa>\d+\.\d{4,8}))?(?P<rest>(?:\s+\S+)*)\s*$')
# A reading that wrote the operation and settlement days into the description: "(ope 05, liq 05; NETO 8,165,600.00)".
_NOTED = re.compile(r'^(?P<folio>\d{1,12})\s+(?P<text>\S.*?)\s+\(ope\s+\d{1,2},\s*liq\s+\d{1,2};\s*NETO\s+'
                    r'(?P<noted_net>' + _MONEY + r')')
_OPE_LIQ_NOTE = re.compile(r'\(ope\s+(?P<ope>\d{1,2}),\s*liq\s+(?P<liq>\d{1,2})', re.I)

# The continuation word a repurchase agreement prints under its line: the start leg and the maturity leg.
_REPO_LEGS = {'INICIO': 'repo_start', 'VENC': 'repo_maturity'}


def _fold(text: str) -> str:
    return unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().upper()


def _clean(text: str) -> str:
    """A printed cell as words: the table rule ``)`` and the OCR doubt mark ``?`` are not part of any value; a
    parenthesised amount keeps its opening bracket (a negative)."""
    text = (text or '').replace('­', '-').replace('?', ' ')
    text = re.sub(r'\)(?=\S)', ') ', text)
    words = []
    for word in text.split():
        if word.startswith('(') and word.endswith(')') and len(word) > 2:
            words.append(word)  # (529,875.29): a printed negative
            continue
        word = word.rstrip(')')
        if len(word) == 1 and not word.isalnum() and word not in '+-':
            continue  # a stray scan mark ('§') standing alone between two cells
        if word:
            words.append(word)
    return ' '.join(words)


def _number(text: Optional[str]) -> Optional[Decimal]:
    if text is None:
        return None
    try:
        return Decimal(text.replace(',', '').strip('()'))
    except InvalidOperation:
        return None


def _minor(text: Optional[str]) -> Optional[int]:
    value = _number(text)
    return None if value is None else int((abs(value) * 100).to_integral_value())


def _side(operation: str, continuation: str) -> str:
    folded = _fold(operation).replace(' ', '')
    leg = _REPO_LEGS.get(_fold(continuation).strip()[:6].strip(), '') if continuation else ''
    if 'REPORTO' in folded:
        return leg or 'repo'
    if folded.startswith('COMPRA'):
        return 'buy'
    if folded.startswith('VENTA'):
        return 'sell'
    return 'other'


def _split_instrument(text: str):
    """(operation, issuer, series) of the printed Descripción + Emisora + Serie cells: the last two words are the
    issuer and series as printed. The operation keeps every word the description column printed."""
    words = text.split()
    if len(words) < 3:
        return None
    return ' '.join(words[:-2]), words[-2], words[-1]


def resolve_day(day: int, anchor: date, *, on_or_before: bool) -> Optional[date]:
    """The date with day-of-month ``day`` nearest ``anchor``: the anchor's month, else the month before
    (``on_or_before``: an operation day never falls after its settlement)."""
    for back in (0, 1):
        year, month = anchor.year, anchor.month - back
        if month == 0:
            year, month = year - 1, 12
        if day > calendar.monthrange(year, month)[1]:
            continue
        found = date(year, month, day)
        if not on_or_before or found <= anchor:
            return found
    return None


_CELL_AMOUNT = re.compile(r'\(?\d[\d,\s]*\.\d{2}\)?\??')
_CELL_TWO_DAYS = re.compile(r'(\d{1,2})(?:[.,]\s*|\s+)(\d{1,2})\.?')


def _cell(text: str, first: bool) -> str:
    """One printed cell, with the two OCR slips measured on the scanned statements undone: an amount whose
    digit groups the scan split ('4,081 ,528.73', '8, 523,422.32', '4,081 528.73' in one cell) and the two day
    columns read as one cell ('13.13'). Only a whole cell is rejoined, never two cells."""
    text = (text or '').strip()
    if _CELL_AMOUNT.fullmatch(text) and re.search(r'\s', text):
        negative = text.startswith('(')
        digits = re.sub(r'[^\d.]', '', text)
        whole, cents = digits.split('.')
        text = f"{int(whole):,}.{cents}"
        text = f'({text})' if negative else text
    elif first and _CELL_TWO_DAYS.fullmatch(text):
        text = ' '.join(_CELL_TWO_DAYS.fullmatch(text).groups())
    return text


def printed_line(cells: Iterable[dict]) -> str:
    """The movement line as printed, its cells joined in column order."""
    ordered = sorted((c for c in cells or [] if isinstance(c, dict)), key=lambda c: (c.get('column_index') or 0))
    return _clean(' '.join(_cell(str(c.get('expected_text') or ''), index == 0) for index, c in enumerate(ordered)))


def trade_from_cash_row(*, cells, description: str, settlement: Optional[date], amount_minor: Optional[int],
                        direction: Optional[str]) -> Optional[dict]:
    """The security leg of one brokerage cash row, or ``None`` when the line moves no security.

    ``cells``: the row's printed cells (``statement_import_original.source_cells``); ``description``: the stored
    description (used only when no cells were kept); ``settlement``: the row's date (the ``Liq`` day the cash moved);
    ``amount_minor``/``direction``: the cash leg as the money ledger holds it (never changed here).

    ``not_printed``: values these statements do not print (execution time, ISIN). ``not_read``: values the page
    prints but the stored reading of this row did not keep (a reading that kept only part of the line).
    """
    line = printed_line(cells)
    match = _MOVEMENT.match(line) if line else None
    basis = 'printed_line'
    if match is None:
        stored = _clean(description or '')
        match = _DESCRIPTION.match(stored) or _NOTED.match(stored)
        basis = 'stored_description'
        if match is None:
            return None
    parts = match.groupdict()
    titulos = _number(parts.get('titulos'))
    noted = bool(parts.get('noted_net'))
    if not titulos and not noted:
        return None  # a cash movement (Retiro, Depósito, Timbrado): no security changes hands
    split = _split_instrument(_clean(parts['text']))
    if split is None:
        return None
    operation, issuer, series = split
    continuation = (parts.get('rest') or '').strip()
    if not continuation:
        # The repo leg word ('Inicio', 'Venc') prints on the line below; the stored description keeps it.
        last = (_clean(description or '').split() or [''])[-1]
        continuation = last if _fold(last) in _REPO_LEGS else ''
    if noted and _side(operation, continuation) == 'other':
        return None  # a model reading's note on a cash line (Timbrado): no security named
    money = (parts.get('money') or '').split()
    ope = liq = None
    if basis == 'printed_line':
        ope, liq = int(parts['ope']), int(parts['liq'])
    else:
        note = _OPE_LIQ_NOTE.search(description or '')
        if note:
            ope, liq = int(note.group('ope')), int(note.group('liq'))
    settlement_date = settlement if settlement is not None and (liq is None or settlement.day == liq) else None
    trade_date = (resolve_day(ope, settlement_date, on_or_before=True)
                  if ope is not None and settlement_date is not None else None)
    columns = dict(gross=None, commission=None, premium=None, tax=None, net=None)
    if len(money) == 5:
        columns = dict(zip(('gross', 'commission', 'premium', 'tax', 'net'), money))
    elif len(money) > 1:
        columns.update(gross=money[0], net=money[-1])
    elif money:
        columns.update(net=money[-1])
    elif noted:
        columns.update(net=parts['noted_net'])
    coupon = parts.get('cupon')
    unreadable = []
    if coupon is not None and not coupon.isdigit():
        unreadable.append(dict(field='coupon', printed=coupon))
        coupon = None
    not_printed = ['execution_time', 'isin']
    not_read = [name for name, value in (('quantity', titulos), ('price', parts.get('precio')),
                                         ('trade_date', trade_date), ('gross', columns['gross']))
                if value is None]
    if basis == 'stored_description' and len(money) != 5:
        not_read += ['commission', 'premium', 'tax']
    net_minor = _minor(columns['net'])
    checks = {}
    if net_minor is not None and amount_minor is not None:
        checks['net_equals_cash_leg'] = net_minor == int(amount_minor)
    if len(money) == 5:
        gross, commission, premium, tax, net = (_number(m) for m in money)
        sign = -1 if (_number(money[-1]) or 0) < 0 else 1
        checks['gross_premium_less_tax_and_commission_equals_net'] = (
            abs(gross) + abs(premium) - abs(tax) - abs(commission) == abs(net)) if sign > 0 else (
            abs(gross) + abs(commission) + abs(tax) == abs(net))
    return dict(
        row_kind='trade', reader=READER_MOVEMENTS, basis=basis,
        printed_text=line or _clean(description or ''),
        operation=operation + ((' ' + continuation) if continuation else ''),
        side=_side(operation, continuation), folio=parts['folio'],
        instrument=f'{issuer} {series}', issuer=issuer, series=series, coupon=coupon, isin=None,
        quantity_printed=parts.get('titulos'), quantity=titulos,
        price_printed=parts.get('precio'), price=_number(parts.get('precio')),
        term_days=int(parts['plazo']) if parts.get('plazo') else None, rate_printed=parts.get('tasa'),
        gross_minor=_minor(columns['gross']), commission_minor=_minor(columns['commission']),
        premium_minor=_minor(columns['premium']), tax_minor=_minor(columns['tax']),
        net_minor=net_minor if net_minor is not None else amount_minor,
        cash_direction=direction,
        trade_date=trade_date, trade_day_printed=ope, settlement_date=settlement_date, settlement_day_printed=liq,
        execution_time=None, not_printed=not_printed, not_read=sorted(set(not_read)), unreadable=unreadable,
        checks=checks)


# ---------------------------------------------------------------------------------------------------------------
# Holdings: POSICIÓN DE VALORES and REPORTOS VIGENTES
# ---------------------------------------------------------------------------------------------------------------

_SPANISH_MONTHS = {'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6, 'JULIO': 7,
                   'AGOSTO': 8, 'SEPTIEMBRE': 9, 'SETIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12}
_AS_OF = re.compile(r'(?:POSICION|VIGENTES)\s+AL\s+(\d{1,2})\s+DE\W*([A-Z]+)\s+DE\W*(\d{4})')
_HOLDING = re.compile(
    r'^(?P<issuer>[+A-Z0-9&.\-]{1,12})\s+(?P<series>[A-Za-z0-9\-]{1,8})\s+(?P<coupon>\d{1,4})\s+(?P<currency>[A-Z]{3})\s+'
    r'(?P<prev_qty>' + _QTY + r')\s+(?P<prev_price>\d+\.\d+)\s+(?P<prev_value>' + _MONEY + r')\s+'
    r'(?P<qty>' + _QTY + r')\s+(?P<price>\d+\.\d+)\s+(?P<tail>.*)$')
_REPO = re.compile(
    r'^(?P<folio>\d{1,12})\s+(?P<start>\d{4}/\d{2}/\d{2})\s+(?P<maturity>\d{4}/\d{2}/\d{2})\s+(?P<term>\d{1,5})\s+'
    r'(?P<rate>\d+\.\d+)\s+(?P<issuer>[A-Z0-9&.\-]{1,12})\s+(?P<series>[A-Z0-9\-]{1,8})\s+(?P<amount>' + _MONEY + r')'
    r'(?P<tail>.*)$')


def _as_of(text: str) -> Optional[list]:
    found = []
    for day, month, year in _AS_OF.findall(_fold(text)):
        number = _SPANISH_MONTHS.get(month)
        if number:
            try:
                found.append(date(int(year), number, int(day)))
            except ValueError:
                continue
    return found


def _table_rows(source: dict):
    for row in source.get('rows') or []:
        cells = sorted(row.get('cells') or [], key=lambda c: c.get('column_index') or 0)
        yield row, cells, _clean(' '.join(str(c.get('expected_text') or '') for c in cells))


def holdings_from_tables(sources: Iterable[dict], *, period_end: Optional[date] = None) -> list:
    """Holdings printed in a casa de bolsa statement's ``POSICIÓN DE VALORES`` and ``REPORTOS VIGENTES`` tables.

    ``sources``: the statement's page tables as the statement import reads them (``page_number``, ``table_index``,
    ``rows`` of ``cells`` with ``expected_text`` and ``locator``). A holdings line is read only when its closing
    quantity times its closing price equals a valuation printed on the same line (to the centavo): that is the
    line's own arithmetic, and the valuation is the one it proves. A line that does not prove is not read.
    """
    found = []
    as_of_position = as_of_repos = None
    for source in sources:
        section = None
        for row, cells, text in _table_rows(source):
            folded = _fold(text)
            dates = _as_of(text)
            if 'REPORTOS VIGENTES' in folded:
                section = 'repo'
                as_of_repos = dates[0] if dates else as_of_repos
                continue
            if 'POSICION AL' in folded and dates:
                section = 'position'
                as_of_position = dates[-1]
                continue
            if section == 'position' or (section is None and 'MXN' in text):
                match = _HOLDING.match(text)
                if match:
                    holding = _holding(match, as_of_position or period_end)
                    if holding:
                        found.append(dict(holding, page_number=source.get('page_number'),
                                          table_index=source.get('table_index'), row_index=row.get('row_index'),
                                          printed_text=text, locator=_row_locator(cells)))
                    continue
            if section == 'repo':
                match = _REPO.match(text)
                if match:
                    found.append(dict(_repo(match, as_of_repos), page_number=source.get('page_number'),
                                      table_index=source.get('table_index'), row_index=row.get('row_index'),
                                      printed_text=text, locator=_row_locator(cells)))
    return found


def _holding(match, as_of):
    parts = match.groupdict()
    quantity, price = _number(parts['qty']), _number(parts['price'])
    expected = (quantity * price).quantize(Decimal('0.01')) if quantity is not None and price is not None else None
    tail = [t for t in parts['tail'].split()]
    valuation = next((t for t in tail if re.fullmatch(_MONEY, t) and _number(t) == expected), None)
    if quantity and valuation is None:
        return None  # the line does not prove its own valuation: not read
    prev_qty, prev_price = _number(parts['prev_qty']), _number(parts['prev_price'])
    return dict(row_kind='holding', reader=READER_HOLDINGS, holding_kind='security',
                instrument=f"{parts['issuer']} {parts['series']}", issuer=parts['issuer'], series=parts['series'],
                coupon=parts['coupon'], isin=None, currency=parts['currency'],
                quantity_printed=parts['qty'], quantity=quantity, price_printed=parts['price'], price=price,
                market_value_minor=_minor(valuation) if valuation else 0,
                previous=dict(quantity_printed=parts['prev_qty'], quantity=str(prev_qty) if prev_qty is not None else None,
                              price_printed=parts['prev_price'], value_minor=_minor(parts['prev_value'])),
                as_of=as_of, proof='quantity_times_price_equals_printed_valuation' if quantity else 'zero_position')


def _repo(match, as_of):
    parts = match.groupdict()
    start, maturity = (date(*map(int, parts[k].split('/'))) for k in ('start', 'maturity'))
    return dict(row_kind='holding', reader=READER_HOLDINGS, holding_kind='repo', folio=parts['folio'],
                instrument=f"{parts['issuer']} {parts['series']}", issuer=parts['issuer'], series=parts['series'],
                isin=None, quantity_printed=None, quantity=None, price_printed=None, price=None,
                market_value_minor=_minor(parts['amount']), rate_printed=parts['rate'], term_days=int(parts['term']),
                trade_date=start, settlement_date=maturity, as_of=as_of, proof='printed_amount_invested')


def _row_locator(cells):
    rects = [c.get('locator') for c in cells if isinstance(c.get('locator'), dict) and c['locator'].get('rect')]
    if not rects:
        return None
    first = rects[0]
    xs0, ys0, xs1, ys1 = zip(*(r['rect'] for r in rects))
    return dict(first, rect=[min(xs0), min(ys0), max(xs1), max(ys1)])
