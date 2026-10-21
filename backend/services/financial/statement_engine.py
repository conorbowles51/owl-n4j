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
import pickle
import re
import threading
from collections import OrderedDict
from contextvars import ContextVar
from datetime import date, timedelta
from functools import lru_cache
from itertools import product

from services.financial.pdf_candidates import _digest
from services.financial.statement_engine_vocabulary import (
    ACCOUNT_LABELS, ADDRESS_WORDS, CLOSING_DATE_LABELS, CONTINUATION_NOTICES, CURRENCY_LABELS, CURRENCY_NAMES, COLUMN_INDEX,
    CYCLE_DAYS_LABELS, HOLDER_LABELS, INDEX, INSTITUTION_WORDS, LIABILITY_EVIDENCE, MONTHS, NOT_A_NAME, PAGE_NUMBERING,
    PAYMENT_BOX_HEADINGS, PERIOD_WORDS, SECTION_HEADINGS, SECTION_SCOPE, TAXPAYER_TYPES, UNDATED_CHARGES, YEAR_TO_DATE, FUZZY_INDEX, fold, label)

LAYOUT = 'generic'
# The library profile applied to the current reading (None for the plain engine).
_PROFILE = ContextVar('statement_engine_profile', default=None)
# The document's movement headings name the date column "DIA"/"DAY": a row may start with the day alone (B2).
_DAY_COLUMN = ContextVar('statement_engine_day_column', default=False)
# The document's day-month order from its unambiguous numeric dates (_document_date_order), or None.
_DOCUMENT_ORDER = ContextVar('statement_engine_document_order', default=None)
# The document never prints an amount in parentheses: a ')' read after an amount is scan noise, not the
# parentheses-for-negative convention (C4, C11).
_NO_PARENS = ContextVar('statement_engine_no_parentheses', default=False)
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
    'period_start_contradicted': ('The start date worked out from the printed days in the billing period does not '
                                  'follow the previous statement for this card in the same file.'),
    'route_library_first': 'This layout is routed to the bank-specific reader library first.',
    'library_disagrees': 'The general reader and the bank-specific reader both reconcile this period but read it differently.',
    'second_date_unnamed': ('Movement lines print a second date, but the heading of that date column could not be '
                            'read, so it is not known whether it is the posting date or the value date.'),
    'date_unread': ('A movement line prints two dates, but one of them could not be read, so the line\'s date '
                    'cannot be confirmed.'),
    'day_balance_date_differs': ('A movement line\'s settlement day is not the day printed on the end-of-day balance '
                                 'after it, or no end-of-day balance follows it, so its date cannot be confirmed.'),
    'line_without_content':'A dated line in the movement table prints nothing else, so its amount is missing (it may have been blacked out).',
    'account_shared': 'This credit line prints the same account number as a deposit account in the same statement, so its records could be mixed with that account. Check it against the PDF before importing it.',
    'principal_only_balance': ('This credit line prints only its principal balance: the amount owed at the opening (principal '
                               'with interest and fees) is not printed, so the movement lines cannot be checked against it.'),
}
# A credit line's movement table that prints the principal, the interest and a balance column side by side
# keeps its balance column as the principal only (C5).
_PRINCIPAL_ONLY_WORDS = ('PRINCIPAL', 'INTEREST', 'BALANCE')
# Hold reasons a principal-only balance explains: the money could not be proved from the printed balances.
_PRINCIPAL_ONLY_EXPLAINS = frozenset({'not_reconciled', 'no_independent_control', 'no_geometry', 'no_opening',
                                      'no_closing', 'unplaced_money_line', 'printed_total_differs', 'two_readings',
                                      'too_many_interpretations'})
# (B7) A line a statement prints inside an account section when nothing moved in the period.
NO_TRANSACTIONS = ('NO TRANSACTIONS THIS PERIOD',)


# ---------------------------------------------------------------------------
# Located tokens
# ---------------------------------------------------------------------------

def _rect(cell, rotation=0):
    """The cell's rectangle and page width in the frame its text reads upright in.

    Stored rectangles are in displayed page space; a page whose text reads turned
    (``reading_rotation`` on its source) is read in its upright frame.
    """
    locator = cell.get('locator') or {}
    rect, size = locator.get('rect'), locator.get('page_size')
    if (not isinstance(rect, list) or len(rect) != 4 or not all(type(v) is int for v in rect)
            or not rect[0] < rect[2] or not rect[1] < rect[3]):
        return None, None
    valid = isinstance(size, list) and len(size) == 2 and all(type(v) is int and v > 0 for v in size)
    if rotation and valid:
        x0, y0, x1, y1 = rect
        width, height = size
        if rotation == 90:
            rect, size = [height - y1, x0, height - y0, x1], [height, width]
        elif rotation == 180:
            rect = [width - x1, height - y1, width - x0, height - y0]
        elif rotation == 270:
            rect, size = [y0, width - x1, y1, width - x0], [height, width]
    width = size[0] if valid else None
    return rect, width


_SIGN_ONLY = re.compile(r'^(?:-|−|\$|US\$|€|£|¥|MN|M\.N\.|MXN|USD|EUR|DLS|CR)$')


_PARENTHESIZED = re.compile(r'\([^()\s]*\)')


def _without_rule_marks(line, mark):
    """(profile ``rule_mark``) The line with the mark the reading prints at every cell's edge (a table rule read
    as text, '28)' '83.10)' 'Ope)Liq)') replaced by spaces, so word positions stay where they were printed. A
    parenthesized amount ('(4,321,987.65)') keeps its parentheses: its sign is printed."""
    kept = {i for m in _PARENTHESIZED.finditer(line) for i in range(m.start(), m.end())}
    return ''.join(' ' if ch == mark and i not in kept else ch for i, ch in enumerate(line))


def _cell_tokens(cell, rotation=0):
    rect, width = _rect(cell, rotation)
    if rect is None:
        return None, None
    lines = cell['expected_text'].split('\n')
    mark = (_PROFILE.get() or {}).get('rule_mark')
    if mark:
        lines = [_without_rule_marks(line, mark) for line in lines]
    count = len(lines)
    tokens = []
    for index, line in enumerate(lines):
        words = [(m.start(), m.end(), m.group()) for m in re.finditer(r'\S+', line)]
        if not words:
            continue
        words = _unglue_leading_date(words)
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
        merged = _rejoin_amounts(merged)
        for s, e, word in merged:
            exact = count == 1 and len(merged) == 1
            x0 = rect[0] + (rect[2] - rect[0]) * (s - start) / span
            x1 = rect[0] + (rect[2] - rect[0]) * (e - start) / span
            tokens.append(dict(t=word, f=fold(word), x0=x0, x1=x1, y0=y0, y1=y1, cell=cell, exact=exact,
                               first=s == start, last=e == end, line=index))
    return tokens, width


# (B2) A full date (day, month, four-digit year) read as the first word of a line with the next word glued to it
# by one to three stray marks the scan read in the gap ("01-MAR-2026'1234567", "01-MAR-2026)/1234567"). The four
# printed year digits end the date; the marks are dropped. Off: the line keeps the glued word and is no movement.
UNGLUE_LEADING_DATE = True
# With a month word the year's end is also found with no mark at all, before a run of figures (a folio):
# "01-MAR-20261234567"; the year must read 19xx or 20xx.
_GLUED_DATE = re.compile(r"^(\d{1,2}[-/.][A-Za-z]{3,10}[-/.]\d{4}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})([^\w\s]{1,3})(\w\S*)$")
_JOINED_DATE = re.compile(r"^(\d{1,2}[-/.][A-Za-z]{3,10}[-/.](?:19|20)\d{2})()(\d{3,}\S*)$")


def _unglue_leading_date(words):
    if not UNGLUE_LEADING_DATE:
        return words
    s, e, word = words[0]
    m = _GLUED_DATE.match(word) or _JOINED_DATE.match(word)
    if not m or not is_date_token(m[1]):
        return words
    return [(s, s + len(m[1]), m[1]), (s + m.end(2), e, m[3])] + words[1:]


# OCR damage around one printed amount (C11): a stray '?' read after it (scan noise beside the
# figure), and the amount split by a space inside one cell ("135 , 700.06", "5,173 846,29").
_NOISE_TAIL = re.compile(r'^([-−(]?(?:US\$|\$)?(?:\d{1,3}(?:,\d{3})*)?[.,]?\d{2}(?:\)|-|−|CR)?)\?$')
# A table's column rule read after an amount ('4,318,207.55|', or a run of dashes printed in the margin beside it,
# '4,318,207.55——'), and, in a document that prints no amount in
# parentheses, a ')' read there ('1,045,320.00)').
_RULE_TAIL = re.compile(r'^([-−(]?(?:US\$|\$)?(?:\d{1,3}(?:,\d{3})*)?[.,]?\d{2}(?:\)|-|−|CR)?)(?:\||——+)$')
_PAREN_TAIL = re.compile(r'^([-−]?(?:US\$|\$)?\d{1,3}(?:,\d{3})*[.,]\d{2})\)$')
# Two separators read before the cents ('2,617,384,.91'): the one next to the cents is the decimal mark.
_DOUBLE_MARK = re.compile(r'^([-−(]?(?:US\$|\$)?\d{1,3}(?:,\d{3})*)[.,]([.,]\d{2}(?:\)|-|−|CR)?)$')
_SPLIT_HEAD = re.compile(r'^[-−(]?(?:US\$|\$)?\d{1,3}(?:,\d{3})*,?$')
_SPLIT_TAIL = re.compile(r'^,?\d{3}(?:,\d{3})*[.,]\d{2}(?:\)|-|−|CR)?$')
_SPLIT_CENTS = re.compile(r'^[.,]?\d{2}(?:\)|-|−|CR)?$')
_GROUPED_AMOUNT = re.compile(r'^[-−(]?(?:US\$|\$)?\d{1,3}(?:,\d{3})+[.,]\d{2}(?:\)|-|−|CR)?$')


def _rejoin_amounts(words):
    """[(start, end, word)] of one cell line with OCR-damaged amounts repaired.

    A trailing '?' after a complete amount (or its cents) is dropped, and of two
    separators printed before the cents the one next to them is kept. Words are joined only inside
    one cell line, only across a gap of spaces or a lone comma, and only when the
    result is one amount with complete three-digit groups (a thousands group is
    never invented): '3,215 , 677.12' -> '3,215,677.12', '12,486, 37' -> '12,486,37', '$4 321.09' -> '$4,321.09',
    '5,291 157,82' -> '5,291,157,82' (read by the document's decimal convention).
    The proof still decides whether the value is used.
    """
    cleaned = []
    for s, e, word in words:
        noise = _NOISE_TAIL.fullmatch(word) or _RULE_TAIL.fullmatch(word) or (
            _NO_PARENS.get() and '(' not in word and _PAREN_TAIL.fullmatch(word))
        if noise:
            e, word = s + len(noise[1]), noise[1]
        double = _DOUBLE_MARK.fullmatch(word)
        if double:
            word = double[1] + double[2]
        cleaned.append((s, e, word))
    cleaned = _rejoin_decimal_mark(cleaned)
    out, index = [], 0
    while index < len(cleaned):
        s, e, word = cleaned[index]
        joined = None
        if _SPLIT_HEAD.fullmatch(word):
            following = cleaned[index + 1:index + 3]
            parts = [p for _, _, p in following]
            for size in (1, 2):
                if len(parts) < size:
                    continue
                if size == 2 and parts[0] != ',' or size == 1 and ',' not in word and not re.match(r'^[-−(]?(?:US)?\$', word):
                    # A head without its own comma (a printed count before an amount) joins only
                    # across a lone comma; a head printing the money sign ('$4 321.09') is not a count.
                    continue
                tail = parts[size - 1]
                head = word.rstrip(',')
                if _SPLIT_TAIL.fullmatch(tail):
                    text = head + ',' + tail.lstrip(',')
                elif _SPLIT_CENTS.fullmatch(tail) and ',' in head and size == 1:
                    # The decimal separator read as a space or detached onto the cents ('5,733,642 43',
                    # '140,527 ,00'): only after complete thousands groups.
                    text = head + ',' + tail.lstrip('.,')
                else:
                    continue
                if _GROUPED_AMOUNT.fullmatch(text):
                    joined = (s, following[size - 1][1], text, size)
                    break
        if not joined and _SPLIT_HEAD.fullmatch(word):
            joined = _rejoin_detached_marks(cleaned, index)
        if joined:
            out.append(joined[:3])
            index += 1 + joined[3]
        else:
            out.append((s, e, word))
            index += 1
    return out


_MARKED_GROUP = re.compile(r'^,\d{3}$')
_MARKED_CENTS = re.compile(r'^[.,]{1,2}\d{2}(?:\)|-|−|CR)?$')


def _rejoin_detached_marks(words, index):
    """(C11) Separators the scan detached onto the following groups ('300 ,000 ,00', '1,724,615 ,.38'):
    a head, then any comma-prefixed three-digit groups, then the cents with their own mark (a doubled mark
    keeps the one next to the cents). Only when the result is one amount with complete thousands groups."""
    s, _, head = words[index]
    parts, end = [head.rstrip(',')], index + 1
    while end < len(words) and _MARKED_GROUP.fullmatch(words[end][2]):
        parts.append(words[end][2])
        end += 1
    if end >= len(words) or not _MARKED_CENTS.fullmatch(words[end][2]):
        return None
    cents = words[end][2]
    if len(cents) > 1 and cents[1] in '.,':
        cents = cents[1:]
    text = ''.join(parts) + cents
    if end == index + 1 and ',' not in head:
        return None  # a bare count before marked cents is not joined here (the decimal-mark rule decides)
    if not _GROUPED_AMOUNT.fullmatch(text):
        return None
    return (s, words[end][1], text, end - index)


_MARK_HEAD = re.compile(r'^[-−(]?(?:US\$|\$)?\d{1,3}(?:,\d{3})*$')
_MARK_CENTS = re.compile(r'^[.,]\d{2}(?:\)|-|−|CR)?$')
_MARKED_HEAD = re.compile(r'^[-−(]?(?:US\$|\$)?\d{1,3}(?:,\d{3})*[.,]$')
_BARE_CENTS = re.compile(r'^\d{2}(?:\)|-|−|CR)?$')


def _rejoin_decimal_mark(words):
    """A space read beside the decimal mark inside one cell line ('715 .00', '11,206,500. 63'): the two
    words are one amount when the mark is printed and two cents digits follow it (C11)."""
    out, index = [], 0
    while index < len(words):
        s, e, word = words[index]
        if index + 1 < len(words):
            _, e2, after = words[index + 1]
            # (A grouped head with detached cents, '8,463,157 .26', is left to the thousands-group rule.)
            if (_MARK_HEAD.fullmatch(word) and ',' not in word and _MARK_CENTS.fullmatch(after)
                    or _MARKED_HEAD.fullmatch(word) and _BARE_CENTS.fullmatch(after)):
                out.append((s, e2, word + after))
                index += 2
                continue
        out.append((s, e, word))
        index += 1
    return out


_CELL_HEAD = re.compile(r'^\d{1,3}(?:,\d{3})*$')
_CELL_TAIL = re.compile(r'^\d{3}(?:,\d{3})*[.,]\d{2}(?:\)|-|−|CR)?$')


def _rejoin_split_cells(tokens):
    """One amount the OCR split into two cells at a thousands separator ('168 | 802.21').

    Joined only when both cells are single-line, the head is digits in complete
    groups, the tail starts with a complete three-digit group and ends in cents,
    and the gap between them is under two character widths of the head (a count
    printed before an amount stands in its own column, several characters away).
    """
    out, index = [], 0
    while index < len(tokens):
        head = tokens[index]
        tail = tokens[index + 1] if index + 1 < len(tokens) else None
        if (tail is not None and head['cell'] is not tail['cell'] and head['line'] == tail['line'] == 0
                and head['last'] and tail['first'] and '\n' not in head['cell']['expected_text']
                and '\n' not in tail['cell']['expected_text']
                and _CELL_HEAD.fullmatch(head['t']) and _CELL_TAIL.fullmatch(tail['t'])):
            char = (head['x1'] - head['x0']) / max(len(head['t']), 1)
            gap = tail['x0'] - head['x1']
            if char > 0 and -char < gap < 2 * char and min(head['y1'], tail['y1']) > max(head['y0'], tail['y0']):
                text = head['t'] + ',' + tail['t']
                out.append(dict(tail, t=text, f=fold(text), x0=head['x0'], exact=False, joined=(head, tail)))
                index += 2
                continue
        out.append(head)
        index += 1
    return out


_PLAIN_AMOUNT = re.compile(r'^\d{1,3}(?:,\d{3})*[.,]\d{2}$|^\d+[.,]\d{2}$')


def _attach_detached_minus(tokens):
    """(C4) A minus printed alone in its own cell, directly before an unsigned amount that opens the next
    cell of the line, after a currency or operator marker ('+$', '$') or a label word, is that amount's
    sign: '+$ | - | 120.45' is -120.45."""
    out, index = [], 0
    while index < len(tokens):
        token = tokens[index]
        after = tokens[index + 1] if index + 1 < len(tokens) else None
        before = out[-1] if out else None
        if (after is not None and token['t'] in ('-', '−') and token['first'] and token['last']
                and after['first'] and after['line'] == token['line'] and after['cell'] is not token['cell']
                and _PLAIN_AMOUNT.match(after['t'])
                and (before is None or before['t'].endswith('$') or not re.search(r'\d', before['t']))):
            out.append(dict(after, t='-' + after['t'], f=fold('-' + after['t']), x0=token['x0'], exact=False))
            index += 2
            continue
        out.append(token)
        index += 1
    return out


def _pages(sources):
    """Rows of every page in reading order, each with its located tokens."""
    pages = {}
    for source in sources:
        heading = False
        payment_boxes = []
        for raw in source['rows']:
            tokens, width, located = [], None, True
            for cell in raw['cells']:
                cell_tokens, cell_width = _cell_tokens(cell, source.get('reading_rotation') or 0)
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
            row = dict(page=source['page_number'], source=source, raw=raw, tokens=tokens,
                       y0=min(t['y0'] for t in tokens), width=width, located=located)
            parts = _split_row(row, heading, payment_boxes) if located else None
            for part in parts or [row]:
                part['tokens'] = _attach_detached_minus(_rejoin_split_cells(part['tokens']))
                part['text'] = ' '.join(t['t'] for t in part['tokens'])
                pages.setdefault(source['page_number'], []).append(part)
            heading = heading or (_is_header(row) and any(column_role(label(t['t'])) == 'description'
                                                          for t in row['tokens']))
            payment_boxes.extend(_payment_box_headings(raw, source.get('reading_rotation') or 0))
    for rows in pages.values():
        rows.sort(key=lambda r: (r['y0'] if r['y0'] is not None else float('inf'), r['source']['table_index'],
                                 r['raw']['row_index'], r.get('x0', 0)))
        _mark_chart_scale(rows)
        _mark_wide_amount_boxes(rows)
    return pages


#: (E2) An amount stored alone in a box much wider than its characters (the reading joined a mark printed beside
#: it, a margin dash or a rule, into its box) has no reliable right edge: its column is found from its box's left
#: edge and the width its characters take in the page's other amount boxes. Off: the box's right edge is used.
WIDE_AMOUNT_BOXES = True
_BOXED_AMOUNT = re.compile(r'^[-−(]?(?:US\$|\$)?\d{1,3}(?:[,.]\d{3})*[.,]\d{2}(?:\)|-|−)?$')


def _mark_wide_amount_boxes(rows):
    """Amounts printed first in their box line whose placed width is at least 1.35 times the page's median width
    per character of one-amount boxes (at least eight such boxes on the page) get ``_left_x1``: their left edge
    plus the median width of their characters."""
    if not WIDE_AMOUNT_BOXES:
        return
    amounts = [t for row in rows for t in row['tokens'] if t['first'] and _BOXED_AMOUNT.match(t['t'])]
    boxed = [t for t in amounts if t['exact']]
    if len(boxed) < 8:
        return
    widths = sorted((t['x1'] - t['x0']) / len(t['t']) for t in boxed)
    median = widths[len(widths) // 2]
    if median <= 0:
        return
    for token in amounts:
        if (token['x1'] - token['x0']) / len(token['t']) >= 1.35 * median:
            token['_left_x1'] = token['x0'] + median * len(token['t'])


# ---------------------------------------------------------------------------
# One stored row holding several printed lines
# ---------------------------------------------------------------------------
#
# A drawn table without row rules is stored as one cell per box: the cell's
# text holds every printed line of the box, one per text line. Two forms are
# read as what they are, printed lines:
#
# * a movement table's body cell (under a heading naming date, description and
#   amount columns) whose dated lines each carry their own amount: every printed
#   line becomes a row of its own (wrapped description lines, section headings
#   and totals included; the reading decides what each is);
# * side-by-side boxes on one stored row (an account summary beside a payment
#   box) where a box prints label + amount lines: each box is read on its own,
#   so one box's label never runs into the other box's line.
#
# A line's horizontal positions inside its box are estimates (the stored cell
# has one rectangle); its vertical band is the line's share of the cell.


def _cell_lines(tokens):
    """[(line index in the cell's text, the line's tokens left to right)] of one cell's printed lines."""
    lines = {}
    for token in tokens:
        lines.setdefault(token['line'], []).append(token)
    return [(index, sorted(lines[index], key=lambda t: t['x0'])) for index in sorted(lines)]


def _dated_money_line(line):
    words = merged_dates(line)
    return bool(words) and _leading_date(words[0]['t'].rstrip('.,')) and any(_money_like(t['t']) for t in words[1:])


def _money_like(text):
    return money(text, 'dot') is not None or money(text, 'comma') is not None


def _label_amount_line(line):
    """A line printing words and then one amount at its end ('Previous Balance $1,234.56')."""
    return (len(line) >= 2 and _money_like(line[-1]['t'])
            and not any(_money_like(t['t']) for t in line[:-1]) and any(label(t['t']) for t in line[:-1])
            and not is_date_token(line[0]['t']))


def _split_row(row, under_heading, payment_boxes):
    """The printed lines (or boxes) of one stored row as rows of their own, or None to keep the row whole."""
    cells = [cell for cell in row['raw']['cells'] if cell['expected_text'].strip()]
    rotation = row['source'].get('reading_rotation') or 0
    by_cell = {}
    for token in row['tokens']:
        by_cell.setdefault(id(token['cell']), []).append(token)
    if under_heading and not rotation and len(cells) == 1 and '\n' in cells[0]['expected_text'].strip():
        lines = _cell_lines(by_cell.get(id(cells[0]), []))
        dated = [line for _, line in lines if _leading_date(merged_dates(line)[0]['t'].rstrip('.,'))]
        if (len(lines) >= 2 and any(_dated_money_line(line) for _, line in lines)
                and all(_dated_money_line(line) for line in dated)):
            count = len(cells[0]['expected_text'].split('\n'))
            return [_line_row(row, cells[0], line, index, count) for index, line in lines]
    if under_heading and not rotation and len(cells) >= 3:
        parts = _merged_total_line(row, cells, by_cell)
        if parts:
            return parts
    if len(cells) >= 2 and any(sum(_label_amount_line(line) for _, line in _cell_lines(by_cell.get(id(cell), []))) >= 2
                               for cell in cells):
        parts = []
        for cell in cells:
            own = by_cell.get(id(cell))
            if not own:
                continue
            part = dict(row, raw=dict(row['raw'], cells=[cell], box=cell['column_index']), tokens=own,
                        y0=min(t['y0'] for t in own), x0=min(t['x0'] for t in own))
            rect, _ = _rect(cell, rotation)
            if rect is not None and any(_beneath(rect, box) for box in payment_boxes):
                part['payment_box'] = True
            parts.append(part)
        return parts
    return None


def _merged_total_line(row, cells, by_cell):
    """(E10) A drawn table row holding the table's last movement line and its printed total line, or None.

    A ruled table with no rule between its last movement and its ``TOTAL`` line stores both printed lines
    in one row of boxes: the description box reads '<description>' over 'TOTAL', the amount boxes the
    movement's amount over the column totals, and a box printing one figure belongs to one of the two
    lines. Read as one movement it has two amounts and no proof can place them. Split only when:

    * the row's first box is one line opening with a date (a movement), and one other box prints two or
      more lines of which only the last is a column-total label;
    * every box of figures prints one line, or as many lines as that box (one per printed line);
    * every other box prints one line.

    A box of figures with one line per printed line is split line by line; a box with one figure belongs
    to the movement line when it is the row's rightmost box of figures (the balance column, which the
    total line does not print) and to the total line otherwise. The proof checks the result twice: the
    movement against the running balance, the total line against the sums of the column.
    Returns ``[movement row, total row]``.
    """
    ordered = sorted(cells, key=lambda c: (_rect(c)[0] or [0])[0])
    first = by_cell.get(id(ordered[0]), [])
    if not first or len(_cell_lines(first)) != 1 or not _leading_date(merged_dates(_cell_lines(first)[0][1])[0]['t'].rstrip('.,')):
        return None
    texts = {id(c): c['expected_text'].strip('\n').split('\n') for c in cells}
    if any(not line.strip() for lines in texts.values() for line in lines) or any(
            c['expected_text'].strip('\n') != c['expected_text'] for c in cells):
        return None
    total_cells = [c for c in cells if len(texts[id(c)]) >= 2 and label(texts[id(c)][-1]) in INDEX['column_total']
                   and not any(label(line) in INDEX['column_total'] for line in texts[id(c)][:-1])]
    if len(total_cells) != 1:
        return None
    total_cell = total_cells[0]
    count = len(texts[id(total_cell)])
    figures = [c for c in cells if c is not total_cell and all(
        all(_money_like(word) for word in line.split()) for line in texts[id(c)])]
    if not figures:
        return None
    rightmost = max(figures, key=lambda c: (_rect(c)[0] or [0])[0])
    movement, total = [], []
    for cell in cells:
        tokens = by_cell.get(id(cell), [])
        lines = texts[id(cell)]
        if cell is total_cell or (cell in figures and len(lines) == count and count > 1):
            split = _cell_lines(tokens)
            if len(split) != count:
                return None
            movement.append((cell, [t for _, line in split[:-1] for t in line], 0, count - 1, count))
            total.append((cell, split[-1][1], count - 1, count, count))
        elif len(lines) == 1:
            (movement if cell not in figures or cell is rightmost else total).append((cell, tokens, None, None, None))
        else:
            return None
    band = next(t for t in by_cell[id(total_cell)] if t['line'] == count - 1)

    def part(pieces, index, at_total):
        own_cells, own = [], []
        for cell, tokens, start, stop, of in pieces:
            if start is None:
                part_cell = cell
            else:
                locator = dict(cell['locator'])
                x0, y0, x1, y1 = locator['rect']
                locator['rect'] = [x0, y0 + (y1 - y0) * start // of, x1, max(y0 + (y1 - y0) * stop // of, y0 + 1)]
                part_cell = dict(cell, expected_text='\n'.join(cell['expected_text'].split('\n')[start:stop]),
                                 locator=locator, cell_line=dict(line=start, lines=of))
            own_cells.append(part_cell)
            for t in tokens:
                moved = dict(t, cell=part_cell, line=t['line'] - (start or 0))
                if at_total and start is None:
                    moved.update(y0=band['y0'], y1=band['y1'])
                own.append(moved)
        raw = dict(row['raw'], cells=own_cells, line=index)
        return dict(row, raw=raw, tokens=sorted(own, key=lambda t: (t['line'], t['x0'])),
                    y0=min(t['y0'] for t in own), x0=min(t['x0'] for t in own), split=(id(row['raw']), index))

    if not any(t for _, tokens, *_ in total for t in tokens):
        return None
    return [part(movement, 0, False), part(total, count - 1, True)]


def _line_row(row, cell, tokens, index, count):
    """One printed line of a multi-line cell as a row: its own cell (the line's text, the line's band of the
    cell's rectangle) and its tokens renumbered as the only line."""
    locator = dict(cell['locator'])
    x0, y0, x1, y1 = locator['rect']
    top, bottom = y0 + (y1 - y0) * index // count, y0 + (y1 - y0) * (index + 1) // count
    locator['rect'] = [x0, top, x1, max(bottom, top + 1)]
    line_cell = dict(cell, expected_text=' '.join(cell['expected_text'].split('\n')[index].split()),
                     locator=locator, cell_line=dict(line=index, lines=count))
    own = [dict(t, cell=line_cell, line=0) for t in tokens]
    raw = dict(row['raw'], cells=[line_cell], line=index)
    return dict(row, raw=raw, tokens=own, y0=min(t['y0'] for t in own), x0=min(t['x0'] for t in own),
                split=(id(row['raw']), index))


def _payment_box_headings(raw, rotation):
    boxes = []
    for cell in raw['cells']:
        if label(cell['expected_text']) in {label(h) for h in PAYMENT_BOX_HEADINGS}:
            rect, _ = _rect(cell, rotation)
            if rect is not None:
                boxes.append(rect)
    return boxes


def _beneath(rect, box):
    """A cell's rectangle printed under a box heading's: below it, inside its horizontal extent."""
    return rect[1] >= box[3] - 1 and rect[0] >= box[0] - 1 and rect[2] <= box[2] + 1


_SCALE_VALUE = re.compile(r'^[-−]?\$?(\d{1,3}(?:,\d{3})*|\d+)[.,]00$')


def _mark_chart_scale(rows):
    """(C11) A chart's axis printed beside summary labels: four or more whole values, each alone at the end
    of its line's cells in one column (same right edge), on successive lines, whose sizes step by one
    constant amount (75, 150, 225, 300). They are tick labels, never amounts: marked so no reading takes
    them as money."""
    candidates = []
    for row in rows:
        for token in row['tokens']:
            m = _SCALE_VALUE.match(token['t'].rstrip('?'))
            alone = sum(1 for other in row['tokens'] if other['cell'] is token['cell']) == 1
            if m and alone and row['width']:
                candidates.append((token, int(m[1].replace(',', '')), row['width']))
    used = set()
    for token, _, width in candidates:
        if id(token) in used:
            continue
        column = sorted((c for c in candidates if abs(c[0]['x1'] - token['x1']) <= width * 0.01),
                        key=lambda c: c[0]['y0'])
        for chain in _arithmetic_chains(column):
            for item in chain:
                item[0]['axis'] = True
                used.add(id(item[0]))


def _arithmetic_chains(column):
    """Runs of at least four entries whose values, in size order, step by one constant amount."""
    ordered = sorted(column, key=lambda c: c[1])
    chains, best = [], []
    for step in {b[1] - a[1] for a, b in zip(ordered, ordered[1:])} - {0}:
        for start in ordered:
            chain = [start]
            while True:
                following = next((c for c in ordered if c[1] == chain[-1][1] + step), None)
                if following is None:
                    break
                chain.append(following)
            if len(chain) > len(best):
                best = chain
    # An axis prints each tick once, one under another: every value of the run occurs once in the column
    # and no other value of the column lies between them.
    counts = {}
    for item in column:
        counts[item[1]] = counts.get(item[1], 0) + 1
    positions = sorted(column.index(item) for item in best)
    if (len(best) >= 4 and all(counts[item[1]] == 1 for item in best)
            and positions == list(range(positions[0], positions[0] + len(positions)))):
        chains.append(best)
    return chains


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


# A dot-decimal amount whose decimal point the scan printed or read as a comma ('147,382,26'):
# comma thousands groups, so it can only be the dot convention.
_WORN = re.compile(r'^(?P<lead>[-−+(]?)\s*(?:US\$|\$|€|£|¥)?\s*(?P<lead2>[-−]?)(?P<int>\d{1,3}(?:,\d{3})*),(?P<frac>\d{2})'
                   r'(?P<trail>\)|-|−|CR)?(?:MN|M\.N\.|MXN|USD|EUR|DLS)?$')
_DOT_THOUSANDS = re.compile(r'\d,\d{3}(?:,\d{3})*\.\d{2}(?:\D|$)')
_COMMA_THOUSANDS = re.compile(r'\d\.\d{3}(?:\.\d{3})*,\d{2}(?:\D|$)')


def separator_style(pages):
    """'dot' or 'comma' decimals for the whole document (C1); None when mixed.

    'dot_worn': the document prints dot decimals with comma thousands, and some of
    its decimal points are printed or read as commas (scans): '1,234.56' and
    '147,382,26' both occur and no amount uses dot thousands with a decimal comma
    ('1.234,56'). Such a document is read in the dot convention, a decimal comma
    included; values are the printed digits either way and the proof decides.
    """
    dot = comma = dot_thousands = comma_thousands = 0
    for rows in pages.values():
        for row in rows:
            for token in row['tokens']:
                text = token['t']
                if _DOT.fullmatch(text) and _UNAMBIGUOUS_DOT.search(text) and not re.search(r'\d\.\d{3}', text):
                    dot += 1
                    dot_thousands += bool(_DOT_THOUSANDS.search(text))
                elif _COMMA.fullmatch(text) and _UNAMBIGUOUS_COMMA.search(text) and not re.search(r'\d,\d{3}', text):
                    comma += 1
                elif _WORN.fullmatch(text) and re.search(r'\d,\d{3},\d{2}$', text):
                    comma += 1
                if _COMMA.fullmatch(text) and _COMMA_THOUSANDS.search(text):
                    comma_thousands += 1
    if dot and comma:
        if dot >= 20 * comma:
            return 'dot'
        if comma >= 20 * dot:
            return 'comma'
        return 'dot_worn' if dot_thousands and not comma_thousands and dot >= 2 * comma else None
    return 'comma' if comma else 'dot'


def money(text, style, exponent=2):
    """Signed minor units of one printed amount token, or None."""
    dot = style in ('dot', 'dot_worn')
    if exponent == 0:
        # Whole-unit currencies (yen) may print ".00": accepted only when the fraction is zero (C3).
        printed = (_DOT if dot else _COMMA).fullmatch(text) if style else None
        if printed and printed['frac'] == '00':
            text = text[:printed.start('frac') - 1] + text[printed.end('frac'):]
        match = _WHOLE.fullmatch(text)
    else:
        match = (_DOT if dot else _COMMA).fullmatch(text)
        if not match and style == 'dot_worn':
            match = _WORN.fullmatch(text)
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


_OCR_ZERO = re.compile(r'(?<![A-Z])[OQ](?=\d)|(?<=\d)[OQ](?![A-Z])')
_OCR_MONTH_O = re.compile(r'(?<=[A-Z]{2})0(?=$|[-/ .])|(?<=[-/ .])0(?=[A-Z]{2})')


def _ocr_date(text):
    """A date token with the scan's letter / digit confusions undone ('O1-JUN-2021', 'Q1-JUN-2021', 'L1-JUN-2021',
    '02-AG0-2021', '03-0CT-2024'): O or Q counts as 0 only between digits or before one, 0 as O only at
    either end of a month word. Only used when the token reads as no date as printed."""
    # A tilde read for the hyphen between a date's parts ('23-FEB~2024').
    text = re.sub(r'(?<=[A-Z0-9])~(?=[A-Z0-9])', '-', text)
    # A day's leading 1 read as a letter at the start of a date ('L1-MAR-2024', 'I5/03/2024').
    text = re.sub(r'^[LI|](?=\d[-/.])', '1', text)
    text = _OCR_MONTH_O.sub('O', _OCR_ZERO.sub('0', text))
    if DATE_SLASH_MARKS:
        # A slash between a day and a month name read as another stroke or doubled ('07\\MAR', '07)MAR',
        # '07/)MAR'): the separator carries no part of the date.
        text = re.sub(r'^(\d{1,2})(?:/?[\\)|]|[\\)|]/)(?=[A-Z]{3,10}$)', r'\1/', text)
    return text


# (B2) A day-and-month date whose slash the scan read as a backslash, a closing parenthesis or a bar, or doubled
# with one, reads as that date (``_ocr_date``). Off: such a token is no date, as before.
DATE_SLASH_MARKS = True


@lru_cache(maxsize=262144)
def _date_parts(text):
    """Possible (day, month, year|None, order) readings of one date token."""
    parts = _date_parts_printed(_dnorm(text).strip(',.:;'))
    if not parts:
        repaired = _ocr_date(_dnorm(text).strip(',.:;'))
        if repaired != _dnorm(text).strip(',.:;') and re.search(r'\d', repaired):
            parts = _date_parts_printed(repaired)
    return parts


def _date_parts_printed(f):
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
# "03 FEB 26/27 FEB 26", "03-FEB-26/27-FEB-26": two day-month-year dates joined by a slash. The OCR
# can split the month word with one space ("27-F EB-26"); the joined letters must name a month.
_SLASH_DATE = r'\d{1,2}[\s-]+[A-Z](?: ?[A-Z]){2,9}\.?[\s-]+\d{2}(?:\d{2})?'
_SLASH_RANGE = re.compile(r'\b(' + _SLASH_DATE + r')\s*/\s*(' + _SLASH_DATE + r')\b')
_SHARED_MONTH = re.compile(r'\b(\d{1,2})\s+AL\s+(\d{1,2})\s+DE\s+([A-Z]{3,10})\s+(?:DE\s+|DEL\s+)?(\d{4})\b')
# "MAR.24-APR.23,2024", "Mar 24 - Apr 23, 2024": month-day to month-day, one year printed for both.
_SHARED_YEAR = re.compile(r'\b([A-Z]{3,10})\.?\s?(\d{1,2})\s*(?:-|TO|THROUGH|THRU)\s*([A-Z]{3,10})\.?\s?(\d{1,2}),?\s*(\d{4})\b')


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
    f = _ocr_date(re.sub(r'[^A-Z0-9/.,\- ]+', ' ', _dnorm(text)))
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
            pieces = re.match(r'(\d{1,2})[\s-]+([A-Z ]+?)\.?[\s-]+(\d{2,4})$', part)
            d, month, year = pieces[1], pieces[2].replace(' ', ''), pieces[3]
            year = int(year) + (2000 if len(year) == 2 else 0)
            dates.append(_calendar(year, MONTHS.get(month, 0), int(d)) if month in MONTHS else None)
        if all(dates) and dates[0] <= dates[1] and (dates[1] - dates[0]).days <= MAX_PERIOD_DAYS:
            found.append(tuple(dates))
    for m in _SHARED_YEAR.finditer(f):
        if m[1] in MONTHS and m[3] in MONTHS:
            year = int(m[5])
            # The printed year is the end's; a start month after the end month is in the year before.
            start = _calendar(year - (MONTHS[m[1]] > MONTHS[m[3]]), MONTHS[m[1]], int(m[2]))
            end = _calendar(year, MONTHS[m[3]], int(m[4]))
            if start and end and start <= end and (end - start).days <= MAX_PERIOD_DAYS:
                found.append((start, end))
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
    if token.get('axis'):
        return None
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
    if row.get('stacked_pairs') is not None:
        # A summary printed as a table: each amount's label is the heading printed over it (D7).
        return row['stacked_pairs']
    pairs, words, values = [], [], []
    previous = None
    width = row.get('width') or 1
    if row.get('payment_box'):
        # The remittance box beside a card summary repeats its new balance: never a control (D7).
        return []
    for token in merged_dates(row['tokens']):
        kind = _value_kind(token, style, exponent)
        if kind == 'date' or ' ' in token['t'] and is_date_token(token['t']):
            continue
        if kind in ('money', 'count'):
            values.append((kind, token))
            previous = token
            continue
        if not label(token['t']) or token['t'] in ('+/-', '+/−', '±'):
            # Printed signs between a label and its value ("=", "+", "+/-") are neither.
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
    """A movement-heading word's role: the shared vocabulary, then the active profile's words. A profile's
    ``ignore`` words come first: an amount column the profile names as not the movement's effect (a gross
    amount beside the net one) is never read as the amount, whatever the shared vocabulary says."""
    profile = _PROFILE.get()
    if profile and text in {label(w) for w in ((profile.get('columns') or {}).get('ignore') or ())}:
        return 'ignore'
    role = COLUMN_INDEX.get(text)
    if role is None and profile:
        role = next((r for r, words in (profile.get('columns') or {}).items() if text in {label(w) for w in words}), None)
    return role


def _role_of(text, liability):
    extra = _profile_role(text, liability)
    if extra:
        return extra
    if liability:
        # Card summaries print components per direction, not one total (D7), or a net of both.
        if text in INDEX['credit_component']:
            return 'credit_component'
        if text in INDEX['debit_component']:
            return 'debit_component'
        if text in INDEX['net_component']:
            return 'net_component'
        if text in INDEX['section_total']:
            return 'section_total'
    for role in ('opening', 'closing', 'subtotal', 'column_total', 'credit_total', 'debit_total'):
        if text in INDEX[role]:
            return role
    for role in ('opening', 'closing', 'subtotal', 'credit_total', 'debit_total'):
        if any(pattern.fullmatch(text) for pattern in FUZZY_INDEX[role]):
            return role
    # A dot or comma the scan glued to a word inside the label ('SALDO. INICIAL') (F1).
    bare = ' '.join(word.strip('.,') for word in text.split())
    if bare != text and bare:
        return _role_of(bare, liability)
    return None


# ---------------------------------------------------------------------------
# Page facts: period, account, numbering, currency, institution, holder
# ---------------------------------------------------------------------------

def _row_is_movement(row, style, exponent):
    tokens = merged_dates(row['tokens'])
    if not tokens:
        return False
    if not _leading_date(tokens[0]['t'].rstrip('.,')):
        return False
    return any(_value_kind(t, style, exponent) == 'money' for t in tokens)


def _day_only(text):
    return _DAY_COLUMN.get() and bool(re.fullmatch(r'\d{1,2}', text)) and 1 <= int(text) <= 31


def _leading_date(text):
    """The first printed word of a dated line: a date, or the day alone under a day column (B2)."""
    return is_date_token(text) or _day_only(text)


def page_facts(rows, style, exponent=2, order=None):
    """``order``: the document's day-month order ('dmy'/'mdy'), used only for a period whose printed dates
    read as a valid range in both orders (B3)."""
    facts = dict(periods=set(), labelled_periods=set(), accounts={}, numbering=set(), currencies=set(),
                 liability=False, legal=set(), holders=set())
    for row in rows:
        if not row['tokens']:
            continue
        text = row['text']
        folded = fold(text)
        movement = _row_is_movement(row, style, exponent)
        if not movement:
            # (B1) A range printed for an interest or dividend accrual ('for the dividend period from ...
            # through ...') dates that accrual, not the statement.
            ranges = [] if _ACCRUAL_PERIOD.search(folded) else (
                period_ranges(text) or (period_ranges(text, order) if order else []))
            if ranges:
                facts['periods'].update(ranges)
                if any(word in folded.split() or folded.startswith(word) for word in PERIOD_WORDS):
                    facts['labelled_periods'].update(ranges)
        for m in PAGE_NUMBERING.finditer(folded):
            # A page number above the printed count ('HOJA 10DE 2' for 'HOJA 1 DE 2') is a misreading,
            # not a page number: the page counts as unnumbered (A3).
            if 1 <= int(m[1]) <= int(m[2]):
                facts['numbering'].add((int(m[1]), int(m[2])))
        if any(phrase in folded for phrase in (fold(p) for p in LIABILITY_EVIDENCE)):
            facts['liability'] = True
        if not movement:
            _accounts(row, facts['accounts'])
            _currency(row, facts['currencies'])
            if any(word in folded for word in INSTITUTION_WORDS) and 6 <= len(folded) <= 160:
                facts['legal'].add(folded)
            _holder_label(row, facts['holders'])
    _two_line_period(rows, facts)
    _stacked_period_label(rows, facts)
    _derived_period(rows, style, exponent, facts)
    return facts


_ACCRUAL_PERIOD = re.compile(r'\b(?:DIVIDEND|INTEREST)S?\s+(?:PERIOD|CYCLE)\b')


def _stacked_period_label(rows, facts):
    """(B1) A period label printed alone in a cell ('Statement Period') with the cell directly below it,
    horizontally overlapping, printing exactly one range: that range is the labelled period."""
    located = [r for r in rows if r['tokens'] and r['y0'] is not None]
    labels = {fold(word) for word in PERIOD_WORDS if len(word.split()) > 1}
    for upper, lower in zip(located, located[1:]):
        for top in upper['raw']['cells']:
            rect = (top.get('locator') or {}).get('rect')
            if not rect or ' '.join(fold(top['expected_text']).split()) not in labels:
                continue
            for bottom in lower['raw']['cells']:
                other = (bottom.get('locator') or {}).get('rect')
                if not other or not (other[0] < rect[2] and rect[0] < other[2]):
                    continue
                found = period_ranges(bottom['expected_text'])
                if len(found) == 1 and not _ACCRUAL_PERIOD.search(fold(bottom['expected_text'])):
                    facts['periods'].add(found[0])
                    facts['labelled_periods'].add(found[0])


_PERIOD_FROM = re.compile(r'^(?:PERIODO\s*:?\s*)?DEL\s+(\S+)$')
_PERIOD_TO = re.compile(r'^AL\s+(\S+)$')


def _two_line_period(rows, facts):
    """(B1) A period printed across two lines of one column: a cell 'Del <date>' with the cell directly
    below it, horizontally overlapping, 'al <date>'. Labelled (the range words are printed)."""
    located = [r for r in rows if r['tokens'] and r['y0'] is not None]
    for upper, lower in zip(located, located[1:]):
        for top in upper['raw']['cells']:
            m = _PERIOD_FROM.match(' '.join(fold(top['expected_text']).split()))
            rect = (top.get('locator') or {}).get('rect')
            if not m or not rect:
                continue
            for bottom in lower['raw']['cells']:
                n = _PERIOD_TO.match(' '.join(fold(bottom['expected_text']).split()))
                other = (bottom.get('locator') or {}).get('rect')
                if n and other and other[0] < rect[2] and rect[0] < other[2]:
                    for period in period_ranges('DEL %s AL %s' % (m[1], n[1])):
                        facts['periods'].add(period)
                        facts['labelled_periods'].add(period)


# A cut date and the number of days in the period, both printed on a statement's heading ('CORTE AL
# 31/01/2024', 'FECHA DE CORTE 31/01/2024', 'DIAS DEL PERIODO 31'; Mexican layouts that print the period
# itself only on a later page or not at all). One letter of PERIODO may be misread by the scan.
_CUT_DATE = re.compile(r'\b(?:FECHA DE )?CORTE(?: AL)?\s+(\d{1,2}/\d{1,2}/\d{4})\b')
_PERIOD_DAYS = re.compile(r'\bDIAS (?:DEL|EN EL) PER[A-Z]ODO\s+(\d{1,2})\b')


def _derived_period(rows, style, exponent, facts):
    """(B1) A page printing exactly one cut date and one day count, and no labelled period of its own,
    prints the period (cut - days + 1, cut). Recorded as labelled (two printed facts) and as derived:
    a labelled period printed elsewhere in the same printed page run wins over it (_segments)."""
    if facts['labelled_periods']:
        return
    cuts, days = set(), set()
    for row in rows:
        if not row['tokens'] or _row_is_movement(row, style, exponent):
            continue
        folded = fold(row['text'])
        cuts.update(m[1] for m in _CUT_DATE.finditer(folded))
        days.update(int(m[1]) for m in _PERIOD_DAYS.finditer(folded))
    if len(cuts) != 1 or len(days) != 1:
        _closing_only_period(rows, style, exponent, facts)
        return
    end, count = _full_date(next(iter(cuts)), 'dmy'), next(iter(days))
    if end is None or not 1 <= count <= MAX_PERIOD_DAYS:
        return
    period = (end - timedelta(days=count - 1), end)
    facts['periods'].add(period)
    facts['labelled_periods'].add(period)
    facts['derived_periods'] = {period}


_CLOSING_DATE = re.compile(r'\b(?:' + '|'.join(re.escape(fold(w)) for w in sorted(CLOSING_DATE_LABELS, key=len, reverse=True))
                           + r')\s+(\d{1,2}/\d{1,2}/\d{4})\b')
_CYCLE_DAYS = re.compile(r'\b(?:' + '|'.join(re.escape(fold(w)) for w in CYCLE_DAYS_LABELS) + r')\s+(\d{1,2})\b')


def _closing_only_period(rows, style, exponent, facts):
    """(B1) A card statement printing only its closing date ('Statement Closing Date') and the days in its
    billing cycle, exactly one of each on the page. The closing date is printed; the start is not: it is
    the closing date less the printed days plus one, recorded as derived (``closing_only``), never as a
    printed date. The closing date is read in the statement's one date order: the library profile's, or
    a date that reads the same way in both orders."""
    closings, days = set(), set()
    for row in rows:
        if not row['tokens'] or _row_is_movement(row, style, exponent):
            continue
        folded = fold(row['text'])
        closings.update(m[1] for m in _CLOSING_DATE.finditer(folded))
        days.update(int(m[1]) for m in _CYCLE_DAYS.finditer(folded))
    if len(closings) != 1 or len(days) != 1:
        return
    end, count = _full_date(next(iter(closings)), (_PROFILE.get() or {}).get('date_order')), next(iter(days))
    if end is None or not 1 <= count <= MAX_PERIOD_DAYS:
        return
    period = (end - timedelta(days=count - 1), end)
    facts['periods'].add(period)
    facts['labelled_periods'].add(period)
    facts['derived_periods'] = {period}
    facts['closing_only'] = {period}


_ACCOUNT_VALUE = re.compile(r'^(?:\*{2,}|X{2,}|#)?[\d][\d -]{3,30}\d$|^(?:\*{2,}|X{2,})\d{3,6}$')


def _accounts(row, found):
    cells = [c['expected_text'] for c in row['raw']['cells']]
    texts = [' '.join(cells)] + cells
    for text in texts:
        # A vertically merged label column is zipped with its values elsewhere.
        if '\n' in text:
            continue
        folded = fold(text)
        for name, rank in _ACCOUNT_LABELS_LONGEST:
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
            # The whole leading run of digit groups: OCR and print both split long numbers (CLABE) into groups.
            run = []
            for part in value.split():
                if not re.fullmatch(r'[\d-]+|(?:\*{2,}|X{2,})\d{3,6}', part):
                    break
                run.append(part)
            first = ''.join(run)
            candidate = first if _ACCOUNT_VALUE.fullmatch(first) else ''
            digits = re.sub(r'\D', '', candidate)
            if candidate and 6 <= len(digits) <= 20 or candidate.startswith(('*', 'X')):
                found.setdefault(candidate.replace(' ', ''), set()).add(rank)
            break
    # Label cell followed by a value cell on the same row.
    raw = row['raw']['cells']
    for index, cell in enumerate(raw[:-1]):
        folded = label(cell['expected_text'])
        for name, rank in _ACCOUNT_LABELS_LONGEST:
            if folded == label(name):
                # The value can continue in the next cells as further digit groups.
                groups = []
                for following in raw[index + 1:]:
                    # A quote mark the scan put before or after the digits is not part of the number (F2).
                    text_value = following['expected_text'].strip().strip('\'\u2018\u2019`"').strip()
                    if not re.fullmatch(r'[\d -]+', text_value):
                        break
                    groups.append(text_value.replace(' ', ''))
                value = ''.join(groups)
                digits = re.sub(r'\D', '', value)
                # Under a full account-number label four printed digits are enough (statements printing only
                # the last digits of the number), as for a stacked label (_stacked_accounts).
                if value and (_ACCOUNT_VALUE.fullmatch(value) or rank >= 3 and re.fullmatch(r'\d{4,5}', value)) \
                        and (4 if rank >= 3 else 6) <= len(digits) <= 20 and not value.startswith('0' * 4):
                    found.setdefault(value, set()).add(rank)
                break


_ACCOUNT_LABELS_LONGEST = sorted(ACCOUNT_LABELS, key=lambda item: len(item[0]), reverse=True)


def _stacked_accounts(rows):
    """[(value, rank)] of account labels printed as a column heading with the value in the line below (A6).

    The label is a whole cell ('ACCOUNT NUMBER' above '2489'); the value is the
    cell of the next line that overlaps it horizontally, digits only. Under a
    full account-number label (rank 3) four printed digits are enough (statements
    printing only the last digits of the number); otherwise the usual 6-20.
    """
    names = {label(name): rank for name, rank in ACCOUNT_LABELS}
    located = [r for r in rows if r['tokens'] and r['y0'] is not None]
    found = []
    for index, row in enumerate(located):
        rotation = row['source'].get('reading_rotation') or 0
        for cell in row['raw']['cells']:
            rank = names.get(label(cell['expected_text']))
            rect, _ = _rect(cell, rotation)
            if rank is None or rect is None:
                continue
            height = rect[3] - rect[1]
            below = next((r for r in located[index + 1:] if r['y0'] > rect[1] + height * 0.5), None)
            if below is None or below['y0'] - rect[3] > height * 1.5:
                continue
            for other in below['raw']['cells']:
                orect, _ = _rect(other, rotation)
                text = other['expected_text'].strip()
                if orect is None or orect[2] <= rect[0] or orect[0] >= rect[2] or not re.fullmatch(r'[\d -]+', text):
                    continue
                digits = re.sub(r'\D', '', text)
                if (4 <= len(digits) <= 20 if rank >= 3 else 6 <= len(digits) <= 20) and not text.startswith('0' * 4):
                    found.append((text.replace(' ', ''), rank))
                break
    return found


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


def _one_substitution(read, word):
    """A word of six or more letters read with exactly one other character in its place (F1, OCR)."""
    return read == word or (len(read) == len(word) >= 6 and sum(a != b for a, b in zip(read, word)) == 1)


_MULTIWORD_CURRENCIES = [(name.split(), code) for name, code in CURRENCY_NAMES.items() if ' ' in name]


def labelled_currency(key, value):
    """The currency a currency label's value names, or ''.

    The value is a currency name ('MONEDA: PESOS'); the label word and the value
    together are one ('Moneda: Nacional' = moneda nacional); or, after the label
    only, a multi-word currency name read with at most one substituted character
    per word of six or more letters ('MONEDA NACTONAL'), when exactly one
    currency is that close.
    """
    words = value.split()
    for size in (3, 2, 1):
        head = ' '.join(words[:size])
        if len(words) >= size and head in CURRENCY_NAMES:
            return CURRENCY_NAMES[head]
    for size in (2, 1):
        joined = ' '.join([key] + words[:size])
        if len(words) >= size and joined in CURRENCY_NAMES:
            return CURRENCY_NAMES[joined]
    close = set()
    for candidate in (words, [key] + words):
        for name, code in _MULTIWORD_CURRENCIES:
            read = candidate[:len(name)]
            if len(read) == len(name) and all(_one_substitution(r, w) for r, w in zip(read, name)):
                close.add(code)
    return close.pop() if len(close) == 1 else ''


def _currency(row, found):
    folded = fold(row['text'])
    for name in CURRENCY_LABELS:
        key = fold(name)
        # Every occurrence of the label counts: its value can repeat the label word ("MONEDA: MONEDA NACIONAL").
        for m in re.finditer(r'(?:^|(?<=\s))' + re.escape(key) + r'\s*:?\s+(?=(.+)$)', folded):
            code = labelled_currency(key, m[1].strip())
            if code:
                found.add(code)


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


def _heading_pages(segment_pages, facts):
    """The statement's first pages, up to and including the first page printing its period."""
    heading = []
    for page in segment_pages[:3]:
        heading.append(page)
        if facts[page]['periods']:
            break
    return heading


def _identity_rows(segment_pages, pages, facts, style):
    """[(page, rows)] of the statement's heading pages, cut at its first movement table (A8).

    The holder is printed above the movements: once a movement-table heading or a
    movement line has been printed, every later line (the rest of that page and
    every later page) is movement text, whose description lines name transfer
    counterparties and their accounts, never the holder.
    """
    result = []
    for page in _heading_pages(segment_pages, facts):
        rows = pages[page]
        cut = next((row['y0'] for row in rows if row['tokens'] and row['y0'] is not None
                    and (_is_header(row) or _row_is_movement(row, style or 'dot', 2))), None)
        if cut is None:
            result.append((page, rows))
            continue
        result.append((page, [row for row in rows if row['y0'] is not None and row['y0'] < cut]))
        break
    return result


def _section_holder(section_pages, pages, facts, style=None):
    """Holder from the statement's heading pages only (A8): up to the first page printing the period,
    and above the statement's first movement table.

    Legal pages print other people's names under the same labels (a complaints
    officer as "Titular"), so labels elsewhere never count. A labelled name and
    the addressee block that disagree give no holder (a person decides).
    """
    heading = _identity_rows(section_pages, pages, facts, style)
    labelled = set()
    for _, rows in heading:
        for row in rows:
            if row['tokens'] and len(row['text']) <= 160:
                _holder_label(row, labelled)
    addressed = ''
    for _, rows in heading:
        addressed = address_holder(rows, style)
        if addressed:
            break
    if len(labelled) > 1:
        return ''
    if labelled:
        name = next(iter(labelled))
        if addressed and fold(addressed) not in fold(name) and fold(name) not in fold(addressed):
            return ''
        return name
    return (addressed or _receipt_holder(section_pages, pages, heading) or _stub_holder(heading, pages, style)
            or _addressless_holder(section_pages, pages, heading, style)
            or _unanchored_holder(section_pages, pages, heading, style))


# (A8) An addressee block printed without its address (the production redacted it) gives the holder
# only with a second printed fact; see _addressless_holder. False: such statements wait for a person.
ADDRESSLESS_HOLDER = True
# Only letters and the marks of a printed name; at most three lines (joint and custodial holders).
_NAME_LINE = re.compile(r"^[A-Z][A-Z.,'&/-]*(?: [A-Z][A-Z.,'&/-]*)+$")
# A company name may hold a word of a letter followed by figures ('K7'); never a word of figures alone.
_COMPANY_LINE = re.compile(r"^[A-Z][A-Z0-9.,'&/-]*(?: [A-Z][A-Z0-9.,'&/-]*)+$")
# A mailing line of figures alone (a mail sequence or the production's placeholder for a redacted line).
_MAILING_FIGURES = re.compile(r'^\d{5,}$')


def _name_line(text, company=False):
    words = ' '.join(fold(text).split())
    return bool((_COMPANY_LINE if company else _NAME_LINE).match(words) and _name_like(words)
                and not words.endswith(':') and not any(word in words for word in INSTITUTION_WORDS))


def _addressless_holder(section_pages, pages, heading, style):
    """(A8) The top line of an addressee block printed with no address, or ''.

    Productions redact the holder's address: the window then prints the name
    lines alone, with no postal-code line to show they are an address block. The
    block is accepted only when all of these hold:

    * it is one to three name lines (letters only, no label, bank or heading
      word) at one left edge in the left half of the statement's first page,
      above its first movement table, with no other line at that edge directly
      above (other than the mailing line below) or below it;
    * a second printed fact marks it as the addressee: either a mailing line of
      figures alone printed at the block's edge directly above it (a mail
      sequence or the redaction's placeholder), or its top line printed again
      as a whole line elsewhere in the statement (page headers and payment
      coupons reprint the addressee);
    * the page's reading checked its printed lines and none near the block is
      unread (a lost first name line would make the second one look like the
      top); a page whose reading did not check gives no holder this way;
    * every block found this way names the same holder.
    """
    if not ADDRESSLESS_HOLDER or not heading:
        return ''
    page, rows = heading[0]
    source = next((row['source'] for row in pages[page] if row['tokens']), None)
    checked = (source or {}).get('printed_lines') or {}
    if source is None or source.get('reading_rotation') or checked.get('checked') is not True:
        return ''
    unread = [rect for rect in checked.get('unread') or [] if isinstance(rect, list) and len(rect) == 4]
    # Each line's cells at its left edge: their own position, not the stored row's (OCR can store a name
    # line and a summary-box line beside it as one row).
    lines = []
    for row in rows:
        if row['tokens'] and row['width']:
            x = min(t['x0'] for t in row['tokens'])
            aligned = _aligned_tokens(row, x)
            if aligned:
                lines.append(dict(row=row, x=x, y=min(t['y0'] for t in aligned),
                                  height=max(t['y1'] - t['y0'] for t in aligned), text=_aligned_text(row, x)))
    found = set()
    for line in lines:
        row, x, y, height = line['row'], line['x'], line['y'], line['height']
        if x > row['width'] * 0.5 or not _name_line(line['text']):
            continue
        tolerance = row['width'] * 0.015
        same_edge = [other for other in lines if abs(other['x'] - x) <= tolerance and other is not line]
        above = [other for other in same_edge if other['y'] < y]
        nearest_above = max(above, key=lambda other: other['y']) if above else None
        if nearest_above is not None and y - nearest_above['y'] <= height * 2.6 and _name_line(nearest_above['text']):
            continue  # not the block's top line
        if nearest_above is not None and y - nearest_above['y'] <= height * 2.6 and any(
                word in ' '.join(fold(nearest_above['text']).split()) for word in INSTITUTION_WORDS):
            continue  # the issuer's own name block continued ('<bank>, S.A.', '<financial group>')
        block = [line]
        for other in sorted(same_edge, key=lambda other: other['y']):
            if other['y'] > block[-1]['y'] and other['y'] - block[-1]['y'] <= height * 2.6:
                if not _name_line(other['text']) or len(block) == 3:
                    block = None
                    break
                block.append(other)
        if not block:
            continue
        bottom = block[-1]['y'] + height
        right = max(t['x1'] for member in block for t in _aligned_tokens(member['row'], x))
        if any(r[0] < right + tolerance and r[2] > x - tolerance and r[1] < bottom + height * 3
               and r[3] > y - height * 3 for r in unread):
            continue
        top = ' '.join(t['t'] for t in _aligned_tokens(row, x) if t['line'] == 0)
        mailing = (nearest_above is not None and y - nearest_above['y'] <= height * 4
                   and _MAILING_FIGURES.match(nearest_above['text'].replace(' ', '')))
        reprinted = sum(1 for p in section_pages for other in pages[p] if other['tokens'] and other is not row
                        and fold(' '.join(other['text'].split())) == fold(' '.join(top.split())))
        if mailing or reprinted:
            found.add(' '.join(top.split()))
    names = {fold(name) for name in found}
    return next(iter(found)) if len(names) == 1 else ''


# (A8) An addressee block whose postal-code line was not read (a barcode printed over it) gives the holder
# only when the statement reprints its top line on another page; see _unanchored_holder. False: such
# statements wait for a person.
UNANCHORED_HOLDER = True


def _above_movements(rows, style):
    """A page's lines above its first movement-table heading or movement line."""
    cut = next((row['y0'] for row in rows if row['tokens'] and row['y0'] is not None
                and (_is_header(row) or _row_is_movement(row, style or 'dot', 2))), None)
    return [row for row in rows if row['tokens'] and row['y0'] is not None and (cut is None or row['y0'] < cut)]


def _unanchored_holder(section_pages, pages, heading, style):
    """(A8) The top line of an addressee block whose postal-code line was not read, or ''.

    The postal line can be printed over the mailing barcode, where the page's reading loses it, so
    ``address_holder`` finds no block ending in one. The block is accepted only when all of these hold:

    * on the statement's first heading page, in its left half: a name line (letters, or a company name's word
      of a letter and figures, 'K7'; no label, bank or heading word) with no line at its edge directly above
      it, followed at the same edge and line pitch by two to four address lines, at least one printing a figure
      (the street number), none a name of a bank, an amount or a date (an address, not a list of names or the
      bank's own lines);
    * the page's reading, where it checked its printed lines, left none unread at the block's edge
      directly above its top line or among its lines (a lost first name line would make the next line
      look like the top);
    * a second printed fact: the top line printed again, as the whole of a line's left cells, above the
      movements of another page of the same statement (the page headings that reprint the addressee);
    * every block found this way names the same holder.
    """
    if not UNANCHORED_HOLDER or not heading:
        return ''
    page, rows = heading[0]
    source = next((row['source'] for row in pages[page] if row['tokens']), None)
    if source is None or source.get('reading_rotation'):
        return ''
    checked = source.get('printed_lines') or {}
    unread = [rect for rect in checked.get('unread') or [] if isinstance(rect, list) and len(rect) == 4]
    lines = []
    for row in rows:
        if row['tokens'] and row['width']:
            x = min(t['x0'] for t in row['tokens'])
            aligned = _aligned_tokens(row, x)
            if aligned:
                lines.append(dict(row=row, x=x, y=min(t['y0'] for t in aligned),
                                  height=max(t['y1'] - t['y0'] for t in aligned), text=_aligned_text(row, x)))
    reprints = set()
    for other in section_pages:
        if other == page:
            continue
        for row in _above_movements(pages[other], style):
            if row['width'] and min(t['x0'] for t in row['tokens']) <= row['width'] * 0.5:
                reprints.add(' '.join(_aligned_text(row, min(t['x0'] for t in row['tokens'])).split()))
    found = set()
    for line in lines:
        row, x, y, height = line['row'], line['x'], line['y'], line['height']
        if x > row['width'] * 0.5 or not _name_line(line['text'], company=True):
            continue
        tolerance = row['width'] * 0.015
        same_edge = sorted((other for other in lines if abs(other['x'] - x) <= tolerance and other is not line),
                           key=lambda other: other['y'])
        if any(y - height * 2.6 <= other['y'] < y for other in same_edge):
            continue  # not the block's top line
        block = [line]
        for other in same_edge:
            if other['y'] > block[-1]['y'] and other['y'] - block[-1]['y'] <= height * 2.6 and len(block) < 5:
                block.append(other)
        address = block[1:]
        if (len(address) < 2 or not any(re.search(r'\d', other['text']) for other in address)
                or any(_not_address(other['row'], x, style) or any(w in other['text'] for w in INSTITUTION_WORDS)
                       for other in address)):
            continue
        bottom = block[-1]['y'] + height
        right = max(t['x1'] for member in block for t in _aligned_tokens(member['row'], x))
        # A printed text line is one line high; a taller unread mark (the mailing barcode under the block) is
        # not a lost line of text.
        if any(r[0] < right + tolerance and r[2] > x - tolerance and r[1] < bottom and r[3] > y - height * 3
               and r[3] - r[1] <= height * 2 for r in unread):
            continue
        top = ' '.join(t['t'] for t in _aligned_tokens(row, x) if t['line'] == 0)
        if ' '.join(fold(top).split()) in reprints:
            found.add(' '.join(top.split()))
    names = {fold(name) for name in found}
    return next(iter(found)) if len(names) == 1 else ''


def _stub_holder(heading, pages, style):
    """(A8) The holder printed in a payment stub below the first page's movement table: the top line of a
    postal-anchored address block there, accepted only when the same name is printed as a whole cell above
    the movements (two printed facts agree; a counterparty in a movement line is never in an address block
    and never repeated as a heading cell)."""
    if not heading:
        return ''
    page, above = heading[0]
    cut = {id(row) for row in above}
    below = [row for row in pages[page] if id(row) not in cut and row['tokens'] and row['y0'] is not None
             and above and row['y0'] > max(r['y0'] for r in above if r['y0'] is not None)]
    if not below or len(below) == len([r for r in pages[page] if r['tokens']]):
        return ''
    names = {fold(' '.join(cell['expected_text'].split())) for row in above for cell in row['raw']['cells']}
    found = {name for _, name, accepted in _address_tops(below, style) if accepted and fold(name) in names}
    return found.pop() if len(found) == 1 else ''


# Mexican statements are fiscal receipts (CFDI): the receipt names its recipient, the account holder,
# under this label, usually on the statement's last page.
_RECEIPT_RECIPIENT = re.compile(r'^\s*NOMBRE DEL RECEPTOR\s*:?\s*(.{3,120}?)\s*$')
_COMPANY_FORM = re.compile(r'^,?\s*(?:S\.?\s*A\.?\s*(?:P\.?\s*I\.?\s*)?(?:B\.?\s*)?|S\.?\s*DE\s*R\.?\s*L\.?\s*|S\.?\s*C\.?\s*)'
                           r'(?:DE\s*C\.?\s*V\.?)?$')


def _receipt_holder(section_pages, pages, heading):
    """The holder when the statement's fiscal receipt names one recipient and a heading line above the
    movements prints that same name, alone or followed by a company legal form (A8): two printed
    facts agree. The heading line's text is the holder (it carries the legal form). Otherwise ''.
    """
    recipients = set()
    for page in section_pages:
        for row in pages[page]:
            if row['tokens']:
                m = _RECEIPT_RECIPIENT.match(' '.join(fold(row['text']).split()))
                if m:
                    recipients.add(m[1])
    if len(recipients) != 1:
        return ''
    recipient = next(iter(recipients))
    if not _name_like(recipient):
        return ''
    found = []
    for _, rows in heading:
        for row in rows:
            if not row['tokens']:
                continue
            x = min(t['x0'] for t in row['tokens'])
            cells = {id(t['cell']) for t in row['tokens'] if t['first'] and abs(t['x0'] - x) <= row['width'] * 0.015}
            text = ' '.join(t['t'] for t in sorted(row['tokens'], key=lambda t: (t['line'], t['x0']))
                            if id(t['cell']) in cells and t['line'] == 0)
            folded = ' '.join(fold(text).split())
            if folded == recipient or (folded.startswith(recipient + ' ') or folded.startswith(recipient + ','))  \
                    and _COMPANY_FORM.match(folded[len(recipient):].strip()):
                found.append(' '.join(text.split()))
    return found[0] if len({fold(name) for name in found}) == 1 else ''


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
        words = fold(row['text']).split()
        for name in _HEADING_CURRENCIES:
            if ' ' + name + ' ' in text and (' ' in name or words[-1:] == [name]
                                              or words[:1] == [name] and not _qualified_dollar(words)):
                if _CODE.fullmatch(name) and not re.search(r'(?<![A-Za-z])' + name + r'(?![A-Za-z])', row['text']):
                    # A bare code is printed in capitals. OCR noise folds to
                    # one: 'Ci cad de Mexico' (Ciudad) was read as CAD, 'SA DE
                    # mn' (SA DE CV) as MN.
                    continue
                found.add(CURRENCY_NAMES[name])
                break
    return found


_CODE = re.compile(r'[A-Z]{2,3}')


def _qualified_dollar(words):
    """'DOLAR AUSTRALIANO', 'DOLAR CANADA': a dollar word followed by a qualifier names another dollar,
    not US dollars (C2). Only the American qualifiers keep the plain reading."""
    return (words[0] in ('DOLAR', 'DOLARES') and len(words) > 1
            and words[1] not in ('AMERICANO', 'AMERICANOS', 'ESTADOUNIDENSE', 'ESTADOUNIDENSES', 'US', 'USD', 'EUA',
                                 'E.U.A.', 'DE', 'SOBRE', 'AL'))


def _holder_label(row, found):
    cells = row['raw']['cells']
    joined = ' '.join(c['expected_text'].strip() for c in cells)
    for name in HOLDER_LABELS:
        # "Label: value" printed in one line; keep the printed text (not folded) of the value.
        m = re.match(r'^\s*' + re.escape(name) + r'\s*:\s*(.{3,120})$', ' '.join(joined.upper().split()))
        if m:
            raw = re.split(r':\s*', joined, maxsplit=1)
            if len(raw) == 2 and raw[1].strip():
                found.add(' '.join(raw[1].split()))
    for index, cell in enumerate(cells[:-1]):
        if label(cell['expected_text']) in {label(n) for n in HOLDER_LABELS}:
            value = ' '.join(cells[index + 1]['expected_text'].split())
            if 3 <= len(value) <= 120 and re.search(r'[A-Za-z]', value):
                found.add(value)


# A postal-code line (A8): a labelled code ('C.P. 01234', 'CODIGO POSTAL 01234', 'ZIP 12345'), a code
# opening a place line ('01234 CIUDAD ...'), or a code closing a place line after a state or a comma
# ('..., ST 12345', '... CITY, PLACE 12345'). A five-digit number closing any other line is a reference
# (a transfer description, a split account number), not an address. Folding turns a ZIP+4 hyphen into a
# space ("20009 6857").
# The 'C.P.' label is matched with one scan substitution between its letters and either mark after it
# ('CAP.', 'C,P.', 'CAP,') (F1).
_POSTAL_LABELLED = re.compile(r'(?:\bC[.,]?\s?[A-Z]?[.,]?\s?P\b[.,]?|\bCODIGO POSTAL|\bZIP(?: CODE)?)\s*:?\s*\d{5}\b')
_POSTAL_LEADING = re.compile(r'^\d{5}\s+[A-Z]{3,}')
_POSTAL_PLACE = re.compile(r'[A-Z]{2,}\.?\s*,\s*[A-Z][A-Z. ]*?\s\d{5}(?:[- ]\d{4})?\s*$')


def _postal(text):
    """Whether a folded line reads as the postal-code line of an address."""
    return bool(_POSTAL_LABELLED.search(text) or _POSTAL_LEADING.search(text) or _POSTAL_PLACE.search(text)
                or _US_ADDRESS.search(text) and re.search(r'\d{5}(?:[- ]\d{4})?\s*$', text))


def _not_address(row, x, style):
    """A movement line, or a line whose cells at the block's left edge carry money or a date, is never part
    of an address block (A8). Cells further right (a period or an account printed beside the address)
    do not count."""
    if _row_is_movement(row, style or 'dot', 2):
        return True
    cells = {id(t['cell']) for t in row['tokens'] if t['first'] and abs(t['x0'] - x) <= row['width'] * 0.015}
    return any(_value_kind(t, style or 'dot', 2) in ('money', 'date') for t in row['tokens'] if id(t['cell']) in cells)


_LABEL_WORDS = {fold(word) for word in NOT_A_NAME} | {'NO', 'NUM', 'NUMERO', 'RFC', 'CONTRATO', 'CLIENTE'}


def _name_like(name):
    """A holder name: letters, at least two words, no label words; a letter-digit token is allowed
    (company names), a bare number (address, reference) is not."""
    return bool(re.search(r'[A-Za-z]{2}', name) and not any(re.fullmatch(r'[\d#.,/-]+', w) or w.startswith('#')
                                                            for w in name.split()) and len(name.split()) >= 2
                and not name.rstrip().endswith(':')
                and not any(re.search(r'\b' + re.escape(word) + r'\b', fold(name)) for word in NOT_A_NAME))


def address_line(text):
    """Whether a printed line reads as a line of a postal address: a postal-code line, a post-office box, or
    a line holding a street, floor, unit or district word (A8)."""
    folded = fold(text)
    words = folded.replace('.', ' ').replace(',', ' ').split()
    return bool(_postal(folded) or re.search(r'\bP\.?\s?O\.?\s?BOX\b', folded)
                or any(word in ADDRESS_WORDS for word in words))


def _street_line(text):
    """A line that reads as the street line under an addressee's name: a street, floor, unit or post-office
    box line, or one holding a house number (a word of figures, with at most one letter after them). A postal
    line is not: the line printed directly above it is the district or city line."""
    folded = fold(text)
    if _postal(folded):
        return False
    return address_line(folded) or any(re.fullmatch(r'\d+[A-Z]?', word) for word in folded.split())


def addressee_name(lines):
    """The holder printed as the first line of an addressee block, from the block's lines top first, or ''
    (A8).

    The name may hold a word of letters and figures ('GRUPO K7'); it is never an address line, and the line
    printed directly under it must read as the street line, or as the taxpayer type closing a block printed
    without its address ('PERSONA MORAL'). A block whose first line is lost to the scan starts with its
    street or district line, which never passes: the reader then gives no holder (a person confirms it)
    rather than an address line.
    """
    if len(lines) < 2:
        return ''
    name = ' '.join(lines[0].split())
    below = fold(lines[1])
    if not _name_like(name) or address_line(name) or any(kind in fold(name) for kind in TAXPAYER_TYPES):
        return ''
    if not (_street_line(lines[1]) or below in TAXPAYER_TYPES):
        return ''
    return name


def address_holder(rows, style=None):
    """The top line of the left address block ending with a postal-code line (A8)."""
    found = [(y0, name) for y0, name, accepted in _address_tops(rows, style) if accepted]
    # The addressee block is the topmost one; a second (fiscal) address block below it is not the holder.
    return min(found)[1] if found else ''


def _address_tops(rows, style=None):
    """[(y0, top line, accepted as a name)] of every address block ending with a postal-code line, and of
    every addressee block confirmed by its reprint in one (A8)."""
    located = [r for r in rows if r['tokens'] and r['width']]
    if not located:
        return []
    found, anchored = [], []
    for index, row in enumerate(located):
        x = min(t['x0'] for t in row['tokens'])
        # The postal line can be the block's own cell only: another box shares its stored row ('<city> <ZIP>'
        # beside the remittance address). Such a block must read as an address block itself: three or four
        # lines (name, street, postal line), or the lines below a paragraph gap that are (_spaced_block).
        own_cell = not _postal(fold(row['text']))
        if own_cell and not _postal(_aligned_text(row, x)):
            continue
        if _not_address(row, x, style):
            continue
        block = _grow_block(located, index, x, style)
        if own_cell:
            block = block if 3 <= len(block) <= 4 else _spaced_block(block)
            top = _block_top(block, x) if block and 3 <= len(block) <= 4 and _street_lines(block, x) else None
            if top and top[2] and not re.search(r'\d', top[1]) and not _damaged_above(located, block, x):
                found.append(top)
            continue
        if 3 <= len(block) <= 7:
            anchored.append((block, x))
            top = _block_top(block, x)
            if top and (_damaged_above(located, block, x) or _issuer_headed(located, block, x)):
                top = (top[0], top[1], False)
            if top:
                found.append(top)
    for block, x in anchored:
        top = _reprinted_block(located, block, x, style)
        if top:
            found.append(top)
    return found


def _grow_block(located, index, x, style):
    """The left-aligned block of lines ending at located[index], bottom first (A8)."""
    row = located[index]
    block = [row]
    for earlier in reversed(located[:index]):
        ex = min(t['x0'] for t in earlier['tokens'])
        if earlier['y0'] > block[-1]['y0']:
            continue
        if abs(ex - x) > row['width'] * 0.015 and not _lead_noise(earlier, x):
            # A movement line printed between two lines means they are not one address block.
            if _row_is_movement(earlier, style or 'dot', 2):
                break
            continue
        if _not_address(earlier, x, style):
            break
        # The issuer's own legal-name or heading line above is not part of the addressee block.
        # Only the cells aligned with the block's left edge count (the issuer's name can share the row).
        first_words = _aligned_text(earlier, x)
        if any(word in first_words for word in INSTITUTION_WORDS) or 'ESTADO DE CUENTA' in first_words or 'STATEMENT' in first_words:
            break
        gap = block[-1]['y0'] - earlier['y0']
        height = max(t['y1'] - t['y0'] for t in block[-1]['tokens'])
        previous_gap = (block[-2]['y0'] - block[-1]['y0']) if len(block) > 1 else 0
        # One blank line in the address column is allowed where the page prints other columns
        # beside it (the space is not a gap between blocks).
        beside = any(earlier['y0'] < other['y0'] < block[-1]['y0'] for other in located)
        if gap > max(height * (4 if beside else 2.6), previous_gap * 1.6):
            break
        block.append(earlier)
        if len(block) >= 7:
            break
    return block


_STREET = re.compile(r'^(?:\d+[A-Z]?|P\.?\s?O\.?\s?BOX|PO BOX)\b')


def _street_lines(block, x):
    """Every line between a block's top (the name) and its postal line opens with a house number or a
    post-office box (A8)."""
    return all(_STREET.match(_aligned_text(row, x)) for row in block[1:-1])


def _spaced_block(block):
    """(A8) The lines of a grown block (bottom first) below its first gap wider than one and a half times its
    own line pitch (postal line to the line above it), when they are at least three, or None. A paragraph
    printed above an address (a change-of-address prompt, help text) is not part of it."""
    if len(block) < 4:
        return None
    pitch = block[0]['y0'] - block[1]['y0']
    if pitch <= 0:
        return None
    for size in range(3, len(block)):
        if block[size - 1]['y0'] - block[size]['y0'] > 1.5 * pitch:
            return block[:size]
    return None


def _lead_noise(row, x):
    """The scan-noise glyph printed left of an address block's edge x at the start of a line, or None.

    A lone mark of one character, or of up to three with no letter pair ('|', '@', 'N', 'i)'), standing
    before a word that starts on the block's edge is noise from the scan, not part of the line (F2).
    """
    tokens = sorted((t for t in row['tokens'] if t['line'] == 0), key=lambda t: t['x0'])
    if len(tokens) < 2:
        return None
    lead, word = tokens[0], tokens[1]
    tolerance = row['width'] * 0.015
    noise = len(lead['t']) == 1 or (len(lead['t']) <= 3 and re.search(r'[^A-Za-z0-9]', lead['t']))
    if noise and abs(lead['x0'] - x) > tolerance and abs(word['x0'] - x) <= tolerance and len(word['t']) > 1:
        return lead
    return None


def _aligned_tokens(row, x):
    """The tokens of the cells of a line that start at the left edge x (a leading noise glyph dropped)."""
    noise = _lead_noise(row, x)
    tolerance = row['width'] * 0.015
    aligned = {id(t['cell']) for t in row['tokens'] if t['first'] and (abs(t['x0'] - x) <= tolerance or t is noise)}
    return [t for t in sorted(row['tokens'], key=lambda t: (t['line'], t['x0'])) if id(t['cell']) in aligned and t is not noise]


def _issuer_headed(located, block, x):
    """(A8) A bank's bare name printed as the first line of the block itself, at its edge and its own
    line pitch ('<BANK> / REMITTANCE DEPT / PO BOX ... / <city> <ZIP>'): the issuer's remittance or
    return address, never the addressee's. A bank heading printed further above, or its legal-name line
    (a comma, a legal form or a designation after the name), is not part of the block."""
    if len(block) < 2:
        return False
    top = block[-1]
    pitch = block[-2]['y0'] - top['y0']
    tolerance = top['width'] * 0.015
    above = [row for row in located if row['y0'] is not None and row['y0'] < top['y0']
             and abs(min(t['x0'] for t in row['tokens']) - x) <= tolerance]
    if not above or pitch <= 0:
        return False
    nearest = max(above, key=lambda row: row['y0'])
    text = ' '.join(_aligned_text(nearest, x).split())
    return (top['y0'] - nearest['y0'] <= pitch * 1.3 and len(text.split()) <= 4 and ',' not in text
            and not _LEGAL_FORM.search(re.sub(r'\b(?:BANK|BANCO)\b', '', text))
            and any(word in text for word in INSTITUTION_WORDS))


def _damaged_above(located, block, x):
    """(A8) The end of a company name (its legal form) printed directly above a block's top, inside the
    block's column but not on its edge: the scan lost the start of the name line ('...RESAS SA DE CV'), so
    the block's top line is not its first and is not taken as the name."""
    top = block[-1]
    tolerance = top['width'] * 0.015
    right = max(t['x1'] for row in block for t in row['tokens'] if abs(min(u['x0'] for u in row['tokens']) - x) <= tolerance
                or _lead_noise(row, x))
    height = max(t['y1'] - t['y0'] for t in top['tokens'])
    for row in located:
        if row['y0'] is None or not top['y0'] - height * 2.6 <= row['y0'] < top['y0']:
            continue
        lead, end = min(t['x0'] for t in row['tokens']), max(t['x1'] for t in row['tokens'])
        words = ' '.join(fold(row['text']).split())
        if (x + tolerance < lead < right and end <= right + tolerance and _NAME_TAIL.search(words)
                and not any(word in words for word in INSTITUTION_WORDS)):
            return True
    return False


# The end of a company name: its printed legal form.
_NAME_TAIL = re.compile(r'(?:\bS\.?\s?A\.?(?:\s?P\.?\s?I\.?)?|\bS\.?\s?DE\s?R\.?\s?L\.?|\bS\.?\s?C\.?)\s?DE\s?C\.?\s?V\.?$'
                        r'|\b(?:INC|LLC|LTD|CORP)\.?$')


def _aligned_text(row, x):
    """Folded text of the cells of a line that start at the left edge x."""
    return fold(' '.join(t['t'] for t in _aligned_tokens(row, x)))


def _block_top(block, x):
    """(y0, name, accepted) of a block's top line, or None."""
    top = block[-1]
    name = ' '.join(t['t'] for t in _aligned_tokens(top, x) if t['line'] == 0)
    # An address line at the top means the scan lost the name line above it.
    accepted = _name_like(name) and not address_line(name)
    if not accepted:
        # A row recognised as one cell can run into the right-hand column ("<name> CLIENTE No. 123"):
        # the words before the first label word are the name when they read as one.
        words = name.split()
        cut = next((i for i, w in enumerate(words) if fold(w).strip(':') in _LABEL_WORDS), None)
        if (cut is not None and cut >= 2 and _name_like(' '.join(words[:cut]))
                and not address_line(' '.join(words[:cut]))):
            name, accepted = ' '.join(words[:cut]), True
    return (top['y0'], name, accepted) if name.strip() else None


def _reprinted_block(located, anchored, x, style):
    """The top of an addressee block printed without a postal line whose address lines are reprinted in
    the postal-anchored block ``anchored`` (the addressee and the fiscal domicile both printed), or None.

    Two of its lines below the top, each of at least two words, must open two different lines of the
    anchored block; the block is grown from the lower of them like any address block and must hold
    both, with a name line above them. Two printed blocks agreeing is the proof that it is an address.
    """
    inside = {id(r) for r in anchored}
    lines = [_aligned_text(r, x) for r in anchored]
    matched = {}
    for index, row in enumerate(located):
        if id(row) in inside:
            continue
        rx = min(t['x0'] for t in row['tokens'])
        text = _aligned_text(row, rx)
        if len(text) < 8 or len(text.split()) < 2:
            continue
        hits = [j for j, line in enumerate(lines) if line == text or line.startswith(text + ' ')]
        if len(hits) == 1:
            matched.setdefault(round(rx / (row['width'] * 0.015)), []).append((index, hits[0]))
    for pairs in matched.values():
        if len({j for _, j in pairs}) < 2 or len(pairs) != len({j for _, j in pairs}):
            continue
        lowest = max(index for index, _ in pairs)
        rx = min(t['x0'] for t in located[lowest]['tokens'])
        block = _grow_block(located, lowest, rx, style)
        ids = {id(r) for r in block}
        if not 3 <= len(block) <= 7 or not all(id(located[i]) in ids for i, _ in pairs):
            continue
        if id(block[-1]) in {id(located[i]) for i, _ in pairs}:
            continue
        return _block_top(block, rx)
    return None


_MONEY_MARK = re.compile(r'^[-−+(]?\s*(US\$|\$|€|£|¥)|(MN|M\.N\.|MXN|USD|EUR|DLS)$')


def identity_evidence(segment, section_pages, rows, pages, facts, style):
    """What the statement prints about its own identity, per fact (layout memory compares it).

    holder: every labelled holder value and every addressee-block top line on the
    statement's heading pages (also lines the engine did not accept as a name);
    institution: legal-name lines repeated on the section's pages, digits removed;
    currency: currencies named in the statement and the markers printed on its amounts.
    A remembered fact applies to another period only when this evidence is the same.
    """
    holder = set()
    for _, heading_rows in _identity_rows(segment['pages'], pages, facts, style):
        for row in heading_rows:
            if row['tokens'] and len(row['text']) <= 160:
                _holder_label(row, holder)
        holder.update(name for _, name, _ in _address_tops(heading_rows, style))
    legal = _repeated_legal([facts[p]['legal'] for p in section_pages])
    currency = {'named:' + code for _, code in segment.get('currency_mentions', [])}
    for row in rows:
        for token in row['tokens']:
            if _value_kind(token, style or 'dot', 2) == 'money':
                mark = _MONEY_MARK.search(token['t'])
                if mark:
                    currency.add('mark:' + (mark[1] or mark[2]))
    return dict(holder=sorted({fold(name) for name in holder} - {''}),
                institution=sorted({' '.join(re.sub(r'\d', ' ', line).split()) for line in legal} - {''}),
                currency=sorted(currency))


def _repeated_legal(legal_by_page):
    counts = {}
    for lines in legal_by_page:
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
    pages = len(legal_by_page)
    return [line for line, count in counts.items() if count >= max(1, (pages + 1) // 2)]


_LEGAL_FORM = re.compile(r'\b(?:S\.?\s?A\.?|N\.?\s?A\.?|INC\.?|INSTITUCION DE BANCA MULTIPLE|CREDIT UNION|BANK|BANCO)\b')
# Designations a bank prints next to its legal name (they are not the name itself).
_DESIGNATION = re.compile(r'\b(?:INSTITUCION DE BANCA MULTIPLE|N\.?\s?A\.?|CREDIT UNION|CASA DE BOLSA)\b')
_DESIGNATION_ONLY = re.compile(r'^(?:INSTITUCION DE BANCA MULTIPLE|GRUPO FINANCIERO|CASA DE BOLSA|SOCIEDAD ANONIMA)\b')
_TRAILING_FORM = re.compile(r'[\s,]+(?:S\.?\s?A\.?(?:\s+DE\s+C\.?\s?V\.?)?|N\.?\s?A\.?|INC\.?)$')


_CONNECTOR_START = re.compile(r'^(?:DE|DEL|Y|E|A|AL|LA|EL|LOS|LAS|POR|PARA|CON|EN|OF|THE|FROM|TO|BY|AND|FOR)\b')


def _institution(legal_by_page, statement_first=(), pages=None):
    """The issuer's name from its legal-name line (A9): short form before its first comma and legal form.

    Two tiers. First, lines printing a banking designation ("Institucion de Banca
    Multiple", "N.A.", "Credit Union", "Casa de Bolsa") directly after the name
    (after its legal form at most), on the statement's first pages or repeated on
    most of its pages. Otherwise, a line repeated on most
    pages whose short form starts or ends with a bank word, has at most six words
    and no number, on a line naming no account (transfer lines name counterparty banks). One name in a tier is the institution; none or several give no
    name (a person decides). Designation-only fragments, headings ("Estado de
    cuenta ...") and narrative lines (starting with a connector word) are never names.
    With ``pages`` (the document's rows), a name of the second tier must be printed on at least two
    lines of the document: a logo read as letters ('EXAMPIE BANK' for a bank every other line names
    differently) is printed once, and is not the issuer's name.
    """
    repeated = set(_repeated_legal(legal_by_page))
    designated, plain = set(), set()
    for line in repeated | {line for line in statement_first if _DESIGNATION.search(line)}:
        if not _LEGAL_FORM.search(line):
            continue
        # A leading year or copyright mark is not part of the name; the legal form ends it.
        name = _NAME_END.split(line.split(',')[0])[0]
        rest = line[len(name):]
        short = re.sub(r'^(?:\(C\)|©)?\s*(?:\d{4}\s+)?', '', name.strip(' .'))
        short = _TRAILING_FORM.sub('', short).strip(' .')
        words = short.split()
        if (not 3 <= len(short) <= 80 or len(words) > 6 or _DESIGNATION_ONLY.match(short)
                # A one-word name carries its bank word ("CITIBANK"); a lone word is a wrapped sentence's tail.
                or (len(words) == 1 and not any(word in short for word in INSTITUTION_WORDS))
                or _CONNECTOR_START.match(short) or any(word in short for word in ('ESTADO DE CUENTA', 'STATEMENT'))
                or not any(word in short or word in line for word in INSTITUTION_WORDS)):
            continue
        if _DESIGNATED_REST.match(rest) or short.endswith('CREDIT UNION'):
            # The designation is printed with the name (after its legal form at most), not elsewhere on the line.
            designated.add(short)
        elif (line in repeated and not re.search(r'\d', short) and not re.search(r'\d{6,}', line)
              and not {'CUENTA', 'ACCOUNT', 'CLABE', 'CONTRATO'} & set(line.split())
              and any(words[0] == w or words[-1] == w or short.startswith(w) or short.endswith(w)
                      for w in ('BANCO', 'BANK', 'CREDIT UNION', 'BANCA', 'CASA DE BOLSA'))
              and (pages is None or _printed_twice(short, pages))):
            plain.add(short)
    for names in (designated, plain):
        if names:
            return next(iter(names)) if len(names) == 1 else ''
    return ''


def _name_words(text):
    return re.sub(r'[^A-Z0-9&]', ' ', fold(text)).split()


def _printed_twice(name, pages):
    """(A9) The issuer's name (its words in order, at least one of them not a banking word) is printed on
    at least two lines of the document."""
    from services.financial.statement_engine_routing import _BANKING_WORDS
    words = _name_words(name)
    if not any(word not in _BANKING_WORDS for word in words):
        return False
    wanted = ' ' + ' '.join(words) + ' '
    count = 0
    for rows in pages.values():
        for row in rows:
            if row['tokens']:
                count += wanted in ' ' + ' '.join(_name_words(row['text'])) + ' '
                if count >= 2:
                    return True
    return False


def _same_issuer(a, b):
    from services.financial.statement_engine_routing import _same_identity
    return _same_identity('institution', a, b)


_DESIGNATED_REST = re.compile(r'^[\s,.]*(?:S\.?\s?A\.?(?:\s+DE\s+C\.?\s?V\.?)?[\s,.]*)?'
                              r'(?:INSTITUCION DE BANCA MULTIPLE|N\.?\s?A\.?|CASA DE BOLSA|CREDIT UNION)\b')
_NAME_END = re.compile(r'\s+(?=S\.?\s?A\.?\b|S\.?\s?P\.?\s?A\.?\b|N\.?\s?A\.?\b|INSTITUCION DE BANCA MULTIPLE\b)')


# ---------------------------------------------------------------------------
# Statements and sections
# ---------------------------------------------------------------------------

def _segments(pages, facts):
    """[(period or None, [page numbers])]: a new printed period, or numbering restarting at 1, starts a segment."""
    _drop_contradicted_derived(pages, facts)
    segments = []
    ordered = sorted(pages)
    for page in ordered:
        f = facts[page]
        period = None
        candidates = f['labelled_periods'] or f['periods']
        if len(candidates) == 1:
            period = next(iter(candidates))
        restart = any(n == 1 for n, _ in f['numbering'])
        current = segments[-1] if segments else None
        # (A2, A3) A printed run that reached its last page ('Page 5 of 5') is complete: a following page that
        # carries only the production's own page stamp (no period, no statement page number: a record or
        # image the production appended) does not continue that statement.
        # A page whose next numbered page continues a run (number above 1) is that run's unnumbered first
        # page, not an appendix.
        following = next((facts[q]['numbering'] for q in ordered[ordered.index(page) + 1:] if facts[q]['numbering']), set())
        other = current is not None and _other_account_statement(f, current, facts)
        finished = (current is not None and not period and not f['numbering'] and f.get('file_numbered')
                    and current['pages'] and any(n == m for n, m in facts[current['pages'][-1]]['numbering'])
                    and not current.get('appendix') and not any(n > 1 for n, _ in following))
        if finished:
            current = dict(period=None, pages=[], conflict=False, appendix=True)
            segments.append(current)
        elif current is not None and current.get('appendix') and (period or f['numbering']):
            # A page printing a period or a statement page number never belongs to appended records.
            current = dict(period=period, pages=[], conflict=len(candidates) > 1)
            segments.append(current)
        elif (current is None or (period and current['period'] and period != current['period'])
                or (restart and current['pages'] and any(facts[p]['numbering'] for p in current['pages'])) or other):
            current = dict(period=period, pages=[], conflict=len(candidates) > 1, mailed_with_previous=other)
            segments.append(current)
        elif period and not current['period']:
            current['period'] = period
        current['pages'].append(page)
        current['conflict'] = current['conflict'] or (len(candidates) > 1 and not f['labelled_periods'])
    # Another account's statement in the same mailing continues its page numbering (A3): every statement
    # of one mailing is checked against the mailing's printed numbering, over all of its pages.
    run = []
    for segment in segments:
        if not segment.get('mailed_with_previous'):
            run = []
        run.append(segment)
        mailing = [page for member in run for page in member['pages']]
        for member in run:
            member['numbering_pages'] = mailing
    return segments


def _other_account_statement(f, current, facts):
    """(A6, A7) A page labelling its own period and printing, under a full account-number label, only
    accounts the statement so far has not printed under one, starts another statement: a second account's
    statement mailed with the first continues its page numbering and can print the same period (a credit
    line's statement inside a deposit statement's envelope)."""
    if not f['labelled_periods'] or not current['pages']:
        return False
    own = {re.sub(r'\D', '', value) for value, ranks in f['accounts'].items() if 3 in ranks} - {''}
    before = {re.sub(r'\D', '', value) for p in current['pages'] for value, ranks in facts[p]['accounts'].items()
              if 3 in ranks} - {''}
    return bool(own and before and not own & before)


def _drop_contradicted_derived(pages, facts):
    """A period derived from a cut date and a day count (B1) yields to a labelled period printed in the
    same printed page run (pages from a page numbered 1 up to the next): if the run labels another
    period, the derived one is a misreading and is dropped."""
    runs, current = [], []
    for page in sorted(pages):
        if any(n == 1 for n, _ in facts[page]['numbering']) and current:
            runs.append(current)
            current = []
        current.append(page)
    if current:
        runs.append(current)
    for run in runs:
        printed = set().union(*(facts[p]['labelled_periods'] - facts[p].get('derived_periods', set()) for p in run))
        for page in run:
            derived = facts[page].get('derived_periods', set())
            if derived and printed and not derived <= printed:
                facts[page]['labelled_periods'] -= derived
                facts[page]['periods'] -= derived
                facts[page]['derived_periods'] = set()


def _drop_file_numbering(facts):
    """(A3) A production stamps its own running page numbers on every page it carries ('Page 9 of 339'
    beside the statement's own 'Page 2 of 5'): a numbering whose count is one for the whole file, whose
    number advances with the physical page everywhere it is printed, and which is printed beside another
    numbering on at least two pages numbers the file, not a statement. It is set aside on every page, so
    it neither breaks, restarts nor extends a statement's run. A numbering that is not in step with the
    physical pages, or that is never printed beside another one, is never set aside."""
    by_count = {}
    for page, f in facts.items():
        for number, count in f['numbering']:
            by_count.setdefault(count, []).append((page, number))
    for count, printed in by_count.items():
        offsets = {page - number for page, number in printed}
        pages = [page for page, _ in printed]
        beside = sum(1 for page in pages if len(facts[page]['numbering']) > 1)
        if (len(offsets) != 1 or len(pages) != len(set(pages)) or len(pages) < 3
                or count < len(pages) or beside < 2):
            continue
        for page, number in printed:
            facts[page]['numbering'].discard((number, count))
            facts[page]['file_numbered'] = True


def _numbering_complete(pages, facts, after=None):
    """Printed page numbers (A3) must leave no gap.

    Unnumbered pages (covers, notices, reverse sides) are extra pages; they may
    stand in for a number only where they physically sit in the gap.
    ``after``: a page (physical number) on which the movement table printed its
    own end; printed pages missing only after it are allowed.
    """
    expected, loose, total, previous = 1, 0, None, None
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
        if number < expected or number > count:
            return False
        if number - expected > loose and (after is None or previous is None or previous < after):
            return False
        expected, loose, previous = number + 1, 0, page
    return total is None or total - (expected - 1) <= loose or (after is not None and previous is not None
                                                                and previous >= after)


# Readings of the last few documents. A live reading of a long production is
# ~140k dicts and lists (a 345-page Navy Federal file), and every full pass of
# the cyclic garbage collector walks every live container with the GIL held:
# eight cached readings made each pass take seconds, long enough for a busy
# worker to miss uvicorn's health ping and be killed with its saves in flight.
# So the cache keeps them pickled (bytes are invisible to the collector, and a
# reading of that file decodes in ~0.15 s) and only the readings of the
# documents in use (the last LIVE_READINGS asked for) stay live, so proposing
# each period of a file in turn decodes nothing.
READINGS_KEPT = 8
LIVE_READINGS = 2
_READINGS = OrderedDict()   # key -> pickled reading
_LIVE_READINGS = OrderedDict()  # key -> reading, at most LIVE_READINGS
_READINGS_LOCK = threading.Lock()


def _keep_live(key, result):
    with _READINGS_LOCK:
        _LIVE_READINGS[key] = result
        _LIVE_READINGS.move_to_end(key)
        while len(_LIVE_READINGS) > LIVE_READINGS:
            _LIVE_READINGS.popitem(last=False)


def _printed_lines_key(source):
    checked = source.get('printed_lines') or {}
    return (checked.get('checked') is True,
            tuple(tuple(rect) for rect in checked.get('unread') or () if isinstance(rect, (list, tuple))),
            tuple(tuple(rect) for rect in checked.get('layer') or () if isinstance(rect, (list, tuple))))


def _source_signature(sources):
    """Identity of a document's stored sources: revisions plus every cell's text and position (None if a
    revision is missing, in which case nothing is cached)."""
    parts = tuple((s['page_number'], s['table_index'], s.get('source_revision'), s.get('reading_rotation') or 0,
                   hash(tuple((c['expected_text'], tuple((c.get('locator') or {}).get('rect') or ()))
                              for r in s['rows'] for c in r['cells'])), _printed_lines_key(s)) for s in sources)
    return parts if all(part[2] for part in parts) else None


# The layer guard (backend half). A reading step that only adds to a page (the skipped-line layer,
# reading revision v20 on) must never cost a period the page proved without it: a document whose pages
# carry layer lines is read with and without them, and each group of statements sharing pages keeps the
# reading that proves more of its periods (the layered one when both prove as many). The evidence
# engine's half keeps the layer from switching off its targeted re-reads (pdf_extraction._withhold_layer).
def _inside(rect, area):
    x, y = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    return area[0] <= x <= area[2] and area[1] <= y <= area[3]


def _without_layer(sources):
    """The sources without the cells the skipped-line layer read, or None when no page carries any."""
    if not any((s.get('printed_lines') or {}).get('layer') for s in sources):
        return None
    stripped = []
    for source in sources:
        checked = source.get('printed_lines') or {}
        layer = [r for r in checked.get('layer') or () if isinstance(r, (list, tuple)) and len(r) == 4]
        if not layer:
            stripped.append(source)
            continue
        rows = []
        for row in source['rows']:
            cells = [c for c in row['cells'] if not (isinstance((c.get('locator') or {}).get('rect'), list)
                     and len(c['locator']['rect']) == 4 and any(_inside(c['locator']['rect'], area) for area in layer))]
            if cells:
                rows.append(dict(row, cells=cells))
        # Without the layer those lines are unread again, as the page OCR left them.
        stripped.append(dict(source, rows=rows, printed_lines=dict(checked=checked.get('checked'),
                             unread=list(checked.get('unread') or []) + [list(r) for r in layer])))
    return stripped


def _keep_proved(layered, base):
    """Per group of statements sharing a page (across both readings), the reading proving more periods."""
    items = [('layered', i, st) for i, st in enumerate(layered)] + [('base', i, st) for i, st in enumerate(base)]
    parent = list(range(len(items)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    pages = [set(st.get('page_numbers') or ()) for _, _, st in items]
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            if pages[a] & pages[b]:
                parent[find(a)] = find(b)
    groups = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)
    kept, any_base = [], False
    for members in groups.values():
        proved = {kind: sum(1 for k, _, st in members if k == kind and st['engine']['proved']) for kind in ('layered', 'base')}
        kind = 'base' if proved['base'] > proved['layered'] else 'layered'
        any_base = any_base or kind == 'base'
        for k, i, st in members:
            if k == kind:
                kept.append((min(st.get('page_numbers') or [0]), i,
                             dict(st, reading_layer='without_skipped_lines') if kind == 'base' else st))
    if not any_base:
        return layered
    return [st for _, _, st in sorted(kept, key=lambda item: (item[0], item[1]))]


def _guarded_reading(sources, profile):
    layered = _read_statements(sources, profile=profile)
    base_sources = _without_layer(sources)
    if base_sources is None:
        return layered
    return _keep_proved(layered, _read_statements(base_sources, profile=profile))


def read_statements(sources, *, profile=None):
    """Every statement section the engine finds, proved or not.

    A reading depends only on the stored sources (their revisions), so the
    last few documents' readings are kept: proposing each period re-reads the
    whole document, never a subset of its pages.
    """
    signature = _source_signature(sources)
    key = (signature, profile and profile.get('name'))
    if signature is not None:
        with _READINGS_LOCK:
            live = _LIVE_READINGS.get(key)
            if live is not None:
                _LIVE_READINGS.move_to_end(key)
                return live
            stored = _READINGS.get(key)
            if stored is not None:
                _READINGS.move_to_end(key)
        if stored is not None:
            result = pickle.loads(stored)
            _keep_live(key, result)
            return result
    token = _PROFILE.set(profile)
    try:
        result = _guarded_reading(sources, profile)
    finally:
        _PROFILE.reset(token)
    if signature is not None:
        stored = pickle.dumps(result, pickle.HIGHEST_PROTOCOL)
        with _READINGS_LOCK:
            _READINGS[key] = stored
            _READINGS.move_to_end(key)
            while len(_READINGS) > READINGS_KEPT:
                _READINGS.popitem(last=False)
        _keep_live(key, result)
    return result


def _read_statements(sources, *, profile=None):
    parens = any(re.search(r'\(\s*(?:US\$|\$)?\s*\d{1,3}(?:,\d{3})*[.,]\d{2}\s*\)', cell['expected_text'])
                 for source in sources for row in source['rows'] for cell in row['cells'])
    marker = _NO_PARENS.set(not parens)
    try:
        return _read_statements_parens(sources, profile)
    finally:
        _NO_PARENS.reset(marker)


def _read_statements_parens(sources, profile):
    pages = _pages(sources)
    if not pages:
        return []
    day_column = any(_is_header(row) and (any(column_role(label(t['t'])) == 'date' and label(t['t']) in _DAY_WORDS
                                              for t in row['tokens']) or _settlement_heading(row))
                     for rows in pages.values() for row in rows if row['tokens']) or _lost_day_heading(pages)
    token = _DAY_COLUMN.set(day_column)
    try:
        return _read_statements_in(pages, sources, profile)
    finally:
        _DAY_COLUMN.reset(token)


_DAY_WORDS = {'DIA', 'DAY'}


def _settlement_words():
    """The active profile's (operation, settlement) day heading words, or None (``settlement_days``)."""
    days = (_PROFILE.get() or {}).get('settlement_days')
    if not days:
        return None
    return {label(w) for w in days['operation']}, {label(w) for w in days['settlement']}


def _under_settlement_word(token, heading):
    """The token is printed under the movement heading's settlement-day word (``settlement_days``), not in a
    column further right (a short folio printed where a lost settlement day would be)."""
    words = _settlement_words()
    return any(label(t['t']) in words[1] and token['x0'] < t['x1'] and token['x1'] > t['x0'] for t in heading['tokens'])


def _settlement_heading(row):
    """A movement heading printing the profile's operation-day word left of its settlement-day word."""
    words = _settlement_words()
    if words is None:
        return False
    operation = [t['x0'] for t in row['tokens'] if label(t['t']) in words[0]]
    settlement = [t['x0'] for t in row['tokens'] if label(t['t']) in words[1]]
    return bool(operation and settlement) and min(operation) < min(settlement)


def _dateless_heading(row):
    """A movement heading printing credit and debit columns and a description but no date word."""
    words = {column_role(label(t['t'])) for t in row['tokens']}
    return {'credit', 'debit'} <= _money_roles(row) and 'description' in words and 'date' not in words


def _lost_day_heading(pages):
    """(B2) A day column whose heading word the scan lost: a movement heading printing credit and debit
    columns and a description but no date word, whose next line starts with a day of the month (1-31)
    alone and carries an amount."""
    style = separator_style(pages) or 'dot'
    for rows in pages.values():
        located = [r for r in rows if r['tokens']]
        for heading, following in zip(located, located[1:]):
            if not _dateless_heading(heading):
                continue
            first = min(following['tokens'], key=lambda t: (t['line'], t['x0']))['t']
            if (re.fullmatch(r'\d{1,2}', first) and 1 <= int(first) <= 31
                    and any(_value_kind(t, style, 2) == 'money' for t in following['tokens'])):
                return True
    return False


def _mark_stacked_summaries(rows, style):
    """(D7) A summary printed as a table: its labels as column headings of one to four lines, its amounts
    in the line below them ('Previous / Balance' ... 'New / Balance' over '$0.00 ... $107.82').

    Each heading word is assigned to the amount nearest it horizontally (the one it overlaps most, or one
    within a fiftieth of the page width); an amount's label is its
    words read top to bottom (``stacked_pairs``, read by ``label_pairs``). The fewest heading lines
    directly above the amounts are taken for which every word overlaps an amount, every amount has a
    label, and the labels name both an opening and a closing balance; otherwise nothing is marked.
    """
    located = [r for r in rows if r['tokens'] and r['y0'] is not None]
    for index, row in enumerate(located):
        if len(row['tokens']) < 3 or any(_value_kind(t, style, 2) != 'money' for t in row['tokens']):
            continue
        height = max(t['y1'] - t['y0'] for t in row['tokens'])
        values = sorted(row['tokens'], key=lambda t: t['x0'])
        headers, bottom = [], row['y0']
        for earlier in reversed(located[:index]):
            if bottom - earlier['y0'] > height * 2.2 or len(headers) == 4:
                break
            if any(_value_kind(t, style, 2) in ('money', 'date', 'count') for t in earlier['tokens']):
                break
            headers.append(earlier)
            bottom = earlier['y0']
            assigned = {id(v): [] for v in values}
            for word in (t for h in headers for t in h['tokens']):
                # The amount the word overlaps most, or (a short word beside its column's amount, '&') the
                # nearest one within a fiftieth of the page width.
                gap, best = min(((max(v['x0'] - word['x1'], word['x0'] - v['x1']), v) for v in values),
                                key=lambda item: item[0])
                if gap > (row['width'] or 0) * 0.02:
                    break
                assigned[id(best)].append(word)
            else:
                if all(assigned.values()):
                    pairs = [(label(' '.join(t['t'] for t in sorted(assigned[id(v)], key=lambda t: (t['y0'], t['x0'])))),
                              [('money', v)]) for v in values]
                    roles = {_role_of(text, liability) for text, _ in pairs for liability in (False, True)}
                    if {'opening', 'closing'} <= roles:
                        row['stacked_pairs'] = pairs
                        break


def _document_date_order(pages):
    """(B3) The day-month order of every numeric date with a year that reads in one order only
    ('11/19/2021': month first), or None when the document prints none or both."""
    orders = set()
    for rows in pages.values():
        for row in rows:
            for token in row['tokens']:
                if not re.search(r'\d[/.-]\d', token['t']):
                    continue
                kinds = {kind for d, mth, y, kind in _date_parts(token['t'])
                         if kind in ('dmy', 'mdy') and y and _calendar(y, mth, d)}
                if len(kinds) == 1:
                    orders |= kinds
    return orders.pop() if len(orders) == 1 else None


def _read_statements_in(pages, sources, profile):
    style = separator_style(pages)
    for rows in pages.values():
        _mark_stacked_summaries(rows, style or 'dot')
    document_order = _document_date_order(pages)
    order = (profile or {}).get('date_order') or document_order
    facts = {page: page_facts(rows, style or 'dot', order=order) for page, rows in pages.items()}
    _drop_file_numbering(facts)
    token = _DOCUMENT_ORDER.set(document_order)
    try:
        return _read_segments(pages, sources, profile, style, facts)
    finally:
        _DOCUMENT_ORDER.reset(token)


def _read_segments(pages, sources, profile, style, facts):
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
    for page, rows in pages.items():
        for value, rank in _stacked_accounts(rows):
            printed = {re.sub(r'\D', '', key) for key in facts[page]['accounts']}
            if re.sub(r'\D', '', value) not in printed:  # the same number printed inline is one account
                facts[page]['accounts'].setdefault(value, set()).add(rank)
    statements = []
    for segment in _segments(pages, facts):
        ordered = [row for page in segment['pages'] for row in pages[page]]
        mentions, labelled = [], set()
        for position, row in enumerate(ordered):
            row['_seg'] = position
            if row['tokens'] and not _row_is_movement(row, style or 'dot', 2):
                named = set()
                _currency(row, named)
                labelled |= named
                named |= _heading_currencies([row], style or 'dot')
                mentions.extend((position, code) for code in named)
        segment['currency_mentions'] = mentions
        segment['currency_labels'] = labelled
        sections = _sections(segment, pages, style or 'dot')
        page_use = {}
        for section in sections:
            for page in {row['page'] for row in section}:
                page_use[page] = page_use.get(page, 0) + 1
        read = []
        for section in sections:
            shared = any(page_use[row['page']] > 1 for row in section)
            read.append(_read_section(section, segment, pages, facts, style, sources, profile, shared=shared,
                                      several=len(sections) > 1))
        if len(read) > 1 and SUMMARY_BOX_MERGE:
            read = _merge_summary_boxes(read)
        if len(read) > 1:
            # A section with no movement, zero balances and no currency or account of its own is not a
            # period anyone could act on (annex and reference pages print zero lines too).
            read = [st for st in read if not _empty_section(st)] or read[:1]
        _hold_shared_account_credit_lines(read)
        statements.extend(read)
    _check_derived_starts(statements)
    return statements


#: (A7, D6) A statement printing a summary box per account on its first page and each account's movement table
#: on later pages reads as two sections of one account and period: the box (balances and printed totals, no
#: movement) and the table. When exactly one of them is proved and the other repeats its printed facts, the
#: box is the proved section's summary, not a period of its own: it joins that section. Off: both are listed,
#: the box held as before.
SUMMARY_BOX_MERGE = True
_BOX_KINDS = ('header', 'balance', 'statement_total')


def _box_facts(statement):
    """(openings, closings, {direction: (total, count)}) a movement-less section prints, or None when it holds
    anything else: a movement, a line it could not place, a scoped total, or two readings of one control."""
    openings, closings, totals = set(), set(), {}
    for row in statement['_rows']:
        kind, fields = row['kind'], row['fields']
        if kind == 'unresolved' and row.get('engine_hold'):
            continue
        if kind not in _BOX_KINDS or fields.get('total_scope'):
            return None
        if kind == 'balance':
            target = {'Opening Balance': openings, 'Closing Balance': closings}.get(fields.get('description'))
            if target is None:
                return None
            target.add(fields.get('balance'))
        elif kind == 'statement_total':
            direction = fields.get('total_direction')
            if direction not in ('credit', 'debit') or direction in totals:
                return None
            totals[direction] = (fields.get('balance'), fields.get('printed_transaction_count'))
    if len(openings) > 1 or len(closings) > 1:
        return None
    return openings, closings, totals


def _box_agrees(box, proved):
    """Every fact the box prints is the proved section's own: both balances it reads, and each printed
    direction total (and count) equal to the proved movements of that direction."""
    openings, closings, totals = box
    rows = proved['_rows']
    own = {d: {r['fields'].get('balance') for r in rows if r['kind'] == 'balance'
               and r['fields'].get('description') == d} for d in ('Opening Balance', 'Closing Balance')}
    if not (openings or closings) or (openings and openings != own['Opening Balance']) or (
            closings and closings != own['Closing Balance']):
        return False
    for direction, (total, count) in totals.items():
        moves = [r for r in rows if r['kind'] == 'transaction' and not r['excluded']
                 and r['fields'].get('direction') == direction]
        if total is None or int(total) != sum(int(r['fields']['amount_minor']) for r in moves):
            return False
        if count is not None and int(count) != len(moves):
            return False
    return True


def _merge_summary_boxes(read):
    """(A7, D6) Join each unproved, movement-less section to the one proved section of the same printed account,
    period, currency and convention whose printed balances and totals it repeats (SUMMARY_BOX_MERGE). The proof
    stays the proved section's own; the box adds its pages and rows to the period's scope, so the period's
    import and overlap checks cover everything printed about it."""
    digits = lambda st: re.sub(r'\D', '', st['account_reference'] or '')
    absorbed = set()
    for box in read:
        if box['engine']['proved'] or not box['period_start'] or not digits(box):
            continue
        facts = _box_facts(box)
        if facts is None:
            continue
        partners = [st for st in read if st is not box and id(st) not in absorbed and st['engine']['proved']
                    and st['period_start'] == box['period_start'] and st['period_end'] == box['period_end']
                    and digits(st) == digits(box) and st['balance_convention'] == box['balance_convention']
                    and (not box['currency'] or st['currency'] == box['currency'])]
        if len(partners) != 1 or not _box_agrees(facts, partners[0]):
            continue
        proved = partners[0]
        kept = [dict(r, kind='header', excluded=True, fields=dict(summary_of=proved['id'],
                                                                     description=r['fields'].get('description', '')))
                for r in box['_rows'] if r['kind'] != 'unresolved']
        before = box['page_numbers'][0] <= proved['page_numbers'][0]
        proved['_rows'] = kept + proved['_rows'] if before else proved['_rows'] + kept
        proved['page_numbers'] = sorted(set(proved['page_numbers']) | set(box['page_numbers']))
        known = {(s['page_number'], s['table_index']) for s in proved['sources']}
        proved['sources'] = sorted(proved['sources'] + [s for s in box['sources']
                                                        if (s['page_number'], s['table_index']) not in known],
                                   key=lambda s: (s['page_number'], s['table_index']))
        # The box keeps its own scope entries, even on a table the section also reads: an import region is
        # the vertical extent of one entry's rows, and one entry spanning the box and the movement table would
        # cross whatever is printed between them (another account's box), making that period read as saved.
        proved['section_sources'] = sorted(proved['section_sources'] + [dict(s) for s in box['section_sources']],
                                           key=lambda s: (s['page_number'], s['table_index'], s['row_indices'][:1]))
        proved['engine'] = dict(proved['engine'], summary_box=box['id'])
        absorbed.add(id(box))
    return [st for st in read if id(st) not in absorbed]


def _check_derived_starts(statements):
    """(B1) A start derived from the printed days in the billing cycle must follow the previous cycle of the
    same account where this file prints it (closing 27 to 35 days earlier): its closing date plus one. A
    start that does not is not used: the period is held."""
    for statement in statements:
        if statement.get('period_start_basis') != 'printed_day_count' or not statement['engine']['proved']:
            continue
        digits = re.sub(r'\D', '', statement['account_reference'])
        start, end = date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end'])
        previous = [date.fromisoformat(other['period_end']) for other in statements if other is not statement
                    and digits and re.sub(r'\D', '', other['account_reference']) == digits and other['period_end']
                    and 27 <= (end - date.fromisoformat(other['period_end'])).days <= 35]
        if previous and start - timedelta(days=1) not in previous:
            statement['engine'].update(proved=False, reason='period_start_contradicted')
            rows = statement['_rows']
            if rows and not any(r.get('engine_hold') for r in rows):
                rows.append(_hold_row(rows, 'period_start_contradicted'))


#: (A6, A7) A credit line sharing its deposit account's number is its own ledger account
#: (accounts.TIER_CREDIT_LINE). Off: such a section is held, as before the ledger could keep them apart.
SHARED_NUMBER_CREDIT_LINES_SEPARATE = True


def _hold_shared_account_credit_lines(read):
    """(A6, A7) Two sections of one statement printing the same account number in the same currency under
    different balance conventions: a deposit account and the credit line attached to it. The ledger knows an
    account by its institution and number, so the amounts-owed section is marked a credit line and kept as
    an account of its own (its key carries the product); the deposit account is read as usual. With the
    switch off the credit line is held, with a named reason."""
    deposits = {(re.sub(r'\D', '', st['account_reference']), st['currency']) for st in read
                if st['account_reference'] and st['balance_convention'] == 'asset_balance'}
    for st in read:
        key = (re.sub(r'\D', '', st['account_reference'] or ''), st['currency'])
        if st['balance_convention'] == 'liability_owed' and key[0] and key in deposits:
            if SHARED_NUMBER_CREDIT_LINES_SEPARATE:
                st['account_reference_kind'] = 'credit_line'
            elif st['engine']['proved']:
                st['engine'] = dict(st['engine'], proved=False, reason='account_shared')
                st['_rows'] = [r for r in st['_rows'] if r['kind'] != 'unresolved'] + [_hold_row(st['_rows'], 'account_shared')]
            else:
                st['engine'] = dict(st['engine'], reason=st['engine'].get('reason') or 'account_shared')


def _empty_section(statement):
    rows = statement['_rows']
    if any(r['kind'] == 'transaction' for r in rows) or statement['engine']['proved']:
        return False
    balances = [r['fields'].get('balance') for r in rows if r['kind'] in ('balance', 'statement_total')]
    # A currency inherited from the statement's label is not the section's own.
    own_currency = statement['currency'] and statement.get('currency_source') != 'printed_statement_currency'
    return (not own_currency and not statement['account_reference']
            and all(value in (None, '0') for value in balances))


def _sections(segment, pages, style):
    """Split a segment at an opening balance that follows a closing balance and movement lines (A7)."""
    rows = [row for page in segment['pages'] for row in pages[page]]
    sections, current, closed, moved, after_close, reopened = [], [], False, False, None, False
    # (E9) After a section's closing balance, a heading printing another set of amount columns than the
    # section's own movement heading opens another table (a list of the checks and items paid, already
    # among the movements): its dated amount lines belong to no section, up to a heading with the
    # movement table's columns again or a balance line. Its other lines stay where they are.
    main_roles, other_table = None, False
    for row in rows:
        pairs = [(text, values) for text, values in label_pairs(row, style, 2) if values]
        roles = {_role_of(text, False) for text, values in pairs}
        if row['tokens'] and _is_header(row):
            header_roles = _money_roles(row)
            if main_roles is None or not moved:
                # The movement table's heading is the one its movements are printed under; a summary printed
                # (and closed) before the movement table has no movements of its own.
                main_roles, other_table = header_roles, False
            elif closed and after_close is not None and header_roles != main_roles:
                # Only after a closing balance that ended the movements (none printed since it): a summary's
                # closing printed above the movement table does not end that table.
                other_table = True
                continue
            else:
                other_table = False
        if other_table:
            if roles & {'opening', 'closing'}:
                other_table = False
            elif _row_is_movement(row, style, 2):
                continue
        new_opening = {money(_control_value([t for kind, t in values if kind == 'money'])['t'], style)
                       for text, values in pairs if _role_of(text, False) == 'opening'
                       and any(kind == 'money' for kind, _ in values)}
        # A heading line repeated on every page ('... Saldo inicial 1,000.00' above each page's table)
        # continues the section: the same text printed on an earlier page of it is not a new opening.
        repeated = any(earlier['page'] != row['page'] and earlier['text'] == row['text'] for earlier in current)
        if ('opening' in roles and closed and current and not repeated
                and (moved or not new_opening <= _endpoints(current, style)['opening'])):
            # Lines printed after the closing balance (the next section's heading) open the next section.
            carried = current[after_close:] if after_close is not None else []
            sections.append(current[:after_close] if after_close is not None else current)
            current, closed, moved, after_close, reopened = list(carried), False, False, None, False
            main_roles = next((_money_roles(r) for r in current if r['tokens'] and _is_header(r)), None)
        elif 'opening' in roles and closed and current and new_opening and not repeated and 'closing' not in roles:
            # The section's own opening printed again after its summary's closing opens its movement
            # table (D6: table endpoints repeat the summary): the lines that follow are still this
            # section's, even where no movement line in them is read; the table's total line ends it.
            after_close, reopened = None, True
        current.append(row)
        if 'closing' in roles or ('column_total' in roles and (moved or reopened)
                                  # A total printed after the section's closing balance, with no movement
                                  # between them, totals another table (a payment slip), not this one.
                                  and (not closed or after_close is None or reopened)):
            # A table's own total line after its movements closes it as its closing balance does: lines
            # printed after it are the next section's heading.
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
            if here['opening'] and here['opening'] <= previous['opening'] and here['closing'] <= previous['closing']:
                merged[-1] = merged[-1] + section
                continue
        if merged and not any(_row_is_movement(r, style, 2) for r in merged[-1]):
            # A summary block whose opening was not read, printing the closing balance this section prints,
            # is this section's summary (its heading), not a period of its own.
            previous, here = _endpoints(merged[-1], style), _endpoints(section, style)
            if not previous['opening'] and previous['closing'] and previous['closing'] <= here['closing']:
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


_HEADING_ACCOUNT = re.compile(r'^([A-Z][A-Z .]{2,60}?)\s+(\d{2,4}(?:-\d{1,8}){1,3})$')
_HEADING_ACCOUNT_NOT = ('TEL', 'TELEFONO', 'FAX', 'RFC', 'R.F.C', 'CLIENTE', 'CODIGO', 'FOLIO', 'SUCURSAL', 'PLAZA',
                        'REFERENCIA', 'PERIODO', 'CP', 'C.P')


_SUFFIX_HEADING = re.compile(r'^([A-Z][A-Z .]{2,60}?)\s*-\s*(\d{3,6})(?:\s+\(CONTINUED[A-Z ]*\))?$')


def _suffix_heading_account(row):
    """'<product name> 1234' from a whole heading line '<product name> - 1234' (a section's account, printed
    as its last digits after the product name), or ''."""
    m = _SUFFIX_HEADING.match(' '.join(_dnorm(row['text']).split()))
    if not m or any(w.strip('.:') in _HEADING_ACCOUNT_NOT for w in m[1].split()):
        return ''
    # The product name stays with the digits, as printed: two accounts of one statement can print the same
    # last digits (a checking account and its line of credit), and the name is what tells them apart.
    printed = re.match(r'^(.*?)\s*-\s*\d', ' '.join(row['text'].split()))
    return (printed[1].strip() + ' ' + m[2]) if printed and printed[1].strip() else m[2]


def _titled_holder(segment_pages, pages, rule):
    """Library profile (data): the holder printed under the statement's title on its pages ('Statement of
    Account' then 'For <name>'). Every page printing the pair must name the same person, or none."""
    titles = {fold(t) for t in rule['title']}
    prefix = fold(rule['prefix']) + ' '
    names = set()
    for page in segment_pages:
        located = [r for r in pages[page] if r['tokens']]
        for upper, lower in zip(located, located[1:]):
            text = ' '.join(fold(upper['text']).split())
            below = ' '.join(lower['text'].split())
            if text in titles and fold(below).startswith(prefix):
                name = below[len(prefix):].strip()
                if _name_like(name):
                    names.add(name)
    return names.pop() if len(names) == 1 else ''


_CLIENT_LINE = re.compile(r'^(\d{6,12})\s+(\S.*)$')


def _client_line(segment_pages, pages):
    """Library profile (data, ``client_line``): (client number, holder) printed as the first line of every page
    of the statement ('<client number> <holder name>'), over the address on its first page. Every page printing
    such a line must print the same pair, and on some page the next line must be a street line (the addressee
    block); otherwise ('', '')."""
    found, addressed = set(), False
    for page in segment_pages:
        located = [r for r in pages[page] if r['tokens']]
        if not located:
            continue
        matched = _CLIENT_LINE.match(' '.join(located[0]['text'].split()))
        if not matched:
            continue
        number, name = matched[1], matched[2].strip()
        if not _name_like(name) or address_line(name):
            return '', ''
        found.add((number, name))
        # A line of rule marks the scan read between the name and the street prints no letter or figure.
        below = [r for r in located[1:] if re.search(r'[A-Za-z0-9]', r['text'])]
        if below and addressee_name([name, ' '.join(below[0]['text'].split())]):
            addressed = True
    return found.pop() if len(found) == 1 and addressed else ('', '')


def _heading_account(row):
    """'<product name> <hyphenated account number>' as a whole heading line, or as one whole line of one of
    its cells (a heading recognised together with the text beside or above it), or ''. One number or none."""
    lines = [row['text']] + [line for cell in row['raw']['cells'] for line in cell['expected_text'].split('\n')]
    found = {_heading_line_account(line) for line in lines} - {''}
    return found.pop() if len(found) == 1 else ''


def _heading_line_account(text):
    m = _HEADING_ACCOUNT.match(_dnorm(text))
    if not m or is_date_token(m[2]) or any(w.strip('.:') in _HEADING_ACCOUNT_NOT for w in m[1].split()):
        return ''
    return m[2] if 9 <= len(re.sub(r'\D', '', m[2])) <= 14 else ''


_INTERBANK_DIGITS = 18
_PRINTED_NUMBER = re.compile(r'(?<![\d-])\d[\d-]{6,16}\d(?![\d-])')


def _printed_over_interbank(account, rows):
    """(account, basis): the printed account number rather than the 18-digit interbank number (A6).

    An interbank number (CLABE: bank 3 + branch 3 + account 11 + check digit 1)
    carries the account number right-aligned in its account field. When the
    statement also prints that account number on its own (any digit run of 8 to
    11 digits that is exactly the end of the account field, outside the
    interbank number's own printing), the account is that printed number; one
    such number or none. Without one the interbank number stays the account
    and the basis says so.
    """
    digits = re.sub(r'\D', '', account)
    if len(digits) != _INTERBANK_DIGITS:
        return account, 'account_number'
    field = digits[6:17]
    own = re.compile(r'[\s-]?'.join(digits))
    found = {}
    for row in rows:
        if not row['tokens']:
            continue
        text = own.sub(' ', row['text'])
        for m in _PRINTED_NUMBER.finditer(text):
            value = m[0].strip('-')
            number = re.sub(r'\D', '', value)
            if 8 <= len(number) <= 11 and field.endswith(number) and field[:len(field) - len(number)].strip('0') == '':
                found.setdefault(number, value)
    if len(found) == 1:
        return next(iter(found.values())), 'account_number'
    return account, 'interbank_number'


def layout_key(header_words, convention):
    """The layout as a person recognises it: its movement headings and balance convention.

    Coarser than the fingerprint (no column positions, no per-period label set),
    so every period of one printed layout shares it; layout memory is keyed by it.
    """
    return _digest(dict(layout='statement-engine-layout-v1', header=sorted(header_words), convention=convention))[:16]


def _prints_liability(rows):
    phrases = [fold(p) for p in LIABILITY_EVIDENCE]
    return any(phrase in fold(row['text']) for row in rows if row['tokens'] for phrase in phrases)


def _read_section(rows, segment, pages, facts, style, sources, profile, shared=False, several=False):
    """One account section. ``shared``: another section is printed on one of its pages, so
    page-level facts (account, currency) cannot be attributed to it; only facts printed
    inside its own rows count (A6, A7, C2)."""
    section_pages = sorted({row['page'] for row in rows})
    f = [facts[p] for p in section_pages]
    # The section's own heading area: everything before its first movement line, ending at its
    # own closing balance (later pages are not its heading).
    head = []
    for row in rows:
        if row['tokens'] and _row_is_movement(row, style or 'dot', 2):
            break
        head.append(row)
        if row['tokens'] and any(_role_of(text, False) == 'closing' for text, values in label_pairs(row, style or 'dot', 2) if values):
            break
    # A section on shared pages names its account in its heading lines on the page where its opening
    # balance is printed: lines left on an earlier page (another section's chart legend or note printed
    # after that section's closing) do not name this one (A6, A7).
    opening_page = next((row['page'] for row in head if row['tokens'] and any(
        _role_of(text, False) == 'opening' for text, values in label_pairs(row, style or 'dot', 2) if values)), None)
    own_head = [row for row in head if row['page'] == opening_page] if opening_page is not None else head
    accounts = {}
    if shared:
        own = {}
        for row in own_head:
            if row['tokens']:
                _accounts(row, own)
        accounts = own
    else:
        # Only the statement's heading pages: account numbers on later pages describe
        # counterparties of transfers, not this account (A6, A10).
        for page in _heading_pages(segment['pages'], facts):
            for value, ranks in facts[page]['accounts'].items():
                accounts.setdefault(value, set()).update(ranks)
    account = ''
    if accounts:
        top = max(max(r) for r in accounts.values())
        best = {v for v, r in accounts.items() if top in r}
        account = next(iter(best)) if len(best) == 1 else ''
    if not account and shared and profile and profile.get('statement_account'):
        # Library profile (data): every section of this layout belongs to the contract printed once on
        # the statement's heading pages (one top-ranked number or none).
        printed = {}
        for page in _heading_pages(segment['pages'], facts):
            for value, ranks in facts[page]['accounts'].items():
                printed.setdefault(value, set()).update(ranks)
        if printed:
            top = max(max(r) for r in printed.values())
            best = {v for v, r in printed.items() if top in r}
            account = next(iter(best)) if len(best) == 1 else ''
    if not account and not accounts and profile and profile.get('account_heading'):
        # Library profile (data): this layout prints the account only after the product name in a
        # section heading ("<product name> 12-34567890-1"). One distinct heading number or none.
        heading_pages = set(_heading_pages(segment['pages'], facts))
        scope = own_head if shared else [row for row in rows if row['page'] in heading_pages]
        found = {_heading_account(row) for row in scope if row['tokens']} - {''}
        account = found.pop() if len(found) == 1 else ''
    account_basis = ''
    if profile and profile.get('account_suffix_heading'):
        # Library profile (data): each section names its own account in its heading, after the product
        # name ('<product name> - 1234'); numbers on the statement's other pages (a deposit slip listing
        # every account) never name a section. One distinct heading number in the section's own heading
        # lines, or none.
        found = {_suffix_heading_account(row) for row in own_head if row['tokens']} - {''}
        account = found.pop() if len(found) == 1 else ''
        account_basis = 'section_heading_suffix' if account else ''
    elif account:
        scope = head if shared else [row for page in _heading_pages(segment['pages'], facts) for row in pages[page]]
        account, account_basis = _printed_over_interbank(account, scope)
    client_number, client_name = _client_line(segment['pages'], pages) if profile and profile.get('client_line') else ('', '')
    if client_number and not account:
        account, account_basis = client_number, 'client_line'
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
    if several:
        # A statement of several sections (C5, A7): card vocabulary counts only where this section prints it,
        # up to its own closing balance. A deposit account printed beside a credit line, or before the
        # statement's closing disclosures about credit lines, does not take their 'credit limit' as its own.
        own = []
        for row in rows:
            own.append(row)
            if row['tokens'] and any(_role_of(text, False) == 'closing'
                                     for text, values in label_pairs(row, style or 'dot', 2) if values):
                break
        liability = _prints_liability(own)
    if profile and profile.get('convention'):
        liability = profile['convention'] == 'liability_owed'
    if profile and profile.get('currency') and not currency and (
            not shared or (profile.get('account_suffix_heading') and not segment.get('currency_mentions'))):
        # A section sharing its pages takes the profile's currency only in a layout whose sections each
        # name their own account (account_suffix_heading), and only when the statement names no currency.
        currency, currency_basis = profile['currency'], 'library_profile'
        try:
            exponent = get_currency(currency).exponent
        except MoneyError:
            exponent = 2
    # The holder belongs to the statement, printed on its first pages, for every one of its sections.
    holder = _section_holder(segment['pages'], pages, facts, style)
    if profile and profile.get('holder_heading'):
        titled = _titled_holder(segment['pages'], pages, profile['holder_heading'])
        if titled and (not holder or fold(holder) == fold(titled)):
            holder = titled
        elif not titled or holder:
            holder = holder if not titled else ''
    if client_name:
        # Library profile (data): the name printed after the client number on every page, never over a
        # different holder read from the address block.
        holder = client_name if not holder or fold(holder) == fold(client_name) else ''
    institution = _institution([item['legal'] for item in f],
                               {line for page in set(_heading_pages(segment['pages'], facts)) | set(segment['pages'][:2])
                                for line in facts[page]['legal']}, pages)
    profiled = (profile or {}).get('institution', '')
    if institution and profiled and not _same_issuer(institution, profiled):
        # The library profile matched printed wording that only its issuer prints: a different name
        # read from a logo or heading is a misreading, never another issuer.
        institution = ''
    institution = institution or profiled
    if holder and fold(holder) in {fold(name) for name in (institution, (profile or {}).get('institution')) if name}:
        # The issuer's own name (its remittance address block) is never the holder.
        holder = ''
    period = segment['period']
    statement = dict(layout_id=LAYOUT, institution=institution, account_reference=account,
                     period_start=period[0].isoformat() if period else '', period_end=period[1].isoformat() if period else '',
                     holder=holder, currency=currency, account_basis=account_basis,
                     # A shared page cannot lend its currency to this section: an unread one stays unread.
                     currency_source=currency_basis or ('printed_account_section' if shared else ''),
                     account_type='credit_card' if liability else 'checking',
                     balance_convention='liability_owed' if liability else 'asset_balance',
                     page_numbers=section_pages,
                     identity_evidence=identity_evidence(segment, section_pages, rows, pages, facts, style))
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
                     layout_fingerprint=reading['fingerprint'], layout_key=reading['layout_key'], engine=reading['proof'])
    if profile:
        statement['engine_profile'] = profile['name']
    if period and any(period in facts[p].get('closing_only', set()) for p in segment['pages']):
        # Only the closing date is printed: the start is the closing date less the printed days in the
        # billing cycle (B1), derived, never printed. The import records it as derived.
        statement.update(period_start_basis='printed_day_count', printed_closing_date=period[1].isoformat())
    numbered = segment.get('numbering_pages') or segment['pages']
    if not _numbering_complete(numbered, facts) and reading['proof']['proved']:
        if reading['table_end'] and _numbering_complete(numbered, facts, after=reading['table_end']):
            # (A3) Printed pages unread only after the page on which the movement table printed its own end
            # (year-to-date heading, column total or closing line, after its last movement): such a page cannot
            # hold one of this period's movements. The proof records it.
            reading['proof']['pages_unread_after_table'] = True
        else:
            reading['proof'].update(proved=False, reason='pages_missing')
    if segment.get('conflict') and reading['proof']['proved']:
        reading['proof'].update(proved=False, reason='no_period')
    if not period and reading['proof']['proved']:
        reading['proof'].update(proved=False, reason='no_period')
    named = {code for _, code in segment.get('currency_mentions', [])}
    if shared and not statement['currency'] and len(named) == 1 and segment.get('currency_labels') == named:
        # A section sharing a page names no currency of its own, and the statement prints exactly one
        # currency, under a currency label ('MONEDA: ...'): that is the statement's currency, so it is the
        # section's (C2). A currency named only in another section's heading is that section's; a
        # statement naming several currencies keeps the rule below (only the section's own heading counts).
        statement.update(currency=next(iter(named)), currency_source='printed_statement_currency')
        try:
            new_exponent = get_currency(statement['currency']).exponent
        except MoneyError:
            new_exponent = 2
        if new_exponent != exponent:
            reading = _reading(rows, statement, style, new_exponent, liability, period)
            statement.update(layout_fingerprint=reading['fingerprint'], layout_key=reading['layout_key'],
                             engine=reading['proof'])
        statement['id'] = _digest(dict(layout_id=LAYOUT, account=account, start=statement['period_start'],
                                       end=statement['period_end'], currency=statement['currency'],
                                       first_page=section_pages[0], first_row=reading['first_row']))
    if len(named) > 1:
        # Several currencies are printed in this statement: the section's own is the nearest one
        # named inside the section above its opening balance; otherwise it stays unread (C2, A7).
        opening = next((r for r in reading['rows'] if r['kind'] == 'balance'
                        and r['fields'].get('description') == 'Opening Balance'), None)
        rows_by_id = {_item(r)['id']: r for r in rows}
        anchor = rows_by_id.get(opening['id'].split(':opening')[0]) if opening else None
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
                statement.update(layout_fingerprint=reading['fingerprint'], layout_key=reading['layout_key'],
                                 engine=reading['proof'])
            statement['id'] = _digest(dict(layout_id=LAYOUT, account=account, start=statement['period_start'],
                                           end=statement['period_end'], currency=attributed, first_page=section_pages[0],
                                           first_row=reading['first_row']))
    statement['_rows'] = reading['rows']
    return statement


# ---------------------------------------------------------------------------
# Reading one section: controls, movements, columns, proof
# ---------------------------------------------------------------------------

# (B5) A table whose movement lines print two date columns: a line that reads only its first date, while the word
# standing at the second date column's left edge is no date but date-shaped ink (digits, a short word: '2l\\MAR'
# beside a first date read '24/MAR'), has its printed dates damaged. Unless what can be read of that ink agrees
# with the first date (``_ink_agrees``), the first date has lost the column that would confirm it and may be
# misread too, so the line's date is not taken and the period is not proved. Off: the line keeps its first date
# and the damaged word joins its description.
UNREAD_SECOND_DATE_HOLDS = True
_DATE_COLUMN_EDGE = 0.01
_DATE_INK = re.compile(r'^(?=\S*\d)\S{2,11}$')


def _unread_second_dates(movements, width):
    """Mark (``date_unread``) and return the movement lines whose second printed date is unread ink (B5)."""
    if not UNREAD_SECOND_DATE_HOLDS:
        return []
    dated = [m for m in movements if m['date_tokens']]
    two = [m for m in dated if len(m['date_tokens']) > 1]
    if len(two) < 2 or 2 * len(two) <= len(dated):
        return []

    def left(token):
        return token['x0'] / (token.get('_width') or width) - token.get('_shift', 0.0)

    lefts = sorted(left(m['date_tokens'][1]) for m in two)
    edge = lefts[len(lefts) // 2]
    unread = []
    for move in dated:
        if len(move['date_tokens']) != 1:
            continue
        tokens = merged_dates(move['row']['tokens'])
        after = [t for t in tokens if t['line'] == move['date_tokens'][0]['line']
                 and t['x0'] > move['date_tokens'][0]['x0'] and t is not move['date_tokens'][0]]
        if not after:
            continue
        word = min(after, key=lambda t: t['x0'])
        if (abs(left(word) - edge) <= _DATE_COLUMN_EDGE and _DATE_INK.match(word['t'])
                and not is_date_token(word['t']) and not any(word is t for t in move['money'])
                and not _ink_agrees(word['t'], move['date_tokens'][0]['t'])):
            move['date_unread'] = True
            unread.append(move)
    return unread


_LEADING_FIGURES = re.compile(r'^(\d{1,2})(?!\d)')
_INK_DATE = re.compile(r'(?<!\d)\d{1,2}[/.-](?:[A-Z]{3,10}|\d{1,2})(?![A-Z\d])')
_MONTH_WORD = re.compile(r'[A-Z]{3,10}')


def _ink_agrees(ink, first):
    """The damaged second date still prints the first date's leading figures, and no month word other than the
    first date's ('07/MXR' or '22/ENE_N0' beside '07/MAR' or '22/ENE'): the two columns print the same day,
    so the first date is corroborated. A whole date the ink carries after marks OCR read over the gap
    ('~-:dO7/MAR', the zero read as O) corroborates only when it is the first date. A leading figure that
    differs ('31' beside '13') or that cannot be read leaves it uncorroborated."""
    inside = [m for m in _INK_DATE.finditer(_OCR_ZERO.sub('0', _dnorm(ink))) if is_date_token(m[0])]
    if inside:
        # A whole date printed inside the ink (a mark OCR read over the gap glued to it): it is that date.
        printed = {(d, mth) for d, mth, _, _ in _date_parts(first)}
        return all({(d, mth) for d, mth, _, _ in _date_parts(m[0])} & printed for m in inside)
    lead, own = _LEADING_FIGURES.match(_dnorm(ink)), _LEADING_FIGURES.match(_dnorm(first))
    if not lead or not own or int(lead[1]) != int(own[1]):
        return False
    months = {MONTHS[w] for w in _MONTH_WORD.findall(_dnorm(ink)) if w in MONTHS}
    printed = {MONTHS[w] for w in _MONTH_WORD.findall(_dnorm(first)) if w in MONTHS}
    return not months or months == printed


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
    # A library profile's order, or the order every unambiguous numeric date of the document prints (B3).
    fixed = (_PROFILE.get() or {}).get('date_order') or _DOCUMENT_ORDER.get()
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
            for position, token in enumerate(move['date_tokens']):
                # The row date lies in the period (the card window below its start); a second printed date
                # (settlement / value date, B5) may fall up to a month either side of it.
                first, last = (low, end) if position == 0 else (start - timedelta(days=31), end + timedelta(days=31))
                found = set()
                if not _date_parts(token['t']) and _day_only(token['t'].rstrip('.,')):
                    # The day alone: the one date with that day inside the printed period (B2).
                    day, cursor = int(token['t'].rstrip('.,')), start
                    while cursor <= end:
                        if cursor.day == day:
                            found.add(cursor)
                        cursor += timedelta(days=1)
                for d, mth, y, kind in _date_parts(token['t']):
                    if kind in ('dmy', 'mdy') and kind != order:
                        continue
                    years = [y] if y else range(first.year, last.year + 1)
                    for year in years:
                        day = _calendar(year, mth, d)
                        if day and first <= day <= last:
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
    """Right-edge bands of money tokens (E2), as fractions of the page width. A band formed only by boxes wider
    than their amounts (``_left_x1``), each reaching another band from its box's left edge, is no column."""
    chosen = [t for t in tokens if t['exact'] or t['last']] or list(tokens)
    edges = sorted(((_edge(t, width), t) for t in chosen), key=lambda pair: pair[0])
    bands = []
    for edge, token in edges:
        if bands and edge - bands[-1][-1][0] <= 0.012:
            bands[-1].append((edge, token))
        else:
            bands.append([(edge, token)])
    centres = [sorted(e for e, _ in band)[len(band) // 2] for band in bands]
    kept = []
    for index, band in enumerate(bands):
        others = [c for i, c in enumerate(centres) if i != index and not all('_left_x1' in t for _, t in bands[i])]
        if all('_left_x1' in t and any(abs(_edge(dict(t, x1=t['_left_x1']), width) - c) <= 0.012 for c in others)
               for _, t in band):
            continue
        kept.append(centres[index])
    return kept or centres


def _edge(token, width):
    """A token's right edge as a fraction of its page width, on its page's aligned position."""
    return token['x1'] / (token['_width'] or width) - token.get('_shift', 0.0)


def _page_shifts(rows, style, exponent, width):
    """{page: horizontal offset} of scanned pages whose amount columns sit to one side of the
    reference page's (the page with the most movement amounts) (E2, F).

    A scan places each sheet with its own offset, so one printed column lands a
    little left or right on each page. A page is aligned only when one offset of
    at most 4% of the width puts more of its movement amounts on the reference
    columns than leaving it in place, and puts at least 80% of them there.
    """
    edges = {}
    for row in rows:
        if row['tokens'] and _row_is_movement(row, style, exponent):
            for token in row['tokens']:
                if (token['exact'] or token['last']) and _value_kind(token, style, exponent) == 'money':
                    edges.setdefault(row['page'], []).append(token['x1'] / (token['_width'] or width))
    if len(edges) < 2:
        return {}
    reference = max(sorted(edges), key=lambda page: len(edges[page]))
    bands = []
    for edge in sorted(edges[reference]):
        if bands and edge - bands[-1][-1] <= 0.012:
            bands[-1].append(edge)
        else:
            bands.append([edge])
    centres = [sorted(band)[len(band) // 2] for band in bands]

    def placed(values, shift):
        return sum(any(abs(value - shift - centre) <= 0.006 for centre in centres) for value in values)

    shifts = {}
    for page, values in edges.items():
        if page == reference:
            continue
        here = placed(values, 0.0)
        best, shift = max((placed(values, step / 1000), -abs(step), step / 1000) for step in range(-40, 41))[0::2]
        if best > here and best >= 0.8 * len(values):
            shifts[page] = shift
    return shifts


def _band(token, columns, width):
    band = _edge_band(token, columns, width)
    if band is None and '_left_x1' in token:
        # A box wider than its amount: the column its characters reach from the box's left edge.
        band = _edge_band(dict(token, x1=token['_left_x1']), columns, width)
    return band


def _edge_band(token, columns, width):
    edge = _edge(token, width)
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
                    shift = group[0].get('_shift', 0.0) * (row['width'] or width)
                    words.append((role, group[0]['x0'] - shift, group[-1]['x1'] - shift, row['width'] or width))
                    break
        for i, column in enumerate(columns):
            scored = []
            for role, x0, x1, w in words:
                if role not in ('credit', 'debit', 'balance', 'amount', 'ignore'):
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


def _money_roles(header):
    """The amount-column roles a movement heading prints (credit, debit, balance, amount)."""
    roles = set()
    tokens = sorted(header['tokens'], key=lambda t: (t['line'], t['x0']))
    for size in (3, 2, 1):
        for index in range(len(tokens) - size + 1):
            role = column_role(label(' '.join(t['t'] for t in tokens[index:index + size])))
            if role in ('credit', 'debit', 'balance', 'amount'):
                roles.add(role)
    return frozenset(roles)


_GLUED_DAYS = re.compile(r'^(\d{1,2})[.,](\d{1,2})$')


def _split_glued_days(row, style):
    """(profile, settlement days) The operation and settlement days read as one word joined by a mark
    ('13.13' for '13 13') at the start of a movement line are the two days. Only the settlement day is
    taken, and it is confirmed against the day printed on the end-of-day balance after the line."""
    tokens = sorted(row['tokens'], key=lambda t: (t['line'], t['x0']))
    if len(tokens) < 3:
        return
    first = tokens[0]
    found = _GLUED_DAYS.match(first['t'])
    if not found or not all(1 <= int(day) <= 31 for day in found.groups()):
        return
    if not any(money(t['t'], style, 2) is not None and re.search(r'[.,]\d{2}\)?$', t['t']) for t in tokens[2:]):
        return
    middle = first['x0'] + (first['x1'] - first['x0']) * len(found[1]) / len(first['t'])
    operation = dict(first, t=found[1], f=fold(found[1]), x1=middle, exact=False, last=False)
    settlement = dict(first, t=found[2], f=fold(found[2]), x0=middle, exact=False)
    row['tokens'] = [operation, settlement] + [t for t in row['tokens'] if t is not first]


def _reading(rows, statement, style, exponent, liability, period):
    width = next((r['width'] for r in rows if r['width']), None)
    proof = dict(engine=ENGINE_VERSION, proved=False, reason='', convention='liability_owed' if liability else 'asset_balance')
    result = dict(rows=[], proof=proof, fingerprint='', layout_key='', first_row='', table_end=None)
    if style is None:
        proof['reason'] = 'separators_mixed'
    if any(not r['located'] and _unlocated_matters(r, style or 'dot', exponent) for r in rows):
        proof['reason'] = proof['reason'] or 'no_geometry'
    controls = dict(opening=[], closing=[], credit_total=[], debit_total=[], credit_component=[], debit_component=[],
                    net_component=[], section_total=[], day_opening=[])
    # (profile) Movement lines print the operation day then the settlement day (``settlement_days``).
    settlement = _DAY_COLUMN.get() and _settlement_words() is not None
    movements, headers, labels_seen, unplaced, continuation_of, column_totals = [], [], set(), [], {}, []
    # The movement table's printed section (its heading's folded label) the lines below belong to (D4).
    section = None
    # Rows printing the end of the movement table: the year-to-date heading, a column total, a closing line.
    ends = []
    region = False
    # Printed totals count only inside a summary block: after an opening balance, up to the closing one (D4, D7).
    in_summary = False
    undated_rows = []
    last_move = None
    for index, row in enumerate(rows):
        row['_index'] = index
        if settlement:
            _split_glued_days(row, style or 'dot')
        for token in row['tokens']:
            token['_width'] = row['width'] or width
            token['_shift'] = 0.0
    shifts = _page_shifts(rows, style or 'dot', exponent, width or 1)
    for row in rows:
        for token in row['tokens']:
            token['_shift'] = shifts.get(row['page'], 0.0)
    # Amount bands from the dated movement lines, before deciding what else carries money (E2).
    early = [t for row in rows if row['tokens'] and _row_is_movement(row, style or 'dot', exponent)
             for t in row['tokens'] if _value_kind(t, style or 'dot', exponent) == 'money']
    early_columns = _columns(early, width or 1) if early else []
    block = (_PROFILE.get() or {}).get('prior_period_block')
    prior = False
    # (E9) The movement table's amount columns, from its first heading; after the table's own total line,
    # a heading printing another set of amount columns opens another table (pending charges, a schedule):
    # its lines are not this period's movements, up to a heading of the movement table again or a balance.
    main_roles, totalled, other_table = None, False, False
    consumed, blank_dated = set(), []
    # Index of the line where the movement table printed its own credit or debit total after a movement (E9).
    table_totals = None
    for index, row in enumerate(rows):
        if not row['tokens'] or row.get('payment_box') or index in consumed:
            continue
        if other_table:
            if _is_header(row) and _money_roles(row) == main_roles:
                other_table = False
            elif any(_role_of(text, liability) in ('opening', 'closing')
                     for text, values in label_pairs(row, style or 'dot', exponent) if values):
                other_table = False
            else:
                continue
        if block:
            # Library profile (data): earlier periods' operations repeated to explain a balance (E7).
            folded = fold(row['text'])
            if any(folded.startswith(fold(p)) for p in block['start']):
                prior = True
            elif any(folded.startswith(fold(p)) for p in block['end']):
                prior = False
            if prior:
                continue
        words = {label(t['t']) for t in row['tokens']}
        if _is_header(row) or _DAY_COLUMN.get() and _dateless_heading(row):
            roles = _money_roles(row)
            if main_roles is None:
                main_roles = roles
            elif totalled and roles != main_roles:
                other_table = True
                continue
            headers.append(row)
            labels_seen.update(w for w in words if column_role(w))
            region = True
            continue
        if region and YEAR_TO_DATE.fullmatch(label(row['text'])):
            # A card's year-to-date block after its section totals: neither movements nor controls, up to the
            # movement table's heading again or a balance (read as another table, E9).
            other_table = True
            last_move = None
            ends.append(index)
            continue
        if region and liability and _section_heading(row, style or 'dot', exponent):
            section = label(row['text'])
            labels_seen.add(section)
            last_move = None
            continue
        if _row_is_movement(row, style or 'dot', exponent):
            tokens = merged_dates(row['tokens'])
            date_tokens = []
            rest = list(tokens)
            if rest and _leading_date(rest[0]['t'].rstrip('.,')):
                date_tokens.append(rest.pop(0))
            while rest and is_date_token(rest[0]['t']) and len(date_tokens) < 2:
                date_tokens.append(rest.pop(0))
            settlement_unread = False
            if settlement:
                # (profile) The operation day, then the settlement day the printed balance moved on: the line is
                # dated by its settlement day. A line printing one day alone cannot say which day it is.
                if (len(date_tokens) == 1 and rest and _day_only(rest[0]['t'].rstrip('.,')) and headers
                        and _under_settlement_word(rest[0], headers[-1])):
                    date_tokens = [rest.pop(0)]
                else:
                    settlement_unread = True
            money_tokens = [t for t in rest if _value_kind(t, style or 'dot', exponent) == 'money']
            words_only = [t for t in rest if t not in money_tokens]
            # Under settlement days the line also prints figures between its days and its label (a folio,
            # titles, a price): only words carry the label of an opening or closing line.
            text = label(' '.join(t['t'] for t in words_only if not settlement or re.search(r'[A-Za-z]', t['t'])))
            role = _role_of(text, liability)
            if role in ('opening', 'closing') and len(money_tokens) >= 1:
                controls[role].append(dict(row=row, value_token=money_tokens[-1], count=None))
                labels_seen.add(text)
                continue
            if role in ('subtotal', 'column_total', 'credit_total', 'debit_total', 'credit_component', 'debit_component',
                        'net_component', 'section_total') and not (role in ('credit_component', 'debit_component')
                                                                   and section == text):
                # A dated line under its own section heading ('Interest Charged:' over '<date> INTEREST CHARGED
                # 1.10') is that section's movement, not the summary's component (D4, D7).
                continue
            first_money = min(money_tokens, key=lambda t: t['x0'])
            description = [t for t in words_only if t['x0'] < first_money['x0'] or t['line'] > 0]
            move = dict(row=row, date_tokens=date_tokens, money=money_tokens, description=description,
                        stray=[t for t in words_only if t not in description], continuation=[], section=section)
            if settlement_unread:
                move['date_unread'] = True
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
            if role in ('credit_total', 'debit_total', 'credit_component', 'debit_component', 'net_component') and not in_summary:
                handled = handled or bool(money_values)
                if role in ('credit_total', 'debit_total') and money_values and movements:
                    # The movement table printing its own totals after its last movement (E9).
                    table_totals = index
                continue
            if role == 'day_balance' and money_values:
                # (profile) The balance at the end of a day, printed after that day's movements: the running
                # balance after the last movement line printed before it (page furniture and a page break may
                # stand between them), or, before any movement, the opening balance again.
                value_token = _control_value(money_values)
                # The day the line names, printed between its label and its balance ('... dia 25 98.01').
                days = [t for _, t in values if t is not value_token and re.fullmatch(r'\d{1,2}', t['t'])]
                if movements:
                    movements[-1].setdefault('day_balances', []).append(value_token)
                    movements[-1].setdefault('balance_days', []).append(int(days[-1]['t']) if len(days) == 1 else None)
                else:
                    controls['day_opening'].append(dict(row=row, value_token=value_token, count=None))
                handled = True
                continue
            if role == 'section_total' and money_values:
                # A section's own printed total (D4): a control on the lines under the section's heading.
                controls['section_total'].append(dict(row=row, value_token=_control_value(money_values), count=None,
                                                      headings=SECTION_HEADINGS[text], scope=SECTION_SCOPE[text]))
                labels_seen.add(text)
                handled = True
                if section in SECTION_HEADINGS[text]:
                    section = None
                continue
            if role in ('opening', 'closing', 'credit_total', 'debit_total', 'credit_component', 'debit_component',
                        'net_component') and money_values:
                count = counts[0]['t'] if role.endswith('_total') and len(counts) == 1 and values[0][0] == 'count' else None
                controls[role].append(dict(row=row, value_token=_control_value(money_values), count=count))
                labels_seen.add(text)
                handled = True
                if role == 'closing':
                    in_summary = False
                    ends.append(index)
            elif (role == 'column_total' and money_values and OTHER_TABLE_TOTALS and table_totals is not None
                  and table_totals > movements[-1]['row']['_index']):
                # (E9) After the movement table printed its own totals, with no movement line since, a column-total
                # line totals another table printed below it (a listing of investments): not this table's control.
                handled = True
            elif role == 'column_total' and not values and movements:
                # A column-total label printed alone after a movement heads the movement table's own totals block
                # ('Total de Movimientos' over its printed debit and credit totals) (E9).
                table_totals = index
            elif role == 'column_total' and money_values:
                ends.append(index)
                column_totals.append(dict(row=row, tokens=money_values))
                labels_seen.add(text)
                handled = True
                totalled = totalled or main_roles is not None
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
            undated_rows.append((row, section))
            continue
        if not has_money and region and len(row['tokens']) == 1 and _leading_date(row['tokens'][0]['t'].rstrip('.,')):
            # A movement date printed with nothing beside it: the line's content is missing (blacked out by
            # a redaction, or not read). Its amount cannot be known, so the period cannot be proved.
            blank_dated.append(row)
            continue
        if not has_money and region:
            two_line = _two_line_entry(rows, index, style or 'dot', exponent, early_columns, width or 1)
            if two_line is not None:
                # (E4) A dated line without an amount whose next line prints the amount is one movement.
                following, date_tokens, words_only, money_tokens = two_line
                move = dict(row=row, date_tokens=date_tokens, money=money_tokens, description=words_only,
                            stray=[], continuation=[following])
                movements.append(move)
                continuation_of[following['_index']] = move
                consumed.add(following['_index'])
                last_move = move
                continue
        if not has_money:
            if last_move is not None and region and _continues(row, last_move):
                last_move['continuation'].append(row)
                continuation_of[index] = last_move
            else:
                last_move = None if last_move is not None and row['page'] == last_move['row']['page'] and _below(row, last_move) else last_move
            continue
        if region and last_move is not None and row['page'] == last_move['row']['page']:
            money_here = [t for t in row['tokens'] if _value_kind(t, style or 'dot', exponent) == 'money']
            band = _band(money_here[0], early_columns, width or 1) if len(money_here) == 1 and early_columns else None
            taken = {_band(t, early_columns, width or 1) for t in last_move['money']}
            if band is not None and band not in taken and _continues(row, last_move):
                # A multi-line entry prints one more value (its amount, or the day's balance) on its last
                # line, in a column the dated line left empty (E3, C9). The proof assigns its role.
                last_move['money'].append(money_here[0])
                last_move['continuation'].append(row)
                continuation_of[index] = last_move
                continue
            unplaced.append(row)
    result['first_row'] = (rows[0]['page'], rows[0]['source']['table_index'], rows[0]['raw']['row_index']) if rows else ''
    # The page on which the movement table printed its end after its last movement (or None).
    last = max((m['row']['_index'] for m in movements), default=None)
    result['table_end'] = next((rows[end]['page'] for end in ends if last is not None and end > last), None)
    # Unplaced money lines only count inside a page's movement region: between its first and last movement.
    spans = {}
    for move in movements:
        spans.setdefault(move['row']['page'], []).append(move['row']['_index'])
    unplaced = [row for row in unplaced if row['page'] in spans
                and min(spans[row['page']]) < row['_index'] < max(spans[row['page']])]
    # A dated line printing nothing else counts only where movement lines of the table follow it on its page
    # (rows blacked out inside the table); a stray date after the table's last movement, or printed in
    # another form than the movement dates (a column of authorisation dates read apart), is not one.
    # Only a date printed in the form the table's movement lines use is a blacked-out movement line.
    shape = lambda text: re.sub(r'[A-Za-z]', 'A', re.sub(r'\d', '9', text))
    forms = {shape(move['date_tokens'][0]['t']) for move in movements if move['date_tokens']}
    blank_dated = [row for row in blank_dated if row['page'] in spans and row['_index'] < max(spans[row['page']])
                   and shape(row['tokens'][0]['t']) in forms]
    # Undated card charges (B6) inside the region are movements ordered at the period end.
    undated = []
    for row, undated_section in undated_rows:
        money_tokens = [t for t in row['tokens'] if _value_kind(t, style or 'dot', exponent) == 'money']
        first_money = min(money_tokens, key=lambda t: t['x0'])
        undated.append(dict(row=row, date_tokens=[], money=money_tokens,
                            description=[t for t in row['tokens'] if t not in money_tokens and t['x0'] < first_money['x0']],
                            stray=[], continuation=[], undated=True, section=undated_section))
    all_moves = sorted(movements + undated, key=lambda m: m['row']['_index'])
    money_tokens = [t for move in all_moves for t in move['money']]
    columns = _columns(money_tokens, width or 1) if money_tokens else []
    hints = _hints(headers, columns, width or 1) if columns else {}
    result['fingerprint'] = _fingerprint({label(t['t']) for h in headers for t in h['tokens']}, columns,
                                         labels_seen, proof['convention'])
    result['layout_key'] = layout_key({label(t['t']) for h in headers for t in h['tokens']}, proof['convention'])
    dated = [m for m in all_moves if not m.get('undated')]
    resolved, date_problem = _resolve_dates(dated, period, liability) if dated else ([], None if period else 'no_period')
    unread_dates = _unread_second_dates(dated, width or 1) + [m for m in dated if m.get('date_unread')
                                                               and settlement]
    # (profile) Every movement's settlement day is the day printed on the end-of-day balance closing its group
    # of lines; a line no end-of-day balance follows is not confirmed.
    day_differs = []
    if settlement:
        group = []
        for move in dated:
            group.append(move)
            if move.get('balance_days'):
                for other in group:
                    day = other['date_tokens'][0]['t'].rstrip('.,') if other['date_tokens'] else ''
                    if not day.isdigit() or any(printed != int(day) for printed in move['balance_days']):
                        day_differs.append(other)
                group = []
        day_differs.extend(group)
    candidates = _search(all_moves, columns, hints, controls, column_totals, style or 'dot', exponent, liability)
    # Among readings with the same money, keep one whose running balance chains (its balances are printed values).
    proving = sorted((c for c in candidates if c['proved']), key=lambda c: not c.get('chain_ok'))
    readings = {}
    for candidate in proving:
        readings.setdefault(candidate['key'], candidate)
    chosen = None
    if not proof['reason']:
        if not all_moves and not controls['opening'] and not controls['closing']:
            proof['reason'] = 'no_movements_or_controls'
        elif not controls['opening']:
            proof['reason'] = 'no_opening'
        elif not controls['closing'] and not column_totals:
            proof['reason'] = 'no_closing'
        elif date_problem:
            proof['reason'] = date_problem
        elif unread_dates:
            proof['reason'] = 'date_unread'
        elif day_differs:
            proof['reason'] = 'day_balance_date_differs'
        elif unplaced:
            proof['reason'] = 'unplaced_money_line'
        elif blank_dated:
            proof['reason'] = 'line_without_content'
        elif candidates and candidates[0].get('overflow'):
            proof['reason'] = 'too_many_interpretations'
        elif len(readings) > 1:
            proof['reason'] = 'two_readings'
        elif len(readings) == 1:
            chosen = next(iter(readings.values()))
            proof.update(proved=True, reason='proved', basis=chosen['basis'])
        else:
            near = [c for c in candidates if c['closing_ok']]
            quiet = _printed_no_transactions(rows, controls, style or 'dot', exponent) if not all_moves else None
            if quiet is not None and len(near) == 1 and not near[0]['totals_failed']:
                # (B7) The section prints, between its equal opening and closing balances, that nothing
                # moved: the source's own statement of no activity is the independent control.
                chosen = near[0]
                proof.update(proved=True, reason='proved', basis='printed_no_transactions',
                             no_transactions_row=quiet)
            else:
                proof['reason'] = ('printed_total_differs' if any(c['totals_failed'] for c in near)
                                   else 'no_independent_control' if near else 'not_reconciled')
    if (not proof['proved'] and liability and proof['reason'] in _PRINCIPAL_ONLY_EXPLAINS
            and any(all(re.search(r'\b' + word + r'\b', fold(h['text']).upper()) for word in _PRINCIPAL_ONLY_WORDS)
                    for h in headers)):
        # (C5) The section's balance is the principal alone; the amount owed it would have to reconcile is not
        # printed. Only the reason changes: the period stays held, and a person supplies the amount owed.
        proof['reason'] = 'principal_only_balance'
    if chosen is None:
        chosen = _best_effort(candidates, hints)
        # A held period keeps a column reading as its prefill only when that reading reconciles the
        # printed balances; otherwise guessed amounts and directions would look valid and be wrong.
        if chosen is not None and not chosen.get('closing_ok'):
            chosen = dict(chosen, values=None)
    proof['assignment'] = chosen['assignment'] if chosen else None
    second_date = _second_date_field(rows, headers, dated, width or 1)
    if second_date is None and any(len(m['date_tokens']) > 1 for m in dated):
        # (B5) A second printed date whose heading names neither a posting nor a value date: carrying it under
        # either name, or dropping it, would save a printed fact wrongly, so the period is not proved. The
        # reconciling reading stays as the prefill.
        if proof['proved']:
            proof.update(proved=False, reason='second_date_unnamed')
        second_date = 'value_date'
    result['rows'] = _rows(rows, all_moves, resolved if not date_problem else None, chosen, controls,
                           column_totals, statement, style or 'dot', exponent, liability, proof, unplaced,
                           second_date=second_date)
    return result


_SECTION_WORDS = INDEX['credit_component'] | INDEX['debit_component']
# (E9) A column-total line after the movement table's own printed totals block (its credit/debit total lines,
# or a column-total label printed alone over them), with no movement line between, totals another table and
# is not checked against the movements. Off: every column total is.
OTHER_TABLE_TOTALS = True
_PLACED_ROLES = ('opening', 'closing', 'credit_total', 'debit_total', 'column_total', 'section_total')


def _unlocated_matters(row, style, exponent):
    """A stored row without positions holds the reading (no_geometry) when one of its printed lines could be
    read as a movement or a balance control: a line starting with a date and carrying an amount, an undated
    card charge, or an amount after an opening, closing, total or section-total label. Lines are taken per
    cell and across cells (the cells' lines side by side). Any other unlocated row is not part of what the
    proof reads."""
    cells = [c['expected_text'].split('\n') for c in sorted(row['raw']['cells'], key=lambda c: c['column_index'])]
    lines = [line for lines in cells for line in lines]
    lines += [' '.join(lines[i] for lines in cells if i < len(lines)) for i in range(max(map(len, cells), default=0))]
    for line in lines:
        words = line.split()
        amounts = [i for i, word in enumerate(words) if money(word, style, exponent) is not None and re.search(r'\d', word)]
        if not amounts:
            continue
        if is_date_token(words[0].rstrip('.,')):
            return True
        text = label(' '.join(words[:amounts[0]]))
        if (any(text == label(p) or text.startswith(label(p) + ' ') for p in UNDATED_CHARGES)
                or _role_of(text, True) in _PLACED_ROLES):
            return True
    return False


def _section_heading(row, style, exponent):
    """A card movement table's section heading ('FEES', 'INTEREST CHARGED'): a line printing only a summary
    component's words, no amount and no date (D4, D7)."""
    return (label(row['text']) in _SECTION_WORDS
            and not any(_value_kind(t, style, exponent) in ('money', 'date') for t in row['tokens']))


def _not_description(row):
    """A line that never continues a movement's description: a table heading, a section heading or total,
    a continuation notice, the year-to-date heading, or a labelled control."""
    text = label(row['text'])
    return (_is_header(row) or text in _SECTION_WORDS or text in {label(n) for n in CONTINUATION_NOTICES}
            or bool(YEAR_TO_DATE.fullmatch(text)) or text in INDEX['section_total']
            or any(_role_of(name, True) for name, _ in label_pairs(row, 'dot', 2)))


def _two_line_entry(rows, index, style, exponent, columns, width):
    """(E4) ``(next row, date tokens, description tokens, money tokens)`` when rows[index] is a dated line
    printing no amount and the next line on the page, directly below it and starting in its description
    band, prints no date of its own and only amounts in the movement columns; otherwise None."""
    row = rows[index]
    tokens = merged_dates(row['tokens'])
    if not tokens or not _leading_date(tokens[0]['t'].rstrip('.,')) or row['y0'] is None:
        return None
    if any(_role_of(text, False) for text, _ in label_pairs(row, style, exponent)) or _is_header(row):
        return None
    date_tokens, rest = [tokens[0]], tokens[1:]
    while rest and is_date_token(rest[0]['t']) and len(date_tokens) < 2:
        date_tokens.append(rest.pop(0))
    if not rest or any(_value_kind(t, style, exponent) == 'money' for t in rest):
        return None
    following = next((r for r in rows[index + 1:] if r['tokens']), None)
    if following is None or following['page'] != row['page'] or following['y0'] is None:
        return None
    later = merged_dates(following['tokens'])
    if _leading_date(later[0]['t'].rstrip('.,')) or _is_header(following):
        return None
    if any(_role_of(text, False) for text, values in label_pairs(following, style, exponent) if values):
        return None
    money_tokens = [t for t in later if _value_kind(t, style, exponent) == 'money']
    placed = lambda t: _band(t, columns, width) is not None or (
        _merged_partner(t, money_tokens) is not None and _band(_merged_partner(t, money_tokens), columns, width) is not None)
    if not money_tokens or not columns or not all(placed(t) for t in money_tokens):
        return None
    height = max(t['y1'] - t['y0'] for t in row['tokens'])
    gap = following['y0'] - max(t['y1'] for t in row['tokens'])
    if gap > height * 1.2 or gap < -height:
        return None
    start = min(t['x0'] for t in rest)
    words = [t for t in later if t not in money_tokens]
    first_money = min(t['x0'] for t in money_tokens)
    if words and min(t['x0'] for t in words) < start - 0.02 * width or any(t['x0'] > first_money for t in words):
        return None
    return following, date_tokens, rest + words, money_tokens


def _printed_no_transactions(rows, controls, style, exponent):
    """(page, table, row) of the one line printing only a no-activity phrase between the section's single
    opening and single closing balance lines, both read and equal, with no other line between them that
    prints an amount or opens with a date; otherwise None."""
    if len(controls['opening']) != 1 or len(controls['closing']) != 1:
        return None
    opening, closing = controls['opening'][0], controls['closing'][0]
    values = {money(item['value_token']['t'], style, exponent) for item in (opening, closing)}
    if len(values) != 1 or None in values:
        return None
    start, end = opening['row']['_index'], closing['row']['_index']
    found = [row for row in rows[start + 1:end] if row['tokens'] and ' '.join(fold(row['text']).split()) in NO_TRANSACTIONS]
    # Between the two balances only the no-activity line and lines that cannot be movements may stand (the
    # page heading repeated where the section crosses a page break, a payment voucher printing a zero
    # total): no amount other than zero and no leading date.
    others = [row for row in rows[start + 1:end] if row['tokens'] and row not in found
              and (any(_value_kind(t, style, exponent) == 'money' and money(t['t'], style, exponent) != 0
                       for t in row['tokens'])
                   or _leading_date(merged_dates(row['tokens'])[0]['t'].rstrip('.,')))]
    if len(found) != 1 or others:
        return None
    row = found[0]
    return (row['page'], row['source']['table_index'], row['raw']['row_index'])


def _undated_charge(row, style, exponent):
    tokens = [t for t in row['tokens'] if _value_kind(t, style, exponent) != 'money']
    money_tokens = [t for t in row['tokens'] if _value_kind(t, style, exponent) == 'money']
    text = label(' '.join(t['t'] for t in tokens))
    return (len(money_tokens) == 1 and money(money_tokens[0]['t'], style, exponent)
            and any(text == label(p) or text.startswith(label(p) + ' ') for p in UNDATED_CHARGES))


def _is_header(row):
    """A movement-table heading: a date word, a money word, and mostly column words (E1)."""
    tokens = sorted(row['tokens'], key=lambda t: (t['line'], t['x0']))
    words = _letter_spaced(tokens)
    if not tokens or len(words) > 16:
        return False
    roles, covered, index = [], 0, 0
    while index < len(words):
        for size in (3, 2, 1):
            group = words[index:index + size]
            role = column_role(label(' '.join(text for text, _ in group))) if len(group) == size else None
            if role:
                roles.append(role)
                covered += size
                index += size
                break
        else:
            index += 1
    return ('date' in roles and bool(set(roles) & {'credit', 'debit', 'amount', 'balance'})
            and covered * 2 >= len(words))


def _letter_spaced(tokens):
    """[(word, line)]: a heading word printed letter-spaced ('F E C H A') is one word (E1): a run of at least
    three single letters on one line is joined."""
    words, index = [], 0
    while index < len(tokens):
        end = index
        while (end < len(tokens) and len(tokens[end]['t']) == 1 and tokens[end]['t'].isalpha()
               and tokens[end]['line'] == tokens[index]['line']):
            end += 1
        if end - index >= 3:
            words.append((''.join(t['t'] for t in tokens[index:end]), tokens[index]['line']))
            index = end
        else:
            words.append((tokens[index]['t'], tokens[index]['line']))
            index += 1
    return words


def _below(row, move):
    last = move['continuation'][-1] if move['continuation'] else move['row']
    return row['y0'] is not None and last['y0'] is not None and row['y0'] > last['y0']


def _continues(row, move):
    """A line without date or money directly below a movement, starting in its description band (E3)."""
    last = move['continuation'][-1] if move['continuation'] else move['row']
    if row.get('split') and last.get('split') and row['split'][0] == last['split'][0]:
        # The next printed line of the same stored cell (_split_row), whose horizontal positions are only
        # estimates: a wrapped description line unless it is printed as something else.
        return row['split'][1] == last['split'][1] + 1 and len(move['continuation']) < 8 and not _not_description(row)
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
        elif hint in ('credit', 'debit', 'amount', 'ignore'):
            # 'ignore' is hinted only by a library profile's ignore column words.
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


def _merged_partner(token, tokens):
    """(E10) The balance printed after ``token`` in the same merged cell, or None.

    A text table can deliver a movement's amount and balance (or its whole line) as one cell; each word's
    position inside it is then interpolated, so an amount that is neither alone in its cell nor its last
    word cannot be placed in a column. It is the line's amount when the line prints exactly two amounts and
    the other is the last word of the same cell line (the balance, placed by the cell's own right edge)."""
    if token['exact'] or token['last'] or len(tokens) != 2:
        return None
    other = next(t for t in tokens if t is not token)
    if other['cell'] is token['cell'] and other['line'] == token['line'] and other['last'] and other['x0'] > token['x0']:
        return other
    return None


def _movement_value(move, assignment, columns, width, style, exponent, liability):
    """Signed effect of one movement line on the printed balance under ``assignment``, or None."""
    amounts, balance, balance_token, zero, partner = [], None, None, False, None
    for token in move['money']:
        band = _band(token, columns, width)
        if band is None:
            # (E10) An amount merged into its balance's cell takes the reading's one signed amount column;
            # the reading proves only through the printed running balance (_search).
            partner = _merged_partner(token, move['money']) if 'amount' in assignment else None
            if partner is None and ((_PROFILE.get() or {}).get('columns') or {}).get('ignore'):
                # (profile) A layout whose profile names the amount columns that are not the movement (gross,
                # fees, taxes) and that reads a line as one merged cell: an amount placed in no column is one of
                # them. The movement is the amount in a column the reading assigns, proved by the balances.
                continue
            if partner is None:
                return None
            role = 'amount'
        else:
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
    for token in move.get('day_balances', ()):
        # (profile) A day's closing balance printed after this line: its running balance.
        value = money(token['t'], style, exponent)
        if value is None or (balance_token is not None and value != balance):
            return None
        balance, balance_token = value, token
    if len(amounts) > 1 or (partner is not None and balance_token is not partner):
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
                balance_token=balance_token, amount_token=token, merged=partner is not None)


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
            # Net summary lines (charges less credits, signed as printed) are part of the charges' side.
            nets = ([money(item['value_token']['t'], style, exponent) for item in controls['net_component']]
                    if role == 'debit_component' else [])
            if parts or nets:
                totals_found += 1
                if None in parts or None in nets or sum(abs(p) for p in parts) + sum(nets) != expected:
                    totals_ok, totals_failed = False, True
        for item in controls['section_total']:
            # A section's printed total equals the net of the lines under its heading (D4).
            printed = money(item['value_token']['t'], style, exponent)
            net = sum(v['effect'] for m, v in zip(moves, values) if not v['zero'] and m.get('section') in item['headings'])
            totals_found += 1
            if printed is None or printed != net:
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
        # A column-total line printing a value in the running-balance column prints the balance after the
        # last movement: a closing-balance candidate (D6); unequal candidates cannot both prove.
        here_closings = dict(closings)
        for item in column_totals:
            for token in item['tokens']:
                band = _band(token, columns, width) if columns else None
                if band is not None and assignment[band] == 'balance':
                    value = money(token['t'], style, exponent)
                    if value is not None:
                        here_closings.setdefault(value, dict(row=item['row'], value_token=token, count=None))
        for opening, closing in product(openings, here_closings):
            net = sum(v['effect'] for v in effects)
            # (profile) A day's balance printed before any movement restates the opening balance.
            closing_ok = opening + net == closing and all(
                money(item['value_token']['t'], style, exponent) == opening for item in controls['day_opening'])
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
            # A column read as the running balance that does not chain contradicts this reading: printed
            # totals cannot prove it (the same reading without that column still can).
            contradicted = any(v['balance'] is not None for v in values) and not chain_ok
            # (E10) An amount placed from a merged cell is proved only by the running balance printed beside it.
            merged = any(v.get('merged') for v in values)
            proved = closing_ok and totals_ok and (chain_ok or (not merged and totals_found > 0 and totals_ok
                                                                and not contradicted))
            basis = 'running_balance' if chain_ok else 'printed_totals'
            key = (opening, closing, tuple((m['row']['_index'], v.get('direction'), v.get('amount')) for m, v in zip(moves, values)))
            results.append(dict(proved=proved, closing_ok=closing_ok, totals_failed=totals_failed, chain_ok=chain_ok,
                                key=key, assignment=assignment, values=values, opening=opening, closing=closing,
                                basis=basis, opening_item=openings[opening], closing_item=here_closings[closing]))
    return results


def _best_effort(candidates, hints):
    usable = [c for c in candidates if c.get('values') is not None and c.get('assignment') is not None]
    if not usable:
        return None
    return max(usable, key=lambda c: (c['closing_ok'], c.get('chain_ok', False),
                                      sum(1 for i, r in enumerate(c['assignment']) if hints.get(i) == r)))


def _item(row, suffix=''):
    source, raw = row['source'], row['raw']
    # A printed line or box of a stored row read as a row of its own (_split_row) keeps the stored row's index.
    part = ':line%d' % raw['line'] if 'line' in raw else ':box%s' % raw['box'] if 'box' in raw else ''
    return dict(id=f"{source['page_number']}:{source['table_index']}:{raw['row_index']}{part}{suffix}",
                page_number=source['page_number'], table_index=source['table_index'], row_index=raw['row_index'],
                source_revision=source['source_revision'], source_cells=raw['cells'], fields={}, issues=[],
                excluded=True, kind='header')


_POSTING_WORDS = {'POST', 'POSTED', 'POSTING'}
# A second date column's heading naming a settlement or value date (measured: 'OPER LIQ' on BBVA).
_VALUE_DATE_WORDS = {'LIQ', 'LIQUIDACION', 'VALOR', 'VALUE', 'SETTLEMENT'}
# Lines searched above a page's first two-date movement for the heading of its date columns, and lines a
# heading of the date columns may span (a two-line heading with a side column's line between them).
_DATE_HEADING_SEARCH = 20
_DATE_HEADING_SPAN = 3


def _date_column_headings(rows, moves, width):
    """The words printed over the date columns of the movement lines carrying two dates, page by page.

    From each page's first such movement, the lines above it on the page are read through their
    words that lie over either date column (a side column's text beside the table counts for
    nothing). A line whose words there are all date-column words ('Trans.', 'Post', 'date',
    'FECHA', 'OPER') is the date columns' heading; up to ``_DATE_HEADING_SPAN`` lines above the
    nearest one count with it (a heading printed on two lines). Other words over the columns (a
    section heading 'Standard Purchases') are passed over. Returns ``{folded word}`` printed over
    the second date column.
    """
    def span(token):
        w = token.get('_width') or width
        return token['x0'] / w, token['x1'] / w

    def over(token, columns):
        x0, x1 = span(token)
        return any(x0 < right and x1 > left for left, right in columns)

    firsts = {}
    for move in moves:
        if len(move['date_tokens']) > 1:
            firsts.setdefault(move['row']['page'], move)
    words = set()
    for page, move in firsts.items():
        first, second = (span(t) for t in move['date_tokens'][:2])
        found = None
        for index in range(move['row']['_index'] - 1, max(-1, move['row']['_index'] - 1 - _DATE_HEADING_SEARCH), -1):
            row = rows[index]
            if row['page'] != page or (found is not None and found - index > _DATE_HEADING_SPAN):
                break
            above = [t for t in row['tokens'] if over(t, (first, second))]
            if above and all(column_role(label(t['t'])) == 'date' for t in above):
                found = index if found is None else found
                words.update(label(t['t']) for t in above if over(t, (second,)))
    return words


def _second_date_field(rows, headers, moves, width):
    """(B5) The field a movement line's second printed date fills: 'booking_date' when the movement
    headings name a posting date ("Trans date / Post date" on card statements), 'value_date' when they
    name a settlement or value date ("FECHA OPER LIQ"), and None when no movement line prints a second
    date or when the headings name neither (the second date's meaning is not printed where it was read).

    The movement heading's own line and the line directly above it count with every word (a heading can
    print on two lines: "Trans. Post" above "date date Description Amount"). A heading line that is not
    read as the movement heading (a side column's text printed on the same line) counts through the words
    over the date columns (``_date_column_headings``).
    """
    if not any(len(m['date_tokens']) > 1 for m in moves):
        return None
    heading_lines = headers + [rows[h['_index'] - 1] for h in headers
                               if h['_index'] > 0 and rows[h['_index'] - 1]['page'] == h['page']]
    words = {label(t['t']) for h in heading_lines for t in h['tokens']} | _date_column_headings(rows, moves, width)
    if words & _POSTING_WORDS:
        return 'booking_date'
    if words & _VALUE_DATE_WORDS:
        return 'value_date'
    return None


def _rows(rows, moves, resolved, chosen, controls, column_totals, statement, style, exponent, liability, proof, unplaced,
          second_date='value_date'):
    """Every source row of the section, in the shared proposal format."""
    items = {}
    order = []
    for row in rows:
        item = _item(row)
        items[row['_index']] = item
        order.append(item)
    if chosen and chosen.get('values') is not None and moves:
        dates = iter(resolved or [])
        for move, value in zip(moves, chosen['values']):
            item = items[move['row']['_index']]
            fields = item['fields']
            description = ' '.join(t['t'] for t in move['description'])
            for extra in move['continuation']:
                description += ' ' + ' '.join(t['t'] for t in extra['tokens']
                                              if not any(t is m for m in move['money']))
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
                if printed and move.get('date_unread'):
                    # (B5) The line's second date is unread ink: its first date is not taken either.
                    item['issues'].append('Check the printed date of this movement.')
                elif printed:
                    fields['date'] = printed[0].isoformat()
                    if len(printed) > 1:
                        fields[second_date] = printed[1].isoformat()
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

    if chosen and chosen.get('opening_item') is not None and chosen.get('values') is not None:
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
    if chosen and chosen.get('values') is not None:
        for entry in controls['section_total']:
            # A section's printed total (D4) as the review's scoped control, with the lines it totals.
            scope = entry['scope']
            control(entry, 'Printed %s total' % scope, 'section_' + scope, kind='statement_total', total_scope=scope)
            for move in moves:
                item = items[move['row']['_index']]
                if move.get('section') in entry['headings'] and item['kind'] == 'transaction':
                    item['fields']['charge_group'] = scope
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
