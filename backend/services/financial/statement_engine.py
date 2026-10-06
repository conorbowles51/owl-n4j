"""General statement engine: reads statement layouts no family reader was written for.

Built from the rules the family readers already solve (see
docs/financial-workflows/statement-engine-knowledge.md). It contains no
institution names and no per-family branches: printed wording lives in
``statement_engine_vocabulary`` (one data table) and anything institution
specific belongs to a library profile (``statement_engine_profiles``) or a
family reader.

How a period is read
--------------------
* Every table cell is split into located tokens (a merged cell keeps exact
  edges for its first and last word; inner words get estimated positions).
* Pages are grouped into statements by their printed period (A1, A2), split
  where printed page numbering restarts, and into account sections where a
  new opening balance follows a closing one (A7).
* Controls are read as label + value pairs whose label is the WHOLE printed
  text before the value (D1-D5). Movement lines start with a printed date and
  carry money (E1-E3); lines without date and money continue a description.
* Money columns are found from the right edges of amounts (E2). Their roles
  (credit, debit, signed amount, running balance, ignored) are CHOSEN BY PROOF:
  every assignment the printed headings allow is tried with every printed
  opening/closing candidate, under the convention the statement prints
  (asset balance, or amounts owed when card wording is printed, C5).

Fail closed (D8)
----------------
A period is proved only if opening + credits - debits = closing to the cent
AND (the running balance chain holds on every printed balance OR printed
totals exist and every one matches) AND every printed total and count that was
read matches. Two different readings that both prove are held. A period that
is not proved is returned with its best reading and a named reason; the reason
is carried by an unresolved line so the existing review gate holds it.
"""
import re
from contextvars import ContextVar
from datetime import date, timedelta
from functools import lru_cache
from itertools import product

from services.financial.pdf_candidates import _digest
from services.financial.statement_engine_vocabulary import (
    ACCOUNT_LABELS, CURRENCY_LABELS, CURRENCY_NAMES, COLUMN_INDEX, HOLDER_LABELS, INDEX, INSTITUTION_WORDS,
    LIABILITY_EVIDENCE, MONTHS, PAGE_NUMBERING, PERIOD_WORDS, UNDATED_CHARGES, FUZZY_INDEX, fold, label)

LAYOUT = 'generic'
# The library profile applied to the current reading (None for the plain engine).
_PROFILE = ContextVar('statement_engine_profile', default=None)
ENGINE_VERSION = 'statement-engine-v1'
MAX_ASSIGNMENTS = 4000
MAX_PERIOD_DAYS = 95

HOLD_MESSAGES = {
    'no_period': 'The printed statement period could not be read.',
    'no_movements_or_controls': 'No printed balances or movement lines were found for this period.',
    'no_opening': 'The opening balance could not be read.',
    'no_closing': 'The closing balance could not be read.',
    'no_geometry': 'The page positions needed to separate the amount columns are missing.',
    'separators_mixed': 'Amounts are printed with both decimal-point and decimal-comma conventions.',
    'date_unresolved': 'A movement date could not be placed in the printed period.',
    'date_order_ambiguous': 'The day and month order of the printed dates could not be established.',
    'unplaced_money_line': 'A line with an amount could not be placed in the movement columns.',
    'too_many_interpretations': 'The amount columns allow too many interpretations to check.',
    'not_reconciled': 'No reading of the amount columns reconciles the opening and closing balances.',
    'no_independent_control': 'The balances reconcile, but no running balance or printed total confirms the movement lines.',
    'printed_total_differs': 'A printed total or count differs from the movement lines read.',
    'two_readings': 'Two different readings of the amount columns both reconcile.',
    'pages_missing': 'The printed page numbering shows missing pages.',
    'route_library_first': 'This layout is routed to the bank-specific reader library first.',
    'library_disagrees': 'The general reader and the bank-specific reader both reconcile this period but read it differently.',
}


# ---------------------------------------------------------------------------
# Located tokens
# ---------------------------------------------------------------------------

def _rect(cell):
    locator = cell.get('locator') or {}
    rect, size = locator.get('rect'), locator.get('page_size')
    if (not isinstance(rect, list) or len(rect) != 4 or not all(type(v) is int for v in rect)
            or not rect[0] < rect[2] or not rect[1] < rect[3]):
        return None, None
    width = size[0] if isinstance(size, list) and len(size) == 2 and type(size[0]) is int and size[0] > 0 else None
    return rect, width


_SIGN_ONLY = re.compile(r'^(?:-|−|\$|US\$|€|£|¥|MN|M\.N\.|MXN|USD|EUR|DLS|CR)$')


def _cell_tokens(cell):
    rect, width = _rect(cell)
    if rect is None:
        return None, None
    lines = cell['expected_text'].split('\n')
    count = len(lines)
    tokens = []
    for index, line in enumerate(lines):
        words = [(m.start(), m.end(), m.group()) for m in re.finditer(r'\S+', line)]
        if not words:
            continue
        start, end = words[0][0], words[-1][1]
        span = max(end - start, 1)
        y0 = rect[1] + (rect[3] - rect[1]) * index / count
        y1 = rect[1] + (rect[3] - rect[1]) * (index + 1) / count
        merged = []
        for s, e, word in words:
            # A detached sign or currency marker belongs to the amount beside it (C2, C4).
            if merged and _SIGN_ONLY.fullmatch(merged[-1][2]) and merged[-1][2] not in ('CR',) and re.match(r'[\d($€£¥]', word):
                ps, _, pw = merged.pop()
                merged.append((ps, e, pw + word))
            elif merged and word in ('-', '−', 'CR') and re.search(r'\d\)?$', merged[-1][2]):
                ps, _, pw = merged.pop()
                merged.append((ps, e, pw + word))
            else:
                merged.append((s, e, word))
        for s, e, word in merged:
            exact = count == 1 and len(merged) == 1
            x0 = rect[0] + (rect[2] - rect[0]) * (s - start) / span
            x1 = rect[0] + (rect[2] - rect[0]) * (e - start) / span
            tokens.append(dict(t=word, f=fold(word), x0=x0, x1=x1, y0=y0, y1=y1, cell=cell, exact=exact,
                               first=s == start, last=e == end, line=index))
    return tokens, width


def _pages(sources):
    """Rows of every page in reading order, each with its located tokens."""
    pages = {}
    for source in sources:
        for raw in source['rows']:
            tokens, width, located = [], None, True
            for cell in raw['cells']:
                cell_tokens, cell_width = _cell_tokens(cell)
                if cell_tokens is None:
                    if cell['expected_text'].strip():
                        located = False
                    continue
                width = width or cell_width
                tokens.extend(cell_tokens)
            if not tokens:
                if raw['cells'] and not located:
                    pages.setdefault(source['page_number'], []).append(dict(
                        page=source['page_number'], source=source, raw=raw, tokens=[], y0=None, width=None,
                        located=False, text=' '.join(c['expected_text'] for c in raw['cells'])))
                continue
            tokens.sort(key=lambda t: (t['line'], t['x0']))
            pages.setdefault(source['page_number'], []).append(dict(
                page=source['page_number'], source=source, raw=raw, tokens=tokens,
                y0=min(t['y0'] for t in tokens), width=width, located=located,
                text=' '.join(t['t'] for t in tokens)))
    for rows in pages.values():
        rows.sort(key=lambda r: (r['y0'] if r['y0'] is not None else float('inf'), r['source']['table_index'],
                                 r['raw']['row_index']))
    return pages


# ---------------------------------------------------------------------------
# Values: money, dates
# ---------------------------------------------------------------------------

_DOT = re.compile(r'^(?P<lead>[-−+(]?)\s*(?:US\$|\$|€|£|¥)?\s*(?P<lead2>[-−]?)(?P<int>\d{1,3}(?:,\d{3})+|\d+)\.(?P<frac>\d{2})'
                  r'(?P<trail>\)|-|−|CR)?(?:MN|M\.N\.|MXN|USD|EUR|DLS)?$')
_COMMA = re.compile(r'^(?P<lead>[-−+(]?)\s*(?:US\$|\$|€|£|¥)?\s*(?P<lead2>[-−]?)(?P<int>\d{1,3}(?:\.\d{3})+|\d+),(?P<frac>\d{2})'
                    r'(?P<trail>\)|-|−|CR)?(?:MN|M\.N\.|MXN|USD|EUR|DLS)?$')
_WHOLE = re.compile(r'^(?P<lead>[-−+(]?)\s*(?:US\$|\$|€|£|¥)?\s*(?P<lead2>[-−]?)(?P<int>\d{1,3}(?:,\d{3})+|\d+)'
                    r'(?P<trail>\)|-|−|CR)?(?:MN|M\.N\.|MXN|USD|EUR|DLS)?$')
_UNAMBIGUOUS_DOT = re.compile(r'\d\.\d{2}(?:\D|$)')
_UNAMBIGUOUS_COMMA = re.compile(r'\d,\d{2}(?:\D|$)')


def separator_style(pages):
    """'dot' or 'comma' decimals for the whole document (C1); None when mixed."""
    dot = comma = 0
    for rows in pages.values():
        for row in rows:
            for token in row['tokens']:
                text = token['t']
                if _DOT.fullmatch(text) and _UNAMBIGUOUS_DOT.search(text) and not re.search(r'\d\.\d{3}', text):
                    dot += 1
                elif _COMMA.fullmatch(text) and _UNAMBIGUOUS_COMMA.search(text) and not re.search(r'\d,\d{3}', text):
                    comma += 1
    if dot and comma:
        return 'dot' if dot >= 20 * comma else 'comma' if comma >= 20 * dot else None
    return 'comma' if comma else 'dot'


def money(text, style, exponent=2):
    """Signed minor units of one printed amount token, or None."""
    if exponent == 0:
        # Whole-unit currencies (yen) may print ".00": accepted only when the fraction is zero (C3).
        printed = (_DOT if style == 'dot' else _COMMA).fullmatch(text) if style else None
        if printed and printed['frac'] == '00':
            text = text[:printed.start('frac') - 1] + text[printed.end('frac'):]
        match = _WHOLE.fullmatch(text)
    else:
        match = (_DOT if style == 'dot' else _COMMA).fullmatch(text)
    if not match or (exponent == 0 and style is None):
        return None
    lead, lead2, trail = match['lead'], match['lead2'], match['trail'] or ''
    if (lead == '(') != (trail == ')'):
        return None
    markers = (lead in ('-', '−')) + (lead2 in ('-', '−')) + (trail in ('-', '−', 'CR')) + (lead == '(')
    if markers > 1:
        return None
    digits = match['int'].replace(',', '').replace('.', '')
    # Printed amounts carry no leading zeros; zero-padded numbers are references (C1).
    if len(digits) > 1 and digits[0] == '0' or len(digits) > 13:
        return None
    frac = match.groupdict().get('frac') or ''
    if exponent and len(frac) != exponent:
        return None
    value = int(digits + frac) if exponent else int(digits)
    return -value if markers else value


def _is_count(text):
    return bool(re.fullmatch(r'\d{1,5}', text))


_NUM_DATE = re.compile(r'^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2}|\d{4}))?$|^(\d{1,2})\.(\d{1,2})\.(\d{4})$')
_ISO_DATE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
_NAME_DATE = re.compile(r'^(\d{1,2})[/ .-]?([A-Z]{3,10})\.?(?:[/ .-]?(\d{2}|\d{4}))?$')
_NAME_FIRST = re.compile(r'^([A-Z]{3,10})\.?[/ .-]?(\d{1,2}),?(?:[/ .-]?(\d{4}))?$')


def _dnorm(text):
    """Upper case without accents, punctuation kept (dates need their separators)."""
    import unicodedata
    upper = ''.join(c for c in unicodedata.normalize('NFKD', text.upper()) if not unicodedata.combining(c))
    return ' '.join(upper.replace('–', '-').replace('−', '-').split())


@lru_cache(maxsize=262144)
def _date_parts(text):
    """Possible (day, month, year|None, order) readings of one date token."""
    f = _dnorm(text).strip(',.:;')
    if m := _ISO_DATE.fullmatch(f):
        return [(int(m[3]), int(m[2]), int(m[1]), 'iso')]
    if m := _NUM_DATE.fullmatch(f):
        a, b, y = (int(m[1]), int(m[2]), m[3]) if m[1] else (int(m[4]), int(m[5]), m[6])
        year = (2000 + int(y) if len(y) == 2 else int(y)) if y else None
        return [(a, b, year, 'dmy'), (b, a, year, 'mdy')]
    if (m := _NAME_DATE.fullmatch(f)) and m[2] in MONTHS:
        y = m[3]
        return [(int(m[1]), MONTHS[m[2]], (2000 + int(y) if y and len(y) == 2 else int(y)) if y else None, 'name')]
    if (m := _NAME_FIRST.fullmatch(f)) and m[1] in MONTHS:
        return [(int(m[2]), MONTHS[m[1]], int(m[3]) if m[3] else None, 'name')]
    return []


@lru_cache(maxsize=262144)
def is_date_token(text):
    return any(1 <= d <= 31 and 1 <= mth <= 12 for d, mth, _, _ in _date_parts(text))


def _calendar(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


# Full dates for the printed period (B1): numeric with year, or with a month name.
_FULL = (r'(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[/.-][A-Z]{3,10}[/.-]\d{2,4}'
         r'|\d{1,2}\s+(?:DE\s+)?[A-Z]{3,10}\.?\s+(?:DE\s+|DEL\s+)?\d{4}|[A-Z]{3,10}\.?\s+\d{1,2},?\s+\d{4}'
         r'|\d{1,2}[/.-]\d{1,2}[/.-]\d{2})')
_RANGE = re.compile(r'(?:^|\b)(' + _FULL + r')\s*(?:AL|A|-|TO|THROUGH|THRU|HASTA)\s+(' + _FULL + r')(?:\b|$)')
_RANGE_TIGHT = re.compile(r'(' + _FULL + r')\s*-\s*(' + _FULL + r')')
# "03 FEB 26/27 FEB 26": two day-month-year dates joined by a slash.
_SLASH_RANGE = re.compile(r'\b(\d{1,2}\s+[A-Z]{3,10}\.?\s+\d{2}(?:\d{2})?)\s*/\s*(\d{1,2}\s+[A-Z]{3,10}\.?\s+\d{2}(?:\d{2})?)\b')
_SHARED_MONTH = re.compile(r'\b(\d{1,2})\s+AL\s+(\d{1,2})\s+DE\s+([A-Z]{3,10})\s+(?:DE\s+|DEL\s+)?(\d{4})\b')


def _full_date(text, order):
    f = ' '.join(_dnorm(text).replace(' DE ', ' ').replace(' DEL ', ' ').split())
    if m := re.fullmatch(r'(\d{1,2})\s+([A-Z]{3,10})\.?\s+(\d{4})', f):
        return _calendar(int(m[3]), MONTHS.get(m[2], 0), int(m[1])) if m[2] in MONTHS else None
    if m := re.fullmatch(r'([A-Z]{3,10})\.?\s+(\d{1,2}),?\s+(\d{4})', f):
        return _calendar(int(m[3]), MONTHS.get(m[1], 0), int(m[2])) if m[1] in MONTHS else None
    options = [(d, mth, y) for d, mth, y, kind in _date_parts(f) if y and (kind in ('iso', 'name') or kind == order or order is None)]
    found = {_calendar(y, mth, d) for d, mth, y in options} - {None}
    return found.pop() if len(found) == 1 else None


def period_ranges(text, order=None):
    """(start, end) ranges printed in one line of text (B1, B3)."""
    f = re.sub(r'[^A-Z0-9/.,\- ]+', ' ', _dnorm(text))
    found = []
    for pattern in (_RANGE, _RANGE_TIGHT):
        for m in pattern.finditer(f):
            options = set()
            for choice in ([order] if order else ['dmy', 'mdy']):
                start, end = _full_date(m[1], choice), _full_date(m[2], choice)
                if start and end and start <= end and (end - start).days <= MAX_PERIOD_DAYS:
                    options.add((start, end))
            if len(options) == 1:
                found.append(options.pop())
    for m in _SLASH_RANGE.finditer(f):
        dates = []
        for part in (m[1], m[2]):
            d, month, year = part.split()[0], part.split()[1].rstrip('.'), part.split()[2]
            year = int(year) + (2000 if len(year) == 2 else 0)
            dates.append(_calendar(year, MONTHS.get(month, 0), int(d)) if month in MONTHS else None)
        if all(dates) and dates[0] <= dates[1] and (dates[1] - dates[0]).days <= MAX_PERIOD_DAYS:
            found.append(tuple(dates))
    for m in _SHARED_MONTH.finditer(f):
        if m[3] in MONTHS:
            start = _calendar(int(m[4]), MONTHS[m[3]], int(m[1]))
            end = _calendar(int(m[4]), MONTHS[m[3]], int(m[2]))
            if start and end and start <= end:
                found.append((start, end))
    return sorted(set(found))


# ---------------------------------------------------------------------------
# Label + value pairs
# ---------------------------------------------------------------------------

def _value_kind(token, style, exponent):
    if money(token['t'], style, exponent) is not None and (exponent or re.search(r'\d', token['t'])):
        if exponent == 0 and _is_count(token['t']) and not token.get('money_column'):
            return 'count'
        return 'money'
    if _is_count(token['t']):
        return 'count'
    if is_date_token(token['t']):
        return 'date'
    return None


_DATE_START = re.compile(r'^(?:\d{1,2}[,.]?|[A-Za-z]{3,10}\.?)$')


def merged_dates(tokens):
    """Tokens in reading order with a date printed as two or three words ("Dec 4", "4 ENE 2024") joined (B1, B2)."""
    key = id(tokens)
    cached = _MERGED.get(key)
    if cached is not None and cached[0] is tokens:
        return cached[1]
    ordered = sorted(tokens, key=lambda t: (t['line'], t['x0']))
    result, index = [], 0
    while index < len(ordered):
        token = ordered[index]
        joined = None
        if not _DATE_START.match(token['t']) or index + 1 >= len(ordered):
            result.append(token)
            index += 1
            continue
        for size in (3, 2):
            group = ordered[index:index + size]
            if len(group) < size or len({t['line'] for t in group}) != 1 or len({id(t['cell']) for t in group}) > size:
                continue
            text = ' '.join(t['t'] for t in group)
            if re.search(r'[A-Za-z]', text) and is_date_token(text) and not is_date_token(group[0]['t']) or (
                    size == 3 and is_date_token(text) and _date_parts(text) and _date_parts(text)[0][2]):
                joined = dict(token, t=text, f=fold(text), x1=group[-1]['x1'], last=group[-1]['last'],
                              exact=False, parts=group)
                index += size
                break
        if joined is None:
            result.append(token)
            index += 1
        else:
            result.append(joined)
    if len(_MERGED) > 200000:
        _MERGED.clear()
    _MERGED[key] = (tokens, result)
    return result


_MERGED = {}


def label_pairs(row, style, exponent):
    """[(folded label, [value tokens])] read left to right on one row.

    A label restarts where a new cell begins after a clear horizontal gap: one
    printed row can hold two side-by-side blocks, and only the words right
    before a value are its label.
    """
    pairs, words, values = [], [], []
    previous = None
    width = row.get('width') or 1
    for token in merged_dates(row['tokens']):
        kind = _value_kind(token, style, exponent)
        if kind == 'date' or ' ' in token['t'] and is_date_token(token['t']):
            continue
        if kind in ('money', 'count'):
            values.append((kind, token))
            previous = token
            continue
        if not label(token['t']):
            # Printed signs between a label and its value ("=", "+") are neither.
            continue
        if values:
            pairs.append((label(' '.join(words)), values))
            words, values = [], []
        elif (words and previous is not None and token['cell'] is not previous['cell']
              and token['line'] == previous['line'] and token['x0'] - previous['x1'] > 0.015 * width):
            pairs.append((label(' '.join(words)), []))
            words = []
        words.append(token['t'])
        previous = token
    if words or values:
        pairs.append((label(' '.join(words)), values))
    return pairs


def _control_value(tokens):
    """The value of a labelled control. One amount is its value; a line printing several
    (a table's endpoint line repeats every column) carries the balance in its rightmost one."""
    return max(tokens, key=lambda t: t['x1']) if len(tokens) > 1 else tokens[0]


def _profile_role(text, liability):
    profile = _PROFILE.get()
    if not profile:
        return None
    for role, phrases in (profile.get('labels') or {}).items():
        if role.endswith('_component') and not liability:
            continue
        if text in {label(p) for p in phrases}:
            return role
    return None


def column_role(text):
    """A movement-heading word's role: the shared vocabulary, then the active profile's words."""
    role = COLUMN_INDEX.get(text)
    profile = _PROFILE.get()
    if role is None and profile:
        role = next((r for r, words in (profile.get('columns') or {}).items() if text in {label(w) for w in words}), None)
    return role


def _role_of(text, liability):
    extra = _profile_role(text, liability)
    if extra:
        return extra
    if liability:
        # Card summaries print components per direction, not one total (D7).
        if text in INDEX['credit_component']:
            return 'credit_component'
        if text in INDEX['debit_component']:
            return 'debit_component'
    for role in ('opening', 'closing', 'subtotal', 'column_total', 'credit_total', 'debit_total'):
        if text in INDEX[role]:
            return role
    for role in ('opening', 'closing', 'subtotal', 'credit_total', 'debit_total'):
        if any(pattern.fullmatch(text) for pattern in FUZZY_INDEX[role]):
            return role
    return None


# ---------------------------------------------------------------------------
# Page facts: period, account, numbering, currency, institution, holder
# ---------------------------------------------------------------------------

def _row_is_movement(row, style, exponent):
    tokens = merged_dates(row['tokens'])
    if not tokens:
        return False
    if not is_date_token(tokens[0]['t'].rstrip('.,')):
        return False
    return any(_value_kind(t, style, exponent) == 'money' for t in tokens)


def page_facts(rows, style, exponent=2):
    facts = dict(periods=set(), labelled_periods=set(), accounts={}, numbering=set(), currencies=set(),
                 liability=False, legal=set(), holders=set())
    for row in rows:
        if not row['tokens']:
            continue
        text = row['text']
        folded = fold(text)
        movement = _row_is_movement(row, style, exponent)
        if not movement:
            ranges = period_ranges(text)
            if ranges:
                facts['periods'].update(ranges)
                if any(word in folded.split() or folded.startswith(word) for word in PERIOD_WORDS):
                    facts['labelled_periods'].update(ranges)
        for m in PAGE_NUMBERING.finditer(folded):
            facts['numbering'].add((int(m[1]), int(m[2])))
        if any(phrase in folded for phrase in (fold(p) for p in LIABILITY_EVIDENCE)):
            facts['liability'] = True
        if not movement:
            _accounts(row, facts['accounts'])
            _currency(row, facts['currencies'])
            if any(word in folded for word in INSTITUTION_WORDS) and 6 <= len(folded) <= 160:
                facts['legal'].add(folded)
            _holder_label(row, facts['holders'])
    return facts


_ACCOUNT_VALUE = re.compile(r'^(?:\*{2,}|X{2,}|#)?[\d][\d -]{3,30}\d$|^(?:\*{2,}|X{2,})\d{3,6}$')


def _accounts(row, found):
    cells = [c['expected_text'] for c in row['raw']['cells']]
    texts = [' '.join(cells)] + cells
    for text in texts:
        # A vertically merged label column is zipped with its values elsewhere.
        if '\n' in text:
            continue
        folded = fold(text)
        for name, rank in ACCOUNT_LABELS:
            key = fold(name)
            m = re.match(r'^' + re.escape(key) + r'\s*(?:NO\.?\s*)?:?\s*(.+)$', folded)
            if not m:
                continue
            value = m[1].strip()
            # "Account number ending in 1234"
            ending = re.fullmatch(r'(?:ENDING IN|TERMINACION|TERMINA EN)\s*:?\s*(\d{4})', value)
            if ending:
                found.setdefault('****' + ending[1], set()).add(rank)
                break
            first = value.split()[0] if value.split() else ''
            candidate = value if _ACCOUNT_VALUE.fullmatch(value) else first if _ACCOUNT_VALUE.fullmatch(first) else ''
            digits = re.sub(r'\D', '', candidate)
            if candidate and 6 <= len(digits) <= 20 or candidate.startswith(('*', 'X')):
                found.setdefault(candidate.replace(' ', ''), set()).add(rank)
            break
    # Label cell followed by a value cell on the same row.
    raw = row['raw']['cells']
    for index, cell in enumerate(raw[:-1]):
        folded = label(cell['expected_text'])
        for name, rank in ACCOUNT_LABELS:
            if folded == label(name):
                value = raw[index + 1]['expected_text'].strip()
                digits = re.sub(r'\D', '', value)
                if _ACCOUNT_VALUE.fullmatch(value) and 6 <= len(digits) <= 20:
                    found.setdefault(value.replace(' ', ''), set()).add(rank)
                break


def _zipped_labels(source_rows):
    """Values of a vertically merged label column (A6): 'L1\\nL2\\nL3' beside rows of values."""
    pairs = []
    for index, row in enumerate(source_rows):
        cells = row['cells']
        if not cells:
            continue
        labels = cells[0]['expected_text'].split('\n')
        if len(labels) < 2:
            continue
        right = [c['expected_text'].strip() for r in source_rows[index:index + len(labels) + 1]
                 for c in r['cells'] if c['column_index'] > cells[0]['column_index']]
        right = [v for value in right for v in value.split('\n')]
        if len(right) == len(labels):
            pairs.extend((label(name), value) for name, value in zip(labels, right))
    return pairs


def _currency(row, found):
    pairs = label_pairs(row, 'dot', 2)
    folded = fold(row['text'])
    for name in CURRENCY_LABELS:
        key = fold(name)
        m = re.match(r'^(?:.*\s)?' + re.escape(key) + r'\s*:?\s+(.+)$', folded)
        if m:
            value = m[1].strip()
            for size in (3, 2, 1):
                head = ' '.join(value.split()[:size])
                if head in CURRENCY_NAMES:
                    found.add(CURRENCY_NAMES[head])
                    break
    del pairs


_US_ADDRESS = re.compile(r'\b(?:A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\s+\d{5}(?:\s?-?\s?\d{4})?\b')
_PESO_MARKERS = re.compile(r'\b(?:MXN|MXP|M\.N\.|MONEDA NACIONAL|PESOS?|C\.P\.|DOLARES|DIVISA|MONEDA)\b')


def _us_dollars(rows):
    """'$' amounts on a statement addressed in the United States, with no peso or other-currency wording (C2).

    The dollar sign alone is ambiguous (MXN prints it too). US card and bank
    statements print a US mailing address (state + ZIP); Mexican statements
    print C.P. codes and peso wording, which refuse this rule.
    """
    dollars = us = False
    for row in rows:
        text = fold(row['text']) if row['tokens'] else ''
        if _PESO_MARKERS.search(text) or re.search(r'[€£¥]', row['text']):
            return False
        dollars = dollars or '$' in row['text']
        us = us or bool(_US_ADDRESS.search(text))
    return dollars and us


def _section_holder(section_pages, pages, facts):
    """Holder from the statement's heading pages only (A8): up to the first page printing the period.

    Legal pages print other people's names under the same labels (a complaints
    officer as "Titular"), so labels elsewhere never count. A labelled name and
    the addressee block that disagree give no holder (a person decides).
    """
    heading = []
    for page in section_pages[:3]:
        heading.append(page)
        if facts[page]['periods']:
            break
    labelled = set()
    for page in heading:
        for row in pages[page]:
            if row['tokens'] and len(row['text']) <= 160:
                _holder_label(row, labelled)
    addressed = ''
    for page in heading:
        addressed = address_holder(pages[page])
        if addressed:
            break
    if len(labelled) > 1:
        return ''
    if labelled:
        name = next(iter(labelled))
        if addressed and fold(addressed) not in fold(name) and fold(name) not in fold(addressed):
            return ''
        return name
    return addressed


_HEADING_CURRENCIES = sorted(CURRENCY_NAMES, key=len, reverse=True)


def _heading_currencies(rows, style):
    """Currencies named in a section's own heading lines (no money, before its first movement) (A7, C2)."""
    found = set()
    for row in rows:
        if not row['tokens']:
            continue
        if _row_is_movement(row, style, 2):
            break
        if any(_value_kind(t, style, 2) == 'money' for t in row['tokens']):
            continue
        text = ' ' + fold(row['text']) + ' '
        for name in _HEADING_CURRENCIES:
            if ' ' + name + ' ' in text and (' ' in name or fold(row['text']).split()[-1:] == [name]
                                              or fold(row['text']).split()[:1] == [name]):
                found.add(CURRENCY_NAMES[name])
                break
    return found


def _holder_label(row, found):
    cells = row['raw']['cells']
    joined = ' '.join(c['expected_text'].strip() for c in cells)
    for name in HOLDER_LABELS:
        m = re.match(r'^\s*' + re.escape(name) + r'\s*:\s*(.{3,120})$', fold(joined))
        if m:
            # Keep the printed text (not folded) of the value.
            raw = re.split(r':\s*', joined, maxsplit=1)
            if len(raw) == 2 and raw[1].strip():
                found.add(' '.join(raw[1].split()))
    for index, cell in enumerate(cells[:-1]):
        if label(cell['expected_text']) in {label(n) for n in HOLDER_LABELS}:
            value = ' '.join(cells[index + 1]['expected_text'].split())
            if 3 <= len(value) <= 120 and re.search(r'[A-Za-z]', value):
                found.add(value)


_POSTAL = re.compile(r'(?:\bC\.?\s?P\.?\s*\d{5}\b|\b\d{5}(?:-\d{4})?\s*$|^\d{5}\s)')


def address_holder(rows):
    """The top line of the left address block ending with a postal-code line (A8)."""
    located = [r for r in rows if r['tokens'] and r['width']]
    if not located:
        return ''
    found = []
    for index, row in enumerate(located):
        if not _POSTAL.search(fold(row['text'])):
            continue
        x = min(t['x0'] for t in row['tokens'])
        block = [row]
        for earlier in reversed(located[:index]):
            ex = min(t['x0'] for t in earlier['tokens'])
            if abs(ex - x) > row['width'] * 0.015 or earlier['y0'] > block[-1]['y0']:
                continue
            # The issuer's own legal-name or heading line above is not part of the addressee block.
            first_words = fold(' '.join(t['t'] for t in earlier['tokens'] if t['x0'] < x + row['width'] * 0.45))
            if any(word in first_words for word in INSTITUTION_WORDS) or 'ESTADO DE CUENTA' in first_words or 'STATEMENT' in first_words:
                break
            gap = block[-1]['y0'] - earlier['y0']
            height = max(t['y1'] - t['y0'] for t in block[-1]['tokens'])
            if gap > height * 2.2:
                break
            block.append(earlier)
            if len(block) >= 7:
                break
        if 3 <= len(block) <= 7:
            top = block[-1]
            name = ' '.join(t['t'] for t in sorted(top['tokens'], key=lambda t: t['x0'])
                            if t['x0'] < x + row['width'] * 0.45)
            if (re.search(r'[A-Za-z]{2}', name) and not re.search(r'\d', name) and len(name.split()) >= 2
                    and not any(word in fold(name) for word in ('BANCO', 'BANK', 'ESTADO DE CUENTA', 'STATEMENT'))):
                found.append((top['y0'], name))
    # The addressee block is the topmost one; a second (fiscal) address block below it is not the holder.
    return min(found)[1] if found else ''


def _institution(legal_by_page):
    """A legal-name furniture line repeated on most pages (A9), short form before its first comma."""
    counts = {}
    for lines in legal_by_page:
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
    pages = len(legal_by_page)
    best = [line for line, count in counts.items() if count >= max(1, (pages + 1) // 2)
            and re.search(r'\b(?:S\.?\s?A\.?|N\.?\s?A\.?|INC\.?|INSTITUCION DE BANCA MULTIPLE|CREDIT UNION|BANK|BANCO)\b', line)]
    names = set()
    for line in best:
        short = line.split(',')[0].strip(' .')
        if 3 <= len(short) <= 80 and any(word in short or word in line for word in INSTITUTION_WORDS):
            names.add(short)
    return next(iter(names)) if len(names) == 1 else ''


# ---------------------------------------------------------------------------
# Statements and sections
# ---------------------------------------------------------------------------

def _segments(pages, facts):
    """[(period or None, [page numbers])]: a new printed period, or numbering restarting at 1, starts a segment."""
    segments = []
    for page in sorted(pages):
        f = facts[page]
        period = None
        candidates = f['labelled_periods'] or f['periods']
        if len(candidates) == 1:
            period = next(iter(candidates))
        restart = any(n == 1 for n, _ in f['numbering'])
        current = segments[-1] if segments else None
        if (current is None or (period and current['period'] and period != current['period'])
                or (restart and current['pages'] and any(facts[p]['numbering'] for p in current['pages']))):
            current = dict(period=period, pages=[], conflict=len(candidates) > 1)
            segments.append(current)
        elif period and not current['period']:
            current['period'] = period
        current['pages'].append(page)
        current['conflict'] = current['conflict'] or (len(candidates) > 1 and not f['labelled_periods'])
    return segments


def _numbering_complete(pages, facts):
    """Printed page numbers (A3) must leave no gap.

    Unnumbered pages (covers, notices, reverse sides) are extra pages; they may
    stand in for a number only where they physically sit in the gap.
    """
    expected, loose, total = 1, 0, None
    for page in pages:
        numbers = facts[page]['numbering']
        if len(numbers) > 1:
            return False
        if not numbers:
            loose += 1
            continue
        number, count = next(iter(numbers))
        if total is not None and count != total:
            return False
        total = count
        if number < expected or number - expected > loose or number > count:
            return False
        expected, loose = number + 1, 0
    return total is None or total - (expected - 1) <= loose


_READINGS = {}


def read_statements(sources, *, profile=None):
    """Every statement section the engine finds, proved or not.

    A reading depends only on the stored sources (their revisions), so the
    last few documents' readings are kept: proposing each period re-reads the
    whole document, never a subset of its pages.
    """
    key = (tuple((s['page_number'], s['table_index'], s.get('source_revision'),
                  hash(tuple((c['expected_text'], tuple((c.get('locator') or {}).get('rect') or ()))
                             for r in s['rows'] for c in r['cells']))) for s in sources),
           profile and profile.get('name'))
    if all(k[2] for k in key[0]) and key in _READINGS:
        return _READINGS[key]
    token = _PROFILE.set(profile)
    try:
        result = _read_statements(sources, profile=profile)
    finally:
        _PROFILE.reset(token)
    if all(k[2] for k in key[0]):
        if len(_READINGS) >= 8:
            _READINGS.pop(next(iter(_READINGS)))
        _READINGS[key] = result
    return result


def _read_statements(sources, *, profile=None):
    pages = _pages(sources)
    if not pages:
        return []
    style = separator_style(pages)
    facts = {page: page_facts(rows, style or 'dot') for page, rows in pages.items()}
    by_source = {}
    for source in sources:
        by_source.setdefault(source['page_number'], []).append(source)
    for page, items in by_source.items():
        for source in items:
            for name, value in _zipped_labels(source['rows']):
                for account_label, rank in ACCOUNT_LABELS:
                    if name == label(account_label) and _ACCOUNT_VALUE.fullmatch(value.strip()):
                        facts.setdefault(page, page_facts([], 'dot'))['accounts'].setdefault(value.strip().replace(' ', ''), set()).add(rank)
                for period in period_ranges(name + ' ' + value) or period_ranges(value):
                    if name in {label(w) for w in PERIOD_WORDS} or 'PERIODO' in name or 'PERIOD' in name:
                        facts[page]['labelled_periods'].add(period)
                        facts[page]['periods'].add(period)
    statements = []
    for segment in _segments(pages, facts):
        ordered = [row for page in segment['pages'] for row in pages[page]]
        mentions = []
        for position, row in enumerate(ordered):
            row['_seg'] = position
            if row['tokens'] and not _row_is_movement(row, style or 'dot', 2):
                named = set()
                _currency(row, named)
                named |= _heading_currencies([row], style or 'dot')
                mentions.extend((position, code) for code in named)
        segment['currency_mentions'] = mentions
        sections = _sections(segment, pages, style or 'dot')
        page_use = {}
        for section in sections:
            for page in {row['page'] for row in section}:
                page_use[page] = page_use.get(page, 0) + 1
        read = []
        for section in sections:
            shared = any(page_use[row['page']] > 1 for row in section)
            read.append(_read_section(section, segment, pages, facts, style, sources, profile, shared=shared))
        if len(read) > 1:
            # A section with no movement, zero balances and no currency or account of its own is not a
            # period anyone could act on (annex and reference pages print zero lines too).
            read = [st for st in read if not _empty_section(st)] or read[:1]
        statements.extend(read)
    return statements


def _empty_section(statement):
    rows = statement['_rows']
    if any(r['kind'] == 'transaction' for r in rows) or statement['engine']['proved']:
        return False
    balances = [r['fields'].get('balance') for r in rows if r['kind'] in ('balance', 'statement_total')]
    return (not statement['currency'] and not statement['account_reference']
            and all(value in (None, '0') for value in balances))


def _sections(segment, pages, style):
    """Split a segment at an opening balance that follows a closing balance and movement lines (A7)."""
    rows = [row for page in segment['pages'] for row in pages[page]]
    sections, current, closed, moved, after_close = [], [], False, False, None
    for row in rows:
        pairs = [(text, values) for text, values in label_pairs(row, style, 2) if values]
        roles = {_role_of(text, False) for text, values in pairs}
        new_opening = {money(_control_value([t for kind, t in values if kind == 'money'])['t'], style)
                       for text, values in pairs if _role_of(text, False) == 'opening'
                       and any(kind == 'money' for kind, _ in values)}
        if 'opening' in roles and closed and current and (moved or not new_opening <= _endpoints(current, style)['opening']):
            # Lines printed after the closing balance (the next section's heading) open the next section.
            carried = current[after_close:] if after_close is not None else []
            sections.append(current[:after_close] if after_close is not None else current)
            current, closed, moved, after_close = list(carried), False, False, None
        current.append(row)
        if 'closing' in roles:
            closed = True
            after_close = len(current)
        elif _row_is_movement(row, style, 2):
            moved = True
            after_close = None
    if current:
        sections.append(current)
    # A section without movement lines that only repeats the previous
    # section's printed balances is a second summary of that section.
    merged = []
    for section in sections:
        if merged and not any(_row_is_movement(r, style, 2) for r in section):
            previous, here = _endpoints(merged[-1], style), _endpoints(section, style)
            if here['opening'] and here['closing'] and here['opening'] <= previous['opening'] and here['closing'] <= previous['closing']:
                merged[-1] = merged[-1] + section
                continue
        merged.append(section)
    return merged


def _endpoints(rows, style):
    found = dict(opening=set(), closing=set())
    for row in rows:
        for text, values in label_pairs(row, style, 2):
            role = _role_of(text, False)
            if role in found and any(kind == 'money' for kind, _ in values):
                found[role].add(money(_control_value([t for kind, t in values if kind == 'money'])['t'], style))
    return found


def _fingerprint(header_words, columns, labels_seen, convention):
    return _digest(dict(engine=ENGINE_VERSION, header=sorted(header_words), labels=sorted(labels_seen),
                        columns=[round(c / 0.02) for c in columns], convention=convention))[:16]


def _read_section(rows, segment, pages, facts, style, sources, profile, shared=False):
    """One account section. ``shared``: another section is printed on one of its pages, so
    page-level facts (account, currency) cannot be attributed to it; only facts printed
    inside its own rows count (A6, A7, C2)."""
    section_pages = sorted({row['page'] for row in rows})
    f = [facts[p] for p in section_pages]
    accounts = {}
    if shared:
        own = {}
        for row in rows:
            if row['tokens'] and not _row_is_movement(row, style or 'dot', 2):
                _accounts(row, own)
        accounts = own
    else:
        for item in f:
            for value, ranks in item['accounts'].items():
                accounts.setdefault(value, set()).update(ranks)
    account = ''
    if accounts:
        top = max(max(r) for r in accounts.values())
        best = {v for v, r in accounts.items() if top in r}
        account = next(iter(best)) if len(best) == 1 else ''
    # The section's own heading area: everything before its first movement line.
    head = []
    for row in rows:
        if row['tokens'] and _row_is_movement(row, style or 'dot', 2):
            break
        head.append(row)
        # A section's heading area also ends at its own closing balance (later pages are not its heading).
        if row['tokens'] and any(_role_of(text, False) == 'closing' for text, values in label_pairs(row, style or 'dot', 2) if values):
            break
    own_currencies = set()
    for row in head:
        if row['tokens']:
            _currency(row, own_currencies)
    headings = _heading_currencies(head, style or 'dot')
    if own_currencies:
        currencies = own_currencies
    elif headings:
        currencies = headings
    elif shared:
        currencies = set()
    else:
        currencies = set().union(*(item['currencies'] for item in f))
    currency = next(iter(currencies)) if len(currencies) == 1 else ''
    currency_basis = 'printed_account_section' if currency else ''
    if not currency and not shared and _us_dollars(rows):
        currency, currency_basis = 'USD', 'dollar_us_address'
    from services.financial.money import get_currency, MoneyError
    try:
        exponent = get_currency(currency).exponent if currency else 2
    except MoneyError:
        exponent = 2
    liability = any(item['liability'] for item in f)
    if profile and profile.get('convention'):
        liability = profile['convention'] == 'liability_owed'
    if profile and profile.get('currency') and not currency and not shared:
        currency, currency_basis = profile['currency'], 'library_profile'
        try:
            exponent = get_currency(currency).exponent
        except MoneyError:
            exponent = 2
    # The holder belongs to the statement, printed on its first pages, for every one of its sections.
    holder = _section_holder(segment['pages'], pages, facts)
    institution = _institution([item['legal'] for item in f]) or (profile or {}).get('institution', '')
    period = segment['period']
    statement = dict(layout_id=LAYOUT, institution=institution, account_reference=account,
                     period_start=period[0].isoformat() if period else '', period_end=period[1].isoformat() if period else '',
                     holder=holder, currency=currency,
                     # A shared page cannot lend its currency to this section: an unread one stays unread.
                     currency_source=currency_basis or ('printed_account_section' if shared else ''),
                     account_type='credit_card' if liability else 'checking',
                     balance_convention='liability_owed' if liability else 'asset_balance',
                     page_numbers=section_pages)
    statement['sources'] = [dict(page_number=s['page_number'], table_index=s['table_index'],
                                 source_revision=s['source_revision'])
                            for s in sources if s['page_number'] in section_pages]
    # Sections can share a page: the rows, not the page, bound this period's import and overlap checks.
    scope = {}
    for row in rows:
        scope.setdefault((row['page'], row['source']['table_index']), []).append(row['raw']['row_index'])
    statement['section_sources'] = [dict(page_number=page, table_index=table, row_indices=sorted(indices))
                                    for (page, table), indices in sorted(scope.items())]
    reading = _reading(rows, statement, style, exponent, liability, period)
    statement.update(id=_digest(dict(layout_id=LAYOUT, account=account, start=statement['period_start'],
                                     end=statement['period_end'], currency=currency, first_page=section_pages[0],
                                     first_row=reading['first_row'])),
                     layout_fingerprint=reading['fingerprint'], engine=reading['proof'])
    if profile:
        statement['engine_profile'] = profile['name']
    if not _numbering_complete(segment['pages'], facts) and reading['proof']['proved']:
        reading['proof'].update(proved=False, reason='pages_missing')
    if segment.get('conflict') and reading['proof']['proved']:
        reading['proof'].update(proved=False, reason='no_period')
    if not period and reading['proof']['proved']:
        reading['proof'].update(proved=False, reason='no_period')
    named = {code for _, code in segment.get('currency_mentions', [])}
    if len(named) > 1:
        # Several currencies are printed in this statement: the section's own is the nearest one
        # named inside the section above its opening balance; otherwise it stays unread (C2, A7).
        opening = next((r for r in reading['rows'] if r['kind'] == 'balance'
                        and r['fields'].get('description') == 'Opening Balance'), None)
        rows_by_id = {(r['page'], r['source']['table_index'], r['raw']['row_index']): r for r in rows}
        anchor = rows_by_id.get((opening['page_number'], opening['table_index'], opening['row_index'])) if opening else None
        start, stop = rows[0]['_seg'], (anchor['_seg'] if anchor else rows[-1]['_seg'])
        own = [code for position, code in segment['currency_mentions'] if start <= position <= stop]
        attributed = own[-1] if own and len(set(own[-1:])) == 1 else ''
        if attributed != currency:
            statement.update(currency=attributed, currency_source='printed_account_section')
            try:
                new_exponent = get_currency(attributed).exponent if attributed else 2
            except MoneyError:
                new_exponent = 2
            if new_exponent != exponent:
                reading = _reading(rows, statement, style, new_exponent, liability, period)
                statement.update(layout_fingerprint=reading['fingerprint'], engine=reading['proof'])
            statement['id'] = _digest(dict(layout_id=LAYOUT, account=account, start=statement['period_start'],
                                           end=statement['period_end'], currency=attributed, first_page=section_pages[0],
                                           first_row=reading['first_row']))
    statement['_rows'] = reading['rows']
    return statement


# ---------------------------------------------------------------------------
# Reading one section: controls, movements, columns, proof
# ---------------------------------------------------------------------------

def _resolve_dates(movements, period, liability):
    """Row date (and a second printed date) for every movement, or a named failure (B2-B4)."""
    if not period:
        return None, 'no_period'
    start, end = period
    low = start - timedelta(days=31 if liability else 0)
    orders = set()
    for move in movements:
        for token in move['date_tokens']:
            for d, mth, y, kind in _date_parts(token['t']):
                if kind in ('dmy', 'mdy') and (d > 12) != (mth > 12) and 1 <= d <= 31 and 1 <= mth <= 12:
                    orders.add(kind)
    fixed = (_PROFILE.get() or {}).get('date_order')
    if fixed and not orders - {fixed}:
        orders = {fixed}
    choices = [orders.pop()] if len(orders) == 1 else (['dmy', 'mdy'] if not orders else [])
    if not choices:
        return None, 'date_order_ambiguous'
    results = []
    for order in choices:
        resolved, ok = [], True
        for move in movements:
            dates = []
            for token in move['date_tokens']:
                found = set()
                for d, mth, y, kind in _date_parts(token['t']):
                    if kind in ('dmy', 'mdy') and kind != order:
                        continue
                    years = [y] if y else range(low.year, end.year + 1)
                    for year in years:
                        day = _calendar(year, mth, d)
                        if day and low <= day <= end:
                            found.add(day)
                if len(found) != 1:
                    ok = False
                    break
                dates.append(found.pop())
            if not ok:
                break
            resolved.append(dates)
        if ok:
            results.append(resolved)
    if not results:
        return None, 'date_unresolved'
    if len(results) > 1 and any(a != b for a, b in zip(results[0], results[1])):
        return None, 'date_order_ambiguous'
    return results[0], None


def _columns(tokens, width):
    """Right-edge bands of money tokens (E2), as fractions of the page width."""
    edges = sorted((t['x1'] / (t['_width'] or width)) for t in tokens if t['exact'] or t['last'])
    if not edges:
        edges = sorted(t['x1'] / (t['_width'] or width) for t in tokens)
    bands = []
    for edge in edges:
        if bands and edge - bands[-1][-1] <= 0.012:
            bands[-1].append(edge)
        else:
            bands.append([edge])
    return [sorted(band)[len(band) // 2] for band in bands]


def _band(token, columns, width):
    edge = token['x1'] / (token['_width'] or width)
    tolerance = 0.015 if (token['exact'] or token['last']) else 0.03
    near = [i for i, c in enumerate(columns) if abs(edge - c) <= tolerance]
    if len(near) == 1:
        return near[0]
    if near:
        return min(near, key=lambda i: abs(edge - columns[i]))
    return None


def _hints(header_rows, columns, width):
    """Column roles printed in the movement headings (E1): hints only."""
    hints = {}
    for row in header_rows:
        tokens = sorted(row['tokens'], key=lambda t: t['x0'])
        words = []
        for index, token in enumerate(tokens):
            for size in (3, 2, 1):
                group = tokens[index:index + size]
                if len(group) < size:
                    continue
                role = column_role(label(' '.join(t['t'] for t in group)))
                if role:
                    words.append((role, group[0]['x0'], group[-1]['x1'], row['width'] or width))
                    break
        for i, column in enumerate(columns):
            scored = []
            for role, x0, x1, w in words:
                if role not in ('credit', 'debit', 'balance', 'amount'):
                    continue
                left, right = x0 / w, x1 / w
                gap = 0 if left - 0.005 <= column <= right + 0.01 else min(abs(column - left), abs(column - right))
                if gap <= 0.05:
                    scored.append((gap, abs(column - right), role))
            if not scored:
                continue
            scored.sort()
            # Two headings equally near the column give no hint.
            if len(scored) > 1 and scored[1][0] == scored[0][0] and abs(scored[1][1] - scored[0][1]) < 0.005 and scored[1][2] != scored[0][2]:
                hints.setdefault(i, set()).update({scored[0][2], scored[1][2]})
                continue
            hints.setdefault(i, set()).add(scored[0][2])
    return {i: next(iter(roles)) for i, roles in hints.items() if len(roles) == 1}


def _reading(rows, statement, style, exponent, liability, period):
    width = next((r['width'] for r in rows if r['width']), None)
    proof = dict(engine=ENGINE_VERSION, proved=False, reason='', convention='liability_owed' if liability else 'asset_balance')
    result = dict(rows=[], proof=proof, fingerprint='', first_row='')
    if style is None:
        proof['reason'] = 'separators_mixed'
    if any(not r['located'] for r in rows):
        proof['reason'] = proof['reason'] or 'no_geometry'
    controls = dict(opening=[], closing=[], credit_total=[], debit_total=[], credit_component=[], debit_component=[])
    movements, headers, labels_seen, unplaced, continuation_of, column_totals = [], [], set(), [], {}, []
    region = False
    # Printed totals count only inside a summary block: after an opening balance, up to the closing one (D4, D7).
    in_summary = False
    undated_rows = []
    last_move = None
    for index, row in enumerate(rows):
        row['_index'] = index
        for token in row['tokens']:
            token['_width'] = row['width'] or width
    # Amount bands from the dated movement lines, before deciding what else carries money (E2).
    early = [t for row in rows if row['tokens'] and _row_is_movement(row, style or 'dot', exponent)
             for t in row['tokens'] if _value_kind(t, style or 'dot', exponent) == 'money']
    early_columns = _columns(early, width or 1) if early else []
    for index, row in enumerate(rows):
        if not row['tokens']:
            continue
        words = {label(t['t']) for t in row['tokens']}
        if _is_header(row):
            headers.append(row)
            labels_seen.update(w for w in words if column_role(w))
            region = True
            continue
        if _row_is_movement(row, style or 'dot', exponent):
            tokens = merged_dates(row['tokens'])
            date_tokens = []
            rest = list(tokens)
            while rest and is_date_token(rest[0]['t']) and len(date_tokens) < 2:
                date_tokens.append(rest.pop(0))
            money_tokens = [t for t in rest if _value_kind(t, style or 'dot', exponent) == 'money']
            words_only = [t for t in rest if t not in money_tokens]
            text = label(' '.join(t['t'] for t in words_only))
            role = _role_of(text, liability)
            if role in ('opening', 'closing') and len(money_tokens) >= 1:
                controls[role].append(dict(row=row, value_token=money_tokens[-1], count=None))
                labels_seen.add(text)
                continue
            if role in ('subtotal', 'column_total', 'credit_total', 'debit_total', 'credit_component', 'debit_component'):
                continue
            first_money = min(money_tokens, key=lambda t: t['x0'])
            description = [t for t in words_only if t['x0'] < first_money['x0'] or t['line'] > 0]
            move = dict(row=row, date_tokens=date_tokens, money=money_tokens, description=description,
                        stray=[t for t in words_only if t not in description], continuation=[])
            movements.append(move)
            last_move = move
            region = True
            continue
        pairs = label_pairs(row, style or 'dot', exponent)
        handled = False
        for text, values in pairs:
            role = _role_of(text, liability)
            money_values = [t for kind, t in values if kind == 'money']
            counts = [t for kind, t in values if kind == 'count']
            if role == 'opening' and money_values:
                in_summary = not region
            if role in ('credit_total', 'debit_total', 'credit_component', 'debit_component') and not in_summary:
                handled = handled or bool(money_values)
                continue
            if role in ('opening', 'closing', 'credit_total', 'debit_total', 'credit_component', 'debit_component') and money_values:
                count = counts[0]['t'] if role.endswith('_total') and len(counts) == 1 and values[0][0] == 'count' else None
                controls[role].append(dict(row=row, value_token=_control_value(money_values), count=count))
                labels_seen.add(text)
                handled = True
                if role == 'closing':
                    in_summary = False
            elif role == 'column_total' and money_values:
                column_totals.append(dict(row=row, tokens=money_values))
                labels_seen.add(text)
                handled = True
            elif role == 'subtotal':
                handled = True
        if handled:
            if any(_role_of(text, liability) in ('closing',) for text, _ in pairs):
                region = False
                last_move = None
            continue
        has_money = any(_value_kind(t, style or 'dot', exponent) == 'money' for t in row['tokens'])
        if has_money and region and early_columns and not any(
                _band(t, early_columns, width or 1) is not None for t in row['tokens']
                if _value_kind(t, style or 'dot', exponent) == 'money'):
            # Numbers outside every amount column are description text (references, quoted amounts).
            has_money = False
        if liability and has_money and movements and _undated_charge(row, style or 'dot', exponent):
            # A card interest/fee line without a date (B6), ordered at the period end only.
            undated_rows.append(row)
            continue
        if not has_money:
            if last_move is not None and region and _continues(row, last_move):
                last_move['continuation'].append(row)
                continuation_of[index] = last_move
            else:
                last_move = None if last_move is not None and row['page'] == last_move['row']['page'] and _below(row, last_move) else last_move
            continue
        if region and last_move is not None and row['page'] == last_move['row']['page']:
            unplaced.append(row)
    result['first_row'] = (rows[0]['page'], rows[0]['source']['table_index'], rows[0]['raw']['row_index']) if rows else ''
    # Unplaced money lines only count inside a page's movement region: between its first and last movement.
    spans = {}
    for move in movements:
        spans.setdefault(move['row']['page'], []).append(move['row']['_index'])
    unplaced = [row for row in unplaced if row['page'] in spans
                and min(spans[row['page']]) < row['_index'] < max(spans[row['page']])]
    # Undated card charges (B6) inside the region are movements ordered at the period end.
    undated = []
    for row in undated_rows:
        money_tokens = [t for t in row['tokens'] if _value_kind(t, style or 'dot', exponent) == 'money']
        first_money = min(money_tokens, key=lambda t: t['x0'])
        undated.append(dict(row=row, date_tokens=[], money=money_tokens,
                            description=[t for t in row['tokens'] if t not in money_tokens and t['x0'] < first_money['x0']],
                            stray=[], continuation=[], undated=True))
    all_moves = sorted(movements + undated, key=lambda m: m['row']['_index'])
    money_tokens = [t for move in all_moves for t in move['money']]
    columns = _columns(money_tokens, width or 1) if money_tokens else []
    hints = _hints(headers, columns, width or 1) if columns else {}
    result['fingerprint'] = _fingerprint({label(t['t']) for h in headers for t in h['tokens']}, columns,
                                         labels_seen, proof['convention'])
    dated = [m for m in all_moves if not m.get('undated')]
    resolved, date_problem = _resolve_dates(dated, period, liability) if dated else ([], None if period else 'no_period')
    candidates = _search(all_moves, columns, hints, controls, column_totals, style or 'dot', exponent, liability)
    proving = [c for c in candidates if c['proved']]
    readings = {}
    for candidate in proving:
        readings.setdefault(candidate['key'], candidate)
    chosen = None
    if not proof['reason']:
        if not all_moves and not controls['opening'] and not controls['closing']:
            proof['reason'] = 'no_movements_or_controls'
        elif not controls['opening']:
            proof['reason'] = 'no_opening'
        elif not controls['closing']:
            proof['reason'] = 'no_closing'
        elif date_problem:
            proof['reason'] = date_problem
        elif unplaced:
            proof['reason'] = 'unplaced_money_line'
        elif candidates and candidates[0].get('overflow'):
            proof['reason'] = 'too_many_interpretations'
        elif len(readings) > 1:
            proof['reason'] = 'two_readings'
        elif len(readings) == 1:
            chosen = next(iter(readings.values()))
            proof.update(proved=True, reason='proved', basis=chosen['basis'])
        else:
            near = [c for c in candidates if c['closing_ok']]
            proof['reason'] = ('printed_total_differs' if any(c['totals_failed'] for c in near)
                               else 'no_independent_control' if near else 'not_reconciled')
    if chosen is None:
        chosen = _best_effort(candidates, hints)
    proof['assignment'] = chosen['assignment'] if chosen else None
    result['rows'] = _rows(rows, all_moves, resolved if not date_problem else None, chosen, controls,
                           column_totals, statement, style or 'dot', exponent, liability, proof, unplaced)
    return result


def _undated_charge(row, style, exponent):
    tokens = [t for t in row['tokens'] if _value_kind(t, style, exponent) != 'money']
    money_tokens = [t for t in row['tokens'] if _value_kind(t, style, exponent) == 'money']
    text = label(' '.join(t['t'] for t in tokens))
    return (len(money_tokens) == 1 and money(money_tokens[0]['t'], style, exponent)
            and any(text == label(p) or text.startswith(label(p) + ' ') for p in UNDATED_CHARGES))


def _is_header(row):
    """A movement-table heading: a date word, a money word, and mostly column words (E1)."""
    tokens = sorted(row['tokens'], key=lambda t: (t['line'], t['x0']))
    if not tokens or len(tokens) > 16:
        return False
    roles, covered, index = [], 0, 0
    while index < len(tokens):
        for size in (3, 2, 1):
            group = tokens[index:index + size]
            role = column_role(label(' '.join(t['t'] for t in group))) if len(group) == size else None
            if role:
                roles.append(role)
                covered += size
                index += size
                break
        else:
            index += 1
    return ('date' in roles and bool(set(roles) & {'credit', 'debit', 'amount', 'balance'})
            and covered * 2 >= len(tokens))


def _below(row, move):
    last = move['continuation'][-1] if move['continuation'] else move['row']
    return row['y0'] is not None and last['y0'] is not None and row['y0'] > last['y0']


def _continues(row, move):
    """A line without date or money directly below a movement, starting in its description band (E3)."""
    last = move['continuation'][-1] if move['continuation'] else move['row']
    if row['page'] != last['page'] or row['y0'] is None or last['y0'] is None or len(move['continuation']) >= 8:
        return False
    height = max(t['y1'] - t['y0'] for t in last['tokens'])
    gap = row['y0'] - max(t['y1'] for t in last['tokens'])
    if gap > height * 1.2 or gap < -height:
        return False
    start = min((t['x0'] for t in move['description']), default=None)
    if start is None:
        return False
    first = min(t['x0'] for t in row['tokens'])
    width = row['width'] or 1
    if first < start - 0.02 * width:
        return False
    return not _is_header(row) and not any(_role_of(text, False) for text, _ in label_pairs(row, 'dot', 2))


def _domains(columns, hints):
    domains = []
    for i in range(len(columns)):
        hint = hints.get(i)
        if hint == 'balance':
            domains.append(('balance', 'ignore'))
        elif hint in ('credit', 'debit', 'amount'):
            domains.append((hint,))
        else:
            domains.append(('credit', 'debit', 'amount', 'balance', 'ignore'))
    return domains


def _valid(assignment):
    roles = [r for r in assignment]
    if any(roles.count(r) > 1 for r in ('credit', 'debit', 'amount', 'balance')):
        return False
    if 'amount' in roles and ({'credit', 'debit'} & set(roles)):
        return False
    return bool({'credit', 'debit', 'amount'} & set(roles))


def _movement_value(move, assignment, columns, width, style, exponent, liability):
    """Signed effect of one movement line on the printed balance under ``assignment``, or None."""
    amounts, balance, balance_token, zero = [], None, None, False
    for token in move['money']:
        band = _band(token, columns, width)
        if band is None:
            return None
        role = assignment[band]
        value = money(token['t'], style, exponent)
        if role == 'ignore' or value is None:
            continue
        if role == 'balance':
            if balance_token is not None:
                return None
            balance, balance_token = value, token
        elif value == 0:
            zero = True
        else:
            amounts.append((role, value, token))
    if len(amounts) > 1:
        return None
    if not amounts:
        return dict(zero=True, balance=balance, balance_token=balance_token) if zero else None
    role, value, token = amounts[0]
    if role in ('credit', 'debit'):
        if value < 0:
            return None
        direction = role
    else:
        # Signed column: asset positive = money in; card positive = a charge (C5, C7).
        direction = ('debit' if value > 0 else 'credit') if liability else ('credit' if value > 0 else 'debit')
    size = abs(value)
    effect = (size if direction == 'debit' else -size) if liability else (size if direction == 'credit' else -size)
    return dict(zero=False, effect=effect, direction=direction, amount=size, balance=balance,
                balance_token=balance_token, amount_token=token)


def _search(moves, columns, hints, controls, column_totals, style, exponent, liability):
    width = 1
    for move in moves:
        for token in move['money']:
            width = token['_width'] or width
            break
    domains = _domains(columns, hints)
    total = 1
    for d in domains:
        total *= len(d)
    if total > MAX_ASSIGNMENTS:
        return [dict(proved=False, overflow=True, closing_ok=False, totals_failed=False, key=None)]
    openings = {}
    for item in controls['opening']:
        value = money(item['value_token']['t'], style, exponent)
        if value is not None:
            openings.setdefault(value, item)
    closings = {}
    for item in controls['closing']:
        value = money(item['value_token']['t'], style, exponent)
        if value is not None:
            closings.setdefault(value, item)
    results = []
    for assignment in product(*domains) if columns else [()]:
        if columns and not _valid(assignment):
            continue
        values = []
        ok = True
        for move in moves:
            value = _movement_value(move, assignment, columns, width, style, exponent, liability) if columns else None
            if value is None:
                ok = False
                break
            values.append(value)
        if not ok and moves:
            results.append(dict(proved=False, closing_ok=False, totals_failed=False, key=None, assignment=assignment,
                                values=None))
            continue
        effects = [v for v in values if not v['zero']]
        credits = sum(v['amount'] for v in effects if v['direction'] == 'credit')
        debits = sum(v['amount'] for v in effects if v['direction'] == 'debit')
        counts = dict(credit=sum(v['direction'] == 'credit' for v in effects), debit=sum(v['direction'] == 'debit' for v in effects))
        totals_ok, totals_found, totals_failed = True, 0, False
        for role, expected in (('credit_component', credits), ('debit_component', debits)):
            parts = [money(item['value_token']['t'], style, exponent) for item in controls[role]]
            if parts:
                totals_found += 1
                if None in parts or sum(abs(p) for p in parts) != expected:
                    totals_ok, totals_failed = False, True
        for role, expected in (('credit_total', credits), ('debit_total', debits)):
            for item in controls[role]:
                printed = money(item['value_token']['t'], style, exponent)
                totals_found += 1
                if printed is None or abs(printed) != expected:
                    totals_ok, totals_failed = False, True
                elif item['count'] is not None and int(item['count']) != counts[role.split('_')[0]]:
                    totals_ok, totals_failed = False, True
        for item in column_totals:
            for token in item['tokens']:
                band = _band(token, columns, width) if columns else None
                role = assignment[band] if band is not None else None
                if role in ('credit', 'debit'):
                    totals_found += 1
                    if money(token['t'], style, exponent) != (credits if role == 'credit' else debits):
                        totals_ok, totals_failed = False, True
        for opening, closing in product(openings, closings):
            net = sum(v['effect'] for v in effects)
            closing_ok = opening + net == closing
            chains = []
            for order in (values, list(reversed(values))):
                previous, pending, compared, mismatch = opening, 0, 0, 0
                for value in order:
                    if not value['zero']:
                        pending += value['effect']
                    if value['balance'] is not None:
                        compared += 1
                        if previous + pending != value['balance']:
                            mismatch += 1
                        previous, pending = value['balance'], 0
                chains.append(compared > 0 and not mismatch)
            chain_ok = any(chains)
            proved = closing_ok and totals_ok and (chain_ok or (totals_found > 0 and totals_ok))
            basis = 'running_balance' if chain_ok else 'printed_totals'
            key = (opening, closing, tuple((m['row']['_index'], v.get('direction'), v.get('amount')) for m, v in zip(moves, values)))
            results.append(dict(proved=proved, closing_ok=closing_ok, totals_failed=totals_failed, chain_ok=chain_ok,
                                key=key, assignment=assignment, values=values, opening=opening, closing=closing,
                                basis=basis, opening_item=openings[opening], closing_item=closings[closing]))
    return results


def _best_effort(candidates, hints):
    usable = [c for c in candidates if c.get('values') is not None and c.get('assignment') is not None]
    if not usable:
        return None
    return max(usable, key=lambda c: (c['closing_ok'], c.get('chain_ok', False),
                                      sum(1 for i, r in enumerate(c['assignment']) if hints.get(i) == r)))


def _item(row, suffix=''):
    source, raw = row['source'], row['raw']
    return dict(id=f"{source['page_number']}:{source['table_index']}:{raw['row_index']}{suffix}",
                page_number=source['page_number'], table_index=source['table_index'], row_index=raw['row_index'],
                source_revision=source['source_revision'], source_cells=raw['cells'], fields={}, issues=[],
                excluded=True, kind='header')


def _rows(rows, moves, resolved, chosen, controls, column_totals, statement, style, exponent, liability, proof, unplaced):
    """Every source row of the section, in the shared proposal format."""
    items = {}
    order = []
    for row in rows:
        item = _item(row)
        items[row['_index']] = item
        order.append(item)
    if chosen and chosen.get('values') is not None:
        dates = iter(resolved or [])
        for move, value in zip(moves, chosen['values']):
            item = items[move['row']['_index']]
            fields = item['fields']
            description = ' '.join(t['t'] for t in move['description'])
            for extra in move['continuation']:
                description += ' ' + extra['text']
                item.setdefault('continuation_sources', []).append(dict(
                    page_number=extra['page'], table_index=extra['source']['table_index'],
                    row_index=extra['raw']['row_index'], source_cells=extra['raw']['cells']))
                items[extra['_index']]['fields']['parent_transaction_id'] = item['id']
            fields['description'] = ' '.join(description.split())
            fields['counterparty'] = ''
            if move.get('undated'):
                fields['date_basis'] = 'statement_end_ordering_only'
            else:
                printed = next(dates, None) if resolved is not None else None
                if move['date_tokens']:
                    fields['date_column'] = str(move['date_tokens'][0]['cell']['column_index'])
                if printed:
                    fields['date'] = printed[0].isoformat()
                    if len(printed) > 1:
                        fields['value_date'] = printed[1].isoformat()
                else:
                    item['issues'].append('Check the printed date of this movement.')
            if move['description']:
                fields['description_column'] = str(move['description'][0]['cell']['column_index'])
            if value['zero']:
                item.update(kind='zero_line', excluded=True)
                continue
            item.update(kind='transaction', excluded=False)
            fields.update(direction=value['direction'], amount_minor=str(value['amount']))
            fields[value['direction']] = str(value['amount'])
            fields[value['direction'] + '_column'] = str(value['amount_token']['cell']['column_index'])
            if value['balance'] is not None:
                fields['balance'] = str(value['balance'])
                fields['balance_column'] = str(value['balance_token']['cell']['column_index'])
            if not fields['description']:
                item['issues'].append('The transaction description is missing.')
    else:
        for move in moves:
            item = items[move['row']['_index']]
            item.update(kind='unresolved', excluded=False)
            item['fields']['description'] = move['row']['text'][:300]
            item['issues'].append('The amount columns of this movement could not be established. Compare it with the PDF.')
    used = set()

    def control(entry, description, role_key, **extra):
        row = entry['row']
        key = row['_index']
        suffix = '' if key not in used else ':' + role_key
        used.add(key)
        item = items[key] if not suffix else _item(row, suffix)
        if suffix:
            order.insert(order.index(items[key]) + 1, item)
        token = entry['value_token']
        item.update(kind=extra.pop('kind', 'balance'), excluded=True)
        item['fields'].update(description=description, balance=str(money(token['t'], style, exponent)),
                              balance_column=str(token['cell']['column_index']), **extra)
        return item

    if chosen and chosen.get('opening_item') is not None:
        control(chosen['opening_item'], 'Opening Balance', 'opening')
        control(chosen['closing_item'], 'Closing Balance', 'closing')
    else:
        for role, description in (('opening', 'Opening Balance'), ('closing', 'Closing Balance')):
            values = {money(e['value_token']['t'], style, exponent) for e in controls[role]} - {None}
            if len(values) == 1:
                control(controls[role][0], description, role)
    for role, direction in (('credit_total', 'credit'), ('debit_total', 'debit')):
        values = {money(e['value_token']['t'], style, exponent) for e in controls[role]} - {None}
        if len(values) == 1 and len(controls[role]) >= 1:
            entry = controls[role][0]
            extra = dict(kind='statement_total', total_direction=direction)
            if entry['count'] is not None:
                extra['printed_transaction_count'] = entry['count']
            item = control(entry, 'Total ' + direction, role, **extra)
            item['fields']['balance'] = str(abs(int(item['fields']['balance'])))
    for row in unplaced:
        item = items[row['_index']]
        item.update(kind='unresolved', excluded=False)
        item['fields']['description'] = row['text'][:300]
        item['issues'].append('This line has an amount that could not be placed in the movement columns. Compare it with the PDF.')
    if not proof['proved']:
        anchor = next((item for item in order if item['kind'] == 'balance'), order[0] if order else None)
        if anchor is not None:
            hold = dict(anchor, id=anchor['id'] + ':engine_hold', fields=dict(description=HOLD_MESSAGES.get(proof['reason'], proof['reason'])),
                        issues=['The general statement reader did not prove this period: '
                                + HOLD_MESSAGES.get(proof['reason'], proof['reason'])
                                + ' Compare the period with the PDF, then exclude this line with a reason once checked.'],
                        excluded=False, kind='unresolved', engine_hold=proof['reason'])
            order.insert(order.index(anchor) + 1, hold)
    return order


# ---------------------------------------------------------------------------
# Catalog and proposal entry points
# ---------------------------------------------------------------------------

def engine_catalog(sources, *, profile=None):
    """Statements the engine reads in these sources (rows removed)."""
    result = []
    for statement in read_statements(sources, profile=profile):
        result.append({k: v for k, v in statement.items() if k != '_rows'})
    return result


def _copy_rows(rows):
    return [dict(row, fields=dict(row['fields']), issues=list(row['issues'])) for row in rows]


def _hold_row(rows, reason):
    anchor = next((r for r in rows if r['kind'] == 'balance'), rows[0])
    return dict(anchor, id=anchor['id'] + ':engine_hold', fields=dict(description=HOLD_MESSAGES.get(reason, reason)),
                issues=['The general statement reader did not prove this period: ' + HOLD_MESSAGES.get(reason, reason)
                        + ' Compare the period with the PDF, then exclude this line with a reason once checked.'],
                excluded=False, kind='unresolved', engine_hold=reason)


def propose_engine_statement(sources, currency, choice):
    """The chosen period's rows. ``sources`` must be every source of the document:
    the period is found again by its id in a reading of the whole document (with the
    same library profile when one served it)."""
    profile = None
    if choice.get('engine_profile'):
        from services.financial.statement_engine_profiles import PROFILES
        profile = next((p for p in PROFILES if p['name'] == choice['engine_profile']), None)
        if profile is None:
            raise ValueError('The reading profile of this statement period is no longer available. Reload the document.')
    for statement in read_statements(sources, profile=profile):
        if statement['id'] == choice['id'] or statement['id'] == choice.get('engine_id'):
            rows = _copy_rows(statement['_rows'])
            reason = (choice.get('engine') or {}).get('reason')
            if reason == 'route_library_first' and rows and not any(r.get('engine_hold') for r in rows):
                rows = rows + [_hold_row(rows, reason)]
            if currency and statement.get('currency') and currency != statement['currency']:
                rows = [dict(row) for row in rows]
                rows.append(dict(rows[0], id=rows[0]['id'] + ':engine_currency', kind='unresolved', excluded=False,
                                 fields=dict(description='Currency differs'), issues=[
                                     'The review currency differs from the currency printed for this statement. Check the currency.']))
            return dict(rows=rows, issues=[])
    raise ValueError('This statement period is no longer read the same way. Reload the document.')
