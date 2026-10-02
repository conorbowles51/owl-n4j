"""Corpus v4: the shapes of live productions that corpus v1-v3 did not cover.

v1-v3 are clean 200 dpi synthetic scans of four families, so their repair
rates are an upper bound. v4 appends, without touching any earlier file:

* families the code has layout readers for but the corpus never exercised:
  Capital One, BBVA Mexico, Scotiabank Mexico, Monex, Kapital, Intercam,
  Santander Mexico, and Andrews teller deposit receipts (not statements);
* the same institutions printing what their readers do not handle
  (Scotiabank and Monex statements with movements);
* MXN, credit balances on cards, overdrawn bank balances;
* ruled (drawn-grid) digital PDFs;
* statements with a missing page, which must be held;
* degraded scans: skew, low resolution, JPEG compression noise, faint print.

Every layout is modelled on the printed labels and positions that the
readers in ``backend/services/financial`` and their synthetic tests expect.
Every name, account number, CLABE, RFC and amount is invented; nothing is
copied from a case. Where an institution prints something no reader handles
(a Scotiabank or Monex movements table), the layout is a plausible invention
and is labelled ``layout_not_supported`` in its defects: it measures the
gap, not a regression.

Expected outcomes follow the corpus convention: ``auto`` when the source
alone establishes every fact, ``decision`` when a person must supply a fact
the source lacks, ``hold`` when the source cannot complete the period (for
example a missing page) and ``not_statement`` for a document that must never
be admitted as a statement period.
"""
from __future__ import annotations

from datetime import date, timedelta

from benchmarks.statement_automation.corpus import (
    L, R, PAGE_WIDTH, damage, money, period_truth, row, _month_end)

ADDED_IN = 'v4'


def truth(**kwargs):
    return period_truth(**kwargs) | dict(added_in=ADDED_IN)


def _lines(y0, step, rows):
    """Lay out ``rows`` (lists of cells) from ``y0`` with a fixed line step."""
    return [(y0 + i * step, cells) for i, cells in enumerate(rows)]


def _signed(minor, *, dollar=False):
    """A signed amount as these layouts print it: a leading minus for credits."""
    return ('-' if minor < 0 else '') + money(minor, dollar=dollar)


# ---------------------------------------------------------------------------
# Capital One card (statement_layout_context + statement_import_card)
# ---------------------------------------------------------------------------

CAPITAL_ONE_HOLDER = 'EXAMPLE CARDHOLDER'


def _mon_day(iso):
    value = date.fromisoformat(iso)
    return f'{value:%b} {value.day}'


def _cycle_text(start, end):
    return f'{start:%b} {start.day}, {start.year} - {end:%b} {end.day}, {end.year} | {(end - start).days + 1} days in Billing Cycle'


def capital_one_pages(*, ending, start, end, opening, rows, split_after=None, damage_cells=(), credit_style='minus'):
    """Return (pages, truth rows, closing) for one Capital One cycle.

    Debits (purchases) raise the amount owed; credits (payments) lower it. A
    closing below zero is a credit balance, printed with a leading minus.
    ``split_after`` moves transactions after that index to a second page
    headed "Transactions (Continued)" (the reader's continuation layout).
    """
    credits = [r for r in rows if r['direction'] == 'credit']
    debits = [r for r in rows if r['direction'] == 'debit']
    paid = sum(r['amount_minor'] for r in credits)
    spent = sum(r['amount_minor'] for r in debits)
    closing = opening - paid + spent
    card = f'Platinum Mastercard ending in {ending}'

    def balance(minor):
        return ('-' if minor < 0 else '') + money(minor, dollar=True)

    first = _lines(20, 12, [
        [L(40, 'Capital One'), L(330, card)],
        [L(330, _cycle_text(start, end))],
        [L(40, CAPITAL_ONE_HOLDER)],
        [L(40, '100 EXAMPLE STREET')],
        [L(40, 'EXAMPLE CITY VA 22000')],
    ])
    first += _lines(110, 12, [
        [L(40, 'Account Summary')],
        [L(40, 'Previous Balance'), R(250, balance(opening))],
        [L(40, 'Payments'), R(250, '- ' + money(paid, dollar=True))],
        [L(40, 'Other Credits'), R(250, '- $0.00')],
        [L(40, 'Transactions'), R(250, '+ ' + money(spent, dollar=True))],
        [L(40, 'Cash Advances'), R(250, '+ $0.00')],
        [L(40, 'Fees Charged'), R(250, '+ $0.00')],
        [L(40, 'Interest Charged'), R(250, '+ $0.00')],
        [L(40, 'New Balance'), R(250, balance(closing))],
    ])
    body = [[L(40, 'Visit capitalone.com to see detailed transactions.')]]
    header = [L(40, 'Trans Date'), L(100, 'Post Date'), L(160, 'Description'), R(560, 'Amount')]

    def line(index, item):
        text = ('- ' if item['direction'] == 'credit' else '') + money(item['amount_minor'], dollar=True)
        ocr = damage(text) if index in damage_cells else None
        posted = (date.fromisoformat(item['date']) + timedelta(days=1)).isoformat()
        item['posted_date'] = posted  # printed Post Date (ground truth)
        return [L(40, _mon_day(item['date'])), L(100, _mon_day(posted)), L(160, item['description']), R(560, text, ocr)]

    indexed = list(enumerate(rows))
    payments = [(i, r) for i, r in indexed if r['direction'] == 'credit']
    purchases = [(i, r) for i, r in indexed if r['direction'] == 'debit']
    body += [[L(40, f'{CAPITAL_ONE_HOLDER} #{ending}: Payments, Credits and Adjustments')], header]
    body += [line(i, r) for i, r in payments]
    body += [[L(40, f'{CAPITAL_ONE_HOLDER} #{ending}: Total Payments, Credits and Adjustments'),
              R(560, '- ' + money(paid, dollar=True))]]
    body += [[L(40, f'{CAPITAL_ONE_HOLDER} #{ending}: Transactions')], header]
    continued = []
    if split_after is None:
        body += [line(i, r) for i, r in purchases]
    else:
        body += [line(i, r) for i, r in purchases[:split_after]]
        continued = [line(i, r) for i, r in purchases[split_after:]]
    closing_lines = [[L(40, f'{CAPITAL_ONE_HOLDER} #{ending}: Total Transactions'), R(560, money(spent, dollar=True))],
                     [L(40, 'Fees')],
                     [L(40, 'Total Fees for This Period'), R(560, '$0.00')],
                     [L(40, 'Interest Charged')],
                     [L(40, 'Interest Charge on Purchases'), R(560, '$0.00')],
                     [L(40, 'Total Interest for This Period'), R(560, '$0.00')],
                     [L(40, 'Totals Year-to-Date')]]
    if split_after is None:
        first += _lines(250, 14, body + closing_lines)
        return [first], list(rows), closing
    first += _lines(250, 14, body)
    second = _lines(20, 12, [[L(40, 'Capital One'), L(330, card)], [L(330, _cycle_text(start, end))]])
    second += _lines(70, 14, [[L(40, 'Transactions (Continued)')], header] + continued + closing_lines)
    return [first, second], list(rows), closing


def capital_one_entries():
    entries = []
    ending, account = '4821', '4821'
    balance = 51230

    def cycle_rows(start, seed):
        day = lambda n: (start + timedelta(days=n)).isoformat()
        return [row(day(3), f'EXAMPLE GROCERY {seed}A', 2511 + seed, 'debit'),
                row(day(9), 'CAPITAL ONE AUTOPAY PYMT', 4000, 'credit'),
                row(day(12), f'EXAMPLE FUEL STATION {seed}B', 3870 + seed, 'debit'),
                row(day(20), f'EXAMPLE PHARMACY {seed}C', 1299 + seed, 'debit')]

    def period(start, end, opening, rows, closing, expected, defects):
        return truth(family='capital-one-card', institution='Capital One', account=account, holder=CAPITAL_ONE_HOLDER,
                     currency='USD', start=start.isoformat(), end=end.isoformat(), opening=opening, closing=closing,
                     rows=rows, expected=expected, defects=defects)

    cycles = [(date(2024, 9, 16), date(2024, 10, 15)), (date(2024, 10, 16), date(2024, 11, 15)),
              (date(2024, 11, 16), date(2024, 12, 15)), (date(2024, 12, 16), date(2025, 1, 15)),
              (date(2025, 1, 16), date(2025, 2, 15)), (date(2025, 2, 16), date(2025, 3, 15))]
    # 1: clean digital, one page.
    start, end = cycles[0]
    rows = cycle_rows(start, 1)
    pages, truth_rows, closing = capital_one_pages(ending=ending, start=start, end=end, opening=balance, rows=rows)
    entries.append(dict(filename='capital-one-2024-10-clean.pdf', mode='digital', pages=pages,
                        periods=[period(start, end, balance, truth_rows, closing, 'auto', [])]))
    balance = closing
    # 2: two pages, transactions continued on page 2.
    start, end = cycles[1]
    rows = cycle_rows(start, 2) + [row((start + timedelta(days=24)).isoformat(), 'EXAMPLE HARDWARE 2D', 5644, 'debit')]
    pages, truth_rows, closing = capital_one_pages(ending=ending, start=start, end=end, opening=balance, rows=rows,
                                                   split_after=2)
    entries.append(dict(filename='capital-one-2024-11-two-pages.pdf', mode='digital', pages=pages,
                        periods=[period(start, end, balance, truth_rows, closing, 'auto', ['multi_page'])]))
    balance = closing
    # 3: the same two-page shape with its continuation page missing.
    start, end = cycles[2]
    rows = cycle_rows(start, 3) + [row((start + timedelta(days=24)).isoformat(), 'EXAMPLE HARDWARE 3D', 7710, 'debit')]
    pages, truth_rows, closing = capital_one_pages(ending=ending, start=start, end=end, opening=balance, rows=rows,
                                                   split_after=2)
    entries.append(dict(filename='capital-one-2024-12-missing-page-2.pdf', mode='digital', pages=pages[:1],
                        missing_pages=[2],
                        periods=[period(start, end, balance, truth_rows, closing, 'hold', ['missing_page'])]))
    balance = closing
    # 4: a scan whose OCR layer misread one amount digit; the image is right.
    start, end = cycles[3]
    rows = cycle_rows(start, 4)
    pages, truth_rows, closing = capital_one_pages(ending=ending, start=start, end=end, opening=balance, rows=rows,
                                                   damage_cells={2})
    entries.append(dict(filename='capital-one-2025-01-ocr-amount-digit.pdf', mode='scan_text_layer', pages=pages,
                        periods=[period(start, end, balance, truth_rows, closing, 'auto', ['ocr_amount_digit'])]))
    balance = closing
    # 5: an overpayment leaves a credit balance (the issuer owes the holder).
    start, end = cycles[4]
    rows = [row((start + timedelta(days=4)).isoformat(), 'EXAMPLE BOOKSHOP 5A', 1830, 'debit'),
            row((start + timedelta(days=10)).isoformat(), 'CAPITAL ONE MOBILE PYMT', balance + 1830 + 2500, 'credit')]
    pages, truth_rows, closing = capital_one_pages(ending=ending, start=start, end=end, opening=balance, rows=rows)
    assert closing == -2500
    entries.append(dict(filename='capital-one-2025-02-credit-balance.pdf', mode='digital', pages=pages,
                        periods=[period(start, end, balance, truth_rows, closing, 'auto', ['credit_balance'])]))
    balance = closing
    # 6: image-only scan at 150 dpi with JPEG compression noise.
    start, end = cycles[5]
    rows = cycle_rows(start, 6)
    pages, truth_rows, closing = capital_one_pages(ending=ending, start=start, end=end, opening=balance, rows=rows)
    entries.append(dict(filename='capital-one-2025-03-scan-150dpi-jpeg.pdf', mode='image_only', pages=pages,
                        degrade=dict(dpi=150, jpeg=35, noise=6),
                        periods=[period(start, end, balance, truth_rows, closing, 'auto',
                                        ['image_only_scan', 'low_dpi', 'jpeg_noise'])]))
    balance = closing
    # 7: an image-only scan at the corpus' usual 200 dpi, no other damage.
    start, end = date(2025, 3, 16), date(2025, 4, 15)
    rows = cycle_rows(start, 7)
    pages, truth_rows, closing = capital_one_pages(ending=ending, start=start, end=end, opening=balance, rows=rows)
    entries.append(dict(filename='capital-one-2025-04-scan-image-only.pdf', mode='image_only', pages=pages,
                        periods=[period(start, end, balance, truth_rows, closing, 'auto', ['image_only_scan'])]))
    return entries


# ---------------------------------------------------------------------------
# BBVA Mexico (statement_import_bbva): Spanish labels, two balance columns
# ---------------------------------------------------------------------------

BBVA_HOLDER = 'COMERCIALIZADORA EJEMPLO SA DE CV'
_ES_MONTHS = ('ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC')


def _dd_mon(iso):
    value = date.fromisoformat(iso)
    return f'{value.day:02d}/{_ES_MONTHS[value.month - 1]}'


def _bbva_header(page, count, account):
    return _lines(20, 12, [[R(590, 'Estado de Cuenta')], [R(590, 'MAESTRA PYME BBVA')],
                           [R(590, f'PAGINA {page} / {count}')],
                           [L(330, 'No. Cuenta'), L(470, account)]])


BBVA_COLUMNS = [L(18, 'OPER'), L(51, 'LIQ'), L(86, 'COD. DESCRIPCIÓN'), L(230, 'REFERENCIA'),
                R(398, 'CARGOS'), R(459, 'ABONOS'), R(525, 'OPERACIÓN'), R(594, 'LIQUIDACIÓN')]


def bbva_pages(*, account, start, end, opening, rows, per_page=None, damage_cells=()):
    """Return (pages, closing, row-line positions per page) for one BBVA period.

    ``per_page`` splits the movements across pages (a list of counts); the
    last page always carries the fiscal footer and disclosures.
    """
    credits = [r for r in rows if r['direction'] == 'credit']
    debits = [r for r in rows if r['direction'] == 'debit']
    closing = opening + sum(r['amount_minor'] for r in credits) - sum(r['amount_minor'] for r in debits)
    chunks = []
    remaining = list(enumerate(rows))
    for size in (per_page or [len(rows)]):
        chunks.append(remaining[:size])
        remaining = remaining[size:]
    assert not remaining
    count = len(chunks) + 1
    pages, grids = [], []
    balance = opening
    for number, chunk in enumerate(chunks, start=1):
        lines = _bbva_header(number, count, account)
        y = 80
        if number == 1:
            lines += _lines(70, 12, [
                [L(40, BBVA_HOLDER)], [L(40, 'AV. EJEMPLO 100 COL. CENTRO')], [L(40, 'CIUDAD DE MEXICO CP 01000')],
                [L(330, 'Periodo'), L(430, f'DEL {start:%d/%m/%Y} AL {end:%d/%m/%Y}')],
                [L(330, 'Fecha de Corte'), L(430, f'{end:%d/%m/%Y}')],
                [L(330, 'No. de Cliente'), L(430, 'B0012345')],
                [L(10, 'BBVA MEXICO, S.A., INSTITUCION DE BANCA MULTIPLE')],
                [L(10, 'Información Financiera'), R(590, 'MONEDA NACIONAL')],
                [L(316, 'Saldo de Liquidación Inicial'), R(590, money(opening))],
                [L(316, 'Saldo de Operación Inicial'), R(590, money(opening))],
                [L(316, 'Depósitos / Abonos (+)'), R(465, str(len(credits))),
                 R(590, money(sum(r['amount_minor'] for r in credits)))],
                [L(316, 'Retiros / Cargos (-)'), R(465, str(len(debits))),
                 R(590, money(sum(r['amount_minor'] for r in debits)))],
                [L(316, 'Saldo Final (+)'), R(590, money(closing))],
                [L(316, 'Saldo de Operación Final'), R(590, money(closing))],
                [L(10, 'Detalle de Movimientos Realizados')]])
            y = 70 + 15 * 12
        else:
            lines.append((y, [L(10, 'BBVA MEXICO, S.A., INSTITUCION DE BANCA MULTIPLE')]))
            y += 18
        table_top = y - 3
        lines.append((y, BBVA_COLUMNS))
        y += 14
        for index, item in chunk:
            balance += item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
            item['balance_after'] = balance
            amount = money(item['amount_minor'])
            ocr = damage(amount) if index in damage_cells else None
            right = 398 if item['direction'] == 'debit' else 459
            lines.append((y, [L(12, _dd_mon(item['date'])), L(53, _dd_mon(item['date'])), L(90, item['description']),
                              R(right, amount, ocr), R(525, money(balance)), R(594, money(balance))]))
            y += 12
            lines.append((y, [L(90, f'REF {item["reference"]}')]))
            y += 14
        grids.append((table_top, y - 3))
        if number == len(chunks):
            lines.append((y + 4, [L(10, 'Total de Movimientos')]))
        pages.append(lines)
    footer = _bbva_header(count, count, account)
    footer += _lines(90, 12, [[L(20, f'Nombre del Receptor : {BBVA_HOLDER}')],
                              [L(250, 'Estimado Cliente,')]]
                     + [[L(20, f'Texto informativo de ejemplo sobre comisiones y aclaraciones, linea {i}.')]
                        for i in range(1, 12)])
    pages.append(footer)
    return pages, closing, grids


def _bbva_rules(grids, pages):
    """Draw a ruled grid round each movement table: row and column rules."""
    columns = [8, 48, 82, 226, 350, 405, 466, 530, 599]
    result = []
    for number in range(len(pages)):
        segments = []
        if number < len(grids):
            top, bottom = grids[number]
            ys = [top] + [y - 3 for y, cells in pages[number] if top < y - 3 < bottom and len(cells) >= 4] + [bottom]
            for y in sorted(set(ys)):
                segments.append((columns[0], y, columns[-1], y))
            for x in columns:
                segments.append((x, top, x, bottom))
        result.append(segments)
    return result


def bbva_entries():
    entries = []
    account = '0198765432'
    balance = 25_000_000  # MXN 250,000.00

    def month_rows(year, month, seed):
        day = lambda d: date(year, month, d).isoformat()
        items = [row(day(2), f'T20 SPEI RECIBIDO CLIENTE {seed}A', 4_500_000 + seed * 1000, 'credit'),
                 row(day(5), f'T17 SPEI ENVIADO PROVEEDOR {seed}B', 1_275_050 + seed, 'debit'),
                 row(day(9), 'S39 SERV BANCA INTERNET OPS', 2_900, 'debit'),
                 row(day(9), 'S40 IVA COM SERV BCA INTERNET', 464, 'debit'),
                 row(day(14), f'N06 PAGO CUENTA DE TERCERO {seed}C', 860_000, 'debit'),
                 row(day(21), f'T20 SPEI RECIBIDO CLIENTE {seed}D', 1_210_000 + seed, 'credit'),
                 row(day(27), f'T17 SPEI ENVIADO NOMINA {seed}E', 3_330_000, 'debit')]
        for n, item in enumerate(items):
            item['reference'] = f'{year % 100:02d}{month:02d}{seed:02d}{n:04d}'
        return items

    def period(start, end, opening, rows, closing, expected, defects):
        return truth(family='bbva-mexico', institution='BBVA Mexico', account=account, holder=BBVA_HOLDER,
                     currency='MXN', start=start.isoformat(), end=end.isoformat(), opening=opening, closing=closing,
                     rows=[{k: v for k, v in r.items() if k != 'reference'} for r in rows],
                     expected=expected, defects=defects)

    variants = [
        (3, 'digital', {}, 'auto', [], 'clean'),
        (4, 'scan_text_layer', {}, 'auto', ['clean_scan_text_layer'], 'scan'),
        (5, 'digital', dict(per_page=[3, 4], drop=[2]), 'hold', ['missing_page'], 'missing-page-2'),
        (6, 'digital', dict(ruled=True), 'auto', ['ruled_pdf'], 'ruled'),
        (7, 'image_only', {}, 'auto', ['image_only_scan'], 'image-only'),
        (8, 'image_only', dict(degrade=dict(skew=1.2)), 'auto', ['image_only_scan', 'skew'], 'scan-skewed'),
        (9, 'scan_text_layer', dict(damage_cells={1}), 'auto', ['ocr_amount_digit'], 'ocr-amount-digit'),
    ]
    for month, mode, options, expected, defects, label in variants:
        start, end = date(2024, month, 1), _month_end(2024, month)
        rows = month_rows(2024, month, month)
        pages, closing, grids = bbva_pages(account=account, start=start, end=end, opening=balance, rows=rows,
                                           per_page=options.get('per_page'),
                                           damage_cells=options.get('damage_cells', ()))
        entry = dict(filename=f'bbva-2024-{month:02d}-{label}.pdf', mode=mode, pages=pages,
                     periods=[period(start, end, balance, rows, closing, expected, defects)])
        if options.get('ruled'):
            entry['rules'] = _bbva_rules(grids, pages)
            entry['ruled'] = True
        if options.get('degrade'):
            entry['degrade'] = options['degrade']
        if options.get('drop'):
            entry['pages'] = [p for n, p in enumerate(pages, start=1) if n not in options['drop']]
            entry['missing_pages'] = options['drop']
        entries.append(entry)
        balance = closing
    return entries


# ---------------------------------------------------------------------------
# Scotiabank Mexico (statement_import_scotiabank): zero-activity summaries.
# The reader handles only the complete three-page no-activity statement; a
# statement with a movements table is printed too and has no reader.
# ---------------------------------------------------------------------------

SCOTIA_HOLDER = 'SERVICIOS EJEMPLO SA DE CV'


def _dd_mon_yy(value):
    return f'{value.day:02d}-{_ES_MONTHS[value.month - 1]}-{value.year % 100:02d}'


def scotiabank_pages(*, account, start, end, opening, rows=()):
    deposits = sum(r['amount_minor'] for r in rows if r['direction'] == 'credit')
    withdrawals = sum(r['amount_minor'] for r in rows if r['direction'] == 'debit')
    closing = opening + deposits - withdrawals

    def pesos(minor):
        return money(minor, dollar=True)

    first = _lines(10, 12, [[L(100, 'PAGINA 1 DE 3')], [L(390, 'Scotiabank')],
                            [L(330, 'Estado de Cuenta'), L(400, 'SCOTIA INV DISP PM +')]])
    first += _lines(70, 12, [[L(40, SCOTIA_HOLDER)], [L(40, 'CALLE EJEMPLO 200')],
                             [L(400, 'Cuenta'), L(470, account)],
                             [L(400, 'Periodo'), L(470, f'{_dd_mon_yy(start)}/{_dd_mon_yy(end)}')],
                             [L(400, 'Moneda'), L(470, 'NACIONAL')]])
    first += [(250, [L(240, 'Comportamiento de transacciones en tu cuenta')]),
              (262, [L(90, 'Resumen de Saldos')]),
              (275, [L(300, f'Saldo inicial = {pesos(opening)}'), L(450, f'Saldo final= {pesos(closing)}')])]
    first += _lines(290, 15, [
        [L(50, 'Saldo inicial'), R(233, pesos(opening))],
        [L(50, '(+) Depósitos'), R(233, pesos(deposits))],
        [L(50, '(+) Intereses recibidos (Tasa 0.00%)'), R(233, '$0.00')],
        [L(50, '(-) Retiros'), R(233, pesos(withdrawals))],
        [L(50, '(-) Comisiones cobradas'), R(233, '$0.00')],
        [L(50, '(-) Impuestos'), R(233, '$0.00')]])
    chart = [(300, deposits), (345, 0), (392, withdrawals), (468, 0), (530, 0)]
    first.append((397, [L(50, '(=) Saldo final de la cuenta'), R(233, pesos(closing))]
                  + [L(x + 2, pesos(value)) for x, value in chart]))
    first.append((424, [L(300, 'Depósitos'), L(345, 'Intereses'), L(392, 'Retiros en efectivo'),
                        L(468, 'Otros cargos*'), L(530, 'Comisiones')]))
    first.append((455, [L(40, 'Sdo. Prom. Min. requerido en cuenta'), R(233, '$10,000.00')]))
    if rows:
        balance = opening
        table = [[L(40, 'Detalle de tus movimientos')],
                 [L(40, 'Fecha'), L(100, 'Concepto'), L(290, 'Referencia'), R(440, 'Depósito'), R(500, 'Retiro'),
                  R(560, 'Saldo')]]
        for item in rows:
            balance += item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
            item['balance_after'] = balance
            value = date.fromisoformat(item['date'])
            table.append([L(40, _dd_mon_yy(value)), L(100, item['description']), L(290, item['reference']),
                          R(440 if item['direction'] == 'credit' else 500, pesos(item['amount_minor'])),
                          R(560, pesos(balance))])
        first += _lines(480, 13, table)
        first.append((480 + 13 * len(table) + 6, [L(40, 'A PARTIR DEL 01-05-24 LA COMISION SERA $14.66 MAS IVA.')]))
    else:
        first.append((550, [L(40, 'A PARTIR DEL 01-05-24 LA COMISION SERA $14.66 MAS IVA.')]))
    second = _lines(10, 12, [[L(100, 'PAGINA 2 DE 3'), L(260, f'Cuenta {account}')]])
    second += _lines(130, 25, [[L(40, 'LOS SIGUIENTES DATOS SON INFORMATIVOS')],
                               [L(40, 'Total de comisiones cobradas en el Periodo:'), L(270, '$0.00')],
                               [L(40, 'Advertencias')]])
    third = _lines(10, 12, [[L(100, 'PAGINA 3 DE 3'), L(260, f'Cuenta {account}')]])
    third += _lines(150, 30, [[L(40, 'ABREVIATURAS:')], [L(40, 'USD-DOLAR ESTADOUNIDENSE')],
                              [L(40, 'TRANSFERENCIAS ELECTRONICAS')], [L(40, 'SCOTIABANK INVERLAT, S.A.')]])
    return [first, second, third], closing


def scotiabank_entries():
    entries = []
    account = '00087654321'

    def period(start, end, opening, rows, closing, expected, defects):
        return truth(family='scotiabank-mexico', institution='Scotiabank Mexico', account=account,
                     holder=SCOTIA_HOLDER, currency='MXN', start=start.isoformat(), end=end.isoformat(),
                     opening=opening, closing=closing,
                     rows=[{k: v for k, v in r.items() if k != 'reference'} for r in rows],
                     expected=expected, defects=defects)

    balance = 1_234_567
    for month, mode, degrade, defects, label in (
            (3, 'digital', None, ['no_activity_source_proven'], 'zero-activity'),
            (4, 'image_only', None, ['no_activity_source_proven', 'image_only_scan'], 'zero-activity-image-only'),
            (5, 'image_only', dict(faint=0.45), ['no_activity_source_proven', 'image_only_scan', 'faint_print'],
             'zero-activity-faint-scan')):
        start, end = date(2024, month, 1), _month_end(2024, month)
        pages, closing = scotiabank_pages(account=account, start=start, end=end, opening=balance)
        entry = dict(filename=f'scotiabank-2024-{month:02d}-{label}.pdf', mode=mode, pages=pages,
                     periods=[period(start, end, balance, [], closing, 'auto', defects)])
        if degrade:
            entry['degrade'] = degrade
        entries.append(entry)
    # The same account with activity: a movements table no reader handles.
    start, end = date(2024, 6, 1), date(2024, 6, 30)
    rows = [row('2024-06-04', 'TRANSF SPEI RECIBIDA EJEMPLO', 3_500_000, 'credit'),
            row('2024-06-11', 'PAGO PROVEEDOR EJEMPLO', 1_820_000, 'debit'),
            row('2024-06-18', 'COMISION MANEJO DE CUENTA', 15_000, 'debit'),
            row('2024-06-26', 'TRANSF SPEI ENVIADA EJEMPLO', 900_000, 'debit')]
    for n, item in enumerate(rows):
        item['reference'] = f'SC24060{n}'
    pages, closing = scotiabank_pages(account=account, start=start, end=end, opening=balance, rows=rows)
    entries.append(dict(filename='scotiabank-2024-06-with-movements.pdf', mode='digital', pages=pages,
                        periods=[period(start, end, balance, rows, closing, 'auto', ['layout_not_supported'])]))
    return entries


# ---------------------------------------------------------------------------
# Monex (statement_import_monex): one contract, a summary page per currency.
# The reader handles balance-only (zero-activity) sections; a section with
# movements has no reader.
# ---------------------------------------------------------------------------

MONEX_HOLDER = 'IMPORTADORA EJEMPLO SA DE CV'
_MONEX_MONTHS = ('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre',
                 'Octubre', 'Noviembre', 'Diciembre')


def monex_pages(*, contract, start, end, sections):
    """``sections`` is a list of (currency label, opening, rows)."""
    count = 1 + len(sections) + 3 + sum(1 for _, _, rows in sections if rows)
    cover = _lines(20, 20, [
        [L(20, 'Monex'), L(300, 'Estado de Cuenta')],
        [L(300, MONEX_HOLDER)], [L(300, 'CALLE EJEMPLO 300')], [L(300, 'C.P.'), L(420, '06000')],
        [L(300, 'TIPO DE CONTRATO:'), L(420, 'PERSONA MORAL')],
        [L(300, 'CONTRATO:'), L(420, contract)],
        [L(300, 'CTA. CLABE:'), L(420, '112180000012345678')],
        [L(300, 'RFC TITULAR:'), L(420, 'IEJ010101AB1')],
        [L(300, 'PERIODO:'), L(420, f'Del {start.day} {_MONEX_MONTHS[start.month - 1]} {start.year} '
                                     f'al {end.day} {_MONEX_MONTHS[end.month - 1]} {end.year}')]])
    pages = [cover]
    closings = []
    number = 2
    for label, opening, rows in sections:
        credits = sum(r['amount_minor'] for r in rows if r['direction'] == 'credit')
        debits = sum(r['amount_minor'] for r in rows if r['direction'] == 'debit')
        closing = opening + credits - debits
        closings.append(closing)
        page = _lines(20, 20, [
            [L(20, 'MONEX'), L(400, f'CONTRATO: {contract}')], [L(20, 'Resumen Cuenta')], [L(20, label)],
            [L(20, 'Saldo inicial:'), L(200, money(opening))],
            [L(20, '+ Total abonos:'), L(200, money(credits))],
            [L(20, '- Total cargos:'), L(200, money(debits))],
            [L(20, 'Saldo vista:'), L(200, money(closing))],
            [L(20, 'Saldo promedio:'), L(200, money(opening))]])
        page.append((700, [L(440, f'Hoja {number} de {count}')]))
        pages.append(page)
        number += 1
        if rows:
            balance = opening
            table = [[L(20, 'MONEX'), L(400, f'CONTRATO: {contract}')], [L(20, f'Movimientos {label}')],
                     [L(20, 'Fecha'), L(80, 'Concepto'), R(420, 'Abonos'), R(490, 'Cargos'), R(560, 'Saldo')]]
            for item in rows:
                balance += item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
                item['balance_after'] = balance
                value = date.fromisoformat(item['date'])
                table.append([L(20, f'{value:%d/%m/%Y}'), L(80, item['description']),
                              R(420 if item['direction'] == 'credit' else 490, money(item['amount_minor'])),
                              R(560, money(balance))])
            page = _lines(20, 20, table)
            page.append((700, [L(440, f'Hoja {number} de {count}')]))
            pages.append(page)
            number += 1
    for label in ('Referencias bancarias', 'Estimado cliente:', 'Aviso de seguridad de la informacion'):
        pages.append(_lines(20, 20, [[L(20, 'MONEX'), L(400, f'CONTRATO: {contract}')], [L(20, label)],
                                     [L(20, 'Instrucciones de deposito USD EUR GBP MXN')]])
                     + [(700, [L(440, f'Hoja {number} de {count}')])])
        number += 1
    return pages, closings


def monex_entries():
    entries = []
    contract = '7712345'

    def period(start, end, opening, rows, closing, currency, expected, defects, note):
        return truth(family='monex-mexico', institution='Monex', account=contract, holder=MONEX_HOLDER,
                     currency=currency, start=start.isoformat(), end=end.isoformat(), opening=opening,
                     closing=closing, rows=rows, expected=expected, defects=defects, notes=note)

    start, end = date(2024, 3, 1), date(2024, 3, 31)
    pages, closings = monex_pages(contract=contract, start=start, end=end,
                                  sections=[('Peso Mexicano', 3_214_550, []), ('Dolar Americano', 7_900, [])])
    entries.append(dict(filename='monex-2024-03-two-currencies-zero-activity.pdf', mode='digital', pages=pages,
        periods=[period(start, end, 3_214_550, [], closings[0], 'MXN', 'auto', ['no_activity_source_proven'],
                        'currency section Peso Mexicano'),
                 period(start, end, 7_900, [], closings[1], 'USD', 'auto', ['no_activity_source_proven'],
                        'currency section Dolar Americano')]))
    start, end = date(2024, 4, 1), date(2024, 4, 30)
    rows = [row('2024-04-08', 'TRASPASO RECIBIDO EJEMPLO', 1_500_000, 'credit'),
            row('2024-04-19', 'PAGO INTERNACIONAL EJEMPLO', 2_250_000, 'debit')]
    pages, closings = monex_pages(contract=contract, start=start, end=end,
                                  sections=[('Peso Mexicano', 3_214_550, rows), ('Dolar Americano', 7_900, [])])
    entries.append(dict(filename='monex-2024-04-peso-movements.pdf', mode='digital', pages=pages,
        periods=[period(start, end, 3_214_550, rows, closings[0], 'MXN', 'auto', ['layout_not_supported'],
                        'currency section Peso Mexicano'),
                 period(start, end, 7_900, [], closings[1], 'USD', 'auto', ['no_activity_source_proven'],
                        'currency section Dolar Americano')]))
    return entries


# ---------------------------------------------------------------------------
# Kapital and Intercam (statement_import_kapital): product sections scoped by
# CLABE and Moneda, a DIA/FOLIO/CONCEPTO/DEPOSITOS/RETIROS/SALDO table.
# ---------------------------------------------------------------------------

def _kapital_header(brand, start, end, number):
    return _lines(20, 20, [[L(20, brand), L(360, 'ESTADO DE CUENTA UNICO')],
                           [L(360, f'Periodo DEL {start.isoformat()} AL {end.isoformat()}')],
                           [L(360, 'Numero'), L(410, number)],
                           [L(360, 'Cliente'), L(410, '87654321')],
                           [L(360, 'R.F.C.'), L(410, 'DEJ010101AB1')]])


def _kapital_footer():
    """The fiscal notice these statements print at the foot of every page."""
    return _lines(700, 10, [[L(40, 'Este documento es una representacion impresa de un CFDI. Para aclaraciones o '
                                   'reclamaciones acuda a su sucursal.')],
                            [L(40, 'Las comisiones vigentes pueden consultarse en la pagina de internet de la '
                                   'institucion y en sucursales.')]])


def kapital_product(*, product, clabe, currency, opening, rows, top):
    """Lines for one product section; returns (lines, closing)."""
    marker = 'MN' if currency == 'MXN' else currency
    deposits = sum(r['amount_minor'] for r in rows if r['direction'] == 'credit')
    withdrawals = sum(r['amount_minor'] for r in rows if r['direction'] == 'debit')
    closing = opening + deposits - withdrawals
    lines = _lines(top, 18, [
        [L(40, product), L(260, f'CLABE {clabe}')],
        [L(40, 'Moneda'), L(220, marker)],
        [L(40, 'Saldo Inicial'), L(220, f'{money(opening)} {marker}')],
        [L(40, '+ Depositos'), L(220, f'{money(deposits)} {marker}')],
        [L(40, '- Retiros'), L(220, f'{money(withdrawals)} {marker}')],
        [L(40, 'Saldo Final'), L(220, f'{money(closing)} {marker}')]])
    if rows:
        y = top + 6 * 18 + 10
        lines.append((y, [L(41, 'DIA'), L(78, 'FOLIO'), L(245, 'CONCEPTO'), R(446, 'DEPOSITOS'), R(502, 'RETIROS'),
                          R(557, 'SALDO')]))
        balance = opening
        for index, item in enumerate(rows):
            y += 13
            balance += item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
            item['balance_after'] = balance
            lines.append((y, [L(41, f'{date.fromisoformat(item["date"]).day:02d}'), L(78, f'{30140000 + index}'),
                              L(147, item['description']),
                              R(446 if item['direction'] == 'credit' else 502, money(item['amount_minor'])),
                              R(557, money(balance))]))
        lines.append((y + 13, [L(370, 'Total'), R(446, money(deposits)), R(502, money(withdrawals)),
                               R(557, money(closing))]))
    return lines, closing


def kapital_entries():
    entries = []
    holder = 'DISTRIBUIDORA EJEMPLO'

    def period(institution, family, clabe, currency, start, end, opening, rows, closing, expected, defects):
        return truth(family=family, institution=institution, account=clabe, holder=holder, currency=currency,
                     start=start.isoformat(), end=end.isoformat(), opening=opening, closing=closing, rows=rows,
                     expected=expected, defects=defects, notes=f'CLABE {clabe}')

    mn_clabe, usd_clabe = '128180000000000011', '128180000000000024'
    mn, usd = 2_500_000, 125_000
    for month, mode, label, defects in ((3, 'digital', 'two-products', []),
                                        (4, 'image_only', 'two-products-image-only', ['image_only_scan'])):
        start, end = date(2024, month, 1), _month_end(2024, month)
        rows = [row(date(2024, month, 5).isoformat(), f'SPEI RECIBIDO CLIENTE EJEMPLO {month}', 1_800_000, 'credit'),
                row(date(2024, month, 12).isoformat(), 'COMISION POR TIMBRADO FISCAL', 1_160, 'debit'),
                row(date(2024, month, 20).isoformat(), f'SPEI ENVIADO PROVEEDOR {month}', 950_000, 'debit')]
        number = f'4202{month:02d}12345678'[:15]
        first = _kapital_header('kapital', start, end, number)
        first += _lines(120, 30, [[L(30, holder)], [L(30, 'Persona Moral')]])
        product, mn_closing = kapital_product(product='SERVICIO EMPRESARIAL FX KAPITAL 123-456-001-6', clabe=mn_clabe,
                                              currency='MXN', opening=mn, rows=rows, top=300)
        first += product + _kapital_footer()
        second = _kapital_header('kapital', start, end, number)
        product, usd_closing = kapital_product(product='SERVICIO EMPRESARIAL FX USD KAPITAL 123-456-002-4',
                                               clabe=usd_clabe, currency='USD', opening=usd, rows=[], top=300)
        second += product + _kapital_footer()
        entries.append(dict(filename=f'kapital-2024-{month:02d}-{label}.pdf', mode=mode, pages=[first, second],
            periods=[period('Kapital', 'kapital-mexico', mn_clabe, 'MXN', start, end, mn, rows, mn_closing, 'auto',
                            defects),
                     period('Kapital', 'kapital-mexico', usd_clabe, 'USD', start, end, usd, [], usd_closing, 'auto',
                            defects + ['no_activity_source_proven'])]))
        mn, usd = mn_closing, usd_closing

    # Intercam prints the same product statement with its own product name
    # and a 136 CLABE; one peso product with movements.
    clabe = '136180000000000017'
    opening = 4_400_000
    start, end = date(2024, 5, 1), date(2024, 5, 31)
    rows = [row('2024-05-07', 'SPEI RECIBIDO EJEMPLO COMERCIAL', 2_000_000, 'credit'),
            row('2024-05-15', 'COMPRA DE DIVISAS EJEMPLO', 3_100_000, 'debit'),
            row('2024-05-28', 'COMISION SPEI', 580, 'debit')]
    page = _kapital_header('Intercam', start, end, '510202405000123')
    page += _lines(120, 30, [[L(30, holder)], [L(30, 'Persona Moral')]])
    product, closing = kapital_product(product='SERVICIO EMPRESARIAL FX 123-456-001-6', clabe=clabe, currency='MXN',
                                       opening=opening, rows=rows, top=300)
    page += product + _kapital_footer()
    entries.append(dict(filename='intercam-2024-05-peso-product.pdf', mode='digital', pages=[page],
        periods=[period('Intercam', 'intercam-mexico', clabe, 'MXN', start, end, opening, rows, closing, 'auto', [])]))
    return entries


# ---------------------------------------------------------------------------
# Santander Mexico (statement_import_santander): account-scoped movement
# sections, continued across pages by repeating the customer/period header.
# ---------------------------------------------------------------------------

SANTANDER_HOLDER = 'TRANSPORTES EJEMPLO SA DE CV'


def _dd_mon_yyyy(value):
    return f'{value.day:02d}-{_ES_MONTHS[value.month - 1]}-{value.year}'


def _santander_context(start, end):
    return _lines(20, 20, [[L(30, 'Banco Santander Mexico, S.A.')],
                           [L(30, SANTANDER_HOLDER), L(350, 'CODIGO DE CLIENTE NO. 23456789')],
                           [L(330, f'PERIODO DEL {_dd_mon_yyyy(start)} AL {_dd_mon_yyyy(end)}')],
                           [L(330, 'MONEDA'), L(430, 'MONEDA NACIONAL')]])


SANTANDER_COLUMNS = [L(30, 'FECHA'), L(80, 'FOLIO'), L(120, 'DESCRIPCION'), R(420, 'DEPOSITO'), R(485, 'RETIRO'),
                     R(550, 'SALDO')]


def santander_pages(*, start, end, checking, cheques_rows, savings, per_page=None):
    """Return (pages, cheques closing, savings closing).

    The checking section's movements are split by ``per_page`` (counts); the
    investment section (no movements) follows on the last page.
    """
    chunks, remaining = [], list(cheques_rows)
    for size in (per_page or [len(cheques_rows)]):
        chunks.append(remaining[:size])
        remaining = remaining[size:]
    assert not remaining
    count = len(chunks)
    deposits = sum(r['amount_minor'] for r in cheques_rows if r['direction'] == 'credit')
    withdrawals = sum(r['amount_minor'] for r in cheques_rows if r['direction'] == 'debit')
    closing = checking + deposits - withdrawals
    balance = checking
    pages = []
    folio = 0
    for number, chunk in enumerate(chunks, start=1):
        lines = _santander_context(start, end)
        y = 120
        if number == 1:
            lines += _lines(y, 20, [[L(30, 'Detalle de movimientos cuenta de cheques.')],
                                    [L(30, 'CUENTA SANTANDER PYME 65-00012345-6')],
                                    [L(30, 'SALDO FINAL DEL PERIODO ANTERIOR:'), R(550, money(checking, dollar=True))]])
            y += 60
        lines.append((y, SANTANDER_COLUMNS))
        for item in chunk:
            y += 18
            folio += 1
            balance += item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
            item['balance_after'] = balance
            lines.append((y, [L(30, _dd_mon_yyyy(date.fromisoformat(item['date']))), L(80, f'{folio:07d}'),
                              L(120, item['description']),
                              R(420 if item['direction'] == 'credit' else 485, money(item['amount_minor'])),
                              R(550, money(balance))]))
        if number == count:
            y += 22
            lines += [(y, [L(120, 'TOTAL'), R(420, money(deposits)), R(485, money(withdrawals))]),
                      (y + 20, [L(30, 'SALDO FINAL DEL PERIODO:'), R(550, money(closing, dollar=True))])]
            y += 60
            lines += _lines(y, 20, [[L(30, 'Detalles de movimientos Dinero Creciente Santander.')],
                                    [L(30, 'INVERSION CRECIENTE 66-00012345-6')],
                                    [L(30, 'SALDO FINAL DEL PERIODO ANTERIOR:'), R(550, money(savings))],
                                    SANTANDER_COLUMNS,
                                    [L(120, 'TOTAL'), R(420, '0.00'), R(485, '0.00')],
                                    [L(30, 'SALDO FINAL DEL PERIODO:'), R(550, money(savings, dollar=True))]])
        lines.append((780, [L(500, f'PAGINA {number} DE {count}')]))
        pages.append(lines)
    return pages, closing, savings


def santander_entries():
    entries = []

    def period(account, start, end, opening, rows, closing, expected, defects, note):
        return truth(family='santander-mexico', institution='Santander', account=account, holder=SANTANDER_HOLDER,
                     currency='MXN', start=start.isoformat(), end=end.isoformat(), opening=opening, closing=closing,
                     rows=rows, expected=expected, defects=defects, notes=note)

    def month_rows(month, count):
        names = ['DEPOSITO EN EFECTIVO EJEMPLO', 'PAGO TRANSFERENCIA SPEI EJEMPLO', 'CARGO DOMICILIADO EJEMPLO',
                 'ABONO TRANSFERENCIA SPEI EJEMPLO', 'COMISION MANEJO DE CUENTA', 'PAGO NOMINA EJEMPLO']
        result = []
        for n in range(count):
            direction = 'credit' if n % 3 == 0 else 'debit'
            result.append(row(date(2024, month, 2 + 2 * n).isoformat(), f'{names[n % len(names)]} {month}-{n}',
                              (1_250_000 if direction == 'credit' else 210_000) + 1_111 * n, direction))
        return result

    checking, savings = 900_000, 5_000_000
    for month, mode, per_page, drop, expected_cheques, defects, label in (
            (3, 'digital', None, None, 'auto', [], 'clean'),
            (4, 'digital', [5, 4], None, 'auto', ['multi_page'], 'continued'),
            (5, 'digital', [4, 4, 3], [2], 'hold', ['missing_page'], 'missing-page-2'),
            (6, 'image_only', None, None, 'auto', ['image_only_scan'], 'image-only')):
        start, end = date(2024, month, 1), _month_end(2024, month)
        rows = month_rows(month, sum(per_page) if per_page else 6)
        pages, closing, savings_closing = santander_pages(start=start, end=end, checking=checking,
                                                          cheques_rows=rows, savings=savings, per_page=per_page)
        entry = dict(filename=f'santander-2024-{month:02d}-{label}.pdf', mode=mode, pages=pages,
            periods=[period('65000123456', start, end, checking, rows, closing, expected_cheques, defects,
                            'CUENTA SANTANDER PYME 65-00012345-6'),
                     period('66000123456', start, end, savings, [], savings_closing, 'auto',
                            [d for d in defects if d != 'missing_page'] + ['no_activity_source_proven'],
                            'INVERSION CRECIENTE 66-00012345-6')])
        if drop:
            entry['pages'] = [p for n, p in enumerate(pages, start=1) if n not in drop]
            entry['missing_pages'] = drop
        entries.append(entry)
        checking = closing
    return entries


# ---------------------------------------------------------------------------
# Andrews teller deposit receipts (deposit_receipt_proposal): evidence of a
# deposit, never a statement period. Uploaded with statements they must be
# kept out of the statement ledger.
# ---------------------------------------------------------------------------

def receipt_page(*, account_mask, holder, effective, printed, share, previous, amount, sequence):
    texts = ['Andrews Federal Credit Union', 'EXAMPLE BRANCH', f'Acct {account_mask} {holder}',
             f'Eff: {effective:%m/%d/%y} Date: {printed:%m/%d/%y}', 'Tlr: 1234 12:35pm',
             f'Deposit to {share}', f'Prev Bal: {money(previous)}', f'Amount: {money(amount)}',
             f'New Bal: {money(previous + amount)}', f'Seq: {sequence}', f'Acct {account_mask}',
             f'Avail Bal S{share[-4:]} {money(previous + amount)}', 'Check Received', 'Receipt Delivery:']
    return _lines(30, 18, [[L(40, text)] for text in texts])


def receipt_entries():
    entries = []
    for day, mode, label, defects in ((date(2021, 3, 23), 'digital', 'digital', []),
                                      (date(2021, 4, 14), 'image_only', 'scan', ['image_only_scan'])):
        page = receipt_page(account_mask='XXXXXX5678', holder='EXAMPLE PERSON', effective=day,
                            printed=day + timedelta(days=1), share='FREE CHECKING 0040', previous=100_000,
                            amount=12_000 + day.day, sequence=f'SYN{day:%m%d}')
        entries.append(dict(filename=f'andrews-receipt-{day:%Y-%m-%d}-{label}.pdf', mode=mode, pages=[page],
            periods=[truth(family='andrews-deposit-receipt', institution='Andrews', account='5678',
                           holder='EXAMPLE PERSON', currency='USD', start=None, end=None, opening=None, closing=None,
                           rows=[], expected='not_statement', defects=['deposit_receipt'] + defects,
                           notes='teller deposit receipt; must not be admitted as a statement period')]))
    return entries


# ---------------------------------------------------------------------------
# Generic labelled statements (no registered layout) under new accounts:
# degraded scans, overdraft, MXN, ruled grid, multi-page and missing pages.
# ---------------------------------------------------------------------------

def generic_v4_pages(*, bank, holder, account, currency, start, end, opening, rows, per_page=None,
                     damage_cells=(), ruled=False):
    """Return (pages, closing, rules). Negative balances print a leading minus.

    ``per_page`` splits the rows across pages (counts); every page carries
    "Page n of m" and continuation pages repeat the column headings.
    """
    chunks, remaining = [], list(enumerate(rows))
    for size in (per_page or [len(rows)]):
        chunks.append(remaining[:size])
        remaining = remaining[size:]
    assert not remaining
    count = len(chunks)
    columns = [L(40, 'Date'), L(120, 'Description'), R(380, 'Credit'), R(460, 'Debit'), R(560, 'Balance')]
    balance = opening
    pages, rules = [], []
    for number, chunk in enumerate(chunks, start=1):
        if number == 1:
            lines = [(40, [L(40, f'Bank: {bank}')]), (54, [L(40, f'Account Name: {holder}')]),
                     (68, [L(40, f'Account Number: {account}')]), (82, [L(40, f'Currency: {currency}')]),
                     (96, [L(40, f'Statement Period: {start:%B} {start.day}, {start.year} - '
                                 f'{end:%B} {end.day}, {end.year}')]),
                     (130, columns),
                     (146, [L(40, start.isoformat()), L(120, 'Opening Balance'), R(560, _signed(opening))])]
            y = 160
        else:
            lines = [(40, [L(40, f'{bank} - Account Number: {account}')]), (70, columns)]
            y = 86
        # Rules: above the headings, under them (above the opening balance on
        # page 1), between rows and below the last row.
        table_top, row_tops = (126 if number == 1 else 66), ([143] if number == 1 else [])
        for index, item in chunk:
            balance += item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
            item['balance_after'] = balance
            amount = money(item['amount_minor'])
            ocr = damage(amount) if index in damage_cells else None
            row_tops.append(y - 3)
            lines.append((y, [L(40, item['date']), L(120, item['description']),
                              R(380 if item['direction'] == 'credit' else 460, amount, ocr), R(560, _signed(balance))]))
            y += 14
        if number == count:
            row_tops.append(y - 3)
            lines.append((y, [L(40, end.isoformat()), L(120, 'Closing Balance'), R(560, _signed(balance))]))
            y += 14
        lines.append((760, [L(260, f'Page {number} of {count}')]))
        pages.append(lines)
        if ruled:
            bottom = y - 3
            xs = [36, 116, 330, 400, 480, 566]
            segments = [(xs[0], t, xs[-1], t) for t in sorted({table_top, *row_tops, bottom})]
            segments += [(x, table_top, x, bottom) for x in xs]
            rules.append(segments)
    return pages, balance, (rules if ruled else None)


def _generic_v4_rows(year, month, seed, *, large_debit=0):
    base = [('Incoming transfer', 98_000 + seed * 1_000, 'credit'), ('Card purchase hardware', 7_215 + seed, 'debit'),
            ('Insurance direct debit', 21_450, 'debit'), ('Client payment received', 164_000 + seed, 'credit'),
            ('Wire to contractor', 77_700 + seed * 10, 'debit')]
    if large_debit:
        base.insert(2, ('Wire to property escrow', large_debit, 'debit'))
    return [row(date(year, month, 2 + 5 * i).isoformat(), f'{desc} {month:02d}-{i}', amount, direction)
            for i, (desc, amount, direction) in enumerate(base)]


DAMAGE_MATRIX = [
    # label, degrade, defects
    ('skew-1deg', dict(skew=1.0), ['skew']),
    ('skew-2-5deg', dict(skew=2.5), ['skew']),
    ('150dpi', dict(dpi=150), ['low_dpi']),
    ('100dpi', dict(dpi=100), ['low_dpi']),
    ('jpeg-noise', dict(jpeg=30, noise=8), ['jpeg_noise']),
    ('faint', dict(faint=0.45), ['faint_print']),
    ('combined', dict(dpi=150, skew=1.0, faint=0.6, jpeg=40, noise=6), ['skew', 'low_dpi', 'faint_print', 'jpeg_noise']),
]


def generic_v4_entries():
    entries = []
    bank, holder, account = 'Lakeside Synthetic Bank', 'Southwind Synthetic Holdings LLC', '66602345'

    def period(start, end, opening, rows, closing, expected, defects, currency='USD', account=account,
               holder=holder, bank=bank):
        return truth(family='generic-labelled', institution=bank, account=account, holder=holder,
                     currency=currency, start=start.isoformat(), end=end.isoformat(), opening=opening,
                     closing=closing, rows=rows, expected=expected, defects=defects)

    balance = 500_000
    months = iter([(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 13)])

    def add(label, mode, defects, expected='auto', degrade=None, per_page=None, drop=None, damage_cells=(),
            ruled=False, large_debit=0):
        nonlocal balance
        year, month = next(months)
        start, end = date(year, month, 1), _month_end(year, month)
        rows = _generic_v4_rows(year, month, month, large_debit=large_debit)
        if per_page:
            rows += [row(date(year, month, 23 + i).isoformat(), f'Card purchase office {month:02d}-{9 + i}',
                         3_300 + i, 'debit') for i in range(sum(per_page) - len(rows))]
        pages, closing, rules = generic_v4_pages(bank=bank, holder=holder, account=account, currency='USD',
                                                 start=start, end=end, opening=balance, rows=rows,
                                                 per_page=per_page, damage_cells=damage_cells, ruled=ruled)
        entry = dict(filename=f'generic-v4-{year}-{month:02d}-{label}.pdf', mode=mode, pages=pages,
                     periods=[period(start, end, balance, rows, closing, expected, defects)])
        if degrade:
            entry['degrade'] = degrade
        if rules:
            entry['rules'] = rules
            entry['ruled'] = True
        if drop:
            entry['pages'] = [p for n, p in enumerate(pages, start=1) if n not in drop]
            entry['missing_pages'] = drop
        entries.append(entry)
        balance = closing

    for label, degrade, defects in DAMAGE_MATRIX:
        add(f'scan-{label}', 'image_only', ['image_only_scan'] + defects, degrade=degrade)
    add('ocr-amount-digit-poor-scan', 'scan_text_layer', ['ocr_amount_digit', 'low_dpi', 'jpeg_noise'],
        degrade=dict(dpi=150, jpeg=35, noise=6), damage_cells={1})
    add('ruled', 'digital', ['ruled_pdf'], ruled=True)
    add('overdrawn', 'digital', ['negative_balance'], large_debit=balance + 150_000)
    add('three-pages', 'digital', ['multi_page'], per_page=[4, 4, 3])
    add('missing-page-2', 'digital', ['missing_page'], expected='hold', per_page=[4, 4, 3], drop=[2])
    add('missing-last-page', 'digital', ['missing_page'], expected='hold', per_page=[4, 4, 3], drop=[3])

    # Pesos on a generic labelled statement.
    mx_bank, mx_holder, mx_account = 'Banco Sintetico del Norte', 'Comercial Sintetica del Norte SA de CV', '77703456'
    start, end = date(2025, 3, 1), date(2025, 3, 31)
    rows = _generic_v4_rows(2025, 3, 7)
    pages, closing, _ = generic_v4_pages(bank=mx_bank, holder=mx_holder, account=mx_account, currency='MXN',
                                         start=start, end=end, opening=2_000_000, rows=rows)
    entries.append(dict(filename='generic-v4-mxn-2025-03-clean.pdf', mode='digital', pages=pages,
        periods=[period(start, end, 2_000_000, rows, closing, 'auto', ['mxn'], currency='MXN', account=mx_account,
                        holder=mx_holder, bank=mx_bank)]))
    return entries


# ---------------------------------------------------------------------------
# Andrews share statements (the layout that dominates the live batch) under
# a new account: the degraded-scan matrix, a continued section and a missing
# continuation page.
# ---------------------------------------------------------------------------

ANDREWS_V4_ACCOUNT = '987654321'


def andrews_v4_entries():
    from benchmarks.statement_automation.corpus import andrews_page, _andrews_header, _mmdd
    entries = []
    account = ANDREWS_V4_ACCOUNT
    savings, checking = 72_000, 310_000
    months = iter([(2022, m) for m in range(1, 13)])

    def share_rows(year, month):
        save = [row(date(year, month, 4).isoformat(), 'Deposit Online Banking Transfer From Share 0040', 4_000, 'credit'),
                row(date(year, month, 23).isoformat(), 'Deposit Dividend', 21, 'credit')]
        check = [row(date(year, month, 4).isoformat(), 'Withdrawal Online Banking Transfer To Share 0000', 4_000, 'debit'),
                 row(date(year, month, 8).isoformat(), f'Withdrawal Debit Card EXAMPLE GROCER {month}', 6_123 + month, 'debit'),
                 row(date(year, month, 15).isoformat(), 'Deposit ACH EXAMPLE EMPLOYER PAYROLL', 121_000, 'credit'),
                 row(date(year, month, 19).isoformat(), f'Withdrawal ACH EXAMPLE UTILITY {month}', 9_870, 'debit'),
                 row(date(year, month, 27).isoformat(), 'Withdrawal Check 1042', 25_000, 'debit')]
        return save, check

    def truths(start, end, openings, closings, rows_by_share, defects, expected=None):
        expected = expected or {}
        return [truth(family='andrews-share', institution='Andrews', account=account, holder='EXAMPLE PERSON',
                      currency='USD', start=start.isoformat(), end=end.isoformat(), opening=openings[share],
                      closing=closings[share], rows=rows_by_share[share], expected=expected.get(share, 'auto'),
                      defects=defects.get(share, []), notes=f'share {share}') | dict(share=share)
                for share in ('0000', '0040')]

    def standard(label, mode, defects, degrade=None, damage_cells=()):
        nonlocal savings, checking
        year, month = next(months)
        start, end = date(year, month, 1), _month_end(year, month)
        save, check = share_rows(year, month)
        lines, closings = andrews_page(account=account, start=start, end=end,
                                       shares=[('0000', 'BASE SHARE SAVINGS', savings, save),
                                               ('0040', 'FREE CHECKING', checking, check)],
                                       damage_cells=damage_cells)
        share_defects = {'0000': list(defects), '0040': list(defects)}
        if damage_cells:
            share_defects['0040'] = share_defects['0040'] + ['ocr_amount_digit']
        entry = dict(filename=f'andrews-v4-{year}-{month:02d}-{label}.pdf', mode=mode, pages=[lines],
                     periods=truths(start, end, {'0000': savings, '0040': checking}, closings,
                                    {'0000': save, '0040': check}, share_defects))
        if degrade:
            entry['degrade'] = degrade
        entries.append(entry)
        savings, checking = closings['0000'], closings['0040']

    standard('scan-image-only', 'image_only', ['image_only_scan'])
    for label, degrade, defects in DAMAGE_MATRIX:
        standard(f'scan-{label}', 'image_only', ['image_only_scan'] + defects, degrade=degrade)
    standard('ocr-amount-digit-faint-scan', 'scan_text_layer', ['faint_print'], degrade=dict(faint=0.5),
             damage_cells={('0040', 1, 'amount')})

    # The checking section continues on printed page 2: complete, then the
    # same shape with page 2 missing (the checking period must be held).
    for label, drop in (('continued-section', None), ('missing-page-2', [2])):
        year, month = next(months)
        start, end = date(year, month, 1), _month_end(year, month)
        save, check = share_rows(year, month)
        first = _andrews_header(account, start, end, 1)
        y = 220
        closings = {}
        balance = savings
        first.append((y, [L(15, f'{start:%m/%d} ID 0000 BASE SHARE SAVINGS Previous Balance'), R(380, money(savings))]))
        for item in save:
            y += 12
            balance += item['amount_minor']
            item['balance_after'] = balance
            first.append((y, [L(15, _mmdd(item['date'])), L(75, item['description']), R(340, money(item['amount_minor'])),
                              R(380, money(balance))]))
        y += 12
        first.append((y, [L(15, _mmdd(end.isoformat())), L(75, 'Ending Balance'), R(380, money(balance))]))
        closings['0000'] = balance
        y += 12
        first.append((y, [L(15, f'{start:%m/%d} ID 0040 FREE CHECKING Previous Balance'), R(380, money(checking))]))
        balance = checking
        lines_by_index = []
        for item in check:
            delta = item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
            balance += delta
            item['balance_after'] = balance
            lines_by_index.append([L(15, _mmdd(item['date'])), L(75, item['description']),
                                   R(340, ('-' if delta < 0 else '') + money(item['amount_minor'])), R(380, money(balance))])
        closings['0040'] = balance
        for cells in lines_by_index[:2]:
            y += 12
            first.append((y, cells))
        first.append((y + 12, [L(15, 'Continued on following page')]))
        second = _andrews_header(account, start, end, 2, names=False)
        y = 220
        for cells in lines_by_index[2:]:
            second.append((y, cells))
            y += 12
        second.append((y, [L(15, _mmdd(end.isoformat())), L(75, 'Ending Balance'), R(380, money(balance))]))
        defects = {'0040': ['multi_page'] + (['missing_page'] if drop else [])}
        entry = dict(filename=f'andrews-v4-{year}-{month:02d}-{label}.pdf', mode='digital', pages=[first, second],
                     periods=truths(start, end, {'0000': savings, '0040': checking}, closings,
                                    {'0000': save, '0040': check}, defects,
                                    expected={'0040': 'hold'} if drop else None))
        if drop:
            entry['pages'] = [first]
            entry['missing_pages'] = drop
        entries.append(entry)
        savings, checking = closings['0000'], closings['0040']
    return entries


# ---------------------------------------------------------------------------
# Credit One with a credit balance (an overpayment): the layout prints the
# balance with a trailing minus, e.g. $75.00-.
# ---------------------------------------------------------------------------

def credit_one_credit_balance_entries():
    from benchmarks.statement_automation.corpus import credit_one_page
    entries = []
    card = '4222 3333 4444 5555'
    balance = 5_000
    for number, (start, end, rows) in enumerate((
            (date(2024, 9, 16), date(2024, 10, 15),
             [row('2024-09-20', 'EXAMPLE SHOP CB1', 2_500, 'debit'),
              row('2024-09-28', 'PAYMENT RECEIVED CB1', 15_000, 'credit')]),
            (date(2024, 10, 16), date(2024, 11, 15),
             [row('2024-10-22', 'EXAMPLE CAFE CB2', 3_000, 'debit')]))):
        lines, truth_rows, closing = credit_one_page(account=card, start=start, end=end, opening=balance, rows=rows,
                                                     interest=0)
        patched = []
        for y, cells in lines:
            new = []
            for index, c in enumerate(cells):
                c = dict(c)
                label = cells[index - 1]['text'] if index else ''
                if label == 'Previous Balance' and balance < 0:
                    c['text'] += '-'
                elif label == 'New Balance' and closing < 0:
                    c['text'] += '-'
                elif label == 'Minimum Payment Due' and closing < 0:
                    c['text'] = '$0.00'
                new.append(c)
            patched.append((y, new))
        entries.append(dict(filename=f'credit-one-v4-cycle-{number + 1}-credit-balance.pdf', mode='digital',
                            pages=[patched],
                            periods=[truth(family='credit-one-card', institution='Credit One Bank',
                                           account=card.replace(' ', ''), holder='EXAMPLE PERSON', currency='USD',
                                           start=start.isoformat(), end=end.isoformat(), opening=balance,
                                           closing=closing, rows=truth_rows, expected='auto',
                                           defects=['credit_balance'])]))
        balance = closing
    return entries


def v4_entries():
    entries = []
    entries += capital_one_entries()
    entries += bbva_entries()
    entries += scotiabank_entries()
    entries += monex_entries()
    entries += kapital_entries()
    entries += santander_entries()
    entries += receipt_entries()
    entries += generic_v4_entries()
    entries += andrews_v4_entries()
    entries += credit_one_credit_balance_entries()
    return entries
