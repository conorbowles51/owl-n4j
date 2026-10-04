"""Tier-A ground truth for real statements, read independently of the pipeline.

The pipeline under test reads PDFs with PyMuPDF, its own table geometry and
Tesseract. This reader uses only pdfplumber on the embedded text layer, so a
period it verifies is evidence about the source, not an echo of the pipeline.

For each document in the private inventory (``real_inventory.py``) it:

1. Reads every page's words and lines with pdfplumber (never pypdf, never the
   evidence engine).
2. Identifies the issuer from marks printed on most pages (legal name, tax id),
   not from a single mention inside a transaction description.
3. Runs that issuer's layout parser, which returns statement periods with the
   printed dates, opening and closing balances, every transaction (date,
   amount, direction from the printed column, description), printed running
   balances and printed controls (totals, counts, page numbering).
4. Reconciles each period: opening + credits - debits must equal closing to the
   cent, and every printed control (credit/debit totals and counts, running
   balances, page sequence) must agree. Only then is the period ``verified``.
   Anything else is ``unverified`` with the reason, or ``incomplete`` when
   pages are missing (such a period must be held).

Documents without a text layer, or with outlined (vector) text, are
``needs_visual``: their truth has to come from a person reading rendered pages.

Output, under the private directory given with ``--out`` (never committed):

* ``manifest.json``: the benchmark harness format (``harness.py --corpus``),
  one entry per document with at least one verified period, file names opaque
  (``<doc id>.pdf``, linked to the private copy). Every period carries
  ``truth_status``; the harness scores only ``verified`` ones.
* ``status.json``: one row per inventory document with its status, issuer,
  periods by status and reasons.
* ``periods/<doc id>.json``: the full private per-document reading.

From ``backend/``::

    PYTHONPATH=<dir with pdfplumber> python -m benchmarks.statement_automation.real_truth \\
        --inventory /mnt/owl-data/fin-real/inventory.json --out /mnt/owl-data/fin-real/truth
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

MONEY = re.compile(r'^\(?-?\$?\s?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?-?$|^\(?-?\$?-?\d+\.\d{2}\)?-?$')
TEXT_MODES = ('digital', 'mixed', 'scan_text_layer')
LINE_TOLERANCE = 2.5

ES_MONTHS = dict(ENE=1, FEB=2, MAR=3, ABR=4, MAY=5, JUN=6, JUL=7, AGO=8, SEP=9, SET=9, OCT=10, NOV=11, DIC=12)
ES_MONTH_NAMES = dict(enero=1, febrero=2, marzo=3, abril=4, mayo=5, junio=6, julio=7, agosto=8, septiembre=9,
                      setiembre=9, octubre=10, noviembre=11, diciembre=12)
EN_MONTHS = dict(JAN=1, FEB=2, MAR=3, APR=4, MAY=5, JUN=6, JUL=7, AUG=8, SEP=9, OCT=10, NOV=11, DEC=12)

# Issuer marks: (issuer, pattern). A mark must appear on at least a third of
# the text pages (and on two pages when there are more than two) to count, so
# a bank named once in a transfer description does not decide the issuer.
ISSUER_MARKS = (
    ('bbva-mexico', r'BBA830831LJ2|BBVA\s+M[EÉ]XICO,\s*S\.\s*A\.'),
    ('monex-mexico', r'BMI9704113PA|Banco\s+Monex,\s*S\.\s*A\.'),
    ('santander-mexico', r'BSM970519DU8|BANCO\s*SANTANDER\s*\(?M\S{0,2}XICO\)?'),
    ('intercam-mexico', r'ICB061106G80|Intercam\s+Banco|CLABE\s+136\d{15}'),
    # "ESTADO DE CUENTA ÚNICO" is issued by Kapital and by Intercam; one parser
    # serves both and takes each account's family from its CLABE bank code.
    ('kapital-mexico', r'KAPITAL|KPTL|CLABE\s+128\d{15}|ESTADO DE CUENTA [UÚ]NICO'),
    ('scotiabank-mexico', r'Scotiabank\s+Inverlat'),
    ('banorte-mexico', r'BMN930209927|Banco\s+Mercantil\s+del\s+Norte'),
    ('capital-one-card', r'Capital\s*One'),
    ('credit-one-card', r'Credit\s*One\s*Bank'),
    ('merrick-card', r'Merrick\s*Bank'),
    ('andrews-share', r'Andrews\s+Federal|ndrewsfcu|^Andrews$|Box\s+4000\s*/\s*Clinton'),
    ('citibank', r'Citibank|citi\.com'),
    ('wells-fargo', r'Wells\s+Fargo'),
)


# ---------------------------------------------------------------------------
# Reading (pdfplumber only)
# ---------------------------------------------------------------------------

@dataclass
class Line:
    top: float
    words: list  # pdfplumber word dicts, left to right

    @property
    def text(self):
        return ' '.join(w['text'] for w in self.words)


@dataclass
class Page:
    number: int  # 1-based
    width: float
    lines: list
    text: str


def group_lines(words, tolerance=LINE_TOLERANCE):
    lines = []
    for word in sorted(words, key=lambda w: (round(w['top'], 1), w['x0'])):
        for line in reversed(lines[-3:]):
            if abs(line.top - word['top']) <= tolerance:
                line.words.append(word)
                break
        else:
            lines.append(Line(word['top'], [word]))
    for line in lines:
        line.words.sort(key=lambda w: w['x0'])
        line.words = merge_spaced_digits(line.words)
    lines.sort(key=lambda l: l.top)
    return lines


def _doubled(text):
    return len(text) >= 4 and len(text) % 2 == 0 and text[0::2] == text[1::2]


def undouble(words, share=0.6):
    """Pages whose glyphs were each printed twice side by side read 'CCRREEDDIITT'. Only when most
    longer words on the page are perfectly doubled is every perfectly doubled word halved."""
    longer = [w for w in words if len(w['text']) >= 4]
    if not longer or sum(_doubled(w['text']) for w in longer) < share * len(longer):
        return words
    return [dict(w, text=w['text'][0::2]) if _doubled(w['text']) else w for w in words]


SPACED = re.compile(r'^[\d,.$\-]$')


def merge_spaced_digits(words, gap=1.2):
    """Join amounts printed one character per word ('2 5 3 , 2 2 6 . 0 9'), only where the glyphs touch."""
    merged, run = [], None
    for word in words:
        single = bool(SPACED.match(word['text']))
        if run is not None and single and word['x0'] - run['x1'] <= gap:
            run = dict(run, text=run['text'] + word['text'], x1=word['x1'], bottom=max(run['bottom'], word['bottom']))
            merged[-1] = run
            continue
        merged.append(word)
        run = dict(word) if single else None
    return merged


WORD_KEYS = ('text', 'x0', 'x1', 'top', 'bottom')
CACHE_VERSION = 'w2'  # bump when read_words changes


def overprinted(chars, tolerance=1.0, share=0.2):
    """True when a fair share of glyphs sit on an identical glyph (bold made by printing twice)."""
    if len(chars) < 20:
        return False
    doubled = sum(1 for a, b in zip(chars, chars[1:])
                  if a['text'] == b['text'] and abs(a['x0'] - b['x0']) <= tolerance and abs(a['top'] - b['top']) <= tolerance)
    return doubled >= share * len(chars) / 2 or doubled >= 50


def read_words(path):
    """pdfplumber words per page: ``[(width, [word, ...]), ...]``."""
    import pdfplumber
    out = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            try:
                # Overprinted glyphs (bold made by printing each character twice)
                # would otherwise read as doubled letters and digits.
                source = page.dedupe_chars(tolerance=1) if overprinted(page.chars) else page
                words = source.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
            except Exception:
                words = []
            out.append((float(page.width), [{k: w[k] for k in WORD_KEYS} for w in words]))
            page.close()
    return out


def read_pages(path, cache_dir=None):
    """Pages as lines of words. ``cache_dir`` keeps the pdfplumber words (private) between runs."""
    import gzip
    cached = Path(cache_dir) / (Path(path).stem + f'.{CACHE_VERSION}.json.gz') if cache_dir else None
    if cached is not None and cached.exists():
        raw = json.loads(gzip.decompress(cached.read_bytes()))
    else:
        raw = read_words(path)
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(gzip.compress(json.dumps(raw).encode()))
    pages = []
    for index, (width, words) in enumerate(raw):
        lines = group_lines(undouble(words))
        pages.append(Page(index + 1, width, lines, '\n'.join(l.text for l in lines)))
    return pages


def detect_issuer(pages):
    text_pages = [p for p in pages if p.text.strip()]
    if not text_pages:
        return None
    # Issuers print their name and tax id in page headers and footers; the
    # middle of a page holds transactions, which name other banks.
    zones = ['\n'.join(l.text for l in p.lines[:14] + p.lines[-14:]) for p in text_pages]
    needed = max(1, min(2, len(text_pages)), len(text_pages) // 3) if len(text_pages) > 2 else 1
    for texts, threshold in ((zones, needed), ([p.text for p in text_pages], max(needed, (len(text_pages) + 1) // 2))):
        best, best_count = None, 0
        for issuer, pattern in ISSUER_MARKS:
            count = sum(1 for text in texts if re.search(pattern, text, re.I | re.M))
            if count > best_count:
                best, best_count = issuer, count
        if best_count >= threshold:
            return best
    return None


# Documents that arrive with statements but are not statements. Matched only
# when no statement period was found.
NOT_STATEMENT_MARKS = (
    ('account information sheet', r'Account Information Sheet'),
    ('transfer receipt', r'Comprobante de Operaci[oó]n'),
    ('wire transfer report', r'Wire\s*Transfer\s*Detail\s*Report'),
    ('membership application', r'MEMBERSHIP APPLICATION'),
    ('online balance page', r'Posici[oó]n Global'),
    ('credit application export', r'DATE_APPLICATION_RECEIVED'),
)


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def money_minor(token):
    """'1,234.56' -> 123456; '(12.00)' / '-12.00' / '12.00-' -> -1200. None if not money."""
    raw = token.strip()
    if not MONEY.match(raw):
        return None
    negative = raw.startswith('(') or raw.startswith('-') or raw.endswith('-') or '$-' in raw or '-$' in raw
    digits = re.sub(r'[^\d]', '', raw)
    value = int(digits)
    return -value if negative else value


def is_money(token):
    return money_minor(token) is not None


def iso(year, month, day):
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def year_for(month, start_iso, end_iso):
    """Year for a day/month printed without a year, inside the period's span."""
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    for year in (end.year, start.year):
        if (year, month) >= (start.year, start.month) and (year, month) <= (end.year, end.month):
            return year
    return end.year


def last4(value):
    digits = re.sub(r'\D', '', value or '')
    return digits[-4:] if len(digits) >= 4 else None


def printed_sequence(pages, pattern):
    """``({printed number: physical page}, total, fillers)`` from a 'page N of M' mark.

    A page without the mark directly before a numbered page stands in for the
    printed numbers between (a cover or insert page counted by the bank).
    """
    sequence, total, unnumbered, fillers = {}, None, [], []
    for page in pages:
        match = re.search(pattern, page.text, re.I)
        if not match:
            unnumbered.append(page.number)
            continue
        number, total = int(match.group(1)), int(match.group(2))
        gap = list(range((max(sequence) if sequence else 0) + 1, number))
        if gap and len(unnumbered) >= len(gap):
            for printed, physical in zip(gap, unnumbered[-len(gap):]):
                sequence[printed] = physical
                fillers.append(physical)
        sequence.setdefault(number, page.number)
        unnumbered = []
    return sequence, total, fillers


# ---------------------------------------------------------------------------
# Periods and reconciliation
# ---------------------------------------------------------------------------

@dataclass
class Period:
    family: str
    institution: str
    currency: str | None = None
    holder: str | None = None
    account: str | None = None  # last 4 digits as printed
    period_start: str | None = None
    period_end: str | None = None
    opening_minor: int | None = None
    closing_minor: int | None = None
    rows: list = field(default_factory=list)
    controls: dict = field(default_factory=dict)
    pages: list = field(default_factory=list)
    page_sequence: dict = field(default_factory=dict)  # printed page numbering: {printed: physical}
    page_total: int | None = None
    problems: list = field(default_factory=list)  # parser-side reasons the reading is not complete
    notes: list = field(default_factory=list)
    share: str | None = None
    kind: str = 'deposit'  # 'card': balances are amounts owed; purchases (debits) raise them


def reconcile(period):
    """``(status, reasons)``: verified only if every printed control agrees to the cent."""
    reasons = list(period.problems)
    if period.page_total:
        printed = set(period.page_sequence)
        missing = sorted(set(range(1, period.page_total + 1)) - printed)
        if missing:
            return 'incomplete', [f'missing printed pages {len(missing)} of {period.page_total}']
    for name in ('period_start', 'period_end', 'opening_minor', 'closing_minor', 'currency', 'account'):
        if getattr(period, name) in (None, ''):
            reasons.append(f'{name} not read')
    if reasons:
        return 'unverified', reasons
    credits = [r for r in period.rows if r['direction'] == 'credit']
    debits = [r for r in period.rows if r['direction'] == 'debit']
    credit_total = sum(r['amount_minor'] for r in credits)
    debit_total = sum(r['amount_minor'] for r in debits)
    sign = -1 if period.kind == 'card' else 1
    if period.opening_minor + sign * (credit_total - debit_total) != period.closing_minor:
        reasons.append('opening + transactions != closing')
    c = period.controls
    if 'credits_total' in c and c['credits_total'] != credit_total:
        reasons.append('credit total differs from printed total')
    if 'debits_total' in c and c['debits_total'] != debit_total:
        reasons.append('debit total differs from printed total')
    if 'credits_count' in c and c['credits_count'] != len(credits):
        reasons.append('credit count differs from printed count')
    if 'debits_count' in c and c['debits_count'] != len(debits):
        reasons.append('debit count differs from printed count')
    if 'rows_count' in c and c['rows_count'] != len(period.rows):
        reasons.append('row count differs from printed count')
    for extra in c.get('other_checks', []):
        if not extra['ok']:
            reasons.append(extra['reason'])
    balance = period.opening_minor
    for index, row in enumerate(period.rows):
        balance += sign * (row['amount_minor'] if row['direction'] == 'credit' else -row['amount_minor'])
        printed = row.get('balance_after')
        if printed is not None and printed != balance:
            reasons.append(f'running balance differs at row {index + 1}')
            break
    earliest = period.period_start
    if period.kind == 'card':  # a card prints the transaction date; it may precede the cycle it posts in
        earliest = (date.fromisoformat(period.period_start) - timedelta(days=60)).isoformat()
    for row in period.rows:
        if not row.get('date'):
            reasons.append('row date not read')
            break
        if not (earliest <= row['date'] <= period.period_end) and not row.get('date_outside_ok'):
            reasons.append('row date outside the printed period')
            break
    if any(r['amount_minor'] <= 0 for r in period.rows):
        reasons.append('non-positive amount')
    return ('verified', []) if not reasons else ('unverified', reasons)


def expected_outcome(period, status):
    if status == 'incomplete':
        return 'hold'
    if not period.holder or not period.account:
        return 'decision'
    return 'auto'


# ---------------------------------------------------------------------------
# Shared layout helpers
# ---------------------------------------------------------------------------

def find(pattern, text, flags=re.I):
    match = re.search(pattern, text, flags)
    return match.group(1) if match else None


def money_after(label, text):
    """First money value printed after ``label`` on the same text line."""
    for line in text.split('\n'):
        match = re.search(label + r'[^\d\-\(\$]*?(\(?-?\$?\s?-?[\d,]*\d\.\d{2}\)?-?)', line, re.I)
        if match:
            return money_minor(match.group(1).replace(' ', ''))
    return None


def column_of(word, columns, slack=12):
    """Name of the right-aligned column whose right edge is nearest ``word``'s."""
    best, distance = None, None
    for name, x1 in columns.items():
        gap = abs(word['x1'] - x1)
        if gap <= slack and (distance is None or gap < distance):
            best, distance = name, gap
    return best


# ---------------------------------------------------------------------------
# BBVA Mexico (BBVA MEXICO, S.A.; "Detalle de Movimientos Realizados")
# ---------------------------------------------------------------------------

BBVA_DATE = re.compile(r'^(\d{2})/([A-Z]{3})$')
BBVA_TABLE_END = re.compile(r'^Total de Movimientos|^Estado de cuenta de Inversiones|'
                            r'^Movimientos de Periodos Anteriores', re.I)
BBVA_FOOTER = re.compile(r'BBVA\s+MEXICO,\s*S\.A\.|Av\.\s+Paseo de la Reforma 510|^Total de Movimientos|'
                         r'^Movimientos de Periodos Anteriores|'
                         r'^Estado de cuenta de Inversiones|^La GAT Real|^Estimado Cliente|^Con BBVA adelante|'
                         r'^Su Estado de Cuenta|^También le informamos|^el cual puede consultarlo', re.I)


def _bbva_columns(page):
    for line in page.lines:
        names = {w['text'].upper(): w for w in line.words}
        if 'CARGOS' in names and 'ABONOS' in names:
            columns = dict(debit=names['CARGOS']['x1'], credit=names['ABONOS']['x1'])
            for key, label in (('balance_operation', 'OPERACIÓN'), ('balance_settlement', 'LIQUIDACIÓN')):
                if label in names:
                    columns[key] = names[label]['x1']
            return columns, line.top
    return None, None


def _settlement_year(operation_month, settlement_month, period):
    year = year_for(operation_month, period.period_start, period.period_end)
    return year + 1 if settlement_month < operation_month else year


def parse_bbva(pages):
    """One period per printed page run "PAGINA 1 / N" ... "PAGINA N / N"."""
    runs, current, unnumbered = [], None, []
    for page in pages:
        match = re.search(r'PAGINA\s+(\d+)\s*/\s*(\d+)', page.text)
        if not match:
            unnumbered.append(page)  # an inserted page (image or text) with no page mark
            continue
        number, total = int(match.group(1)), int(match.group(2))
        if number == 1 or current is None or current['total'] != total or number in current['seq'] \
                or number < max(current['seq']):
            current = dict(total=total, seq={}, pages=[], fillers=[])
            runs.append(current)
        # The bank numbers its inserts: unnumbered pages directly before this
        # one stand in for the printed numbers between the last page and it.
        before = max(current['seq']) if current['seq'] else 0
        gap = list(range(before + 1, number))
        if gap and len(unnumbered) >= len(gap):
            for printed, filler in zip(gap, unnumbered[-len(gap):]):
                current['seq'][printed] = filler.number
                current['fillers'].append(filler.number)
        current['seq'][number] = page.number
        current['pages'].append(page)
        unnumbered = []
    periods = []
    for run in runs:
        periods.append(_bbva_period(run))
    return periods


def _bbva_period(run):
    pages = run['pages']
    text = '\n'.join(p.text for p in pages)
    first = pages[0].text
    period = Period(family='bbva-mexico', institution='BBVA Mexico', pages=[p.number for p in pages],
                    page_sequence=run['seq'], page_total=run['total'])
    if run['fillers']:
        period.notes.append(f"{len(run['fillers'])} unnumbered page(s) stand for printed page numbers")
    match = re.search(r'Periodo\s+DEL\s+(\d{2})/(\d{2})/(\d{4})\s+AL\s+(\d{2})/(\d{2})/(\d{4})', first, re.I)
    if match:
        d1, m1, y1, d2, m2, y2 = map(int, match.groups())
        period.period_start, period.period_end = iso(y1, m1, d1), iso(y2, m2, d2)
    account = find(r'No\.\s*de\s*Cuenta\s+(\d[\d\- ]{5,})', first) or find(r'No\.\s*Cuenta\s+(\d{6,})', text)
    period.account = last4(account)
    moneda = find(r'Informaci[oó]n Financiera\s+MONEDA\s+([A-ZÁÉÍÓÚ]+)', first) or ''
    period.currency = dict(NACIONAL='MXN', EUROS='EUR', EURO='EUR', DOLARES='USD', DÓLARES='USD',
                           DOLAR='USD').get(moneda.upper())
    if period.currency is None:
        if re.search(r'MONEDA\s+NACIONAL|\bM\.N\.', first):
            period.currency = 'MXN'
        elif re.search(r'\bEUROS?\b', first):
            period.currency = 'EUR'
        elif re.search(r'D[OÓ]LARES|\bUSD\b|DLLS', first, re.I):
            period.currency = 'USD'
    # Holder: the first line under the period line that is not a bank label.
    lines = first.split('\n')
    for index, line in enumerate(lines):
        if re.search(r'Periodo\s+DEL', line, re.I):
            for candidate in lines[index + 1:index + 4]:
                candidate = re.sub(r'\s+Fecha de Corte.*$', '', candidate).strip()
                if candidate and not re.search(r'Fecha de Corte|No\.|R\.F\.C|PAGINA', candidate, re.I):
                    period.holder = candidate
                    break
            break
    # Every printed row is in the operation balance; the settlement balance
    # ("Saldo Final (+)") leaves out rows that settle after the period. The
    # operation balances are reconciled; the settlement closing is checked
    # separately once the rows are read.
    opening_settled = money_after(r'Saldo de Liquidaci[oó]n Inicial', text)
    opening = money_after(r'Saldo de Operaci[oó]n Inicial', text)
    closing_settled = money_after(r'Saldo Final \(\+\)', text)
    closing = money_after(r'Saldo de Operaci[oó]n Final', text)
    period.opening_minor = opening
    period.closing_minor = closing
    other = []
    match = re.search(r'Dep[oó]sitos\s*/\s*Abonos\s*\(\+\)\s+(\d+)\s+(-?[\d,]+\.\d{2})', text)
    if match:
        period.controls['credits_count'] = int(match.group(1))
        period.controls['credits_total'] = money_minor(match.group(2))
    match = re.search(r'Retiros\s*/\s*Cargos\s*\(-\)\s+(\d+)\s+(-?[\d,]+\.\d{2})', text)
    if match:
        period.controls['debits_count'] = int(match.group(1))
        period.controls['debits_total'] = money_minor(match.group(2))
    match = re.search(r'TOTAL IMPORTE CARGOS\s+(-?[\d,]+\.\d{2})\s+TOTAL MOVIMIENTOS CARGOS\s+(\d+)', text)
    if match:
        other.append(dict(ok=period.controls.get('debits_total') in (None, money_minor(match.group(1))),
                          reason='summary and movement debit totals differ'))
        period.controls.setdefault('debits_total', money_minor(match.group(1)))
        period.controls.setdefault('debits_count', int(match.group(2)))
        period.controls['debits_total_movements'] = money_minor(match.group(1))
    match = re.search(r'TOTAL IMPORTE ABONOS\s+(-?[\d,]+\.\d{2})\s+TOTAL MOVIMIENTOS ABONOS\s+(\d+)', text)
    if match:
        other.append(dict(ok=period.controls.get('credits_total') in (None, money_minor(match.group(1))),
                          reason='summary and movement credit totals differ'))
        period.controls.setdefault('credits_total', money_minor(match.group(1)))
        period.controls.setdefault('credits_count', int(match.group(2)))
    period.controls['other_checks'] = other
    if not period.period_start:
        period.problems.append('period dates not read')
        return period
    rows, row = [], None
    in_table = True
    for page in pages:
        columns, header_top = _bbva_columns(page)
        if columns is None or not in_table:
            continue
        for line in page.lines:
            if BBVA_TABLE_END.match(line.text):
                row, in_table = None, False
                continue
            if line.top <= header_top:
                continue
            words = [w['text'] for w in line.words]
            if BBVA_FOOTER.search(line.text):
                row = None
                if BBVA_TABLE_END.match(line.text):
                    in_table = False
                continue
            if not in_table:
                continue
            if len(words) >= 2 and BBVA_DATE.match(words[0]) and BBVA_DATE.match(words[1]):
                day, month = BBVA_DATE.match(words[1]).groups()
                if month not in ES_MONTHS:
                    period.problems.append('unknown month abbreviation')
                    continue
                day0, month0 = BBVA_DATE.match(words[0]).groups()
                amounts = {}
                description = []
                for w in line.words[2:]:
                    column = column_of(w, columns) if is_money(w['text']) else None
                    if column:
                        if column in amounts:
                            period.problems.append('two values in one column')
                        amounts[column] = money_minor(w['text'])
                    elif not amounts:
                        description.append(w['text'])
                if not amounts:
                    # A dated line with no amount at all (e.g. account opening) is
                    # information, not a movement; the printed counts still apply.
                    period.notes.append('dated line without an amount')
                    row = None
                    continue
                if ('debit' in amounts) == ('credit' in amounts):
                    period.problems.append('row without exactly one amount column')
                    continue
                direction = 'debit' if 'debit' in amounts else 'credit'
                if month0 not in ES_MONTHS:
                    period.problems.append('unknown month abbreviation')
                    continue
                # OPER is the transaction date; LIQ (settlement) may fall after the period.
                row = dict(date=iso(year_for(ES_MONTHS[month0], period.period_start, period.period_end),
                                    ES_MONTHS[month0], int(day0)),
                           settlement_date=iso(_settlement_year(ES_MONTHS[month0], ES_MONTHS[month], period),
                                               ES_MONTHS[month], int(day)),
                           description=' '.join(description[1:]) if description and re.fullmatch(r'[A-Z]\d{2}', description[0]) else ' '.join(description),
                           code=description[0] if description and re.fullmatch(r'[A-Z]\d{2}', description[0]) else None,
                           amount_minor=amounts[direction], direction=direction)
                if 'balance_operation' in amounts:
                    row['balance_after'] = amounts['balance_operation']
                if 'balance_settlement' in amounts:
                    row['settlement_balance'] = amounts['balance_settlement']
                rows.append(row)
            elif row is not None:
                # Continuation text; a money value aligned with an amount column here is a layout we do not model.
                if any(is_money(w['text']) and column_of(w, columns) in ('debit', 'credit') for w in line.words):
                    period.problems.append('amount on a continuation line')
    period.rows = rows
    if closing_settled is not None and closing is not None:
        later = sum((r['amount_minor'] if r['direction'] == 'credit' else -r['amount_minor'])
                    for r in rows if r.get('settlement_date') and r['settlement_date'] > period.period_end)
        other.append(dict(ok=closing - later == closing_settled,
                          reason='settlement closing differs from operation closing less rows settling later'))
    if opening_settled is not None and opening is not None and opening_settled != opening:
        period.notes.append('operation and settlement opening differ')
    if not rows and period.opening_minor is not None and period.closing_minor is not None:
        if period.controls.get('credits_count', 0) or period.controls.get('debits_count', 0):
            period.problems.append('printed movements but none read')
    return period


# ---------------------------------------------------------------------------
# Monex (Banco Monex; one contract, one movement table per currency)
# ---------------------------------------------------------------------------

MONEX_DATE = re.compile(r'^(\d{1,2})/([A-Za-z]{3})\.?(?:\((\d{1,2})/([A-Za-z]{3})\))?$')
MONEX_TABLE_OPEN = re.compile(r'^Saldo\s+Inicial:?\s+(\S+)\s+(\S+)\s+(\S+)\s*$', re.I)
MONEX_TABLE_CLOSE = re.compile(r'^Saldo\s+Final:?\s+(\S+)(?:\s+(\S+))?\s+(\S+)\s*$', re.I)
MONEX_CURRENCIES = (('MXN', r'peso\s+mexicano'), ('USD', r'd[oó]lar\s+americano'), ('EUR', r'\beuros?\b'),
                    ('CAD', r'd[oó]lar\s+canad'), ('GBP', r'libra\s+esterlina'), ('CHF', r'franco\s+suizo'),
                    ('JPY', r'\byen\b'))
MONEX_SECTION = re.compile(r'(Resumen\s+Divisas\s+|Resumen\s+cuenta\s+|CUENTA\s+VISTA\s+|Movimientos\s+)?'
                           r'(peso\s+mexicano|d[oó]lar\s+americano|euros?|d[oó]lar\s+canad[aá]|libra\s+esterlina|'
                           r'franco\s+suizo)\s+al\s+\d', re.I)


def _monex_dates(text):
    """Printed period: 'Del 1 Abril 2022 al 30 abril 2022' or '1 al 31 de MAYO de 2019'."""
    m = re.search(r'PERIODO:?\s*Del\s+(\d{1,2})\s+(?:de\s+)?([A-Za-zé]+)\s+(?:de\s+)?(\d{4})\s+al\s+(\d{1,2})\s+'
                  r'(?:de\s+)?([A-Za-zé]+)\s+(?:de\s+)?(\d{4})', text, re.I)
    if m:
        d1, mo1, y1, d2, mo2, y2 = m.groups()
        a, b = ES_MONTH_NAMES.get(mo1.lower()), ES_MONTH_NAMES.get(mo2.lower())
        if a and b:
            return iso(int(y1), a, int(d1)), iso(int(y2), b, int(d2))
    m = re.search(r'PERIODO:?\s*(?:Del\s+)?(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+([A-Za-zé]+)\s+de\s+(\d{4})', text, re.I)
    if m:
        d1, d2, mo, y = m.groups()
        month = ES_MONTH_NAMES.get(mo.lower())
        if month:
            return iso(int(y), month, int(d1)), iso(int(y), month, int(d2))
    return None, None


def _monex_currency(text):
    found = None
    for match in MONEX_SECTION.finditer(text):
        found = match.group(2)
    if found is None:
        return None
    for code, pattern in MONEX_CURRENCIES:
        if re.search(pattern, found, re.I):
            return code
    return None


def _monex_holder(page):
    """First line of the address block that ends with the postcode line ('C.P.')."""
    for index, line in enumerate(page.lines):
        cp = next((w for w in line.words if w['text'].startswith('C.P')), None)
        if cp is None:
            continue
        block = []
        top = line.top
        for previous in reversed(page.lines[:index]):
            words = [w for w in previous.words if abs(w['x0'] - cp['x0']) < 160 and w['x0'] >= cp['x0'] - 5]
            if not words or top - previous.top > 16:
                break
            block.insert(0, ' '.join(w['text'] for w in words))
            top = previous.top
        if block:
            return block[0]
    return None


def parse_monex(pages):
    """One period per currency section ('<currency> al <date>' heading).

    A section with a movement table is bounded by the table's printed opening
    and closing lines; a section without one is a period with no movements only
    when it prints zero credits, zero debits and equal opening and closing.
    """
    text = '\n'.join(p.text for p in pages)
    start, end = _monex_dates(text)
    contract = find(r'CONTRATO:\s*(\d{5,})', text)
    holder = _monex_holder(pages[0]) if pages else None
    sequence, total, _ = printed_sequence(pages, r'Hoja\s+(\d+)\s+de\s+(\d+)')
    sections, section = [], None
    for page in pages:
        for line in page.lines:
            heading = MONEX_SECTION.search(line.text)
            if heading and not MONEX_TABLE_OPEN.match(line.text):
                if section is not None and section['table'] == 'open':
                    section['problems'].append('section heading inside an open movement table')
                section = dict(currency=_monex_currency(line.text), summary=[], table=None, lines=[], pages=[page.number],
                               problems=[], opening=None, closing=None)
                sections.append(section)
                continue
            if section is None:
                continue
            if page.number not in section['pages']:
                section['pages'].append(page.number)
            opened = MONEX_TABLE_OPEN.match(line.text)
            closed = MONEX_TABLE_CLOSE.match(line.text)
            if opened and all(is_money(v) for v in opened.groups()):
                if section['table'] is not None:
                    section['problems'].append('second movement table in one currency section')
                section['table'], section['opening'] = 'open', money_minor(opened.group(3))
            elif closed and all(is_money(v) for v in closed.groups() if v) and section['table'] == 'open':
                section['table'], section['closing'] = 'closed', money_minor(closed.group(3))
            elif section['table'] == 'open':
                section['lines'].append((page.number, line))
            elif section['table'] is None:
                section['summary'].append(line.text)
    periods = []
    for section in sections:
        preface = '\n'.join(section['summary'])
        summary = dict(opening=money_after(r'Saldo\s+inicial:', preface),
                       credits=money_after(r'\+\s*(?:Total\s+)?abonos:', preface),
                       debits=money_after(r'-\s*(?:Total\s+)?cargos:', preface),
                       closing=money_after(r'Saldo\s+total:', preface) if re.search(r'Saldo\s+total:', preface, re.I)
                       else money_after(r'SALDO\s+FINAL:', preface))
        period = Period(family='monex-mexico', institution='Monex', holder=holder, account=last4(contract),
                        period_start=start, period_end=end, page_sequence=sequence, page_total=total,
                        currency=section['currency'], pages=section['pages'], problems=list(section['problems']))
        period.controls['summary'] = summary
        if summary['credits'] is not None:
            period.controls['credits_total'] = summary['credits']
        if summary['debits'] is not None:
            period.controls['debits_total'] = summary['debits']
        if section['table'] is None:
            if None in summary.values():
                period.problems.append('currency section without a movement table or a full summary')
            elif summary['credits'] or summary['debits'] or summary['opening'] != summary['closing']:
                period.problems.append('summary prints movements but no movement table was found')
            period.opening_minor, period.closing_minor = summary['opening'], summary['closing']
            period.notes.append('no movement table; printed zero totals')
        else:
            if section['table'] == 'open':
                period.problems.append('movement table has no printed closing line')
            if None in summary.values():
                period.problems.append('currency summary not read')
            period.opening_minor, period.closing_minor = section['opening'], section['closing']
            period.controls['other_checks'] = [
                dict(ok=summary['opening'] in (None, period.opening_minor), reason='summary opening differs from table'),
                dict(ok=summary['closing'] in (None, period.closing_minor), reason='summary closing differs from table')]
            period._dated = section['lines']
            _monex_rows(period)
            del period._dated
        periods.append(period)
    # The peso summary lists every other currency with its opening, credits,
    # debits and balance; each must match a section read above.
    listed = re.findall(r'^(d[oó]lar\s+americano|euros?|d[oó]lar\s+canad[aá]|libra\s+esterlina|franco\s+suizo)\s+'
                        r'(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', text, re.I | re.M)
    for name, *values in listed:
        if not all(is_money(v) for v in values):
            continue
        opening, credits, debits, closing = (money_minor(v) for v in values)
        code = _monex_currency(name + ' al 1')
        if not any(p.currency == code and p.opening_minor == opening and p.closing_minor == closing
                   and p.controls.get('credits_total') == credits and p.controls.get('debits_total') == debits
                   for p in periods):
            target = next((p for p in periods if p.currency == code), periods[0] if periods else None)
            if target is not None:
                target.problems.append('currency listed in the summary does not match a section read')
    return periods


def _monex_rows(period):
    lines = period._dated
    dated = [i for i, (_, line) in enumerate(lines) if line.words and MONEX_DATE.match(line.words[0]['text'])]
    for i, (_, line) in enumerate(lines):
        values = [money_minor(w['text']) for w in line.words if is_money(w['text'])]
        if i not in dated and len(values) >= 6 and (values[-6] or values[-5]):
            period.problems.append('undated movement line')
    for i in dated:
        number, line = lines[i]
        day, month, _, _ = MONEX_DATE.match(line.words[0]['text']).groups()
        month = ES_MONTHS.get(month.upper())
        values = [w for w in line.words if is_money(w['text'])]
        if month is None or len(values) < 6:
            period.problems.append('movement line not read')
            continue
        credit, debit, guarantee_move, _, _, total = (money_minor(w['text']) for w in values[-6:])
        neighbours = [l for j, (n, l) in enumerate(lines) if j not in dated and n == number
                      and min(abs(l.top - lines[k][1].top) for k in dated if lines[k][0] == n) == abs(l.top - line.top)]
        words = [w['text'] for w in line.words[1:] if w not in values[-6:]]
        description = ' '.join([l.text for l in neighbours if l.top < line.top] + words +
                               [l.text for l in neighbours if l.top > line.top])
        date_iso = iso(year_for(month, period.period_start, period.period_end), month, int(day)) \
            if period.period_start else None
        if credit and debit:
            period.problems.append('movement with both a credit and a debit')
            continue
        if not credit and not debit:
            if guarantee_move:
                period.notes.append('guarantee movement without credit or debit')
            continue
        if credit is not None and credit < 0 or debit is not None and debit < 0:
            period.problems.append('negative movement amount')
            continue
        period.rows.append(dict(date=date_iso, description=description.strip(), amount_minor=credit or debit,
                                direction='credit' if credit else 'debit', balance_after=total))


# ---------------------------------------------------------------------------
# Santander Mexico (statement layouts 2019 and 2025; online movement query)
# ---------------------------------------------------------------------------

SANTANDER_DATE = re.compile(r'^(\d{2})-([A-Z]{3})-(\d{4})$')
SANTANDER_ACCOUNT = re.compile(r'(\d{2}-\d{8}-\d)')
SANTANDER_PAGE = r'(?:HOJA|P\S{0,3}gina)\s+(\d+)\s+DE\s+(\d+)'


def split_runs(pages, pattern):
    """Split pages into runs that each restart at printed page 1 (one statement per run)."""
    runs, current, unnumbered = [], None, []
    for page in pages:
        match = re.search(pattern, page.text, re.I)
        if not match:
            if current is not None:
                current['pages'].append(page)
            unnumbered.append(page)
            continue
        number, total = int(match.group(1)), int(match.group(2))
        if current is None or number == 1 or current['total'] != total or number in current['seq'] \
                or number < max(current['seq']):
            current = dict(total=total, seq={}, pages=[], fillers=[])
            for filler in unnumbered:  # leading unnumbered pages belong to the run they precede
                if filler not in current['pages']:
                    current['pages'].append(filler)
            runs.append(current)
            for run in runs[:-1]:
                run['pages'] = [p for p in run['pages'] if p not in unnumbered]
        gap = list(range((max(current['seq']) if current['seq'] else 0) + 1, number))
        if gap and len(unnumbered) >= len(gap):
            for printed, filler in zip(gap, unnumbered[-len(gap):]):
                current['seq'][printed] = filler.number
                current['fillers'].append(filler.number)
        current['seq'].setdefault(number, page.number)
        if page not in current['pages']:
            current['pages'].append(page)
        unnumbered = []
    for run in runs:
        run['pages'].sort(key=lambda p: p.number)
    return runs


def parse_santander(pages):
    text = '\n'.join(p.text for p in pages)
    if re.search(r'Consulta de Movimientos de la Cuenta', text, re.I):
        return parse_santander_query(pages)
    return [period for run in split_runs(pages, SANTANDER_PAGE) for period in _santander_run(run)]


def _santander_dates(text):
    m = re.search(r'PERIODO\s*:?\s*DEL\s+(\d{2})-([A-Z]{3})-(\d{4})\s+AL\s+(\d{2})-([A-Z]{3})-(\d{4})', text, re.I)
    if m:
        d1, m1, y1, d2, m2, y2 = m.groups()
        if m1.upper() in ES_MONTHS and m2.upper() in ES_MONTHS:
            return iso(int(y1), ES_MONTHS[m1.upper()], int(d1)), iso(int(y2), ES_MONTHS[m2.upper()], int(d2))
    m = re.search(r'PERIODO\s*:?\s*(?:DEL\s+)?(\d{1,2})\s+(?:DE\s+([A-Z]+)\s+)?AL\s+(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})',
                  text, re.I)
    if m:
        d1, mo1, d2, mo2, y = m.groups()
        a, b = ES_MONTH_NAMES.get((mo1 or mo2).lower()), ES_MONTH_NAMES.get(mo2.lower())
        if a and b:
            return iso(int(y) - (1 if a > b else 0), a, int(d1)), iso(int(y), b, int(d2))
    return None, None


def _santander_holder(text):
    for line in text.split('\n'):
        if 'CODIGO DE CLIENTE' in line.upper():
            before = re.split(r'CODIGO DE CLIENTE', line, flags=re.I)[0].strip()
            if before:
                return before
    lines = text.split('\n')
    for index, line in enumerate(lines):
        if 'CODIGO DE CLIENTE' in line.upper() and index:
            return lines[index - 1].strip() or None
    return None


class _Columns(dict):
    """Right edges by column name (``column_of``), with header centres kept alongside."""
    centres = None


def _santander_columns(line):
    names, centres = _Columns(), {}
    for w in line.words:
        word = w['text'].upper()
        key = ('credit' if word in ('DEPOSITOS', 'DEPOSITO', 'DEPÓSITOS', 'DEPÓSITO') else
               'debit' if word in ('RETIROS', 'RETIRO') else 'balance' if word == 'SALDO' else None)
        if key:
            names[key] = w['x1']
            centres[key] = (w['x0'] + w['x1']) / 2
    names.centres = centres
    return names if {'credit', 'debit'} <= set(names) else None


def _nearest_centre(word, header_words):
    """Column whose header centre is nearest the value's centre (values not aligned to the header edge)."""
    centre = (word['x0'] + word['x1']) / 2
    centres = header_words.centres or {}
    return min(centres, key=lambda name: abs(centres[name] - centre)) if centres else None


def _santander_run(run):
    pages = run['pages']
    text = '\n'.join(p.text for p in pages)
    start, end = _santander_dates(text)
    holder = _santander_holder(text)
    moneda = find(r'MONEDA\s*:?\s*(?:MONEDA\s+)?([A-Z]+(?:\s+[A-Z]+)?)', text) or ''
    currency = 'MXN' if 'NACIONAL' in moneda.upper() else 'USD' if re.search(r'D[OÓ]LAR', moneda, re.I) else None
    balances = {}
    for line in text.split('\n'):
        m = re.search(r'(\d{2}-\d{8}-\d)\s+(-?[\d,]+\.\d{2})\s+[\d.]+%\s+(-?[\d,]+\.\d{2})\s+[\d.]+%', line)
        if m:
            balances[m.group(1)] = (money_minor(m.group(2)), money_minor(m.group(3)))
    periods, period, columns, account = [], None, None, None
    for page in pages:
        for index, line in enumerate(page.lines):
            found = SANTANDER_ACCOUNT.search(line.text)
            if found and not re.search(r'%|CLABE', line.text):
                account = found.group(1)
            header = _santander_columns(line)
            if header:
                columns = header
                continue
            opened = re.match(r'^(?:\d{2}-[A-Z]{3}-\d{4}\s+)?SALDO FINAL DEL PERIODO ANTERIOR:?\s*\$?\s*(-?[\d,. ]+\.\s?\d\s?\d)\s*$',
                              line.text)
            if opened and is_money(opened.group(1).replace(' ', '')):
                period = Period(family='santander-mexico', institution='Santander', holder=holder,
                                account=last4(account), period_start=start, period_end=end, currency=currency,
                                page_sequence=run['seq'], page_total=run['total'], pages=[page.number])
                period.opening_minor = money_minor(opened.group(1).replace(' ', ''))
                period.controls['account_printed'] = account
                periods.append(period)
                continue
            if period is None or period.closing_minor is not None and 'closed' in period.controls:
                continue
            if page.number not in period.pages:
                period.pages.append(page.number)
            total = re.match(r'^TOTAL\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})(?:\s+(-?[\d,]+\.\d{2}))?\s*$', line.text)
            if total:
                period.controls['credits_total'] = money_minor(total.group(1))
                period.controls['debits_total'] = money_minor(total.group(2))
                if total.group(3):
                    period.closing_minor = money_minor(total.group(3))
                period.controls['total_line'] = True
                continue
            closing = re.match(r'^SALDO FINAL DEL PERIODO:?\s*\$?\s*(-?[\d,]+\.\d{2})', line.text)
            if closing:
                value = money_minor(closing.group(1))
                if period.closing_minor is not None and period.closing_minor != value:
                    period.problems.append('closing printed twice with different values')
                period.closing_minor = value
                period.controls['closed'] = True
                continue
            if 'total_line' in period.controls:
                if re.match(r'^(Detalle|DETALLE|INFORMACION FISCAL)', line.text):
                    period.controls['closed'] = True
                continue
            words = line.words
            date = SANTANDER_DATE.match(words[0]['text']) if words else None
            if not date:
                continue
            if columns is None:
                period.problems.append('movement before a column header')
                continue
            values = [w for w in words if is_money(w['text'])]
            placed = {id(w): column_of(w, columns, 14) or _nearest_centre(w, columns) for w in values}
            amount = next((w for w in values if placed[id(w)] in ('credit', 'debit')), None)
            balance = next((w for w in values if placed[id(w)] == 'balance'), None)
            if amount is None:
                if re.search(r'SALDO FINAL DEL PERIODO ANTERIOR', line.text):
                    continue
                period.problems.append('movement line without an amount in a deposit or withdrawal column')
                continue
            day, month, year = date.groups()
            if month not in ES_MONTHS:
                period.problems.append('unknown month abbreviation')
                continue
            description = ' '.join(w['text'] for w in words[1:] if w not in values)
            row = dict(date=iso(int(year), ES_MONTHS[month], int(day)), description=description,
                       amount_minor=money_minor(amount['text']), direction=placed[id(amount)])
            if balance is not None:
                row['balance_after'] = money_minor(balance['text'])
            period.rows.append(row)
    for period in periods:
        period.controls.pop('closed', None)
        period.controls.pop('total_line', None)
        printed = period.controls.get('account_printed')
        if printed in balances:
            before, after = balances[printed]
            period.controls['other_checks'] = [
                dict(ok=before == period.opening_minor, reason='summary previous-month balance differs from opening'),
                dict(ok=after == period.closing_minor, reason='summary current balance differs from closing')]
        else:
            period.problems.append('account not found in the balance summary')
        if 'credits_total' not in period.controls:
            period.problems.append('movement table without a printed TOTAL line')
    return periods


def parse_santander_query(pages):
    """Online 'Consulta de Movimientos' printout: printed opening, closing, counts and totals."""
    text = '\n'.join(p.text for p in pages)
    period = Period(family='santander-mexico', institution='Santander', pages=[p.number for p in pages])
    sequence, total, _ = printed_sequence(pages, r'P\S{0,3}gina\s+(\d+)\s+de\s+(\d+)')
    period.page_sequence, period.page_total = sequence, total
    m = re.search(r'Periodo:\s*(\d{2})/(\d{2})/(\d{4})\s+al\s+(\d{2})/(\d{2})/(\d{4})', text)
    if m:
        d1, m1, y1, d2, m2, y2 = map(int, m.groups())
        period.period_start, period.period_end = iso(y1, m1, d1), iso(y2, m2, d2)
    period.account = last4(find(r'N[uú]mero de Cuenta:\s*(\d+)', text))
    period.holder = (find(r'Contrato CMC:\s*\d+\s+(.+?)\s+Periodo:', text) or '').strip() or None
    period.currency = find(r'Saldo Inicial:\s*\$?[\d,.-]+\s+([A-Z]{3})', text)
    period.opening_minor = money_after(r'Saldo Inicial:', text)
    period.closing_minor = money_after(r'Saldo Final:', text)
    counts = dict(credits_count=find(r'N[uú]mero de Abonos:\s*(\d+)', text),
                  debits_count=find(r'N[uú]mero de Cargos:\s*(\d+)', text),
                  rows_count=find(r'Total de Movimientos:\s*(\d+)', text))
    period.controls.update({k: int(v) for k, v in counts.items() if v is not None})
    for key, label in (('credits_total', r'Importe Total Abonos:'), ('debits_total', r'Importe Total Cargos:')):
        value = money_after(label, text)
        if value is not None:
            period.controls[key] = value
    rows = []
    for page in pages:
        for line in page.lines:
            words = [w['text'] for w in line.words]
            if len(words) < 6 or not re.fullmatch(r'\d{8}', words[1]) or not re.fullmatch(r'\d{2}:\d{2}', words[2]):
                continue
            index = next((i for i in range(3, len(words) - 2) if all(is_money(w) for w in words[i:i + 3])), None)
            if index is None:
                period.problems.append('movement line not read')
                continue
            debit, credit, balance = (money_minor(w) for w in words[index:index + 3])
            if bool(debit) == bool(credit):
                period.problems.append('movement line without exactly one of debit and credit')
                continue
            d = words[1]
            rows.append(dict(date=iso(int(d[4:]), int(d[2:4]), int(d[:2])), description=' '.join(words[4:index]),
                             amount_minor=credit or debit, direction='credit' if credit else 'debit',
                             balance_after=balance))
    if rows and period.opening_minor is not None:
        def consistent(ordered):
            value = period.opening_minor
            for r in ordered:
                value += r['amount_minor'] if r['direction'] == 'credit' else -r['amount_minor']
                if value != r['balance_after']:
                    return False
            return True
        if not consistent(rows) and consistent(list(reversed(rows))):
            rows.reverse()
            period.notes.append('printed newest first')
    period.rows = rows
    if rows and period.opening_minor is not None and rows[0].get('balance_after') == period.opening_minor:
        period.problems.append('printed opening is the balance after the first movement')
    period.notes.append('online movement query, not a monthly statement')
    return [period]


# ---------------------------------------------------------------------------
# Kapital Bank (ex Autofin; "ESTADO DE CUENTA ÚNICO", one section per account)
# ---------------------------------------------------------------------------

KAPITAL_ACCOUNT = re.compile(r'(\d{3}-\d{5}-\d{3}-\d)\s+CLABE\s+(\d{3})')
# The same "ESTADO DE CUENTA ÚNICO" layout is issued under two bank codes.
UNICO_FAMILIES = {'128': ('kapital-mexico', 'Kapital'), '136': ('intercam-mexico', 'Intercam')}


def _kapital_columns(line):
    names, centres = _Columns(), {}
    for w in line.words:
        word = w['text'].upper()
        key = ('credit' if word.startswith('DEP') else 'debit' if word.startswith('RETIRO') else
               'balance' if word == 'SALDO' else None)
        if key:
            names[key] = w['x1']
            centres[key] = (w['x0'] + w['x1']) / 2
    names.centres = centres
    return names if {'credit', 'debit', 'balance'} <= set(names) else None


def parse_kapital(pages):
    return [period for run in split_runs(pages, r'Hoja\s+(\d+)\s+de\s+(\d+)') for period in _kapital_run(run)]


def _kapital_run(run):
    pages = run['pages']
    text = '\n'.join(p.text for p in pages)
    m = re.search(r'Per[ií]odo\s+DEL\s+(\d{4})-(\d{2})-(\d{2})\s+AL\s+(\d{4})-(\d{2})-(\d{2})', text, re.I)
    start = end = None
    if m:
        y1, m1, d1, y2, m2, d2 = map(int, m.groups())
        start, end = iso(y1, m1, d1), iso(y2, m2, d2)
    holder = None
    first = pages[0].text.split('\n') if pages else []
    for index, line in enumerate(first):
        if re.match(r'^Versi[oó]n\s', line) and index + 1 < len(first):
            holder = first[index + 1].strip() or None
            break
    periods, period, columns, summary = [], None, None, []
    for page in pages:
        for line in page.lines:
            found = KAPITAL_ACCOUNT.search(line.text)
            if found:
                family, institution = UNICO_FAMILIES.get(found.group(2), ('unico-unknown-bank', 'unknown'))
                period = Period(family=family, institution=institution, holder=holder, period_start=start,
                                period_end=end, account=last4(found.group(1)), page_sequence=run['seq'],
                                page_total=run['total'], pages=[page.number])
                period.controls['account_printed'] = found.group(1)
                periods.append(period)
                columns, summary = None, []
                continue
            if period is None:
                continue
            if page.number not in period.pages:
                period.pages.append(page.number)
            header = _kapital_columns(line)
            if header:
                columns = header
                continue
            total = re.match(r'^Total\s+(-?[\d,]+\.\d{2})(?:\s+[A-Z]{3})?\s+(-?[\d,]+\.\d{2})(?:\s+[A-Z]{3})?'
                             r'(?:\s+(-?[\d,]+\.\d{2})(?:\s+[A-Z]{3})?)?\s*$', line.text)
            if total:
                period.controls['credits_total'] = money_minor(total.group(1))
                period.controls['debits_total'] = money_minor(total.group(2))
                if total.group(3):
                    period.controls['table_closing'] = money_minor(total.group(3))
                period.controls['ended'] = True
                continue
            if period.controls.get('ended'):
                continue
            if columns is None:
                summary.append(line.text)
                moneda = re.match(r'^Moneda\s+([A-Z]{2,3})\b', line.text)
                if moneda:
                    period.currency = dict(MN='MXN', MXN='MXN', USD='USD', EUR='EUR').get(moneda.group(1))
                if re.match(r'^Saldo Inicial\s', line.text) and period.opening_minor is None:
                    period.opening_minor = money_after(r'Saldo Inicial', line.text)
                elif re.match(r'^Saldo Final\s', line.text):
                    period.closing_minor = money_after(r'Saldo Final', line.text)
                elif re.match(r'^\+\s*Dep[oó]sitos\s', line.text):
                    period.controls['summary_credits'] = money_after(r'Dep[oó]sitos', line.text)
                elif re.match(r'^-\s*Retiros\s', line.text):
                    period.controls['summary_debits'] = money_after(r'Retiros', line.text)
                elif re.match(r'^[+-]\s*(Intereses|I\.S\.R\.|Comisiones)', line.text):
                    value = money_after(r'(?:Cheques|Inversiones|Efectivamente)', line.text)
                    if value:
                        period.notes.append('interest, tax or fee printed in the summary')
                continue
            words = line.words
            if len(words) < 3 or not re.fullmatch(r'\d{1,2}', words[0]['text']) or not re.fullmatch(r'\d{3,}', words[1]['text']):
                continue
            values = [w for w in words if is_money(w['text'])]
            placed = {id(w): column_of(w, columns, 14) or _nearest_centre(w, columns) for w in values}
            amounts = [w for w in values if placed[id(w)] in ('credit', 'debit')]
            balance = next((w for w in values if placed[id(w)] == 'balance'), None)
            if len(amounts) != 1:
                period.problems.append('movement line without exactly one amount')
                continue
            day = int(words[0]['text'])
            date_iso = None
            if start and end:
                s_, e_ = date.fromisoformat(start), date.fromisoformat(end)
                date_iso = iso(e_.year, e_.month, day) if s_.month == e_.month else None
            row = dict(date=date_iso, description=' '.join(w['text'] for w in words[2:] if w not in values),
                       amount_minor=money_minor(amounts[0]['text']), direction=placed[id(amounts[0])])
            if balance is not None:
                row['balance_after'] = money_minor(balance['text'])
            period.rows.append(row)
    for period in periods:
        c = period.controls
        c.pop('ended', None)
        checks = [dict(ok=c.get('summary_credits') in (None, c.get('credits_total', c.get('summary_credits'))),
                       reason='summary deposits differ from the table total'),
                  dict(ok=c.get('summary_debits') in (None, c.get('debits_total', c.get('summary_debits'))),
                       reason='summary withdrawals differ from the table total'),
                  dict(ok=c.get('table_closing') in (None, period.closing_minor),
                       reason='table closing differs from the summary closing')]
        c['other_checks'] = checks
        if 'credits_total' not in c:
            if 'summary_credits' in c and 'summary_debits' in c:
                c['credits_total'], c['debits_total'] = c['summary_credits'], c['summary_debits']
            else:
                period.problems.append('no printed totals')
    return periods


# ---------------------------------------------------------------------------
# Capital One card statements (one statement per "Page 1 of N" run)
# ---------------------------------------------------------------------------

_MON = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
EN_DATE_ROW = re.compile(r'^' + _MON + r'\s+(\d{1,2})\s+(?:' + _MON + r'\s+(\d{1,2})\s+)?(.*?)\s*(-\s*)?\$\s?([\d,]+\.\d{2})$')


def _card_date(month, day, period):
    number = EN_MONTHS[month.upper()]
    return iso(year_for(number, _shift(period.period_start, -60), period.period_end), number, int(day))


def _shift(value, days):
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def _usd(label, text, signed=False):
    """Dollar value after ``label``. With ``signed``, a minus printed before the '$' makes it negative
    (a credit balance on a card); otherwise the sign is the label's arithmetic and is dropped."""
    m = re.search(label + r'\s*([+=])?\s*(-)?\s*\$\s?([\d,]+\.\d{2})', text)
    if not m:
        return None
    value = money_minor(m.group(3))
    return -value if signed and m.group(2) else value


def parse_capital_one(pages):
    return [_capital_one_run(run) for run in split_runs(pages, r'Page\s+(\d+)\s+of\s+(\d+)')]


def _capital_one_run(run):
    pages = run['pages']
    text = '\n'.join(p.text for p in pages)
    period = Period(family='capital-one-card', institution='Capital One', currency='USD', kind='card',
                    pages=[p.number for p in pages], page_sequence=run['seq'])
    numbered = sorted(run['seq'])
    if numbered and numbered != list(range(1, numbered[-1] + 1)):
        period.problems.append('printed page numbers not consecutive')
    m = re.search(r'([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s+(\d{4})\s+-\s+([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s+(\d{4})\s*\|\s*\d+\s+days',
                  text)
    if m:
        a, d1, y1, b, d2, y2 = m.groups()
        if a.upper() in EN_MONTHS and b.upper() in EN_MONTHS:
            period.period_start = iso(int(y1), EN_MONTHS[a.upper()], int(d1))
            period.period_end = iso(int(y2), EN_MONTHS[b.upper()], int(d2))
    period.account = find(r'(?:Account\s+)?Ending\s+in\s+(\d{4})', text)
    summary = dict(previous=_usd(r'Previous Balance', text, signed=True), payments=_usd(r'Payments', text),
                   other_credits=_usd(r'Other Credits', text), transactions=_usd(r'\nTransactions', '\n' + text),
                   cash_advances=_usd(r'Cash Advances', text), fees=_usd(r'Fees Charged', text),
                   interest=_usd(r'Interest Charged', text), new=_usd(r'New Balance\s*=', text, signed=True))
    period.controls['summary'] = summary
    period.opening_minor, period.closing_minor = summary['previous'], summary['new']
    if None in summary.values():
        period.problems.append('account summary not fully read')
    section, rows, member_totals = None, [], []
    for page in pages:
        right = float('inf')
        for line in page.lines:
            words = [w['text'] for w in line.words]
            if 'Description' in words and 'Amount' in words and words[0] in ('Date', 'Trans'):
                right = line.words[words.index('Amount')]['x1'] + 12
        for line in page.lines:
            # The table is the left column; a marketing panel to its right shares its lines.
            t = ' '.join(w['text'] for w in line.words if w['x0'] < right)
            head = re.search(r'#(\d{4}):\s*(Payments, Credits and Adjustments|Transactions|'
                             r'Total(?:\s+Transactions)?\s+\$\s?([\d,]+\.\d{2}))', t)
            if head:
                if head.group(3):
                    member_totals.append(money_minor(head.group(3)))
                    section = None
                else:
                    section = 'credits' if head.group(2).startswith('Payments') else 'purchases'
                    if period.holder is None:
                        period.holder = t[:t.index('#')].strip() or None
                continue
            if re.match(r'^Fees$', t):
                section = 'fees'
                continue
            if re.match(r'^(Interest Charged|Total Transactions for This Period|Total Fees for This Period|Totals Year-to-Date)', t):
                if t.startswith('Total Transactions'):
                    period.controls['transactions_total_line'] = _usd(r'Total Transactions for This Period', t)
                if t.startswith('Total Fees'):
                    period.controls['fees_total_line'] = _usd(r'Total Fees for This Period', t)
                section = 'interest' if t.startswith('Interest Charged') else None
                continue
            if section == 'interest':
                m = re.match(r'^Interest Charge on (.+?)\s+\$\s?([\d,]+\.\d{2})$', t)
                if m and money_minor(m.group(2)):
                    rows.append(dict(date=period.period_end, description='Interest Charge on ' + m.group(1),
                                     amount_minor=money_minor(m.group(2)), direction='debit', group='interest',
                                     date_printed=False))
                continue
            if section is None:
                continue
            m = EN_DATE_ROW.match(t)
            if not m:
                continue
            month, day, post_month, post_day, description, minus, amount = m.groups()
            if not period.period_start:
                continue
            row = dict(date=_card_date(month, day, period), description=description.strip(),
                       amount_minor=money_minor(amount), direction='credit' if minus else 'debit', group=section)
            if post_month:
                row['posted_date'] = _card_date(post_month, post_day, period)
            rows.append(row)
    period.rows = rows
    credits = sum(r['amount_minor'] for r in rows if r['direction'] == 'credit')
    purchases = sum(r['amount_minor'] if r['direction'] == 'debit' else 0 for r in rows if r['group'] == 'purchases')
    fees = sum(r['amount_minor'] for r in rows if r['group'] == 'fees')
    interest = sum(r['amount_minor'] for r in rows if r['group'] == 'interest')
    if None not in summary.values():
        period.controls['other_checks'] = [
            dict(ok=credits == summary['payments'] + summary['other_credits'],
                 reason='credit rows differ from printed payments and other credits'),
            dict(ok=purchases == summary['transactions'] + summary['cash_advances'],
                 reason='purchase rows differ from printed transactions and cash advances'),
            dict(ok=fees == summary['fees'], reason='fee rows differ from printed fees'),
            dict(ok=interest == summary['interest'], reason='interest rows differ from printed interest')]
    for row in rows:
        row.pop('group', None)
        if not row.pop('date_printed', True):
            row['date_outside_ok'] = True
            row['date_unprinted'] = True  # the statement prints no date for it (interest at cycle end)
    return period


# ---------------------------------------------------------------------------
# Citi card statements
# ---------------------------------------------------------------------------

CITI_ROW = re.compile(r'^(\d{2})/(\d{2})\s+(?:(\d{2})/(\d{2})\s+)?(.*?)\s*(-)?\$([\d,]+\.\d{2})$')
CITI_SECTIONS = (('credits', r'^Payments,\s*Credits\s+and\s+Adjustments'), ('purchases', r'^Standard\s+Purchases'),
                 ('advances', r'^(Standard\s+)?Cash\s+Advances\s*$'),
                 ('fees', r'^Fees\s+charged'), ('interest', r'^Interest\s+charged'))


def parse_citi(pages):
    return [_citi_run(run) for run in split_runs(pages, r'Page\s+(\d+)\s+of\s+(\d+)')]


def _citi_run(run):
    pages = run['pages']
    text = '\n'.join(p.text for p in pages)
    period = Period(family='citi-card', institution='Citibank', currency='USD', kind='card',
                    pages=[p.number for p in pages], page_sequence=run['seq'], page_total=run['total'])
    m = re.search(r'Billing Period:\s*(\d{2})/(\d{2})/(\d{2})\s*-\s*(\d{2})/(\d{2})/(\d{2})', text)
    if m:
        m1, d1, y1, m2, d2, y2 = map(int, m.groups())
        period.period_start, period.period_end = iso(2000 + y1, m1, d1), iso(2000 + y2, m2, d2)
    period.account = find(r'Account number ending in:?\s*(\d{4})', text)
    summary = dict(previous=_usd(r'Previous balance', text, signed=True), payments=_usd(r'Payments', text),
                   credits=_usd(r'\bCredits(?!\s+and)', text), purchases=_usd(r'Purchases(?!\s+if)', text),
                   advances=_usd(r'Cash advances', text), fees=_usd(r'\bFees(?!\s+charged)', text),
                   interest=_usd(r'\bInterest(?!\s+charge)', text),
                   new=_usd(r'New balance(?!\s+as\s+of)', text, signed=True))
    period.controls['summary'] = summary
    period.opening_minor, period.closing_minor = summary['previous'], summary['new']
    if None in summary.values():
        period.problems.append('account summary not fully read')
    first = pages[0].text.split('\n') if pages else []
    for index, line in enumerate(first):
        if re.search(r'PLATINUM|CARD\b', line) and index + 1 < len(first):
            period.holder = first[index + 1].strip() or None
            break
    section, rows, pending = None, [], None
    for page in pages:
        right = float('inf')
        for line in page.lines:
            words = [w['text'] for w in line.words]
            if 'Description' in words and 'Amount' in words:
                right = line.words[words.index('Amount')]['x1'] + 12
        for line in page.lines:
            t = ' '.join(w['text'] for w in line.words if w['x0'] < right)
            matched = next((name for name, pattern in CITI_SECTIONS if re.match(pattern, t, re.I)), None)
            if matched:
                section, pending = matched, None
                continue
            total = re.match(r'^Total (fees|interest) charged in this billing period\s+\$([\d,]+\.\d{2})', t)
            if total:
                period.controls[total.group(1) + '_total_line'] = money_minor(total.group(2))
                section = None
                continue
            if re.match(r'^(\d{4} totals year-to-date|Interest charge calculation|Total (fees|interest) charged in \d{4})', t, re.I):
                section, pending = None, None
            if section is None:
                continue
            if not period.period_start:
                continue
            m = CITI_ROW.match(t)
            if not m:
                dated = re.match(r'^(\d{2})/(\d{2})\s+(?:(\d{2})/(\d{2})\s+)?(\D.*)$', t)
                tail = re.search(r'(-)?\$([\d,]+\.\d{2})$', t)
                if dated and not tail:
                    pending = dated.groups()  # a row whose amount is printed on a later line
                elif tail and pending is not None:
                    mo, dy, pm, pd, description = pending
                    minus, amount = tail.groups()
                    pending = None
                    m = True
                elif tail:
                    period.problems.append('amount line without a date')
                if m is None:
                    continue
            else:
                mo, dy, pm, pd, description, minus, amount = m.groups()
                pending = None
            if not money_minor(amount):
                period.notes.append('zero-amount line')
                continue
            year = year_for(int(mo), _shift(period.period_start, -60), period.period_end)
            # Purchases sometimes follow the payments block without their own heading:
            # within that block the printed sign decides.
            group = section
            if section in ('credits', 'purchases'):
                group = 'credits' if minus else 'purchases'
            row = dict(date=iso(year, int(mo), int(dy)), description=description.strip(),
                       amount_minor=money_minor(amount), direction='credit' if minus else 'debit', group=group)
            if pm:
                row['posted_date'] = iso(year_for(int(pm), _shift(period.period_start, -60), period.period_end),
                                         int(pm), int(pd))
            rows.append(row)
    period.rows = rows
    groups = defaultdict(int)
    for r in rows:
        groups[r['group']] += r['amount_minor'] if r['direction'] == 'debit' else -r['amount_minor']
    if None not in summary.values():
        period.controls['other_checks'] = [
            dict(ok=-groups['credits'] == summary['payments'] + summary['credits'],
                 reason='credit rows differ from printed payments and credits'),
            dict(ok=groups['purchases'] == summary['purchases'], reason='purchase rows differ from printed purchases'),
            dict(ok=groups['advances'] == summary['advances'], reason='cash advance rows differ from printed cash advances'),
            dict(ok=groups['fees'] == summary['fees'], reason='fee rows differ from printed fees'),
            dict(ok=groups['interest'] == summary['interest'], reason='interest rows differ from printed interest'),
            dict(ok=period.controls.get('fees_total_line') in (None, summary['fees']),
                 reason='fee total line differs from the summary'),
            dict(ok=period.controls.get('interest_total_line') in (None, summary['interest']),
                 reason='interest total line differs from the summary')]
    for row in rows:
        row.pop('group', None)
    return period


# ---------------------------------------------------------------------------
# Andrews Federal Credit Union (scanned; the producer's OCR text layer)
# ---------------------------------------------------------------------------

_OCR_DIGIT = r'[\dOoIl]'
ANDREWS_TAIL = re.compile(r'(-\s?)?(' + _OCR_DIGIT + r'[\dOoIl,]*\s?[.,]\s?' + _OCR_DIGIT + r'\s?' + _OCR_DIGIT +
                          r')\s+(-\s?)?(' + _OCR_DIGIT + r'[\dOoIl,]*\s?[.,]\s?' + _OCR_DIGIT + r'\s?' + _OCR_DIGIT + r')$')
ANDREWS_SINGLE = re.compile(r'(-\s?)?(' + _OCR_DIGIT + r'[\dOoIl,]*\s?[.,]\s?' + _OCR_DIGIT + r'\s?' + _OCR_DIGIT + r')$')
ANDREWS_DATES = re.compile(r'^(\d{2})/(\d{2})/(\d{2})\s+(\d{2})/(\d{2})/(\d{2})$')


def ocr_money(text, negative=False):
    """An amount from an OCR layer: letters that stand for digits, spaces inside the number,
    and a comma printed for the decimal point. Returns minor units or None."""
    value = re.sub(r'\s', '', text).translate(str.maketrans('OoIl', '0011'))
    if re.fullmatch(r'\d[\d,]*,\d{2}', value) and not re.fullmatch(r'\d{1,3}(,\d{3})+', value):
        value = value[:-3] + '.' + value[-2:]
    if not re.fullmatch(r'\d{1,3}(,\d{3})*\.\d{2}|\d+\.\d{2}', value):
        return None
    minor = int(value.replace(',', '').replace('.', ''))
    return -minor if negative else minor


def parse_andrews(pages):
    statements, current = [], None
    for page in pages:
        head = page.lines[:16]
        dates = next((ANDREWS_DATES.match(l.text) for l in head if ANDREWS_DATES.match(l.text)), None)
        if dates is None or not any('Account Statement' in l.text for l in head):
            current = None  # not a statement page (application, signature card, notice)
            continue
        m1, d1, y1, m2, d2, y2 = map(int, dates.groups())
        key = (iso(2000 + y1, m1, d1), iso(2000 + y2, m2, d2))
        index = next(i for i, l in enumerate(head) if ANDREWS_DATES.match(l.text))
        number = head[index + 1].text.strip() if index + 1 < len(head) else ''
        body = index + 2 if number.isdigit() else index + 1
        number = int(number) if number.isdigit() else None
        member = next((m.group(1) for l in head for m in [re.search(r'\b(\d{9})\b', l.text)] if m), None)
        if current is None or current['key'] != key or number == 1 or current['member'] != member:
            current = dict(key=key, member=member, pages=[], numbers=[], continued=False)
            statements.append(current)
        current['pages'].append((page, body))
        current['numbers'].append(number)
    periods = []
    for statement in statements:
        periods.extend(_andrews_statement(statement))
    return periods


def _line_spacing(lines):
    gaps = sorted(b.top - a.top for a, b in zip(lines, lines[1:]) if b.top - a.top > 1)
    return gaps[len(gaps) // 2] if gaps else None


def _andrews_statement(statement):
    start, end = statement['key']
    numbers = statement['numbers']
    problems = []
    # OCR can lose a page-number line; every number that was read must sit in
    # its place. A page truly missing breaks the running balance or the ending.
    if any(n is not None and n != i + 1 for i, n in enumerate(numbers)) or numbers[0] not in (1, None):
        problems.append('statement page numbers not read in sequence')
    last_page = statement['pages'][-1][0]
    if any('Continued on following page' in l.text for l in last_page.lines):
        problems.append('last page says it continues')
    holder = None
    first_page, body = statement['pages'][0]
    lines = first_page.lines
    for i, line in enumerate(lines[:body + 8]):
        if re.match(r'^>\d+<$', line.text.strip()) and i + 1 < len(lines):
            holder = lines[i + 1].text.strip()
            break
    periods, period, row = [], None, None
    for page, body in statement['pages']:
        spacing = _line_spacing(page.lines[body:])
        previous_top = None
        for line in page.lines[body:]:
            t = line.text.strip()
            if 'Continued on following page' in t:
                break  # below it: page footer, not statement lines
            if re.fullmatch(r'[\d,.\s]+', t) and not re.search(r'\d{2}/\d{2}', t):
                continue  # scan control numbers in the footer
            if period is not None and not period.controls.get('closed') and previous_top is not None and spacing \
                    and line.top - previous_top > 2.2 * spacing:
                # A blank band inside a share section: the OCR layer may have lost lines there.
                period.problems.append('gap in the OCR text inside a share section')
            previous_top = line.top
            opened = re.match(r'^(\d{2})/(\d{2})\s+ID\s+([\dOo.\s]{4,6}?)\s+(.+?)\s+Previous\s+Balance\s+(.+)$', t)
            if opened:
                share = re.sub(r'\D', '', opened.group(3).translate(str.maketrans('Oo', '00')))
                period = Period(family='andrews-share', institution='Andrews Federal Credit Union', currency='USD',
                                holder=holder, account=statement['member'], period_start=start, period_end=end,
                                share=share if len(share) == 4 else None, pages=[p.number for p, _ in statement['pages']],
                                problems=list(problems))
                period.opening_minor = ocr_money(opened.group(5))
                if period.share is None:
                    period.problems.append('share id not read')
                if period.opening_minor is None:
                    period.problems.append('previous balance not read')
                periods.append(period)
                row = None
                continue
            if period is None:
                continue
            ending = re.match(r'^(\d{2})/(\d{2})\s+Ending\s+Balance\s+(.+)$', t)
            if ending:
                period.closing_minor = ocr_money(ending.group(3))
                if period.closing_minor is None:
                    period.problems.append('ending balance not read')
                period.controls['closed'] = True
                row = None
                continue
            if period.controls.get('closed'):
                continue
            dated = re.match(r'^(\d{2})/(\d{2})\s+(?:(\d{2})/(\d{2})\s+)?(.*)$', t)
            if not dated or not re.match(r'^(Deposit|Withdrawal|Recurring|Fee|Dividend|Transfer|Check|Draft|Loan|'
                                         r'Payment|Interest|Credit|Debit|ATM|POS|ACH|Share|Adjustment)', dated.group(5), re.I):
                if row is not None and len(row['description']) < 200:
                    row['description'] += ' ' + t
                continue
            body_text = dated.group(5)
            tail = ANDREWS_TAIL.search(body_text)
            if not tail:
                period.problems.append('movement line amount or balance not read')
                row = None
                continue
            amount = ocr_money(tail.group(2), negative=bool(tail.group(1)))
            balance = ocr_money(tail.group(4), negative=bool(tail.group(3)))
            if amount is None or balance is None or amount == 0:
                period.problems.append('movement line amount or balance not read')
                row = None
                continue
            month, day = int(dated.group(1)), int(dated.group(2))
            row = dict(date=iso(year_for(month, start, end), month, day),
                       description=body_text[:tail.start()].strip(), amount_minor=abs(amount),
                       direction='debit' if amount < 0 else 'credit', balance_after=balance)
            period.rows.append(row)
    for period in periods:
        if not period.controls.pop('closed', False):
            period.problems.append('no ending balance line')
    return periods


PARSERS = {
    'bbva-mexico': parse_bbva,
    'monex-mexico': parse_monex,
    'santander-mexico': parse_santander,
    'kapital-mexico': parse_kapital,
    'intercam-mexico': parse_kapital,
    'capital-one-card': parse_capital_one,
    'citibank': parse_citi,
    'andrews-share': parse_andrews,
}


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def document_truth(doc, docs_dir, cache_dir=None):
    """Private per-document result: status, issuer, periods (each with truth_status)."""
    result = dict(id=doc['id'], sha256=doc['sha256'], mode=doc.get('mode'), pages=doc.get('pages'),
                  inventory_family=doc.get('family'))
    if doc.get('hash') != 'verified':
        return dict(result, status='unavailable', reason='original not verified against evidence hash')
    if doc.get('mode') not in TEXT_MODES:
        return dict(result, status='needs_visual', reason=f"no usable text layer ({doc.get('mode')})")
    try:
        pages = read_pages(Path(docs_dir) / f"{doc['id']}.pdf", cache_dir)
    except Exception as error:
        return dict(result, status='unverified', reason=f'pdfplumber could not read: {type(error).__name__}')
    issuer = detect_issuer(pages)
    result['issuer'] = issuer
    result['text_pages'] = sum(1 for p in pages if p.text.strip())
    if not result['text_pages']:
        return dict(result, status='needs_visual', reason='the independent reader finds no text on any page')
    text = '\n'.join(p.text for p in pages)
    parser = PARSERS.get(issuer)
    if parser is None:
        form = next((name for name, pattern in NOT_STATEMENT_MARKS if re.search(pattern, text, re.I)), None)
        if form:
            return dict(result, status='not_statement', reason=form)
        statementish = re.search(r'estado de cuenta|statement|saldo|balance', text, re.I)
        if not statementish:
            return dict(result, status='not_statement', reason='no statement marks in the text layer')
        return dict(result, status='needs_parser', reason=f'no tier-A parser for issuer {issuer or "unknown"}')
    try:
        periods = parser(pages)
    except Exception as error:
        return dict(result, status='unverified', reason=f'parser error {type(error).__name__}',
                    trace=traceback.format_exc()[-2000:])
    textless = sum(1 for p in pages if not p.text.strip())
    ocr_pages = ocr_layer_pages(Path(docs_dir) / f"{doc['id']}.pdf") if doc.get('mode') in ('mixed', 'scan_text_layer') else set()
    out = []
    for index, period in enumerate(periods):
        status, reasons = reconcile(period)
        if status == 'verified' and ocr_pages & set(period.pages):
            # Reconciled, but read from a producer's OCR layer over a scan: a
            # consistent misread (amount, balance and ending together) cannot be
            # ruled out from that layer alone. Confirmed visually, not scored.
            status, reasons = 'ocr_reconciled', ['reconciled from an OCR text layer; needs visual confirmation']
        if status == 'incomplete' and set(period.page_sequence) and min(map(int, period.page_sequence)) > 1 \
                and not textless:
            # Printed page 1 is absent. When everything else reconciles, the
            # absent page may be the bank's numbered insert; it cannot be seen,
            # so the period is neither scored nor treated as a known hold.
            trial = Period(**{k: v for k, v in period.__dict__.items() if k != 'page_total'})
            if reconcile(trial)[0] == 'verified':
                status, reasons = 'unverified', ['printed page 1 absent; the rest reconciles']
        if status == 'incomplete' and textless:
            # The printed page is present as an image (or outlined text) rather
            # than missing: its facts need visual reading, not a hold.
            status, reasons = 'unverified', ['printed page without a text layer'] + reasons
        record = {k: v for k, v in period.__dict__.items()}
        record.update(id=f"{doc['id']}#{index + 1}", truth_status=status, truth_reasons=reasons,
                      expected=expected_outcome(period, status))
        out.append(record)
    statuses = Counter(p['truth_status'] for p in out)
    if not out:
        form = next((name for name, pattern in NOT_STATEMENT_MARKS if re.search(pattern, text, re.I)), None)
        if form:
            return dict(result, status='not_statement', reason=form)
        if issuer == 'bbva-mexico' and re.search(r'FONDOS DE INVERSI[OÓ]N', text):
            return dict(result, status='needs_parser', reason='BBVA investment fund statement (no tier-A parser)')
        status = 'unverified'
        result['reason'] = 'parser found no statement period'
    elif statuses.get('verified') == len(out):
        status = 'verified'
    elif statuses.get('verified'):
        status = 'partly_verified'
    elif statuses.get('ocr_reconciled'):
        status = 'ocr_reconciled'
    elif statuses.get('incomplete') == len(out):
        status = 'incomplete'
    else:
        status = 'unverified'
    if doc.get('mode') == 'mixed' and status != 'verified':
        result['image_pages'] = doc.get('page_kinds', {}).get('image_only', 0)
    return dict(result, status=status, periods=out, period_status=dict(statuses))


def ocr_layer_pages(path):
    """Physical page numbers that are a full-page image carrying a text layer (an OCR layer)."""
    import fitz
    from .real_inventory import classify_page
    with fitz.open(str(path)) as pdf:
        return {index + 1 for index, page in enumerate(pdf) if classify_page(page) == 'scan_text_layer'}


def mark_duplicates(results):
    """The same printed period (issuer, account, dates, balances) read from two documents."""
    seen = {}
    for result in sorted(results, key=lambda r: r['id']):
        for period in result.get('periods', []):
            if period['truth_status'] not in ('verified', 'ocr_reconciled'):
                continue
            key = (period['family'], period['account'], period['period_start'], period['period_end'],
                   period['opening_minor'], period['closing_minor'], len(period['rows']))
            if key in seen:
                period['duplicate_of'] = seen[key]
                period['expected'] = 'duplicate'
            else:
                seen[key] = period['id']


def manifest_period(period):
    return dict(id=period['id'], family=period['family'], institution=period['institution'],
                account=period['account'], account_printed=bool(period['account']),
                holder=period['holder'] or '', holder_printed=bool(period['holder']),
                currency=period['currency'], period_start=period['period_start'], period_end=period['period_end'],
                start_printed=bool(period['period_start']), opening_minor=period['opening_minor'],
                closing_minor=period['closing_minor'], expected=period['expected'], defects=[],
                notes='', share=period.get('share'), added_in='real', truth_status=period['truth_status'],
                duplicate_of=period.get('duplicate_of'),
                rows=[dict({k: v for k, v in r.items() if k in ('date', 'description', 'amount_minor', 'direction',
                                                                 'balance_after', 'posted_date')},
                           **({'date': None} if r.get('date_unprinted') else {})) for r in period['rows']])


def write_outputs(out, results, docs_dir):
    out = Path(out)
    (out / 'periods').mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    for result in results:
        (out / 'periods' / f"{result['id']}.json").write_text(json.dumps(result, indent=1, default=str) + '\n')
    files = []
    for result in sorted(results, key=lambda r: r['id']):
        periods = result.get('periods') or []
        if not any(p['truth_status'] in ('verified', 'ocr_reconciled') for p in periods):
            continue
        name = f"{result['id']}.pdf"
        link = out / name
        if not link.exists():
            link.symlink_to(Path(docs_dir).resolve() / name)
        files.append(dict(filename=name, sha256=result['sha256'], size=(Path(docs_dir) / name).stat().st_size,
                          pages=result['pages'], mode=result['mode'], periods=[manifest_period(p) for p in periods]))
    manifest = dict(version='real-tier-a', synthetic=False, files=files)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n')
    status = [dict(id=r['id'], status=r['status'], issuer=r.get('issuer'), inventory_family=r.get('inventory_family'),
                   mode=r.get('mode'), pages=r.get('pages'), reason=r.get('reason'),
                   period_status=r.get('period_status', {}),
                   period_reasons=dict(Counter(reason for p in r.get('periods', []) for reason in p['truth_reasons'])))
              for r in sorted(results, key=lambda r: r['id'])]
    (out / 'status.json').write_text(json.dumps(status, indent=1, sort_keys=True) + '\n')
    return manifest, status


VISUAL = ('needs_visual', 'needs_parser', 'unverified', 'partly_verified', 'ocr_reconciled', 'incomplete')
SHARD_SIZE = 40
SHARD_PAGES = 400  # a shard also closes at about this many pages (some documents run to hundreds)
POOL_BELOW = 10  # families with fewer documents share pooled shards


def _chunks(docs, size, pages):
    chunk, total = [], 0
    for doc in docs:
        if chunk and (len(chunk) >= size or total + (doc['pages'] or 0) > pages):
            yield chunk
            chunk, total = [], 0
        chunk.append(doc)
        total += doc['pages'] or 0
    if chunk:
        yield chunk


def visual_queue(results, size=SHARD_SIZE):
    """Documents whose truth still needs a person reading rendered pages, in shards by family.

    ``work`` per document: ``read`` (no usable text, no parser, or periods that
    did not reconcile) and/or ``confirm`` (periods reconciled from an OCR
    layer: the values are known and need visual confirmation).
    """
    entries = []
    for r in sorted(results, key=lambda r: r['id']):
        if r['status'] not in VISUAL:
            continue
        periods = r.get('periods') or []
        pending = [dict(id=p['id'], status=p['truth_status'], reasons=p['truth_reasons'][:4])
                   for p in periods if p['truth_status'] != 'verified']
        work = sorted({'confirm' if p['status'] == 'ocr_reconciled' else 'read' for p in pending}
                      or {'read'})
        family = (periods[0]['family'] if periods else r.get('issuer')) or (r.get('inventory_family') or 'unknown').rstrip('?')
        entries.append(dict(id=r['id'], family=family, status=r['status'], mode=r.get('mode'), pages=r.get('pages'),
                            reason=r.get('reason'), work=work, periods=pending))
    by_family = defaultdict(list)
    for entry in entries:
        by_family[entry['family']].append(entry)
    shards, pooled = [], []
    for family in sorted(by_family):
        docs = sorted(by_family[family], key=lambda e: (e['work'], e['id']))
        if len(docs) < POOL_BELOW:
            pooled.extend(docs)
            continue
        for part in _chunks(docs, size, SHARD_PAGES):
            shards.append(dict(families=[family], documents=part))
    for part in _chunks(sorted(pooled, key=lambda d: (d['family'], d['id'])), size, SHARD_PAGES):
        shards.append(dict(families=sorted({d['family'] for d in part}), documents=part))
    for number, shard in enumerate(shards, 1):
        shard.update(shard=f'v{number:02d}', count=len(shard['documents']),
                     pages=sum(d['pages'] or 0 for d in shard['documents']),
                     work=dict(Counter(w for d in shard['documents'] for w in d['work'])))
    return dict(shard_size=size, documents=len(entries), shards=shards)


def summarise(status):
    """Counts only."""
    by_family = defaultdict(Counter)
    periods = defaultdict(Counter)
    reasons = Counter()
    for row in status:
        family = row['issuer'] or (row['inventory_family'] or 'unknown').rstrip('?')
        by_family[family][row['status']] += 1
        periods[family].update(row['period_status'])
        reasons.update(row['period_reasons'])
    return dict(documents=dict(Counter(r['status'] for r in status)),
                documents_by_family={k: dict(v) for k, v in sorted(by_family.items())},
                periods_by_family={k: dict(v) for k, v in sorted(periods.items())},
                periods=dict(sum(periods.values(), Counter())), unverified_reasons=dict(reasons.most_common()))


def _work(args):
    doc, docs_dir, cache_dir = args
    try:
        return document_truth(doc, docs_dir, cache_dir)
    except Exception as error:
        return dict(id=doc['id'], sha256=doc['sha256'], status='unverified', mode=doc.get('mode'),
                    pages=doc.get('pages'), reason=f'error {type(error).__name__}', inventory_family=doc.get('family'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--docs', type=Path, help='private copies (default: <inventory dir>/docs)')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--cache', type=Path, help='private pdfplumber word cache directory')
    parser.add_argument('--only', help='comma-separated document ids (others reuse periods/<id>.json)')
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text())
    docs_dir = args.docs or args.inventory.parent / 'docs'
    only = set(args.only.split(',')) if args.only else None
    todo, results = [], []
    for doc in inventory['documents']:
        cached = args.out / 'periods' / f"{doc['id']}.json"
        if only is not None and doc['id'] not in only and cached.exists():
            results.append(json.loads(cached.read_text()))
        else:
            todo.append((doc, docs_dir, args.cache))
    todo.sort(key=lambda item: -(item[0].get('pages') or 0))
    with ProcessPoolExecutor(max_workers=max(1, min(args.jobs, 2))) as pool:
        for count, result in enumerate(pool.map(_work, todo, chunksize=1), 1):
            results.append(result)
            if count % 25 == 0:
                print(f'{count}/{len(todo)} documents read', flush=True)
    for result in results:  # recomputed every run, since it depends on all documents
        for period in result.get('periods', []):
            period.pop('duplicate_of', None)
            period['expected'] = expected_outcome(Period(**{k: period[k] for k in Period.__dataclass_fields__}),
                                                  period['truth_status'])
    mark_duplicates(results)
    _, status = write_outputs(args.out, results, docs_dir)
    queue = visual_queue(results)
    (args.out / 'visual-queue.json').write_text(json.dumps(queue, indent=1) + '\n')
    print('Visual queue: ' + json.dumps(dict(documents=queue['documents'], shards=[
        dict(shard=s['shard'], families=s['families'], count=s['count'], pages=s['pages'], work=s['work'])
        for s in queue['shards']])))
    print(json.dumps(summarise(status), indent=1))
    print('Truth written.')


if __name__ == '__main__':
    sys.exit(main())
