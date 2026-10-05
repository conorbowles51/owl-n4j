"""Deterministic synthetic statement corpus with ground truth.

Every name, number and payment here is invented. The PDFs mimic the printed
shapes that the registered layout readers recognise (generic labelled
statements, Credit One, Merrick and Andrews), and inject the defects observed
in real collections: damaged OCR digits in amount/balance cells, an unprinted
statement start date, missing holder or account fields, an omitted payment
row, exact duplicate copies, genuinely quiet periods and multi-period PDFs.

Three render modes:

* ``digital``: an ordinary embedded text layer.
* ``scan_text_layer``: the printed page is a raster image and the embedded
  text is an invisible OCR layer. Defects live in the OCR layer only; the image
  shows the true values, exactly as a scanned production with poor OCR does.
* ``image_only``: the raster image with no text layer, forcing full-page OCR.
* ``tiled_text_layer`` (r1-reproduced): the printed lines are small image
  strips that cover a fraction of the page, under an invisible OCR layer; the
  shape of a third-party OCR production that does not raster the whole page.

Run ``python -m benchmarks.statement_automation.corpus --out DIR`` from
``backend/`` to regenerate. Output is byte-stable for a given PyMuPDF version;
the committed manifest records each file's SHA-256 so a regenerated corpus
that differs is detected before it is compared with an older baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

PAGE_WIDTH, PAGE_HEIGHT = 600, 800
FONT_SIZE = 7
SCAN_DPI = 200
CORPUS_VERSION = 'statement-automation-corpus-v4'


# ---------------------------------------------------------------------------
# Page model: a page is a list of printed cells. Each cell has a position,
# printed text, and optionally a different OCR-layer text (a defect).
# ---------------------------------------------------------------------------

def L(x, text, ocr=None):
    return dict(x=x, text=text, ocr=ocr, align='left')


def R(right, text, ocr=None):
    return dict(x=right, text=text, ocr=ocr, align='right')


def money(minor, *, dollar=False, sign=''):
    value = f'{abs(minor) // 100:,}.{abs(minor) % 100:02d}'
    return f"{sign}{'$' if dollar else ''}{value}"


def damage(text):
    """A plausible OCR misreading of one digit; never changes the image."""
    for good, bad in (('0', 'O'), ('5', 'S'), ('1', 'l'), ('8', 'B')):
        index = text.rfind(good, 0, len(text) - 3) if '.' in text else text.rfind(good)
        if index >= 0:
            return text[:index] + bad + text[index + 1:]
    return text[:-1] + '?'


def shift(text, delta_minor):
    """``text`` misread by exactly one digit so that its value moves by ``delta_minor``.

    The result is a valid-looking amount in the same printed format, the shape
    of an OCR confusion such as 3/8, 5/6, 1/7 or 0/8. Raises if no single-digit
    change produces that value, so a corpus case cannot silently become a
    different defect.
    """
    sign = '-' if text.startswith('-') else ''
    trailing = '-' if text.endswith('-') else ''
    dollar = '$' in text
    digits = int(''.join(ch for ch in text if ch.isdigit()))
    value = -digits if sign or trailing else digits
    moved = value + delta_minor
    if (moved < 0) != (value < 0) or moved == 0:
        raise ValueError(f'{text} cannot move by {delta_minor} without changing sign')
    result = money(moved, dollar=dollar, sign=sign) + trailing
    if len(result) != len(text) or sum(a != b for a, b in zip(result, text)) != 1:
        raise ValueError(f'{text} -> {result} is not a single-digit misreading')
    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _draw(page, lines, *, use_ocr, render_mode=0):
    import fitz
    for y, cells in lines:
        for cell in cells:
            text = cell['ocr'] if use_ocr and cell['ocr'] is not None else cell['text']
            if not text:
                continue  # the OCR layer lost this printed text entirely
            width = fitz.get_text_length(text, fontname='helv', fontsize=FONT_SIZE)
            x = cell['x'] - width if cell['align'] == 'right' else cell['x']
            page.insert_text((x, y + FONT_SIZE), text, fontsize=FONT_SIZE, fontname='helv',
                             render_mode=render_mode)


def _rule(page, segments):
    """Drawn table rules (corpus v4 ruled PDFs): thin vector lines."""
    import fitz
    for x0, y0, x1, y1 in segments:
        page.draw_line(fitz.Point(x0, y0), fitz.Point(x1, y1), color=(0, 0, 0), width=0.6)


def _degraded_scan(source, degrade, seed):
    """Raster of ``source`` with the damage of a poor production scan.

    ``degrade`` keys (all optional): ``dpi`` scan resolution; ``faint``
    fraction of ink density kept (0.4 = pale toner); ``skew`` degrees of
    rotation; ``noise`` Gaussian sigma in grey levels; ``jpeg`` quality.
    Deterministic: the noise generator is seeded per page.
    """
    import io
    import fitz
    import numpy
    from PIL import Image
    pixmap = source.get_pixmap(dpi=degrade.get('dpi', SCAN_DPI), colorspace=fitz.csGRAY, alpha=False)
    image = Image.frombytes('L', (pixmap.width, pixmap.height), pixmap.samples)
    if degrade.get('faint'):
        keep = degrade['faint']
        image = image.point(lambda v: int(round(255 - (255 - v) * keep)))
    if degrade.get('skew'):
        image = image.rotate(degrade['skew'], resample=Image.BICUBIC, expand=False, fillcolor=255)
    if degrade.get('noise'):
        pixels = numpy.asarray(image, dtype=numpy.float64)
        pixels = pixels + numpy.random.default_rng(seed).normal(0.0, degrade['noise'], pixels.shape)
        image = Image.fromarray(numpy.clip(numpy.rint(pixels), 0, 255).astype(numpy.uint8), 'L')
    buffer = io.BytesIO()
    if degrade.get('jpeg'):
        image.save(buffer, format='JPEG', quality=degrade['jpeg'])
    else:
        image.save(buffer, format='PNG')
    return buffer.getvalue()


def _line_strips(lines):
    """One image strip per printed line, just tall enough for its text."""
    import fitz
    return [fitz.Rect(30, y - 2, PAGE_WIDTH - 30, y + FONT_SIZE + 3) for y, cells in lines if cells]


def render(pages, mode, degrade=None, rules=None):
    """Return PDF bytes. ``pages`` is a list of line lists.

    ``degrade`` (scan modes) and ``rules`` (a list of line segments per page)
    were added in corpus v4; without them the output is the v3 output.
    """
    import fitz
    document = fitz.open()
    for number, lines in enumerate(pages):
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        segments = rules[number] if rules else ()
        if mode == 'digital':
            _draw(page, lines, use_ocr=False)
            _rule(page, segments)
            continue
        printed = fitz.open()
        source = printed.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        _draw(source, lines, use_ocr=False)
        _rule(source, segments)
        if mode == 'tiled_text_layer':
            for strip in _line_strips(lines):
                pixmap = source.get_pixmap(dpi=SCAN_DPI, colorspace=fitz.csGRAY, alpha=False, clip=strip)
                page.insert_image(strip, stream=pixmap.tobytes('png'))
            printed.close()
            _draw(page, lines, use_ocr=True, render_mode=3)
            continue
        if degrade:
            page.insert_image(page.rect, stream=_degraded_scan(source, degrade, seed=number + 1))
        else:
            pixmap = source.get_pixmap(dpi=SCAN_DPI, colorspace=fitz.csGRAY, alpha=False)
            page.insert_image(page.rect, stream=pixmap.tobytes('png'))
        printed.close()
        if mode == 'scan_text_layer':
            _draw(page, lines, use_ocr=True, render_mode=3)
        elif mode != 'image_only':
            raise ValueError(mode)
    data = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    document.close()
    return data


# ---------------------------------------------------------------------------
# Ground truth helpers
# ---------------------------------------------------------------------------

def row(day, description, amount_minor, direction):
    return dict(date=day, description=description, amount_minor=amount_minor, direction=direction)


def period_truth(*, family, institution, account, holder, currency, start, end, opening, closing,
                 rows, expected, defects, holder_printed=True, account_printed=True,
                 start_printed=True, notes=''):
    return dict(family=family, institution=institution, account=account, holder=holder,
                holder_printed=holder_printed, account_printed=account_printed, currency=currency,
                period_start=start, period_end=end, start_printed=start_printed,
                opening_minor=opening, closing_minor=closing, rows=rows,
                expected=expected, defects=defects, notes=notes)


# ---------------------------------------------------------------------------
# Family: generic labelled bank statement (no registered layout; header labels)
# ---------------------------------------------------------------------------

def _long(day):
    return f'{day:%B} {day.day}, {day.year}'


def generic_statement(*, holder, account, start, end, opening, rows, include_holder=True,
                      include_account=True, omit=(), damage_cells=(), ocr_text=None, shifts=None):
    """Return (pages, truth rows, closing). ``rows`` carry the true payments.

    ``omit`` removes printed rows (by index) from the page while the printed
    balances still include them, as a missing physical line would.
    ``damage_cells`` names (row index, 'amount'|'balance') OCR defects.
    ``shifts`` maps (row index, 'amount'|'balance') to a value change that the
    OCR layer shows as a single misread digit (a valid-looking wrong value).
    """
    shifts = shifts or {}
    lines = [(40, [L(40, 'Bank: Harbour Synthetic Bank')])]
    if include_holder:
        lines.append((54, [L(40, f'Account Name: {holder}')]))
    if include_account:
        lines.append((68, [L(40, f'Account Number: {account}')]))
    lines += [(82, [L(40, 'Currency: USD')]),
              (96, [L(40, f'Statement Period: {_long(start)} - {_long(end)}')]),
              (130, [L(40, 'Date'), L(120, 'Description'), R(380, 'Credit'), R(460, 'Debit'), R(560, 'Balance')]),
              (146, [L(40, start.isoformat()), L(120, 'Opening Balance'), R(560, money(opening))])]
    balance = opening
    y = 160
    for index, item in enumerate(rows):
        balance += item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
        item['balance_after'] = balance  # printed running balance (ground truth)
        if index in omit:
            continue
        amount_text = money(item['amount_minor'])
        balance_text = money(balance)
        ocr = (ocr_text or {}).get(index) or (damage(amount_text) if (index, 'amount') in damage_cells else None)
        if (index, 'amount') in shifts:
            ocr = shift(amount_text, shifts[index, 'amount'])
        amount_cell = R(380 if item['direction'] == 'credit' else 460, amount_text, ocr)
        balance_ocr = damage(balance_text) if (index, 'balance') in damage_cells else None
        if (index, 'balance') in shifts:
            balance_ocr = shift(balance_text, shifts[index, 'balance'])
        balance_cell = R(560, balance_text, balance_ocr)
        lines.append((y, [L(40, item['date']), L(120, item['description']), amount_cell, balance_cell]))
        y += 14
    lines.append((y, [L(40, end.isoformat()), L(120, 'Closing Balance'), R(560, money(balance))]))
    return [lines], balance


# ---------------------------------------------------------------------------
# Family: Credit One card (one cycle per page; a PDF may hold several cycles)
# ---------------------------------------------------------------------------

def _mmdd(value):
    return value[5:7] + '/' + value[8:10]


def credit_one_page(*, account, start, end, opening, rows, interest=0, holder='EXAMPLE PERSON',
                    include_holder=True, damage_cells=(), ocr_text=None):
    payments = sum(r['amount_minor'] for r in rows if r['direction'] == 'credit')
    purchases = sum(r['amount_minor'] for r in rows if r['direction'] == 'debit')
    closing = opening + purchases - payments + interest
    period = f'{start:%B} {start.day:02d}, {start.year} to {end:%B} {end.day:02d}, {end.year}'
    lines = [
        (10, [L(200, 'CREDIT ONE BANK CREDIT CARD STATEMENT')]),
        (22, [L(200, 'Account Number ' + account)]),
        (34, [L(200, period)]),
        (60, [L(150, 'SUMMARY OF ACCOUNT ACTIVITY'), L(345, 'PAYMENT INFORMATION')]),
        (72, [L(140, 'Previous Balance'), L(260, money(opening, dollar=True)), L(300, 'New Balance'),
              L(445, money(closing, dollar=True))]),
        (84, [L(140, 'Payments'), L(260, money(payments, dollar=True)), L(300, 'Minimum Payment Due'),
              L(445, money(min(closing, 2500), dollar=True))]),
        (96, [L(140, 'Purchases'), L(260, money(purchases, dollar=True))]),
        (120, [L(140, 'New Balance'), L(260, money(closing, dollar=True))]),
        (245, [L(275, 'TRANSACTIONS')]),
        (257, [L(140, 'Reference Number'), L(218, 'Trans Date Post Date Description of Transaction or Credit'),
               R(470, 'Amount')]),
    ]
    y = 270
    for index, item in enumerate(rows):
        text = ('-' if item['direction'] == 'credit' else '') + money(item['amount_minor'])
        cell = R(470, text, (ocr_text or {}).get(index) or (damage(text) if (index, 'amount') in damage_cells else None))
        lines.append((y, [L(140, f'REF{start:%y%m}{index:04d}'), L(222, _mmdd(item['date'])),
                          L(252, _mmdd(item['date'])), L(290, item['description']), cell]))
        y += 12
    lines += [(y, [L(290, 'Fees')]),
              (y + 12, [L(290, 'TOTAL FEES FOR THIS PERIOD'), R(470, '0.00')]),
              (y + 24, [L(290, 'Interest Charged')]),
              (y + 36, [L(222, _mmdd(end.isoformat())), L(252, _mmdd(end.isoformat())),
                        L(290, 'Interest Charge on Purchases'), R(470, money(interest))]),
              (y + 48, [L(290, 'TOTAL INTEREST FOR THIS PERIOD'), R(470, money(interest))]),
              (y + 60, [L(282, f'{end.year} Totals Year-to-Date')])]
    if include_holder:
        lines += [(700, [L(140, 'CREDIT ONE BANK'), L(335, holder)]),
                  (712, [L(140, 'PO BOX 100'), L(335, '100 FIRST AVENUE')]),
                  (724, [L(140, 'EXAMPLE CITY CA 90000'), L(335, 'EXAMPLE CITY DC 20000')])]
    truth_rows = list(rows)
    if interest:
        truth_rows.append(row(end.isoformat(), 'Interest Charge on Purchases', interest, 'debit'))
    return lines, truth_rows, closing


# ---------------------------------------------------------------------------
# Family: Merrick card (prints a statement/closing date only; no start date)
# ---------------------------------------------------------------------------

def merrick_page(*, account, closing_day, opening, rows, holder='EXAMPLE HOLDER', include_holder=True,
                 damage_cells=(), shifts=None):
    purchases = sum(r['amount_minor'] for r in rows if r['direction'] == 'debit')
    payments = sum(r['amount_minor'] for r in rows if r['direction'] == 'credit')
    closing = opening + purchases - payments
    lines = [(30, [L(40, 'MERRICK BANK')]),
             (44, [L(40, f'Statement Date: {closing_day:%m/%d/%y}')]),
             (58, [L(40, f'Account Number: {account}')])]
    if include_holder:
        lines.append((72, [L(40, 'Send Payments to:'), L(200, holder)]))
    lines += [(150, [L(90, 'MERRICK ACCOUNT SUMMARY')]),
              (180, [L(90, 'Summary of Account Activity'), L(330, 'Payment Information')]),
              (200, [L(95, 'Previous Balance'), R(280, money(opening, dollar=True)), L(330, 'New Balance'),
                     R(520, money(closing, dollar=True))]),
              (215, [L(95, 'Payments'), R(280, '- ' + money(payments, dollar=True)),
                     L(330, 'Minimum Payment Due'), R(520, '$35.00')]),
              (230, [L(95, 'Purchases'), R(280, '+ ' + money(purchases, dollar=True))]),
              (255, [L(95, 'New Balance'), R(280, money(closing, dollar=True))]),
              (350, [L(30, 'Transactions, Payments and Credits')]),
              (365, [L(30, 'Trans Date'), L(270, 'Item Description'), R(535, 'Amount')])]
    y = 380
    for index, item in enumerate(rows):
        text = money(item['amount_minor']) + ('-' if item['direction'] == 'credit' else '')
        ocr = damage(text) if (index, 'amount') in damage_cells else None
        if (shifts or {}).get(index):
            ocr = shift(text, shifts[index])
        cell = R(535, text, ocr)
        lines.append((y, [L(30, _mmdd(item['date'])), L(150, f'2413{closing_day:%m%d}{index:04d}ABCDE'),
                          L(270, item['description']), cell]))
        y += 15
    end = closing_day.strftime('%m/%d')
    lines += [(y, [L(30, 'Fees')]),
              (y + 15, [L(30, 'TOTAL FEES FOR THIS PERIOD'), R(535, '0.00')]),
              (y + 30, [L(30, 'Interest Charged')]),
              (y + 45, [L(30, end), L(270, 'Interest Charge on Purchases'), R(535, '0.00')]),
              (y + 60, [L(30, 'TOTAL INTEREST FOR THIS PERIOD'), R(535, '0.00')]),
              (y + 75, [L(30, f'{closing_day.year} Totals Year-to-Date')])]
    return lines, list(rows), closing


# ---------------------------------------------------------------------------
# Family: Andrews share statement (several shares/accounts per period)
# ---------------------------------------------------------------------------

def _andrews_header(account, start, end, printed_page, names=True):
    header = [[L(420, 'Account Statement')], [L(40, 'Andrews')], [L(300, account)],
              [L(300, f'{start:%m/%d/%y} {end:%m/%d/%y}')], [L(300, str(printed_page))]]
    if names:
        header += [[L(20, '>1234567890<')], [L(20, 'EXAMPLE PERSON')], [L(20, 'JOINT PERSON')],
                   [L(20, '1 TEST STREET')]]
    return [(20 + i * 12, cells) for i, cells in enumerate(header)]


def andrews_page(*, account, start, end, shares, printed_page=1, damage_cells=(), omit=(), ocr_lost=(),
                 endpoint_ocr=None, shifts=None):
    """``shares`` is a list of (share id, label, opening, rows).

    ``shifts`` maps (share, row index, 'amount'|'balance') or (share, 'ending')
    to a value change the OCR layer shows as one misread digit.

    ``ocr_lost`` names (share, row index) lines the scan shows but its OCR
    layer lost entirely. ``endpoint_ocr`` maps (share, 'opening'|'closing') to
    the OCR-layer text of that printed balance ('' when OCR lost the value).
    """
    endpoint_ocr = endpoint_ocr or {}
    shifts = shifts or {}

    def endpoint(share, role, value):
        text = money(value)
        if role == 'closing' and (share, 'ending') in shifts:
            return R(380, text, shift(text, shifts[share, 'ending']))
        return R(380, text, endpoint_ocr.get((share, role)))

    lines = _andrews_header(account, start, end, printed_page)
    y = 220
    closings = {}
    for share, label, opening, rows in shares:
        lines.append((y, [L(15, f'{start:%m/%d} ID {share} {label} Previous Balance'), endpoint(share, 'opening', opening)]))
        y += 12
        balance = opening
        for index, item in enumerate(rows):
            delta = item['amount_minor'] if item['direction'] == 'credit' else -item['amount_minor']
            balance += delta
            item['balance_after'] = balance
            if (share, index) in omit:
                continue
            amount_text = ('-' if delta < 0 else '') + money(item['amount_minor'])
            balance_text = money(balance)
            amount_ocr = damage(amount_text) if (share, index, 'amount') in damage_cells else None
            balance_ocr = damage(balance_text) if (share, index, 'balance') in damage_cells else None
            if (share, index, 'amount') in shifts:
                amount_ocr = shift(amount_text, shifts[share, index, 'amount'])
            if (share, index, 'balance') in shifts:
                balance_ocr = shift(balance_text, shifts[share, index, 'balance'])
            amount_cell = R(340, amount_text, amount_ocr)
            balance_cell = R(380, balance_text, balance_ocr)
            cells = [L(15, _mmdd(item['date'])), L(75, item['description']), amount_cell, balance_cell]
            if (share, index) in ocr_lost:
                cells = [{**cell, 'ocr': ''} for cell in cells]
            lines.append((y, cells))
            y += 12
        lines.append((y, [L(15, _mmdd(end.isoformat())), L(75, 'Ending Balance'), endpoint(share, 'closing', balance)]))
        y += 12
        closings[share] = balance
    return lines, closings


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------

def _generic_rows(month, seed):
    base = [('Incoming transfer', 125000 + seed * 1000, 'credit'), ('Card purchase grocer', 8510 + seed, 'debit'),
            ('Utility direct debit', 14320, 'debit'), ('Payroll deposit', 210055, 'credit'),
            ('Wire to supplier', 99900 + seed * 10, 'debit')]
    return [row(date(2023, month, 3 + 5 * i).isoformat(), f'{desc} {month:02d}-{i}', amount, direction)
            for i, (desc, amount, direction) in enumerate(base)]


def _month_end(year, month):
    following = date(year + (month == 12), month % 12 + 1, 1)
    return date.fromordinal(following.toordinal() - 1)


def build():
    """Return a list of corpus entries: (filename, mode, pages, periods)."""
    entries = []
    holder, account = 'Northwind Synthetic Trading LLC', '55501234'
    opening = 1_000_000
    generic = [
        # month, mode, options, expected, defects
        (1, 'digital', {}, 'auto', []),
        (2, 'digital', {}, 'auto', []),
        (3, 'scan_text_layer', dict(damage_cells={(1, 'amount')}), 'auto', ['ocr_amount_digit']),
        (4, 'scan_text_layer', dict(damage_cells={(2, 'balance')}), 'auto', ['ocr_balance_digit']),
        (5, 'digital', dict(include_holder=False), 'decision', ['holder_not_printed']),
        (6, 'digital', dict(include_account=False), 'decision', ['account_not_printed']),
        (7, 'digital', dict(omit={3}), 'hold', ['omitted_row']),
        (8, 'digital', dict(quiet=True), 'decision', ['no_activity']),
        (9, 'image_only', {}, 'auto', ['image_only_scan']),
        # OCR read 5 as 8: a valid-looking amount; the printed balances are right.
        (10, 'scan_text_layer', dict(ocr_text={0: '1,380.00'}), 'auto', ['ocr_valid_but_wrong_amount']),
    ]
    for month, mode, options, expected, defects in generic:
        quiet = options.pop('quiet', False)
        start, end = date(2023, month, 1), _month_end(2023, month)
        rows = [] if quiet else _generic_rows(month, month)
        pages, closing = generic_statement(holder=holder, account=account, start=start, end=end,
                                           opening=opening, rows=rows, **options)
        truth = period_truth(family='generic-labelled', institution='Harbour Synthetic Bank', account=account,
            holder=holder, currency='USD', start=start.isoformat(), end=end.isoformat(), opening=opening,
            closing=closing, rows=rows, expected=expected, defects=defects,
            holder_printed=options.get('include_holder', True), account_printed=options.get('include_account', True))
        entries.append(dict(filename=f'generic-{month:02d}-{"-".join(defects) or "clean"}.pdf', mode=mode,
                            pages=pages, periods=[truth]))
        opening = closing
    generic_closing = opening
    # Exact duplicate copy of January: identical bytes, different file name.
    entries.append(dict(filename='generic-01-copy-of-clean.pdf', copy_of='generic-01-clean.pdf'))

    # Credit One: a two-cycle PDF crossing a year boundary, plus defects.
    card = '4111 1111 1111 1111'
    cycles = [(date(2023, 12, 16), date(2024, 1, 15)), (date(2024, 1, 16), date(2024, 2, 15)),
              (date(2024, 2, 16), date(2024, 3, 15)), (date(2024, 3, 16), date(2024, 4, 15)),
              (date(2024, 4, 16), date(2024, 5, 15))]
    balance = 10000
    credit_one_pages = []
    for number, (start, end) in enumerate(cycles):
        if number == 4:
            rows = []
        else:
            rows = [row(date.fromordinal(start.toordinal() + 2 + number).isoformat(), f'EXAMPLE SHOP {number}A', 2500 + number * 111, 'debit'),
                    row(date.fromordinal(start.toordinal() + 9).isoformat(), f'PAYMENT RECEIVED {number}B', 4000, 'credit'),
                    row(date.fromordinal(start.toordinal() + 15).isoformat(), f'EXAMPLE CAFE {number}C', 1875 + number, 'debit')]
        options = {}
        expected, defects = 'auto', []
        if number == 2:
            options['damage_cells'] = {(2, 'amount')}
            defects = ['ocr_amount_digit']
        if number == 3:
            options['include_holder'] = False
            expected, defects = 'decision', ['holder_not_printed']
        if number == 4:
            expected, defects = 'decision', ['no_activity']
        interest = 0 if number == 4 else 200
        lines, truth_rows, closing = credit_one_page(account=card, start=start, end=end, opening=balance,
                                                     rows=rows, interest=interest, **options)
        truth = period_truth(family='credit-one-card', institution='Credit One Bank', account=card.replace(' ', ''),
            holder='EXAMPLE PERSON', currency='USD', start=start.isoformat(), end=end.isoformat(), opening=balance,
            closing=closing, rows=truth_rows, expected=expected, defects=defects,
            holder_printed=options.get('include_holder', True))
        credit_one_pages.append((lines, truth, options.get('damage_cells')))
        balance = closing
    # Two valid-looking OCR misreadings that cancel out: 25.11 -> 28.11 and
    # 18.79 -> 15.79. Printed totals still reconcile; only the image is right.
    start, end = date(2024, 5, 16), date(2024, 6, 15)
    rows = [row('2024-05-18', 'EXAMPLE BOOKSHOP 6A', 2511, 'debit'),
            row('2024-05-25', 'PAYMENT RECEIVED 6B', 4000, 'credit'),
            row('2024-06-01', 'EXAMPLE GARAGE 6C', 1879, 'debit')]
    lines, truth_rows, closing = credit_one_page(account=card, start=start, end=end, opening=balance, rows=rows,
                                                 interest=200, ocr_text={0: '28.11', 2: '15.79'})
    card_closing = closing
    cancelling = (lines, period_truth(family='credit-one-card', institution='Credit One Bank',
        account=card.replace(' ', ''), holder='EXAMPLE PERSON', currency='USD', start=start.isoformat(),
        end=end.isoformat(), opening=balance, closing=closing, rows=truth_rows, expected='auto',
        defects=['ocr_valid_but_wrong_amounts_cancelling']))
    entries.append(dict(filename='credit-one-two-cycles.pdf', mode='digital',
                        pages=[credit_one_pages[0][0], credit_one_pages[1][0]],
                        periods=[credit_one_pages[0][1], credit_one_pages[1][1]]))
    for index in (2, 3, 4):
        lines, truth, damaged = credit_one_pages[index]
        entries.append(dict(filename=f'credit-one-cycle-{index + 1}-{"-".join(truth["defects"]) or "clean"}.pdf',
                            mode='scan_text_layer' if damaged else 'digital', pages=[lines], periods=[truth]))
    entries.append(dict(filename='credit-one-cycle-6-ocr-valid-but-wrong-cancelling.pdf', mode='scan_text_layer',
                        pages=[cancelling[0]], periods=[cancelling[1]]))

    # Merrick: closing-only statements. Two statements in one PDF, one damaged scan.
    merrick_account = '1111 2222 3333 4444'
    closings = [date(2021, 4, 25), date(2021, 5, 25), date(2021, 6, 25), date(2021, 7, 25)]
    balance = 0
    merrick = []
    for number, closing_day in enumerate(closings):
        month = closing_day.month
        rows = [row(date(2021, month, 2 + number).isoformat(), f'EXAMPLE STORE {number}A', 1400 + number * 37, 'debit'),
                row(date(2021, month, 10).isoformat(), f'PAYMENT THANK YOU {number}B', 2500 if number else 0, 'credit'),
                row(date(2021, month, 20).isoformat(), f'EXAMPLE DINER {number}C', 10000 + number, 'debit')]
        rows = [r for r in rows if r['amount_minor']]
        options = {}
        defects = ['start_not_printed']
        expected = 'auto'
        if number == 2:
            options['damage_cells'] = {(0, 'amount')}
            defects = defects + ['ocr_amount_digit']
        if number == 3:
            options['include_holder'] = False
            defects = defects + ['holder_not_printed']
            expected = 'decision'
        lines, truth_rows, closing = merrick_page(account=merrick_account, closing_day=closing_day, opening=balance,
                                                  rows=rows, **options)
        truth = period_truth(family='merrick-card', institution='Merrick Bank', account=merrick_account.replace(' ', ''),
            holder='EXAMPLE HOLDER', currency='USD', start=None, end=closing_day.isoformat(), opening=balance,
            closing=closing, rows=truth_rows, expected=expected, defects=defects, start_printed=False,
            holder_printed=options.get('include_holder', True))
        merrick.append((lines, truth, options.get('damage_cells')))
        balance = closing
    merrick_closing = balance
    entries.append(dict(filename='merrick-two-statements.pdf', mode='digital',
                        pages=[merrick[0][0], merrick[1][0]], periods=[merrick[0][1], merrick[1][1]]))
    entries.append(dict(filename='merrick-2021-06-ocr-amount-digit.pdf', mode='scan_text_layer',
                        pages=[merrick[2][0]], periods=[merrick[2][1]]))
    entries.append(dict(filename='merrick-2021-07-holder-not-printed.pdf', mode='digital',
                        pages=[merrick[3][0]], periods=[merrick[3][1]]))

    # Andrews: one period, two shares (two account sections) per PDF.
    andrews_account = '123456789'
    variants = [
        (6, 'digital', {}, 'clean'),
        (7, 'scan_text_layer', dict(damage_cells={('0040', 1, 'balance')}), 'ocr-balance-digit'),
        (8, 'digital', dict(omit={('0040', 1)}), 'omitted-row'),
    ]
    savings, checking = 50000, 120000
    for month, mode, options, label in variants:
        start, end = date(2020, month, 1), _month_end(2020, month)
        save_rows = [row(date(2020, month, 3).isoformat(), 'Deposit Online Banking Transfer From Share 0040', 2000, 'credit'),
                     row(date(2020, month, 21).isoformat(), 'Deposit Dividend', 13, 'credit')]
        check_rows = [row(date(2020, month, 3).isoformat(), 'Withdrawal Online Banking Transfer To Share 0000', 2000, 'debit'),
                      row(date(2020, month, 9).isoformat(), f'Withdrawal Debit Card EXAMPLE MARKET {month}', 4567 + month, 'debit'),
                      row(date(2020, month, 15).isoformat(), 'Deposit ACH EXAMPLE EMPLOYER PAYROLL', 150000, 'credit')]
        lines, closings_by_share = andrews_page(account=andrews_account, start=start, end=end,
            shares=[('0000', 'BASE SHARE SAVINGS', savings, save_rows), ('0040', 'FREE CHECKING', checking, check_rows)],
            **options)
        omitted = bool(options.get('omit'))
        damaged = bool(options.get('damage_cells'))
        periods = []
        for share, opening, rows_, share_closing in (('0000', savings, save_rows, closings_by_share['0000']),
                                                    ('0040', checking, check_rows, closings_by_share['0040'])):
            defects = []
            expected = 'auto'
            if share == '0040' and omitted:
                defects, expected = ['omitted_row'], 'hold'
            if share == '0040' and damaged:
                defects = ['ocr_balance_digit']
            periods.append(period_truth(family='andrews-share', institution='Andrews', account=andrews_account,
                holder='EXAMPLE PERSON', currency='USD', start=start.isoformat(), end=end.isoformat(),
                opening=opening, closing=share_closing, rows=rows_, expected=expected, defects=defects,
                notes=f'share {share}') | dict(share=share))
        entries.append(dict(filename=f'andrews-2020-{month:02d}-{label}.pdf', mode=mode, pages=[lines], periods=periods))
        savings, checking = closings_by_share['0000'], closings_by_share['0040']
    entries.extend(andrews_quiet_and_endpoint_entries(andrews_account))
    entries += _compensating_entries(generic_opening=generic_closing, card_opening=card_closing,
                                     merrick_opening=merrick_closing,
                                     savings=savings, checking=checking)
    # Corpus v4: families, damage and outcomes v1-v3 did not cover. Appended
    # so every earlier file keeps its bytes and its ground truth.
    from benchmarks.statement_automation.corpus_v4 import v4_entries
    entries += v4_entries()
    return entries


def _compensating_entries(*, generic_opening, card_opening, merrick_opening, savings, checking):
    """Corpus v2: valid-looking OCR misreads that every printed control accepts.

    Each case is a scan whose image prints the true values while its OCR layer
    carries single-digit confusions (5/8, 3/0, 7/1, 0/6, 0/3) arranged so
    that totals, endpoint balances and running balances all still reconcile.
    Clean scans of the same layouts check that verification does not hold
    correct readings. Entries are appended after v1 so every v1 file keeps its
    bytes and results stay comparable.
    """
    entries = []
    holder, account = 'Northwind Synthetic Trading LLC', '55501234'
    # Generic running-balance statement: a purchase read 3.00 high, its printed
    # balance read 3.00 low and the next purchase read 3.00 low, so every
    # running balance and the closing balance still agree.
    opening = generic_opening
    for month, shifts, defects in (
            (11, {(1, 'amount'): 300, (1, 'balance'): -300, (2, 'amount'): -300},
             ['ocr_valid_but_wrong_running_balance_chain']),
            (12, {}, ['clean_scan_text_layer'])):
        start, end = date(2023, month, 1), _month_end(2023, month)
        rows = _generic_rows(month, month)
        pages, closing = generic_statement(holder=holder, account=account, start=start, end=end,
                                           opening=opening, rows=rows, shifts=shifts)
        truth = period_truth(family='generic-labelled', institution='Harbour Synthetic Bank', account=account,
            holder=holder, currency='USD', start=start.isoformat(), end=end.isoformat(), opening=opening,
            closing=closing, rows=rows, expected='auto', defects=defects)
        entries.append(dict(filename=f'generic-{month:02d}-{"-".join(defects)}.pdf', mode='scan_text_layer',
                            pages=pages, periods=[truth]))
        opening = closing

    # Credit One: 17.11 read as 11.11 (7/1) and 30.62 as 36.62 (0/6); then a
    # clean scan of the next cycle.
    card = '4111 1111 1111 1111'
    balance = card_opening
    for start, end, rows, ocr_text, defects in (
            (date(2024, 6, 16), date(2024, 7, 15),
             [row('2024-06-19', 'EXAMPLE PHARMACY 7A', 1711, 'debit'),
              row('2024-06-25', 'PAYMENT RECEIVED 7B', 4000, 'credit'),
              row('2024-07-02', 'EXAMPLE PARKING 7C', 3062, 'debit')],
             {0: '11.11', 2: '36.62'}, ['ocr_valid_but_wrong_amounts_cancelling_7_1_0_6']),
            (date(2024, 7, 16), date(2024, 8, 15),
             [row('2024-07-18', 'EXAMPLE BOOKSHOP 8A', 2934, 'debit'),
              row('2024-07-26', 'PAYMENT RECEIVED 8B', 4000, 'credit'),
              row('2024-08-03', 'EXAMPLE GARAGE 8C', 1598, 'debit')],
             {}, ['clean_scan_text_layer'])):
        lines, truth_rows, closing = credit_one_page(account=card, start=start, end=end, opening=balance,
                                                     rows=rows, interest=200, ocr_text=ocr_text)
        truth = period_truth(family='credit-one-card', institution='Credit One Bank', account=card.replace(' ', ''),
            holder='EXAMPLE PERSON', currency='USD', start=start.isoformat(), end=end.isoformat(), opening=balance,
            closing=closing, rows=truth_rows, expected='auto', defects=defects)
        cycle = 7 if ocr_text else 8
        entries.append(dict(filename=f'credit-one-cycle-{cycle}-{"-".join(defects)}.pdf', mode='scan_text_layer',
                            pages=[lines], periods=[truth]))
        balance = closing

    # Merrick: 15.48 read as 18.48 (5/8) and 103.34 as 100.34 (3/0); the
    # purchases total and new balance are unchanged.
    closing_day = date(2021, 8, 25)
    rows = [row('2021-08-06', 'EXAMPLE STORE 4A', 1548, 'debit'),
            row('2021-08-10', 'PAYMENT THANK YOU 4B', 2500, 'credit'),
            row('2021-08-20', 'EXAMPLE DINER 4C', 10334, 'debit')]
    lines, truth_rows, closing = merrick_page(account='1111 2222 3333 4444', closing_day=closing_day,
        opening=merrick_opening, rows=rows, shifts={0: 300, 2: -300})
    truth = period_truth(family='merrick-card', institution='Merrick Bank', account='1111222233334444',
        holder='EXAMPLE HOLDER', currency='USD', start=None, end=closing_day.isoformat(), opening=merrick_opening,
        closing=closing, rows=truth_rows, expected='auto', start_printed=False,
        defects=['start_not_printed', 'ocr_valid_but_wrong_amounts_cancelling_5_8_3_0'])
    entries.append(dict(filename='merrick-2021-08-ocr-valid-but-wrong-cancelling.pdf', mode='scan_text_layer',
                        pages=[lines], periods=[truth]))

    # Andrews: a deposit of 1,500.00 read as 1,530.00 (0/3) with its running
    # balance and the share's ending balance misread the same way.
    # Its own month: the account's 2020-09 statement is the quiet-checking case.
    year, month = 2021, 5
    start, end = date(year, month, 1), _month_end(year, month)
    save_rows = [row(date(year, month, 3).isoformat(), 'Deposit Online Banking Transfer From Share 0040', 2000, 'credit'),
                 row(date(year, month, 21).isoformat(), 'Deposit Dividend', 13, 'credit')]
    check_rows = [row(date(year, month, 3).isoformat(), 'Withdrawal Online Banking Transfer To Share 0000', 2000, 'debit'),
                  row(date(year, month, 9).isoformat(), f'Withdrawal Debit Card EXAMPLE MARKET {month}', 4567 + month, 'debit'),
                  row(date(year, month, 15).isoformat(), 'Deposit ACH EXAMPLE EMPLOYER PAYROLL', 150000, 'credit')]
    lines, closings_by_share = andrews_page(account='123456789', start=start, end=end,
        shares=[('0000', 'BASE SHARE SAVINGS', savings, save_rows), ('0040', 'FREE CHECKING', checking, check_rows)],
        shifts={('0040', 2, 'amount'): 3000, ('0040', 2, 'balance'): 3000, ('0040', 'ending'): 3000})
    periods = []
    for share, opening_, rows_ in (('0000', savings, save_rows), ('0040', checking, check_rows)):
        defects = ['ocr_valid_but_wrong_amount_balance_and_ending'] if share == '0040' else []
        periods.append(period_truth(family='andrews-share', institution='Andrews', account='123456789',
            holder='EXAMPLE PERSON', currency='USD', start=start.isoformat(), end=end.isoformat(),
            opening=opening_, closing=closings_by_share[share], rows=rows_, expected='auto', defects=defects,
            notes=f'share {share}') | dict(share=share))
    entries.append(dict(filename='andrews-2021-05-ocr-valid-but-wrong-consistent.pdf', mode='scan_text_layer',
                        pages=[lines], periods=periods))
    return entries


def andrews_quiet_and_endpoint_entries(account):
    """Andrews quiet periods (provable and not) and damaged endpoint balances.

    A share section with no activity prints its Previous Balance line followed
    directly by its Ending Balance line. Whether that can be established from
    the source depends on the reading: a lost OCR line, a section split by a
    page break, or an unreadable balance must not pass as a quiet period.
    """
    entries = []

    def savings_rows(month, year):
        return [row(date(year, month, 4).isoformat(), 'Deposit Online Banking Transfer From Share 0040', 3000, 'credit'),
                row(date(year, month, 22).isoformat(), 'Deposit Dividend', 17, 'credit')]

    def checking_rows(month, year):
        return [row(date(year, month, 5).isoformat(), 'Withdrawal Online Banking Transfer To Share 0000', 3000, 'debit'),
                row(date(year, month, 12).isoformat(), f'Withdrawal Debit Card EXAMPLE PHARMACY {month}', 2345, 'debit'),
                row(date(year, month, 16).isoformat(), 'Deposit ACH EXAMPLE EMPLOYER PAYROLL', 98000, 'credit')]

    def truths(start, end, shares, closings, defects_by_share, expected_by_share, notes=''):
        result = []
        for share, _, opening, rows_ in shares:
            result.append(period_truth(family='andrews-share', institution='Andrews', account=account,
                holder='EXAMPLE PERSON', currency='USD', start=start.isoformat(), end=end.isoformat(),
                opening=opening, closing=closings[share], rows=rows_, expected=expected_by_share.get(share, 'auto'),
                defects=defects_by_share.get(share, []), notes=f'share {share}' + (f'; {notes}' if notes else ''))
                | dict(share=share))
        return result

    savings, checking = 61000, 230000
    # Provable quiet checking share: digital, scanned with a good OCR layer, and image only.
    for (year, month), mode, label in (((2020, 9), 'digital', 'quiet-checking'),
                                       ((2020, 10), 'scan_text_layer', 'quiet-checking-scan'),
                                       ((2020, 11), 'image_only', 'quiet-checking-image-only')):
        start, end = date(year, month, 1), _month_end(year, month)
        shares = [('0000', 'BASE SHARE SAVINGS', savings, savings_rows(month, year)),
                  ('0040', 'FREE CHECKING', checking, [])]
        lines, closings = andrews_page(account=account, start=start, end=end, shares=shares)
        entries.append(dict(filename=f'andrews-{year}-{month:02d}-{label}.pdf', mode=mode, pages=[lines],
            periods=truths(start, end, shares, closings, {'0040': ['no_activity_source_proven']}, {})))
        savings = closings['0000']

    # The scan shows two equal and opposite payments; its OCR layer lost both
    # lines, so the printed balances are equal. This is not a quiet period.
    start, end = date(2020, 12, 1), date(2020, 12, 31)
    lost = [row('2020-12-07', 'Deposit Mobile Check Deposit', 5000, 'credit'),
            row('2020-12-09', 'Withdrawal Debit Card EXAMPLE OUTFITTERS', 5000, 'debit')]
    shares = [('0000', 'BASE SHARE SAVINGS', savings, savings_rows(12, 2020)), ('0040', 'FREE CHECKING', checking, lost)]
    lines, closings = andrews_page(account=account, start=start, end=end, shares=shares,
                                   ocr_lost={('0040', 0), ('0040', 1)})
    entries.append(dict(filename='andrews-2020-12-ocr-lost-lines-equal-balances.pdf', mode='scan_text_layer', pages=[lines],
        periods=truths(start, end, shares, closings, {'0040': ['ocr_lost_rows_equal_balances']}, {},
                       notes='OCR layer lost two payment lines; printed balances are equal')))
    savings = closings['0000']

    # A genuinely quiet checking section that a page break splits: the page
    # alone cannot establish that nothing was lost between the two pages.
    start, end = date(2021, 1, 1), date(2021, 1, 31)
    first = _andrews_header(account, start, end, 1)
    y = 220
    first.append((y, [L(15, f'{start:%m/%d} ID 0000 BASE SHARE SAVINGS Previous Balance'), R(380, money(savings))]))
    balance = savings
    save = savings_rows(1, 2021)
    for item in save:
        y += 12
        balance += item['amount_minor']
        item['balance_after'] = balance
        first.append((y, [L(15, _mmdd(item['date'])), L(75, item['description']), R(340, money(item['amount_minor'])),
                          R(380, money(balance))]))
    first += [(y + 12, [L(15, _mmdd(end.isoformat())), L(75, 'Ending Balance'), R(380, money(balance))]),
              (y + 24, [L(15, f'{start:%m/%d} ID 0040 FREE CHECKING Previous Balance'), R(380, money(checking))]),
              (y + 36, [L(15, 'Continued on following page')])]
    second = _andrews_header(account, start, end, 2, names=False)
    second.append((220, [L(15, _mmdd(end.isoformat())), L(75, 'Ending Balance'), R(380, money(checking))]))
    shares = [('0000', 'BASE SHARE SAVINGS', savings, save), ('0040', 'FREE CHECKING', checking, [])]
    entries.append(dict(filename='andrews-2021-01-quiet-section-across-pages.pdf', mode='digital', pages=[first, second],
        periods=truths(start, end, shares, {'0000': balance, '0040': checking},
                       {'0040': ['no_activity', 'section_spans_pages']}, {'0040': 'decision'})))
    savings = balance

    # Damaged endpoint balances in the OCR layer of a scan; the image is right.
    start, end = date(2021, 2, 1), date(2021, 2, 28)
    shares = [('0000', 'BASE SHARE SAVINGS', savings, savings_rows(2, 2021)),
              ('0040', 'FREE CHECKING', checking, checking_rows(2, 2021))]
    _, closings = andrews_page(account=account, start=start, end=end, shares=deepcopy_rows(shares))
    lines, closings = andrews_page(account=account, start=start, end=end, shares=shares,
        endpoint_ocr={('0000', 'opening'): damage(money(savings)), ('0040', 'closing'): damage(money(closings['0040']))})
    entries.append(dict(filename='andrews-2021-02-ocr-endpoint-balances.pdf', mode='scan_text_layer', pages=[lines],
        periods=truths(start, end, shares, closings, {'0000': ['ocr_opening_balance_digit'],
                                                      '0040': ['ocr_closing_balance_digit']}, {})))
    savings, checking = closings['0000'], closings['0040']

    # A quiet checking share whose ending balance digit is damaged in OCR.
    start, end = date(2021, 3, 1), date(2021, 3, 31)
    shares = [('0000', 'BASE SHARE SAVINGS', savings, savings_rows(3, 2021)), ('0040', 'FREE CHECKING', checking, [])]
    lines, closings = andrews_page(account=account, start=start, end=end, shares=shares,
                                   endpoint_ocr={('0040', 'closing'): damage(money(checking))})
    entries.append(dict(filename='andrews-2021-03-quiet-ocr-ending-balance-digit.pdf', mode='scan_text_layer', pages=[lines],
        periods=truths(start, end, shares, closings, {'0040': ['no_activity_source_proven', 'ocr_closing_balance_digit']}, {})))
    savings = closings['0000']

    # The OCR layer lost an ending balance value entirely; the image shows it.
    start, end = date(2021, 4, 1), date(2021, 4, 30)
    shares = [('0000', 'BASE SHARE SAVINGS', savings, savings_rows(4, 2021)),
              ('0040', 'FREE CHECKING', checking, checking_rows(4, 2021))]
    lines, closings = andrews_page(account=account, start=start, end=end, shares=shares,
                                   endpoint_ocr={('0000', 'closing'): ''})
    entries.append(dict(filename='andrews-2021-04-ocr-lost-ending-balance.pdf', mode='scan_text_layer', pages=[lines],
        periods=truths(start, end, shares, closings, {'0000': ['ocr_lost_closing_balance']}, {})))
    return entries


def deepcopy_rows(shares):
    return [(share, label, opening, [dict(item) for item in rows_]) for share, label, opening, rows_ in shares]


def write(out, only=None):
    """Render the corpus. ``only`` (development aid) keeps file names containing it."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = dict(version=CORPUS_VERSION, synthetic=True, files=[])
    produced = {}
    for entry in build():
        if only and only not in entry['filename']:
            continue
        if 'copy_of' in entry:
            data = produced[entry['copy_of']]
            original = next(f for f in manifest['files'] if f['filename'] == entry['copy_of'])
            record = dict(filename=entry['filename'], mode=original['mode'], copy_of=entry['copy_of'],
                          periods=[{**p, 'expected': 'duplicate', 'defects': ['exact_duplicate_copy'],
                                    'duplicate_of': entry['copy_of']} for p in original['periods']])
        else:
            data = render(entry['pages'], entry['mode'], entry.get('degrade'), entry.get('rules'))
            record = dict(filename=entry['filename'], mode=entry['mode'], pages=len(entry['pages']),
                          periods=entry['periods'])
            for key in ('degrade', 'missing_pages', 'ruled'):
                if entry.get(key):
                    record[key] = entry[key]
        produced[entry['filename']] = data
        (out / entry['filename']).write_bytes(data)
        record['sha256'] = hashlib.sha256(data).hexdigest()
        record['size'] = len(data)
        for index, period in enumerate(record['periods']):
            period['id'] = f"{entry['filename']}#{index + 1}"
        manifest['files'].append(record)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default=str(Path(__file__).with_name('corpus')))
    parser.add_argument('--only', help='Development aid: render only files whose name contains this text.')
    args = parser.parse_args(argv)
    manifest = write(args.out, args.only)
    periods = sum(len(f['periods']) for f in manifest['files'])
    print(f"Wrote {len(manifest['files'])} PDFs, {periods} statement periods to {args.out}")


if __name__ == '__main__':
    main()
