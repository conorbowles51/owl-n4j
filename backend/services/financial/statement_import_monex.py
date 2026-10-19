"""Banco Monex contract statements: one period per printed currency section.

Fitted to the two layouts Monex prints (both read from real productions):

* landscape ("Estado de Cuenta | Banco"): a cover with the contract, CLABE and
  period; a peso summary headed "Resumen Divisas Peso Mexicano al <date>"
  whose movements follow on the next pages; then one "Resumen cuenta /
  <currency> al <date>" page per other currency, its movements below it;
* portrait (2019-2021): every section headed "CUENTA VISTA <CURRENCY> al
  <date>", summary and movements on the same page.

Each section prints its own controls (Saldo inicial, + Total abonos /
+ ABONOS, - Total cargos / - CARGOS, Saldo vista / SALDO FINAL) and, when money
moved, a movement table bounded by printed "Saldo inicial:" and "Saldo final:"
lines. A movement line is the printed date followed, at its right, by exactly
six amounts: credit, debit, guarantee movement, guarantee (or unavailable)
balance, available balance and total balance. The total balance is the running
balance. Descriptions wrap over several lines around (landscape) or below
(portrait) the dated line and are joined to the nearest dated line.

The contract is established only when the printed CLABE carries the Monex bank
code (112) and the contract number, and every numbered page ("Hoja n de m") is
present. A section whose structure is not understood refuses the whole
contract. A value that is read but disagrees with another printed value (a
table endpoint against the summary, a line that cannot be placed) is proposed
as an unresolved line, so the period stays held for a person, never admitted.
Credit annexes, routing references, notices and tax certificates are not
account sections and contribute nothing.
"""
import re
from datetime import date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box, norm, text
from services.financial.statement_import_proposal import exact_amount

LAYOUT = 'monex-mexico-currency-summary'
MONTHS = {name: i for i, name in enumerate(('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO',
    'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'), 1)}
SHORT_MONTHS = dict(ENE=1, FEB=2, MAR=3, ABR=4, MAY=5, JUN=6, JUL=7, AGO=8, SEP=9, SET=9, OCT=10, NOV=11, DIC=12)
CURRENCIES = {'PESO MEXICANO': 'MXN', 'DOLAR AMERICANO': 'USD', 'EURO': 'EUR', 'EUROS': 'EUR',
    'LIBRA ESTERLINA': 'GBP', 'FRANCO SUIZO': 'CHF', 'DOLAR CANADA': 'CAD', 'DOLAR CANADIENSE': 'CAD',
    'DOLAR AUSTRALIANO': 'AUD', 'CORONA SUECA': 'SEK', 'YEN JAPONES': 'JPY'}
# The portrait layout prints a code under each section title; MXP is the
# pre-1993 peso code Monex still prints for pesos.
PRINTED_CODES = {'MXP': 'MXN', 'MXN': 'MXN', 'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP', 'CHF': 'CHF',
    'CAD': 'CAD', 'AUD': 'AUD', 'SEK': 'SEK', 'JPY': 'JPY'}
MONEX_BANK_CODE = '112'
AMOUNT = re.compile(r'-?\d{1,3}(?:,\d{3})*\.\d{2}|-?\d+\.\d{2}')
LEADING_AMOUNT = re.compile(r'(' + AMOUNT.pattern + r')(?:\s+\D.*)?')
ROW_DATE = re.compile(r'(\d{1,2})/([A-Z]{3})(?:\((\d{1,2})/([A-Z]{3})\))?')
CONTROL_LABELS = {'SALDO INICIAL:': 'opening', '+ TOTAL ABONOS:': 'credit', '+ ABONOS:': 'credit',
    '- TOTAL CARGOS:': 'debit', '- CARGOS:': 'debit', 'SALDO VISTA:': 'closing', 'SALDO FINAL:': 'closing',
    'SALDO TOTAL:': 'total'}
# Lines that end a currency section: other products and the closing pages.
TERMINATORS = ('ANEXO CREDITO', 'CREDITOS VIGENTES', 'DETALLE CREDITO', 'DETALLE DE CREDITO',
    'MOVIMIENTOS DEL CREDITO', 'MOVIMIENTOS SUBCUENTA', 'REFERENCIAS BANCARIAS', 'ESTIMADO CLIENTE',
    'COMPROBANTE FISCAL', 'AVISO DE SEGURIDAD')
# Words of the movement table's column headings (in any grouping the text
# layer produces).
HEADER_WORDS = {'FECHA', 'FECHAS', 'LIQUIDACION', '(PACTADA)', 'DESCRIPCION', 'REFERENCIA', 'ABONOS', 'CARGOS',
    'MOVIMIENTO', 'SALDO', 'EN', 'NO', 'GARANTIA', 'DISPONIBLE', 'TOTAL'}
FOOTER = re.compile(r'^(?:BANCO MONEX ?, S\.? ?A\.?|MONEX GRUPO FINANCIERO|AV\. PASEO DE LA REFORMA|'
                    r'CIUDAD DE MEXICO,? C\.P\.|WWW\.MONEX\.COM\.MX$)')


class NotUnderstood(Exception):
    """The printed structure differs from both known layouts: refuse the contract."""


# ---------------------------------------------------------------------------
# Lines and values
# ---------------------------------------------------------------------------

def _lines(items):
    """Located rows of one page in reading order, cells left to right."""
    located = []
    for s in items:
        for r in s['rows']:
            cells = [c for c in r['cells'] if c['expected_text'].strip()]
            if not cells:
                continue
            if any(box(c) is None for c in cells):
                raise NotUnderstood('unplaced cell')
            cells = sorted(cells, key=lambda c: box(c)[0])
            located.append(dict(source=s, row=r, cells=cells, top=min(box(c)[1] for c in cells),
                                words=[norm(c['expected_text']) for c in cells]))
    located.sort(key=lambda line: (line['top'], line['source']['table_index'], line['row']['row_index']))
    for line in located:
        line['text'] = ' '.join(line['words'])
    return located


def _address(line):
    return (line['source']['page_number'], line['source']['table_index'], line['row']['row_index'])


def _date_words(day, month, year):
    try:
        return date(int(year), MONTHS[month], int(day))
    except (KeyError, ValueError):
        return None


def _period(value):
    """'DEL 1 ENERO 2022 AL 31 ENERO 2022' or '1 AL 30 DE ABRIL DE 2019'."""
    value = re.sub(r'^PERIODO:?\s*', '', norm(value))
    m = re.fullmatch(r'DEL (\d{1,2}) (?:DE )?([A-Z]+) (?:DE )?(\d{4}) AL (\d{1,2}) (?:DE )?([A-Z]+) (?:DE )?(\d{4})', value)
    if m:
        start, end = _date_words(m[1], m[2], m[3]), _date_words(m[4], m[5], m[6])
    else:
        m = re.fullmatch(r'(?:DEL )?(\d{1,2}) AL (\d{1,2}) DE ([A-Z]+) DE (\d{4})', value)
        start, end = (_date_words(m[1], m[3], m[4]), _date_words(m[2], m[3], m[4])) if m else (None, None)
    if not start or not end or not 0 <= (end - start).days <= 62:
        return None
    return start.isoformat(), end.isoformat()


def _as_of(value):
    """A section's printed balance date: 'AL 31 ENERO 2022' or 'AL 30 DE ABRIL DE 2019'."""
    m = re.fullmatch(r'AL (\d{1,2}) (?:DE )?([A-Z]+) (?:DE )?(\d{4})', value)
    found = _date_words(m[1], m[2], m[3]) if m else None
    return found.isoformat() if found else None


def _amount_cell(cell):
    return bool(AMOUNT.fullmatch(cell['expected_text'].strip()))


def _value_text(cell):
    """The amount printed in a control's value cell (the portrait layout can
    merge the next label into the same cell: '51.99 SALDO PROMEDIO ...')."""
    m = LEADING_AMOUNT.fullmatch(cell['expected_text'].strip())
    return m[1] if m else None


def _row_date(value, start, end):
    """The printed day/month (the first one when two are printed) within the period."""
    m = ROW_DATE.fullmatch(value)
    if not m or m[2] not in SHORT_MONTHS:
        return None
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    found = []
    for year in range(first.year, last.year + 1):
        try:
            candidate = date(year, SHORT_MONTHS[m[2]], int(m[1]))
        except ValueError:
            continue
        if first <= candidate <= last:
            found.append(candidate.isoformat())
    return found[0] if len(found) == 1 else None


# ---------------------------------------------------------------------------
# Contract runs (cover + numbered pages)
# ---------------------------------------------------------------------------

def _labelled(lines, label):
    """Values printed after ``label`` on one line (as the next cell, or in the same cell)."""
    found = []
    for line in lines:
        for i, word in enumerate(line['words']):
            if word == label and i + 1 < len(line['cells']):
                found.append(line['cells'][i + 1]['expected_text'].strip())
            elif word.startswith(label + ' '):
                found.append(line['cells'][i]['expected_text'].strip()[len(label):].strip())
    return found


def _holder(lines):
    """The top line of the address block that ends with the postal code line."""
    postal = [(line, cell) for line in lines for cell, word in zip(line['cells'], line['words'])
              if re.fullmatch(r'C\.P\.:?(?: \d{5})?', word)]
    if len(postal) != 1:
        return ''
    line, cell = postal[0]
    x = box(cell)[0]
    block, top = [], line['top']
    for previous in reversed([l for l in lines if l['top'] < line['top']]):
        near = [c for c in previous['cells'] if abs(box(c)[0] - x) <= 8000]
        if not near:
            continue
        if top - previous['top'] > 25000:
            break
        block.insert(0, near[0]['expected_text'].strip())
        top = previous['top']
    return block[0] if block and re.search(r'[A-Za-z]{2}', block[0]) else ''


def _cover(lines):
    """(contract, start, end, holder) from a cover page, else None."""
    joined = '\n'.join(line['text'] for line in lines)
    if not all(label in joined for label in ('CONTRATO:', 'CTA. CLABE:', 'RFC TITULAR', 'PERIODO:')):
        return None
    contracts = {v for v in _labelled(lines, 'CONTRATO:') if re.fullmatch(r'\d{5,11}', v)}
    clabes = {re.sub(r'\s', '', v) for v in _labelled(lines, 'CTA. CLABE:')}
    periods = {p for v in _labelled(lines, 'PERIODO:') if (p := _period(v))}
    if len(contracts) != 1 or len(clabes) != 1 or len(periods) != 1:
        return None
    contract, clabe = next(iter(contracts)), next(iter(clabes))
    # A CLABE is bank (3) + branch (3) + account (11) + check digit: the bank
    # must be Monex and the account must be this contract.
    if not re.fullmatch(r'\d{18}', clabe) or clabe[:3] != MONEX_BANK_CODE or int(clabe[6:17]) != int(contract):
        return None
    start, end = next(iter(periods))
    return contract, start, end, _holder(lines)


def _page_number(lines):
    numbers = {(int(m[1]), int(m[2])) for line in lines for m in [re.fullmatch(r'HOJA (\d+) DE (\d+)', line['text'])] if m}
    return next(iter(numbers)) if len(numbers) == 1 else (None if not numbers else 'conflict')


def _tax_certificate(lines):
    content = [l['text'] for l in lines
               if not re.fullmatch(r'(?:MONEX ?)?(?:ESTADO DE CUENTA \| BANCO ?)?(?:CONTRATO: \d+)?', l['text'])]
    return bool(content) and content[0].startswith('COMPROBANTE FISCAL DIGITAL')


def _runs(pages):
    """Complete numbered contract runs: (first page, count, cover, lines by page).

    Every page after the cover prints "Hoja n de m", n rising by one per
    physical page. The cover is printed page 1, or page 2 when the production
    puts an unnumbered notice before it (the notice is then printed page 1 and
    belongs to the run). A page with no readable table (a blank page printed
    only with its number) is accepted between two correctly numbered pages:
    the PDF holds it, and any money on it would break the section controls.
    An unnumbered tax certificate inside the run is accepted the same way.
    """
    lines = {}
    for page, items in pages.items():
        try:
            lines[page] = _lines(items)
        except NotUnderstood:
            lines[page] = None
    runs, used = [], set()
    for cover_page in sorted(pages):
        if cover_page in used or lines[cover_page] is None or (cover := _cover(lines[cover_page])) is None:
            continue
        number = _page_number(lines[cover_page])
        if number == 'conflict' or (number is not None and number[0] != 1):
            continue
        offset, count = (1, number[1]) if number else (None, None)
        page, complete = cover_page + 1, True
        while count is None or page - cover_page + offset <= count:
            printed = _page_number(lines[page]) if lines.get(page) is not None else None
            if page in pages and lines[page] is None:
                complete = False
                break
            if printed is None:
                after = _page_number(lines[page + 1]) if lines.get(page + 1) is not None else None
                expected_after = None if offset is None else page + 1 - cover_page + offset
                certificate = page in pages and offset is not None and _tax_certificate(lines[page])
                blank = page not in pages and after not in (None, 'conflict') and after[0] == expected_after
                if not (certificate or blank) or count is None:
                    complete = False
                    break
                page += 1
                continue
            if printed == 'conflict':
                complete = False
                break
            if offset is None:
                offset = printed[0] - (page - cover_page)
                if offset not in (1, 2):
                    complete = False
                    break
            if printed[0] != page - cover_page + offset or (count is not None and printed[1] != count):
                complete = False
                break
            count = printed[1]
            if not 2 <= count <= 200:
                complete = False
                break
            if any(m and m[1] != cover[0] for line in lines[page] for m in [re.fullmatch(r'CONTRATO: (\d+)', line['text'])]):
                complete = False
                break
            page += 1
        if not complete or not count:
            continue
        first = cover_page - (offset - 1)
        if first not in pages or lines[first] is None or (first != cover_page and _page_number(lines[first]) is not None):
            continue
        last = cover_page + count - offset
        span = [p for p in range(first, last + 1) if p in pages]
        used.update(span)
        runs.append((first, last - first + 1, cover, {p: lines[p] for p in span}))
    return runs


# ---------------------------------------------------------------------------
# Currency sections
# ---------------------------------------------------------------------------

def _section_start(line, following):
    """(currency, as-of date, style) when ``line`` opens a currency section."""
    words = line['words']
    if 'RESUMEN DIVISAS' in words:
        i = words.index('RESUMEN DIVISAS')
        rest = words[i + 1:]
        if len(rest) == 2 and rest[0] in CURRENCIES:
            return CURRENCIES[rest[0]], _as_of(rest[1]), 'landscape'
        raise NotUnderstood('peso summary heading')
    if words == ['RESUMEN CUENTA'] and following is not None:
        if 'RESUMEN DIVISAS' in following['words']:
            return None
        nxt = following['words']
        if len(nxt) == 2 and nxt[0] in CURRENCIES:
            return CURRENCIES[nxt[0]], _as_of(nxt[1]), 'landscape'
        raise NotUnderstood('currency summary heading')
    if words and words[0].startswith('CUENTA VISTA ') and len(words) >= 2 and words[1].startswith('AL '):
        label = words[0][len('CUENTA VISTA '):]
        if label not in CURRENCIES:
            raise NotUnderstood('currency label')
        return CURRENCIES[label], _as_of(words[1]), 'portrait'
    return None


def _furniture(line, contract, in_table=False):
    """Page header and footer text; inside a movement table a lone word such
    as 'Cuenta' is part of a wrapped description, not a page heading."""
    t = line['text']
    return (t == 'ESTADO DE CUENTA | BANCO'
            or (not in_table and t in ('ESTADO DE CUENTA', 'BANCO', 'CUENTA', 'CUENTA VISTA', 'RESUMEN CUENTA'))
            or re.fullmatch(r'HOJA \d+ DE \d+', t) is not None or t == 'CONTRATO: ' + contract
            or FOOTER.match(t) is not None)


def _sections(run):
    """Every currency section of one contract run, parsed. Raises NotUnderstood."""
    first, count, (contract, start, end, holder), lines = run
    ordered = [line for page in sorted(lines) for line in lines[page]]
    sections, section = [], None
    for index, line in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        opened = _section_start(line, following)
        if opened:
            currency, as_of, style = opened
            if as_of != end:
                raise NotUnderstood('section date differs from the period end')
            section = dict(currency=currency, style=style, heading=line, lines=[line], controls={}, table=None,
                           page=line['source']['page_number'])
            sections.append(section)
            continue
        if any(line['text'].startswith(t) for t in TERMINATORS):
            section = None
            continue
        if section is None:
            if line['words'] and ROW_DATE.fullmatch(line['words'][0]) and sum(map(_amount_cell, line['cells'])) >= 2:
                raise NotUnderstood('dated line outside a currency section')
            continue
        section['lines'].append(line)
    if not sections or len({s['currency'] for s in sections}) != len(sections):
        raise NotUnderstood('no or repeated currency sections')
    for section in sections:
        _read_section(section, contract, start, end)
    # A currency the peso summary lists must have its own section: a section
    # page the reading lost cannot silently drop a period.
    if any(section.get('listed', set()) - {s['currency'] for s in sections} for section in sections):
        raise NotUnderstood('a listed currency has no section')
    return sections


def _header_columns(table, cells, page):
    """Credit and debit heading positions on one page (a continued table can
    sit a few points to the side on the next page). A heading merged with its
    neighbours ('Cargos Movimiento garantia') is placed by its share of the
    cell's characters; a heading printed alone is exact and always wins."""
    columns = table['columns'].setdefault(page, {})
    for cell in cells:
        value = cell['expected_text'].strip()
        rect = box(cell)
        for m in re.finditer(r'\S+', value):
            word = norm(m[0])
            if word not in ('ABONOS', 'CARGOS'):
                continue
            exact = norm(value) == word
            if not exact and columns.get(word, (None, False))[1]:
                continue
            place = rect if exact else [rect[0] + (rect[2] - rect[0]) * m.start() // len(value), rect[1],
                                        rect[0] + (rect[2] - rect[0]) * m.end() // len(value), rect[3]]
            columns[word] = (place, exact)


def _columns(table, page):
    """The credit and debit heading centres for a line on ``page`` (from that
    page's heading, else the nearest earlier page of the same table) and
    whether both headings were printed as cells of their own."""
    for candidate in sorted((p for p in table['columns'] if p <= page), reverse=True):
        found = table['columns'][candidate]
        if {'ABONOS', 'CARGOS'} <= set(found):
            return (_centre(found['ABONOS'][0]), _centre(found['CARGOS'][0]),
                    found['ABONOS'][1] and found['CARGOS'][1])
    return None


def _read_section(section, contract, start, end):
    table, phase = None, 'summary'
    for line in section['lines'][1:]:
        words, cells = line['words'], line['cells']
        if _furniture(line, contract, in_table=phase == 'open'):
            continue
        if phase == 'summary':
            if ROW_DATE.match(words[0]) and any(AMOUNT.search(w) for w in words[1:]):
                raise NotUnderstood('dated line outside the movement table')
            if words[0].startswith('MOVIMIENTOS'):
                phase, table = 'header', dict(columns={}, opening=None, closing=None, lines=[], start=line)
                continue
            if words[0] in CURRENCIES and len(cells) >= 5 and all(_amount_cell(c) for c in cells[1:5]):
                # The peso summary lists every other currency of the contract.
                section.setdefault('listed', set()).add(CURRENCIES[words[0]])
            for i, word in enumerate(words):
                role = CONTROL_LABELS.get(word)
                if role is None or i + 1 >= len(cells):
                    continue
                value = _value_text(cells[i + 1])
                if value is None:
                    raise NotUnderstood('control value')
                if role in section['controls']:
                    raise NotUnderstood('repeated control')
                section['controls'][role] = (line, cells[i + 1], value)
            continue
        if phase == 'closed':
            if words[0].startswith('MOVIMIENTOS') or (ROW_DATE.fullmatch(words[0]) and any(map(_amount_cell, cells))):
                raise NotUnderstood('movement line after the closed table')
            continue
        if words[0].startswith('MOVIMIENTOS'):
            continue  # a continuation page repeats the heading
        if all(w in HEADER_WORDS for w in line['text'].split()):
            _header_columns(table, cells, line['source']['page_number'])
            continue
        label = next((l for l in ('SALDO INICIAL:', 'SALDO FINAL:') if words[0] == l or words[0].startswith(l + ' ')), None)
        if label:
            # The text layer may merge the label and its amounts into one cell.
            tokens = (cells[0]['expected_text'].strip()[len(label):].split()
                      + [c['expected_text'].strip() for c in cells[1:]])
            if not 2 <= len(tokens) <= 3 or not all(AMOUNT.fullmatch(t) for t in tokens):
                raise NotUnderstood('table endpoint')
            if label == 'SALDO INICIAL:':
                if phase != 'header' or table['opening'] is not None:
                    raise NotUnderstood('table opening')
                table['opening'], phase = (line, tokens[-1]), 'open'
            else:
                if phase != 'open':
                    raise NotUnderstood('table closing')
                table['closing'], phase = (line, tokens[-1]), 'closed'
            continue
        if phase != 'open':
            raise NotUnderstood('line before the table opening')
        table['lines'].append(line)
    if phase not in ('summary', 'closed'):
        raise NotUnderstood('movement table not closed')
    if set(section['controls']) - {'total'} != {'opening', 'credit', 'debit', 'closing'}:
        raise NotUnderstood('currency summary controls')
    if table is not None:
        for line in table['lines']:
            if _columns(table, line['source']['page_number']) is None:
                raise NotUnderstood('movement columns')
    section['table'] = table


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def _contract_sections(sources):
    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).append(source)
    found = []
    for run in _runs(pages):
        try:
            sections = _sections(run)
        except NotUnderstood:
            continue
        found.append((run, sections, pages))
    return found


def monex_catalog(sources):
    groups, handled = [], set()
    for run, sections, pages in _contract_sections(sources):
        first, count, (contract, start, end, holder), _ = run
        all_items = [s for p in range(first, first + count) for s in pages.get(p, [])]
        for section in sections:
            identity = dict(layout_id=LAYOUT, institution='Monex', account_reference=contract,
                currency=section['currency'], period_start=start, period_end=end)
            scope = {}
            for line in section['lines']:
                page, table_index, row_index = _address(line)
                scope.setdefault((page, table_index), []).append(row_index)
            groups.append(dict(id=_digest(identity), **identity, account_type='checking', holder=holder,
                summary_page=section['page'], currency_source='printed_account_section',
                account_reference_kind='multi_currency_contract',
                section_sources=[dict(page_number=p, table_index=t, row_indices=sorted(r)) for (p, t), r in sorted(scope.items())],
                sources=[dict(page_number=s['page_number'], table_index=s['table_index'], source_revision=s['source_revision']) for s in all_items],
                page_numbers=list(range(first, first + count))))
        handled.update((s['page_number'], s['table_index']) for s in all_items)
    return groups, handled


def _chosen_section(sources, choice):
    for run, sections, _ in _contract_sections(sources):
        if run[2][0] != choice['account_reference'] or (run[2][1], run[2][2]) != (choice['period_start'], choice['period_end']):
            continue
        for section in sections:
            if section['currency'] == choice['currency']:
                return section
    return None


# ---------------------------------------------------------------------------
# Proposal
# ---------------------------------------------------------------------------

def _money(value, currency):
    negative = value.startswith('-')
    amount = exact_amount(value.lstrip('-'), currency)
    return str(-int(amount)) if negative and amount != '0' else amount


def propose_monex_statement(sources, currency, choice):
    section = _chosen_section(sources, choice)
    if section is None:
        raise ValueError('This currency section could not be read again. Review this statement again.')
    items, by_address = [], {}
    for source in sources:
        for raw in source['rows']:
            address = (source['page_number'], source['table_index'], raw['row_index'])
            item = dict(id=':'.join(map(str, address)), page_number=address[0], table_index=address[1], row_index=address[2],
                source_revision=source['source_revision'], source_cells=raw['cells'], fields={}, issues=[], excluded=True, kind='header')
            items.append(item)
            by_address[address] = item
    controls = section['controls']
    values = {}
    for role, (line, cell, value) in controls.items():
        item = by_address[_address(line)]
        try:
            values[role] = _money(value, currency)
        except ValueError as exc:
            values[role] = None
            if role != 'total':
                item['issues'].append(str(exc))
        if role == 'total':
            continue
        balance = role in ('opening', 'closing')
        item.update(kind='balance' if balance else 'statement_total')
        item['fields'].update(description=role.title() + ' Balance' if balance else 'Total ' + role,
            balance_column=str(cell['column_index']), balance=values[role] or '')
        if balance:
            item['fields']['standalone_balance'] = 'true'
        else:
            item['fields']['total_direction'] = role
    if 'total' in controls and values.get('total') != values.get('closing'):
        line = controls['total'][0]
        _unresolved(by_address[_address(line)], line, 'The summary prints a total balance that differs from the '
            'available balance. Check the PDF for investments or guarantees before importing this section.')
    table = section['table']
    if table is not None:
        _propose_table(section, table, by_address, values, currency, choice)
    return dict(rows=items, issues=[])


def _unresolved(item, line, message):
    item.update(kind='unresolved', excluded=False)
    item['fields'].setdefault('description', line['text'][:300] if line else '')
    item['issues'].append(message)


def _tokens(cells, dated_first):
    """Cells split where the text layer merged them: a leading row date, and a
    trailing run of amounts ('0.00 1,000,000.00', or text followed by its
    amounts). A split part keeps its source cell and a box proportional to its
    characters; the printed controls, not these positions, decide admission."""
    result = []
    for index, cell in enumerate(cells):
        value = cell['expected_text'].strip()
        spans = []
        rest = 0
        if index == 0 and dated_first:
            m = re.match(r'\d{1,2}/[A-Za-z]{3}(?:\(\d{1,2}/[A-Za-z]{3}\))?(?=\s|$)', value)
            if m:
                spans.append((m.start(), m.end()))
                rest = m.end()
        amounts = list(re.finditer(r'(?<!\S)(?:' + AMOUNT.pattern + r')(?!\S)', value[rest:]))
        trailing = []
        end = len(value)
        for m in reversed(amounts):
            if value[rest + m.end():end].strip():
                break
            trailing.insert(0, (rest + m.start(), rest + m.end()))
            end = rest + m.start()
        if value[rest:end].strip():
            text_start = rest + len(value[rest:end]) - len(value[rest:end].lstrip())
            spans.append((text_start, len(value[rest:end].rstrip()) + rest))
        spans += trailing
        if len(spans) <= 1:
            result.append(dict(text=value, cell=cell, box=box(cell), exact=True))
            continue
        x0, y0, x1, y1 = box(cell)
        for start, stop in spans:
            result.append(dict(text=value[start:stop], cell=cell, exact=False, box=[x0 + (x1 - x0) * start // len(value), y0,
                                                                                     x0 + (x1 - x0) * stop // len(value), y1]))
    return result


def _centre(rect):
    return (rect[0] + rect[2]) / 2


def _propose_table(section, table, by_address, values, currency, choice):
    # The table's printed endpoints must equal the currency summary's.
    for role, endpoint in (('opening', table['opening']), ('closing', table['closing'])):
        line, value = endpoint
        try:
            printed = _money(value, currency)
        except ValueError:
            printed = None
        if printed is None or printed != values.get(role):
            _unresolved(by_address[_address(line)], line, f'The movement table prints a different {role} balance from the '
                'currency summary. Compare both with the PDF before importing this section.')
    anchors, texts = [], []
    for line in table['lines']:
        item = by_address[_address(line)]
        first = line['cells'][0]['expected_text'].strip()
        dated = ROW_DATE.match(norm(first)) is not None and re.match(r'\d{1,2}/[A-Za-z]{3}(?:\(\d{1,2}/[A-Za-z]{3}\))?(?:\s|$)', first) is not None
        credit_x, debit_x, exact_headings = _columns(table, line['source']['page_number'])
        # Amounts right of the debit column are the guarantee and balance
        # columns; an amount left of the credit column is part of a description.
        boundary = debit_x + (debit_x - credit_x) / 2
        money_from = credit_x - (debit_x - credit_x)
        tokens = _tokens(line['cells'], dated)
        date_token = tokens.pop(0) if dated else None
        money = [t for t in tokens if AMOUNT.fullmatch(t['text']) and _centre(t['box']) >= money_from]
        if not money and not dated:
            texts.append(line)
            continue
        anchors.append((line, item))
        nearer_credit = lambda t: abs(_centre(t['box']) - credit_x) <= abs(_centre(t['box']) - debit_x)
        if len(money) == 6:
            # A complete line: credit, debit, guarantee movement, guarantee
            # (or unavailable) balance, available balance, total balance, in
            # printed order. Exact positions must also agree with the
            # headings; positions estimated inside a merged cell cannot, and
            # a swap there is caught by the printed totals and balances.
            movement, balances = money[:2], money[2:]
            credits, debits = [money[0]], [money[1]]
            exact = exact_headings and money[0]['exact'] and money[1]['exact']
            misplaced = exact and (not nearer_credit(money[0]) or nearer_credit(money[1]))
        else:
            movement = [t for t in money if _centre(t['box']) < boundary]
            balances = [t for t in money if _centre(t['box']) >= boundary]
            credits = [t for t in movement if nearer_credit(t)]
            debits = [t for t in movement if t not in credits]
            misplaced = len(credits) > 1 or len(debits) > 1
        if misplaced:
            _unresolved(item, line, 'The credit and debit columns of this movement line could not be placed. Compare it '
                'with the PDF and choose the amount and direction.')
            continue
        try:
            credit = int(_money(credits[0]['text'], currency)) if credits else 0
            debit = int(_money(debits[0]['text'], currency)) if debits else 0
        except ValueError as exc:
            _unresolved(item, line, str(exc))
            continue
        if not credit and not debit and (movement or balances):
            # A line without money in the credit or debit column (for example
            # interest net of its tax) is not a payment. Its balance columns
            # are not used: the section's printed totals, endpoints and the
            # running balance printed on every payment already fix the period.
            continue
        if credit < 0 or debit < 0 or (credit and debit) or len(balances) != 4 or not dated:
            _unresolved(item, line, 'This movement line could not be read completely. Compare it with the PDF and enter '
                'its date, amount and direction.')
            continue
        total_token = balances[-1]
        try:
            total = _money(total_token['text'], currency)
        except ValueError as exc:
            _unresolved(item, line, str(exc))
            continue
        fields = item['fields']
        item.update(kind='transaction', excluded=False)
        direction, token, amount = ('credit', credits[0], credit) if credit else ('debit', debits[0], debit)
        fields.update(direction=direction, amount_minor=str(amount), balance=total,
            date_column=str(date_token['cell']['column_index']), balance_column=str(total_token['cell']['column_index']))
        fields[direction + '_column'] = str(token['cell']['column_index'])
        day = _row_date(norm(date_token['text']), choice['period_start'], choice['period_end'])
        if day:
            fields['date'] = day
        else:
            item['issues'].append('Check this payment date against the printed statement period.')
        middle = [t for t in tokens if t not in money and t['box'][0] < money[0]['box'][0]]
        reference = re.fullmatch(r'(?:(.*\S)\s+)?(\d{1,20})', middle[-1]['text']) if middle else None
        if reference and (reference[1] is None or len(reference[2]) >= 5):
            fields['bank_reference'] = reference[2]
            middle = middle[:-1] + ([dict(middle[-1], text=reference[1])] if reference[1] else [])
        fields['description'] = ' '.join(t['text'] for t in middle)
        if middle:
            fields['description_column'] = str(middle[0]['cell']['column_index'])
    owners = _description_owners(section['style'], anchors, texts)
    anchor_of = {id(i): a for a, i in anchors}
    parts = {}
    for line in texts:
        owner = owners.get(id(line))
        if owner is None or owner['kind'] != 'transaction':
            continue
        anchor = anchor_of[id(owner)]
        page = line['source']['page_number']
        joined = ' '.join(c['expected_text'].strip() for c in line['cells'])
        above = (page, line['top']) < (anchor['source']['page_number'], anchor['top'])
        parts.setdefault(id(owner), []).append((above, (page, line['top']), joined))
        by_address[_address(line)]['fields']['parent_transaction_id'] = owner['id']
        owner.setdefault('continuation_sources', []).append(dict(page_number=page, table_index=line['source']['table_index'],
            row_index=line['row']['row_index'], source_cells=line['row']['cells']))
    for _, item in anchors:
        if item['kind'] != 'transaction':
            continue
        fields = item['fields']
        found = sorted(parts.get(id(item), []), key=lambda p: p[1])
        fields['description'] = ' '.join([p[2] for p in found if p[0]] + ([fields['description']] if fields.get('description') else [])
                                         + [p[2] for p in found if not p[0]]).strip()
        if not fields['description']:
            item['issues'].append('Check the payment description.')


def _description_owners(style, anchors, texts):
    """Which dated line each wrapped description line belongs to.

    Portrait: a description starts on its dated line and continues below it.
    Landscape: the dated line is printed vertically centred on its
    description, so on each page the lines between two dated lines are split
    to make every block as symmetric as possible (fewest lines out of
    balance, then the split at the widest vertical space). Lines at the top
    of a continuation page may end the previous page's last block.
    """
    owners = {}
    item_of = {id(a): i for a, i in anchors}
    everything = sorted(texts + [a for a, _ in anchors], key=lambda l: (l['source']['page_number'], l['top']))
    if style == 'portrait':
        current = None
        for line in everything:
            if id(line) in item_of:
                current = item_of[id(line)]
            elif current is not None:
                owners[id(line)] = current
        return owners
    previous_last = None
    for page in sorted({l['source']['page_number'] for l in everything}):
        sequence = [l for l in everything if l['source']['page_number'] == page]
        marks = [n for n, l in enumerate(sequence) if id(l) in item_of]
        if not marks:
            for line in sequence:
                if previous_last is not None:
                    owners[id(line)] = previous_last
            continue
        bounds = [-1] + marks
        gaps = [list(range(bounds[j] + 1, bounds[j + 1])) for j in range(len(marks))]
        tail = list(range(marks[-1] + 1, len(sequence)))

        def space(j, s):
            """Vertical space at the split point of gap j after s lines go up."""
            members = gaps[j]
            upper = sequence[members[s - 1]] if s else (sequence[marks[j - 1]] if j else None)
            lower = sequence[members[s]] if s < len(members) else sequence[marks[j]]
            return (lower['top'] - upper['top']) if upper is not None else 0

        # best[s] = (imbalance, -space) of the best splits of gaps 0..j with s lines of gap j going up.
        choices0 = [0] if previous_last is None else range(len(gaps[0]) + 1)
        best = {s: ((0, -space(0, s)), [s]) for s in choices0}
        for j in range(1, len(marks)):
            following = {}
            for s in range(len(gaps[j]) + 1):
                options = []
                for prior, (cost, path) in best.items():
                    above = len(gaps[j - 1]) - prior
                    options.append(((cost[0] + abs(above - s), cost[1] - space(j, s)), path + [s]))
                following[s] = min(options, key=lambda o: o[0])
            best = following
        final = min(((cost[0] + abs(len(gaps[-1]) - s - len(tail)), cost[1]), path) for s, (cost, path) in best.items())
        splits = final[1]
        for j, members in enumerate(gaps):
            up = members[:splits[j]]
            for n in up:
                owners[id(sequence[n])] = item_of[id(sequence[marks[j - 1]])] if j else previous_last
            for n in members[splits[j]:]:
                owners[id(sequence[n])] = item_of[id(sequence[marks[j]])]
        for n in tail:
            owners[id(sequence[n])] = item_of[id(sequence[marks[-1]])]
        previous_last = item_of[id(sequence[marks[-1]])]
    return owners


def monex_no_activity_evidence(sources, choice, rows, currency):
    """A currency summary's printed zero + Total abonos / - Total cargos prove it quiet.

    A movement table whose lines all carry zero credits and debits (interest
    net of its tax) does not move the balance; any line with money in the
    credit or debit column is a proposed row, which leaves this question
    unasked.
    """
    from services.financial.statement_printed_no_activity import zero_totals_evidence

    def guard():
        # A dated line with money outside a movement table refuses the whole
        # contract (_read_section), and every table line with money is
        # proposed as a payment or an unresolved line, so the section must
        # still be read as before.
        if _chosen_section(sources, choice) is None:
            return ('section_unread', 'This currency section could not be read again. Check the page before confirming that it contains no transactions.')
        return None

    return zero_totals_evidence(rows, choice, currency, family='monex-mexico', guard=guard)
