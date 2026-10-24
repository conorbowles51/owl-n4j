"""Read Andrews savings/checking sections without mixing their account shares.

Recognition uses the measured account/period heading and each printed share
heading. Continuations use adjacent source pages or a complete block ordered by
unique printed page numbers. They require the same account and period, a prior
continuation notice and no conflicting page number.
Original cells are retained, including joined or damaged OCR money fields.
"""
import re
from datetime import date
from difflib import SequenceMatcher

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_proposal import exact_amount

_LAYOUT = 'andrews-share-statement'
_DATE = r'\d\s*\d\s*/\s*\d\s*\d'
_SPACED_MONEY = r'[+-]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\s*\.\s*\d{2}'
_FULL_DATE = r'\d\s*\d\s*/\s*\d\s*\d\s*/\s*(?:2\s*0\s*)?\d\s*\d'
_TYPES = {'BASE SHARE SAVINGS': 'savings', 'FREE CHECKING': 'checking', 'VISA PAYMENT': 'other'}
# Printed share labels. A club share (HOLIDAY CLUB, VACATION CLUB) is a savings
# share the member pays into for a dated purpose; its section prints exactly
# like the base share's, with its own ID and Previous Balance heading.
_LABELS = r'BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT|[A-Z]+(?: [A-Z]+)? CLUB'


def _share_type(label):
    return _TYPES.get(label) or ('savings' if label.endswith(' CLUB') else 'other')

# OCR may insert spaces inside a fixed printed label. Match its letters exactly;
# this does not repair account numbers, dates, amounts or substituted glyphs.
_PREVIOUS = re.compile(r'(?<![A-Za-z])' + r'\s*'.join('PreviousBalance') + r'(?![A-Za-z])')
# OCR may put spaces inside the heading's date or share ID (``06 / 01``,
# ``ID 001 0``); only the spacing is ignored, never a glyph.
_HEADING_DATE = r'\d\s?\d\s?/\s?\d\s?\d'
_SHARE_ID = r'\d\s?\d\s?\d\s?\d'
# Measured on a real scan: a speck between two digits of the share ID read as
# a point (``ID 004.0 FREE CHECKING``). The four digits and the printed label
# must still be read exactly; one point or middle dot is ignored like a space.
# Reverse in one place: False reads only spaces.
SHARE_ID_SPECK = True
if SHARE_ID_SPECK:
    _SHARE_ID = r'\d[\s.·]?\d[\s.·]?\d[\s.·]?\d'


def _share_reference(text):
    return re.sub(r'[\s.·]+', '', text)
_SHARE = re.compile(r'^(' + _HEADING_DATE + r') ID (' + _SHARE_ID + r') (' + _LABELS + ') ' + _PREVIOUS.pattern + r'(?: |$)')
_SHARE_LABEL = re.compile(r'^' + _HEADING_DATE + r' ID \S+(?: \S+)? (' + _LABELS + ')(?: |$)')

# The Ending Balance line; a date read with a space inside it (``06/ 30``) is
# the same printed date when spaced row dates are read (``SPACED_ROW_DATES``).
_ENDING_LINE = r'^\d{2}/\d{2} Ending Balance(?: |$)'
_ENDING_BODY = r'(\d{2}/\d{2}) Ending Balance'
_SPACED_ENDING_LINE = r'^' + _HEADING_DATE + r' Ending Balance(?: |$)'
_SPACED_ENDING_BODY = r'(' + _HEADING_DATE + r') Ending Balance'

_CLOSED = re.compile(r'^(' + _HEADING_DATE + r') ID (' + _SHARE_ID + r') (' + _LABELS + ') Closed$')
# The printed continuation notice. OCR can put spaces or a stray point or
# middle dot between its letters (``Continued·on fol low.ing page``); every
# letter must still be read exactly and in order.
_CONTINUED = re.compile(r'[\s.·]*'.join('Continuedonfollowingpage'))


def _continued(text):
    return bool(_CONTINUED.search(text))


_WITHDRAWAL = r'\s*'.join('Withdrawal')
_DEPOSIT = r'\s*'.join('Deposit')
_RECURRING = r'\s*'.join('Recurring')
_PAYMENT = re.compile(r'^(' + _DATE + r'|\S+)(?: (' + _DATE + r'))? ((?:' + _RECURRING +
                      r'\s+)?(' + _WITHDRAWAL + '|' + _DEPOSIT + r')\b.*)$')
_DAMAGED_DATE_PAYMENT = re.compile(r'^(.{1,12}?) ((?:' + _RECURRING +
                                 r'\s+)?(' + _WITHDRAWAL + '|' + _DEPOSIT + r')\b.*)$')

# Neil's ruling of 2026-10-09: a payment whose Withdrawal/Deposit word OCR
# misread takes its direction from its printed amount (minus or no sign) only
# when the previous and the new printed balances agree with it exactly: three
# printed facts agree. Anything unread or disagreeing stays held. Reverse: False.
MISREAD_VERB_DIRECTION = True
DIRECTION_FROM_SIGN_AND_BALANCES = 'printed_sign_and_balances'
_VERBS = ('Withdrawal', 'Deposit')
_DIRECTION_UNREAD = ('Check the amount and whether money entered or left the account. '
                     'The number or its minus sign may have been read incorrectly.')


def _resemblance(letters, word):
    """How closely the start of ``letters`` reads as ``word`` (best of three lengths)."""
    return max(SequenceMatcher(None, letters[:size], word.lower()).ratio()
               for size in (len(word) - 1, len(word), len(word) + 1))


def _misread_verb(description):
    """The printed payment word a damaged first word stands for, or None.

    Only its letters are compared: OCR spaces and stray marks inside the word
    are dropped (``Wi thdraw;al``, ``IHthdrawal``, ``WithQrawal``), and a
    damaged ``Recurring`` before it is passed over. The word must read at least
    three quarters like exactly one of the two printed words and clearly not
    like the other. It only keeps the sign/word conflict hold; the direction
    itself is never taken from this resemblance.
    """
    letters = re.sub(r'[^A-Za-z]', '', description).lower()
    if _resemblance(letters, 'Recurring') >= .75:
        letters = letters[len('Recurring'):]
    scores = {verb: _resemblance(letters, verb) for verb in _VERBS}
    found = [verb for verb, score in scores.items() if score >= .75]
    if len(found) != 1 or min(scores.values()) >= .5:
        return None
    return found[0]


def _text(row):
    return ' '.join(c['expected_text'].strip() for c in row['cells']).strip()


def _ending_balance(row, width):
    """Recognise the label without substituting characters in its date."""
    cells = row['cells']
    if len(cells) < 2 or cells[1]['expected_text'].strip() != 'Ending Balance':
        return None
    box = _box(cells[0])
    return (re.fullmatch(r'\S{4,7}', cells[0]['expected_text'].strip())
            if box and box[0] < width * .08 else None)


def is_andrews_fee_summary(source):
    page = andrews_page(source, allow_unbranded=True)
    if not page:
        return False
    body = [row for row in source['rows'] if row['row_index'] >= page['body_start']]
    labels = {_text(row) for row in body}
    def first(row):
        return row['cells'][0]['expected_text'].strip(' |[]') if row['cells'] else ''
    firsts = {first(row) for row in body}
    summary_labels = {'Total Returned Item Fees', 'Total Overdraft Fees',
                      'Dividends Paid Year to Date', 'Total Dividends Paid Year to Date'}
    def divider(row):
        text = _text(row)
        return (re.match(r'^[|\[]\s*-{3,}', text) and text.endswith('|')
                and not re.search(r'\d[,.]\d{2}\b|\d{1,2}/\d{1,2}|Withdrawal|Deposit|Recurring', text))
    if any(row['cells'] and first(row) not in summary_labels
           and re.search(r'\d', _text(row))
           and not divider(row)
           and not (len(row['cells']) == 1 and re.fullmatch(r'[\d,. ]+', _text(row))) for row in body):
        return False
    return (({'Total Returned Item Fees', 'Total Overdraft Fees'} <= firsts
             or bool({'Dividends Paid Year to Date', 'Total Dividends Paid Year to Date'} & firsts))
            and not any(re.match(r'^\S{4,7}\s+(?:ID|Withdrawal|Deposit|Recurring)\b', text)
                        or re.match(r'^\d{2}/\d{2}\b', text) for text in labels))


def _box(cell):
    value = cell.get('locator', {})
    rect = value.get('rect')
    if (not isinstance(rect, list) or len(rect) != 4 or
            not all(type(v) is int for v in rect) or not rect[0] < rect[2] or not rect[1] < rect[3]):
        return None
    return rect


def _full_date(value):
    m = re.fullmatch(r'(\d{2})/(\d{2})/(20\d{2}|\d{2})', re.sub(r'\s+', '', value))
    if not m:
        return None
    try:
        return date(int(m[3]) + (2000 if len(m[3]) == 2 else 0), int(m[1]), int(m[2]))
    except ValueError:
        return None


# Letters an OCR layer was measured to put for digits in the heading's cycle
# line; used only to compare a continuation page with the page before it.
_CYCLE_LOOKALIKES = str.maketrans({'O': '0', 'o': '0', 'l': '1', 'I': '1'})


def andrews_page(source, *, allow_unbranded=False):
    """Identify the heading, never a number from the body or an application."""
    rows = source['rows']
    cells = [c for r in rows for c in r['cells']]
    marks = [c for c in cells if re.fullmatch(r'\.?Andrews', c['expected_text'].strip()) and _box(c)]
    # OCR can put a stray mark between the two printed words; their letters must be exact.
    titles = [c for c in cells if re.fullmatch(r'Account[-·.,]?Statement', re.sub(r'\s+', '', c['expected_text'])) and _box(c)]
    # A title read with a lower-case ``s`` is accepted only on a page without
    # the brand mark, which opens nothing unless it continues the previous
    # page's statement (``andrews_catalog``).
    lowercase_title = False
    if not titles and not marks:
        titles = [c for c in cells if re.fullmatch(r'Account[-·.,]?statement', re.sub(r'\s+', '', c['expected_text'])) and _box(c)]
        lowercase_title = bool(titles)
    if len(titles) != 1 or len(marks) > 1 or (not marks and not allow_unbranded):
        return None
    size = titles[0]['locator'].get('page_size', [])
    if not isinstance(size, list) or len(size) != 2:
        return None
    width, height = size
    if (type(width) is not int or type(height) is not int or
            not width * .4 < _box(titles[0])[0] or _box(titles[0])[3] > height * .15 or
            any(_box(c)[0] >= width * .4 or _box(c)[3] > height * .15 for c in marks)):
        return None
    top = [r for r in rows if r['cells'] and all(_box(c) and _box(c)[3] < height * .2 for c in r['cells'])]
    # The printed account number is nine digits; OCR may split them with
    # spaces (``1234 56 789``). Only spaces are removed, never a glyph.
    accounts = [(r, c) for r in top for c in r['cells']
                if re.fullmatch(r'(?:\d\s*){8}\d', c['expected_text'].strip()) and _box(c)[0] > width * .4]
    cycles = []
    for row in top:
        m = re.fullmatch(r'(' + _FULL_DATE + r')\s+(' + _FULL_DATE + r')', _text(row))
        if m:
            a, b = _full_date(m[1]), _full_date(m[2])
            if a and b and 0 <= (b-a).days <= 62:
                cycles.append((row, a, b))
    cycle_lookalike = False
    if not cycles:
        # A cycle read with a letter for a digit (``09/0l/23``) can only
        # continue the previous page's statement: the catalog accepts such a
        # page only when the dates then equal that page's exactly.
        for row in top:
            text = _text(row)
            if not re.search(r'[OolI]', text):
                continue
            m = re.fullmatch(r'(' + _FULL_DATE + r')\s+(' + _FULL_DATE + r')', text.translate(_CYCLE_LOOKALIKES))
            if m and re.fullmatch(r'[\dOolI/\s]+', text):
                a, b = _full_date(m[1]), _full_date(m[2])
                if a and b and 0 <= (b-a).days <= 62:
                    cycles.append((row, a, b))
        cycle_lookalike = bool(cycles)
    if len(accounts) != 1 or len(cycles) != 1:
        return None
    account_row, account = accounts[0]
    cycle_row, start, end = cycles[0]
    if account_row['row_index'] >= cycle_row['row_index']:
        return None
    following = next((r for r in rows if r['row_index'] > cycle_row['row_index']), None)
    page_number = None
    if following and re.fullmatch(r'\d{1,3}', _text(following)):
        page_number = int(_text(following))
    body = following['row_index'] + 1 if page_number is not None else cycle_row['row_index'] + 1
    return dict(account=re.sub(r'\s+', '', account['expected_text']), start=start.isoformat(), end=end.isoformat(),
                branded=bool(marks), account_spaced=bool(re.search(r'\s', account['expected_text'].strip())),
                printed_page=page_number, body_start=body, width=width,
                heading_rows=[r['row_index'] for r in rows if r['row_index'] < body],
                **(dict(continuation_only=True) if cycle_lookalike or lowercase_title else {}))


_NAME_LINE = re.compile(r'[A-Z][A-Z .\'-]{3,95}')
_STREET_LINE = re.compile(r'\d+ [A-Z0-9 .#\'-]+')
_CITY_LINE = re.compile(r"[A-Z][A-Z .'-]+ [A-Z]{2} \d{5}(?:-\d{4})?")


def _unmarked_holder(rows, page):
    """The addressee lines of a mailing block whose marker is absent or damaged.

    Some statement runs print the address block with no ``>digits<`` line
    above it, and OCR can damage the line where it is printed. The block is
    then accepted only in its complete printed form, as the first lines below
    the account/period heading: one to three name lines, one street line and
    one city/state/ZIP line, all at the left of the page, followed directly by
    the first share heading. Above the names only two lines may be passed
    over, each at most once: the printed page number when it was not read as
    a number (one to three characters), and the mailing code line (its eight
    to twelve digits, whatever the brackets were read as). Nothing is taken
    from either line. Anything else (a damaged name, street or city line,
    other text in between) reads no holder, so the account still needs a
    person's confirmation.
    """
    if page is None:
        return ''
    body = [r for r in rows if r['row_index'] >= page['body_start'] and r['cells']]
    if body and page['printed_page'] is None and re.fullmatch(r'\S{1,3}', _text(body[0])):
        body = body[1:]
    if body and re.fullmatch(r'[^A-Za-z0-9\s]?\s*(?:\d\s*){8,12}[^A-Za-z0-9\s]{0,2}', _text(body[0])):
        body = body[1:]
    names = []
    for index, row in enumerate(body):
        text = _text(row)
        if not all(_box(c) and _box(c)[0] < page['width'] * .4 for c in row['cells']):
            return ''
        if _NAME_LINE.fullmatch(text) and not _STREET_LINE.fullmatch(text) and len(names) < 3:
            names.append(text)
            continue
        if (not names or index + 2 >= len(body) or not _STREET_LINE.fullmatch(text)
                or not _CITY_LINE.fullmatch(_text(body[index + 1]))):
            return ''
        heading = _text(body[index + 2])
        if not (_SHARE_LABEL.match(heading) or _PREVIOUS.search(heading)):
            return ''
        value = ' / '.join(names)
        return value if len(value) <= 128 else ''
    return ''


def _holder(rows, page=None):
    """The addressee lines immediately following the printed mailing marker.

    When no marker reading yields a holder, the complete mailing block below
    the heading is read instead (``_unmarked_holder``), given the page heading.
    """
    return _marked_holder(rows) or _unmarked_holder(rows, page)


def _marked_holder(rows):
    names = []
    active = False
    relaxed_marker = False
    for index, row in enumerate(rows):
        text = _text(row)
        if re.fullmatch(r'>\d{8,12}<', text):
            active = True
        elif re.fullmatch(r'>\s*(?:\d\s*){8,12}«?<', text):
            # Spacing inside the mailing code and a doubled closing bracket
            # are not part of the holder's name. Require the complete postal
            # block below before accepting this less exact marker.
            active = relaxed_marker = True
        elif active:
            if re.fullmatch(r'[A-Z][A-Z .\'-]{3,95}', text):
                names.append(text)
            else:
                if relaxed_marker:
                    city = _text(rows[index + 1]) if index + 1 < len(rows) else ''
                    if (not 1 <= len(names) <= 3 or not re.fullmatch(r'\d+ [A-Z0-9 .#\'-]+', text)
                            or not re.fullmatch(r"[A-Z][A-Z .'-]+ [A-Z]{2} \d{5}(?:-\d{4})?", city)):
                        return ''
                    relaxed_marker = False
                break
    value = ' / '.join(names)
    return value if len(value) <= 128 and not relaxed_marker else ''


def _reading_order(sources):
    """Order a complete, uniquely numbered block by its printed page numbers.

    The physical pages must be contiguous and print the same account/period.
    Missing or repeated numbers keep their original order. No number is inferred
    for an unreadable heading. Original page addresses are never changed.
    """
    ordered = sorted(sources, key=lambda s: (s['page_number'], s['table_index']))
    block = []

    def emit():
        numbers = [page['printed_page'] for _, page in block]
        if (len(numbers) > 1 and sorted(numbers) == list(range(1, len(numbers)+1))
                and next(page for _, page in block if page['printed_page'] == 1)['branded']
                and numbers != sorted(numbers)):
            group = (block[0][0]['page_number'], block[0][0]['table_index'])
            return [(source, group) for source, _ in sorted(block, key=lambda item: item[1]['printed_page'])]
        return [(source, None) for source, _ in block]

    for source in ordered:
        page = andrews_page(source, allow_unbranded=True)
        if page is None or page['printed_page'] is None:
            yield from emit()
            block = []
            yield source, None
            continue
        if block:
            previous_source, previous = block[-1]
            if (source['page_number'] != previous_source['page_number'] + 1 or
                    source['table_index'] != previous_source['table_index'] or
                    any(page[k] != previous[k] for k in ('account', 'start', 'end'))):
                yield from emit()
                block = []
        block.append((source, page))
    yield from emit()


def _opening_corroborated_by_next_page(source, page, following):
    """An unreadable logo needs the next branded, matching printed page 2."""
    if (following is None or page['printed_page'] not in (None, 1)
            or following['page_number'] != source['page_number'] + 1
            or following['table_index'] != source['table_index']
            or not any(_SHARE.match(_text(r)) for r in source['rows'] if r['row_index'] >= page['body_start'])
            or not any(_continued(_text(r)) for r in source['rows'])):
        return False
    next_page = andrews_page(following)
    return (next_page is not None and next_page['printed_page'] == 2
            and all(next_page[k] == page[k] for k in ('account', 'start', 'end')))


def _account_corroborated(page, ordered, index):
    """An account number read with spaces inside needs an adjacent page printing it exactly.

    Spaces in the account cell show the reading struggled there; a digit
    could be misread too. Such a page may open a section only when the PDF
    page before or after it is an Andrews statement page (of any period)
    whose account cell reads, without any space, the same nine digits. A
    misread digit then shows as a different number and the page is not read.
    """
    source = ordered[index][0]
    for step in (-1, 1):
        if not 0 <= index + step < len(ordered):
            continue
        other = ordered[index + step][0]
        if (other['page_number'] != source['page_number'] + step or other['table_index'] != source['table_index']):
            continue
        neighbour = andrews_page(other, allow_unbranded=True)
        if (neighbour is not None and not neighbour['account_spaced']
                and neighbour['account'] == page['account']):
            return True
    return False


def andrews_catalog(sources):
    groups = {}
    handled = set()
    incomplete = set()
    previous = None
    active = None
    ordered = list(_reading_order(sources))
    for index, (source, order_group) in enumerate(ordered):
        page = andrews_page(source, allow_unbranded=True)
        key = (source['page_number'], source['table_index'])
        if page is None:
            active = None
            previous = None
            continue
        follows = (previous and (key == (previous['pdf_page'] + 1, previous['table_index']) or
                   order_group is not None and order_group == previous['order_group']))
        continues = (follows and active
                     and previous['continues'] and page['account'] == previous['account']
                     and (page['start'], page['end']) == (previous['start'], previous['end'])
                     and (page['printed_page'] is None or previous['printed_page'] is None
                          or page['printed_page'] == previous['printed_page'] + 1)
                     and page['printed_page'] != 1)
        following = ordered[index + 1][0] if index + 1 < len(ordered) else None
        if page.get('continuation_only') and not continues:
            active = None
            previous = None
            continue
        if page['account_spaced'] and not continues and not _account_corroborated(page, ordered, index):
            active = None
            previous = None
            continue
        # Exact printed account/period details and a branded next page can
        # establish an opening whose logo OCR missed. Never infer its dates.
        if not page['branded'] and not continues and not _opening_corroborated_by_next_page(source, page, following):
            active = None
            previous = None
            continue
        if not continues:
            active = None
        addressed = set()
        unknown = False
        for row in source['rows']:
            if row['row_index'] < page['body_start']:
                continue
            text = _text(row)
            if _continued(text):
                break
            match = _SHARE.match(text)
            if _PREVIOUS.search(text) or (_SHARE_LABEL.match(text) and not _CLOSED.fullmatch(text)):
                active = None
                if match:
                    identity = dict(layout_id=_LAYOUT, institution='Andrews Federal Credit Union',
                        account_reference=page['account'] + ' / Share ' + _share_reference(match[2]),
                        main_account_reference=page['account'], share_reference=_share_reference(match[2]),
                        account_label=match[3], account_type=_share_type(match[3]),
                        period_start=page['start'], period_end=page['end'])
                    # Another opening heading is another statement occurrence,
                    # even when account and dates match an earlier copy.
                    identifier = _digest(dict(**identity, opening_source=[*key, row['row_index']]))
                    active = groups.setdefault(identifier, dict(id=identifier, **identity,
                        holder=_holder(source['rows'], page), sources=[], page_numbers=[]))
                else:
                    unknown = True
            if active is not None:
                if order_group is not None:
                    active['uses_printed_page_order'] = True
                scope = next((s for s in active['sources'] if (s['page_number'], s['table_index']) == key), None)
                if scope is None:
                    scope = dict(page_number=key[0], table_index=key[1], source_revision=source['source_revision'],
                                 row_indices=[], heading_rows=page['heading_rows'])
                    active['sources'].append(scope)
                    active['page_numbers'].append(key[0])
                scope['row_indices'].append(row['row_index'])
                addressed.add(active['id'])
            elif re.match(r'^\d{2}/\d{2}(?: |$)', text):
                unknown = True
            closure = _CLOSED.fullmatch(text)
            if closure and active:
                closed_on = _period_date(closure[1], active)
                if (_share_reference(closure[2]) == active['share_reference'] and closure[3] == active['account_label']
                        and closed_on):
                    active['account_closure'] = dict(date=closed_on, page_number=source['page_number'], table_index=source['table_index'],
                        row_index=row['row_index'], source_cells=row['cells'])
                else:
                    unknown = True
                active = None
            if (re.match(_SPACED_ENDING_LINE if SPACED_ROW_DATES else _ENDING_LINE, text)
                    or _ending_balance(row, page['width'])):
                active = None
        if addressed:
            handled.add(key)
        if unknown:
            incomplete.add(key)
        previous = dict(**page, pdf_page=key[0], table_index=key[1], order_group=order_group,
                        continues=any(_continued(_text(r)) for r in source['rows']))
    return list(groups.values()), handled, incomplete


def leading_continuation_rows(source, page):
    """Row indices of the payments a page carries over from the previous page.

    A continuation page opens with the payments of a section whose share
    heading is on an earlier page, up to that section's Ending Balance (or a
    continuation notice) and before any share heading of its own. Returns
    those rows, ending balance included, or ``[]`` when the page opens with a
    heading or an address block (no payment before the first heading).
    Identity is not established here: the rows belong to whichever section
    the previous page leaves open.
    """
    rows = []
    for row in source['rows']:
        if row['row_index'] < page['body_start']:
            continue
        text = _text(row)
        if _PREVIOUS.search(text) or _SHARE_LABEL.match(text) or _continued(text):
            break
        rows.append(row)
        if re.match(r'^\d{2}/\d{2} Ending Balance(?: |$)', text) or _ending_balance(row, page['width']):
            break
    if not any(row['cells'] and _box(row['cells'][0]) and _box(row['cells'][0])[0] < page['width'] * .08
               and (_PAYMENT.match(_text(row)) or _DAMAGED_DATE_PAYMENT.match(_text(row))) for row in rows):
        return []
    return [row['row_index'] for row in rows]


def unassigned_andrews_groups(sources, handled):
    """Expose orphan payment pages for an explicit account assignment.

    A readable main account and period do not establish which share owns a
    continuation after a missing page. Keep its payments available for the
    existing reviewed row move, without allowing this group to be imported.
    """
    groups = []
    for source in sources:
        key = (source['page_number'], source['table_index'])
        if key in handled:
            continue
        page = andrews_page(source)
        if not page or page.get('continuation_only'):
            # Its dates were read with a letter: they name no period of their own.
            continue
        body = [r for r in source['rows'] if r['row_index'] >= page['body_start']]
        if any(_SHARE_LABEL.match(_text(r)) or _PREVIOUS.search(_text(r)) for r in body):
            continue
        first = next((r for r in body if r['cells'] and _box(r['cells'][0])
                      and _box(r['cells'][0])[0] < page['width'] * .08
                      and (_PAYMENT.match(_text(r)) or _DAMAGED_DATE_PAYMENT.match(_text(r)))), None)
        if first is None:
            continue
        indices = []
        for row in body:
            if row['row_index'] < first['row_index']:
                continue
            if _continued(_text(row)):
                break
            indices.append(row['row_index'])
            if _ending_balance(row, page['width']):
                break
        identity = dict(layout_id=_LAYOUT, main_account_reference=page['account'],
                        period_start=page['start'], period_end=page['end'],
                        unassigned_source=list(key))
        groups.append(dict(id=_digest(identity), **identity,
            institution='Andrews Federal Credit Union', account_reference='',
            account_label=f"Unassigned payments on PDF page {source['page_number']}",
            account_type='other', share_reference='', holder='', assignment_only=True,
            page_numbers=[source['page_number']],
            sources=[dict(page_number=key[0], table_index=key[1], source_revision=source['source_revision'],
                          row_indices=indices, heading_rows=page['heading_rows'])]))
    return groups


def _period_date(text, statement):
    text = re.sub(r'\s+', '', text)
    if not re.fullmatch(_DATE, text):
        return None
    start, end = date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end'])
    options = set()
    for year in range(start.year, end.year+1):
        value = _full_date(text + '/' + str(year))
        if value and start <= value <= end:
            options.add(value.isoformat())
    return next(iter(options)) if len(options) == 1 else None


def _ordinary_additional_date(printed, primary):
    """Recognise nearby date text without assigning it a transaction-date role."""
    printed = re.sub(r'\s+', '', printed)
    if not primary or not re.fullmatch(_DATE, printed):
        return False
    first = date.fromisoformat(primary)
    for year in (first.year - 1, first.year):
        additional = _full_date(printed + '/' + str(year))
        if additional and 0 <= (first - additional).days <= 31:
            return True
    return False


def andrews_source_regions(sources, statement):
    """Physical account sections remain comparable when OCR renumbers rows.

    A region is the section's vertical extent on its page. On a page whose text
    reads turned (``reading_rotation``) it is measured in the frame the page
    reads upright in: in displayed space every printed row of a sideways page
    spans the page's whole height, so any two sections would appear to overlap.
    """
    from services.financial.statement_engine import _rect
    lookup = {(s['page_number'], s['table_index']): s for s in sources}
    result = []
    for scope in statement['sources']:
        source = lookup[(scope['page_number'], scope['table_index'])]
        rotation = source.get('reading_rotation') or 0
        cells = [c for r in source['rows'] if r['row_index'] in scope['row_indices'] for c in r['cells']]
        if not cells or any(_box(c) is None for c in cells):
            return None
        locator = cells[0]['locator']
        if any((c['locator'].get('page_size'), c['locator'].get('space')) !=
               (locator.get('page_size'), locator.get('space')) for c in cells):
            return None
        boxes = [_rect(c, rotation)[0] for c in cells] if rotation else [_box(c) for c in cells]
        if any(box is None for box in boxes):
            return None
        page_size = list(locator['page_size'])
        if rotation in (90, 270):
            page_size = page_size[::-1]
        result.append(dict(page_number=scope['page_number'], table_index=scope['table_index'],
            page_size=page_size, space=locator['space'] + (f'_upright_{rotation}' if rotation else ''),
            top=min(box[1] for box in boxes), bottom=max(box[3] for box in boxes)))
    return result


def source_regions_overlap(current, previous):
    """None means incomparable coordinate spaces, requiring a broader check."""
    if not current or not previous:
        return None
    overlapping = False
    for a in current:
        for b in previous:
            if a['page_number'] != b['page_number']:
                continue
            if (a['page_size'], a['space']) != (b['page_size'], b['space']):
                return None
            overlapping |= min(a['bottom'], b['bottom']) > max(a['top'], b['top'])
    return overlapping


def _amount(text, currency, *, separate_cell=False):
    # OCR can insert spaces between digits in one measured money cell. Only
    # join those spaces after geometry separates the amount from its balance.
    # Never join adjacent numbers in a combined amount/balance text cell or
    # replace letters, signs or decimal punctuation.
    value = re.sub(r'\s+', '', text)
    if not re.fullmatch(_SPACED_MONEY, text) and not (
            separate_cell and re.fullmatch(_SPACED_MONEY, value)):
        raise ValueError('Check the amount in the PDF, including its sign and decimal point.')
    return int(exact_amount(value, currency))


def _money_cells(row, width):
    return [c for c in row['cells'] if _box(c) and _box(c)[0] >= width * .46]


# The long credit-voucher payment label. OCR may put spaces inside its
# words or read the C of "Credit" in lower case; every other letter must be
# read exactly.
_VOUCHER_LABEL = (r'((?:Recurring\s+)?Withdrawal\s+Adjustment\s+Debit\s+Card\s+'
                  r'[Cc]\s*r\s*e\s*d\s*i\s*t\s+Voucher)')


def _voucher_money(row, following, width, currency):
    """Read the long credit-voucher layouts, retaining their cells.

    A numeric suffix is accepted only after the printed payment label. A
    following line must contain only two measured money cells immediately
    beneath that label. No digit, sign, account or balance is inferred.

    The label cell can also hold both the amount and the running balance
    (``... Credit Voucher 0.25 1234.56``) when it reaches the money columns.
    Those two values are then read from that cell's page text only, never
    crop-checked as money: the payment's own running balance check and the
    next line's (whose cells are) must both hold, or the period stays held.
    The date cell may also hold the printed date, an additional date and the
    label together, when the money is printed on the following line.
    """
    cells = row['cells']
    if not cells or len(cells) > 3 or not all(_box(c) for c in cells):
        return None
    joined = None
    if len(cells) == 1:
        joined = re.fullmatch(r'(' + _DATE + r'(?:\s+' + _DATE + r')?)\s+' + _VOUCHER_LABEL, cells[0]['expected_text'].strip())
        if not joined or _box(cells[0])[0] >= width * .08:
            return None
        date_cell = description_cell = cells[0]
        match = re.fullmatch(_VOUCHER_LABEL + r'()()', joined[2])
        date_text = joined[1]
    else:
        date_cell, description_cell = cells[:2]
        if not (_box(date_cell)[0] < width * .08 and
                _box(date_cell)[2] <= _box(description_cell)[0] < width * .46):
            return None
        match = re.fullmatch(_VOUCHER_LABEL + r'(?:\s+(' + _SPACED_MONEY + r'))?(?:\s+(' + _SPACED_MONEY + r'))?',
                             description_cell['expected_text'].strip())
        date_text = date_cell['expected_text'].strip()
    if not match:
        return None
    inline_pair = bool(match[2] and match[3])
    wrapped = not match[2]
    if wrapped:
        if len(cells) != (1 if joined else 2) or following is None or len(following['cells']) not in (1, 2):
            return None
        money_cells = _money_cells(following, width)
        if len(money_cells) != len(following['cells']):
            return None
        if len(money_cells) == 1:
            # The following line read as one joined amount and balance cell
            # (crop-checked as such): exactly one space separates two amounts.
            pair = re.fullmatch(r'(' + _SPACED_MONEY + r')\s+(' + _SPACED_MONEY + r')', money_cells[0]['expected_text'].strip())
            if not pair or len(re.findall(r'\.', money_cells[0]['expected_text'])) != 2:
                return None
            inline_pair = True
            money_cells = money_cells * 2
            amount_text, balance_text = pair[1], pair[2]
        else:
            amount_text, balance_text = [c['expected_text'].strip() for c in money_cells]
    elif inline_pair:
        if len(cells) != 2 or _box(description_cell)[2] < width * .46:
            return None
        money_cells = [description_cell, description_cell]
        amount_text, balance_text = match[2], match[3]
    else:
        if len(cells) != 3 or _box(cells[2])[0] < width * .46:
            return None
        money_cells = [description_cell, cells[2]]
        amount_text, balance_text = match[2], cells[2]['expected_text'].strip()
    measured = cells + (money_cells if wrapped else [])
    space = tuple(cells[0]['locator'].get(k) for k in ('page', 'page_size', 'space', 'units'))
    if any(tuple(c['locator'].get(k) for k in ('page', 'page_size', 'space', 'units')) != space
           for c in measured):
        return None
    left, right = [_box(c) for c in money_cells]
    if not inline_pair and (left[2] > right[0] or max(left[1], right[1]) >= min(left[3], right[3])):
        return None
    description_box = _box(description_cell)
    if wrapped:
        height = description_box[3] - description_box[1]
        if not (description_box[2] <= left[2] and
                description_box[3] - height * .25 <= min(left[1], right[1]) <= description_box[3] + height * 1.1):
            return None
    elif max(description_box[1], _box(date_cell)[1]) >= min(description_box[3], _box(date_cell)[3]):
        return None
    try:
        _amount(amount_text, currency, separate_cell=wrapped and not inline_pair)
        _amount(balance_text, currency, separate_cell=not inline_pair)
    except ValueError:
        return None
    return dict(body=date_text + ' ' + match[1],
                money_cells=money_cells, amount_text=amount_text, balance_text=balance_text,
                source_row=following if wrapped else row, wrapped=wrapped, inline_pair=inline_pair)


_DATE_UNREAD = 'Check the full date in the PDF. It could not be read within this statement period.'
_ADDITIONAL_UNREAD = ('Check the additional date printed beside this payment. It is unreadable, later than '
                      'the row date or more than 31 days earlier.')
# A payment's printed row date whose only damage is OCR marks (a speck before
# or after it, a point or colon inside it, a letter measured to stand for a
# digit or for the slash) is read only when it lies within the period and
# between the cleanly read dates of the payments before and after it: this
# statement prints its payments in date order (0 of 6,465 verified rows out of
# order). Reverse in one place: False.
ORDERED_DAMAGED_DATES = True
DATE_READ_IN_ORDER = 'printed_date_marks_ignored_in_payment_order'
ENDING_DATE_IS_PERIOD_END = 'printed_date_marks_ignored_period_end'
_DATE_DIGIT_LOOKALIKES = str.maketrans({'O': '0', 'o': '0', 'l': '1', 'I': '1'})
# The Ending Balance date must equal the printed period end, so the wider set
# measured in Andrews money cells may stand for its digits.
_ENDING_DATE_LOOKALIKES = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'l': '1', 'I': '1', 'B': '8', 'S': '5', 'Z': '2'})


def _damaged_date(text, statement, lookalikes=_DATE_DIGIT_LOOKALIKES):
    """``(row date, additional printed date or None)`` once OCR marks are set aside, else ``None``."""
    tokens = text.split()
    if not 1 <= len(tokens) <= 2:
        return None
    cleaned = []
    for token in tokens:
        letters = ''.join(sorted(k for k in map(chr, lookalikes)))
        keep = '\\d' + re.escape(letters)
        token = re.sub(r'^[^' + keep + r']+|[^' + keep + r']+$', '', token)
        token = re.sub(r'(?<=[' + keep + r'/])[.:](?=[' + keep + r'/])', '', token)
        if len(token) == 5 and token[2] in 'ilI|' and re.fullmatch(r'[' + keep + r']{4}', token[:2] + token[3:]):
            token = token[:2] + '/' + token[3:]
        token = token.translate(lookalikes)
        if not re.fullmatch(r'\d{2}/\d{2}', token):
            return None
        cleaned.append(token)
    value = _period_date(cleaned[0], statement)
    if not value:
        return None
    if len(cleaned) == 2 and not _ordinary_additional_date(cleaned[1], value):
        return None
    return value, cleaned[1] if len(cleaned) == 2 else None


def _date_damaged_rows_in_order(rows, damaged, statement):
    """Read the damaged row dates that the period's payment order fixes (``ORDERED_DAMAGED_DATES``)."""
    # The section's printed opening and ending balance lines carry the
    # period's first and last dates: they bound its first and last payment.
    chain = [r for r in rows if r['kind'] == 'balance' or not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]
    clean = [None if r['id'] in damaged else r['fields'].get('date') for r in chain]
    for index, row in enumerate(chain):
        if row['id'] not in damaged:
            continue
        found = _damaged_date(damaged[row['id']], statement)
        before = clean[index - 1] if index else None
        after = clean[index + 1] if index + 1 < len(chain) else None
        if not found or not before or not after or not before <= found[0] <= after:
            continue
        fields = row['fields']
        fields['date'] = found[0]
        fields['date_reading'] = DATE_READ_IN_ORDER
        row['issues'] = [issue for issue in row['issues'] if issue != _DATE_UNREAD]
        if found[1] is not None:
            fields['additional_printed_date'] = found[1]
            row['issues'] = [issue for issue in row['issues'] if issue != _ADDITIONAL_UNREAD]
        elif fields.get('additional_printed_date') and _ordinary_additional_date(fields['additional_printed_date'], found[0]):
            row['issues'] = [issue for issue in row['issues'] if issue != _ADDITIONAL_UNREAD]


# A line printed inside an account section with no money and no payment word
# (a dated notice such as a pending credit announced before its voucher) is
# set aside as information only when the next payment's running balance
# continues exactly from the balance printed before the line: no money moved
# on it. Reverse in one place: False keeps such lines for the investigator.
MONEYLESS_NOTICES = True
# A dated money row whose first cell is a printed date read with a space
# inside it. Reverse in one place: False needs the date without spaces.
SPACED_ROW_DATES = True
NOTICE_BASIS = 'no_money_and_running_balance_unbroken'


def _moneyless_notices(result, notices):
    """Set aside each run of money-less lines whose next payment reconciles from the balance before them."""
    positions = {row['id']: index for index, row in enumerate(result)}
    marked = {row['id'] for row in notices}
    for row in notices:
        index = positions[row['id']]
        following = next((r for r in result[index + 1:] if r['id'] not in marked
                          and r['kind'] not in ('continuation', 'statement_information')), None)
        if (following is None or following['kind'] != 'transaction' or following['excluded']
                or following['fields'].get('balance_difference_minor') != '0'
                or any(k not in following['fields'] for k in ('amount_minor', 'direction', 'balance'))):
            continue
        row.update(excluded=True, kind='statement_information', issues=[])
        row['fields']['information_basis'] = NOTICE_BASIS


def propose_andrews_statement(sources, currency, statement):
    result = []
    damaged_dates = {}
    notices = []
    previous_balance = None
    previous_payment = None
    scopes = {(s['page_number'], s['table_index']):s for s in statement['sources']}
    order = {key: index for index, key in enumerate(scopes)}
    for source in sorted(sources, key=lambda s: order[(s['page_number'], s['table_index'])]):
        page = andrews_page(source, allow_unbranded=True)
        scope = scopes[(source['page_number'], source['table_index'])]
        money_continuations = {}
        for position, row in enumerate(source['rows']):
            index = row['row_index']
            if index not in scope['row_indices'] and index not in scope['heading_rows']:
                continue
            cells = row['cells']
            text = _text(row)
            item = dict(id=f"{source['page_number']}:{source['table_index']}:{index}",
                        page_number=source['page_number'], table_index=source['table_index'], row_index=index,
                        source_revision=source['source_revision'], source_cells=cells, fields={},
                        issues=[], excluded=True, kind='statement_information')
            result.append(item)
            if index not in scope['row_indices']:
                continue
            item['fields']['statement_layout'] = _LAYOUT
            if index in money_continuations:
                parent = money_continuations[index]
                item.update(kind='continuation')
                item['fields']['parent_transaction_id'] = parent['id']
                parent.setdefault('continuation_sources', []).append(dict(
                    page_number=source['page_number'], row_index=index, source_cells=cells))
                continue
            # The period/year-to-date fee summary is not a second set of fee
            # payments, even when it follows an account's continuation page.
            if (cells and cells[0]['expected_text'].strip() in
                    ('Total Returned Item Fees', 'Total Overdraft Fees') and len(cells) == 3):
                continue
            if _continued(text):
                continue
            closure = statement.get('account_closure')
            if (closure and source['page_number'] == closure['page_number']
                    and source['table_index'] == closure['table_index'] and index == closure['row_index']):
                item['fields'].update(account_closed_on=closure['date'], description=text)
                continue
            money_cells = _money_cells(row, page['width'])
            money = ' '.join(c['expected_text'].strip() for c in money_cells)
            body = ' '.join(c['expected_text'].strip() for c in cells if c not in money_cells)
            opening = _SHARE.match(body)
            closing = re.fullmatch(_SPACED_ENDING_BODY if SPACED_ROW_DATES else _ENDING_BODY, body)
            damaged_closing = not closing and _ending_balance(row, page['width'])
            if opening or closing or damaged_closing:
                item.update(kind='balance')
                fields = item['fields']
                fields['description'] = 'Opening Balance' if opening else 'Closing Balance'
                fields['date'] = (_period_date((opening or closing)[1], statement) or '') if opening or closing else ''
                if damaged_closing and ORDERED_DAMAGED_DATES:
                    # A speck or a measured look-alike in the Ending Balance
                    # date: read only when it is then the printed period end.
                    found = _damaged_date(damaged_closing[0], statement, _ENDING_DATE_LOOKALIKES)
                    if found and found[1] is None and found[0] == statement.get('period_end'):
                        fields.update(date=found[0], date_reading=ENDING_DATE_IS_PERIOD_END)
                if money_cells:
                    fields['balance_column'] = str(money_cells[-1]['column_index'])
                try:
                    fields['balance'] = str(_amount(money, currency, separate_cell=len(money_cells) == 1))
                except ValueError:
                    item['issues'].append('Check this balance in the PDF. Its digits or decimal point could not be read.')
                if opening:
                    previous_balance = int(fields['balance']) if 'balance' in fields else None
                elif 'balance' in fields and previous_balance is not None and int(fields['balance']) != previous_balance:
                    item['issues'].append('The closing balance differs from the last transaction balance. Check for a missing transaction or a misread balance.')
                previous_payment = None
                continue
            # Continuation references can also begin MM/DD; only a transaction
            # verb or a measured date + money row can begin another payment.
            parsed = _PAYMENT.match(body)
            first_box = _box(cells[0]) if cells else None
            damaged_date_payment = (_DAMAGED_DATE_PAYMENT.match(body)
                                    if not parsed and first_box and first_box[0] < page['width'] * .08 else None)
            # A printed date read with a space inside (``06/ 03``) still opens a
            # dated money row when it is the row's first cell.
            spaced_date = (SPACED_ROW_DATES and cells and re.fullmatch(_DATE, cells[0]['expected_text'].strip())
                           and re.match(r'^(' + _DATE + r')(?: |$)', body))
            dated_money = (first_box and first_box[0] < page['width'] * .08 and money_cells
                           and (re.match(r'^\S{4,7}(?: |$)', body) or spaced_date))
            if dated_money and re.match(r'^\S{4,7}(?: |$)', body):
                spaced_date = None
            if parsed or damaged_date_payment or dated_money:
                following = source['rows'][position + 1] if position + 1 < len(source['rows']) else None
                if following is not None and following['row_index'] not in scope['row_indices']:
                    following = None
                voucher = _voucher_money(row, following, page['width'], currency) if parsed else None
                if voucher:
                    body, money_cells = voucher['body'], voucher['money_cells']
                    parsed = _PAYMENT.match(body)
                    item['value_sources'] = {name: dict(page_number=source['page_number'],
                        table_index=source['table_index'], row_index=voucher['source_row']['row_index'], source_cell=cell)
                        for name, cell in zip(('amount', 'balance'), money_cells)}
                    if voucher['wrapped']:
                        money_continuations[voucher['source_row']['row_index']] = item
                item.update(excluded=False, kind='transaction' if parsed else 'unresolved')
                fields = item['fields']
                date_text = (parsed[1] if parsed else damaged_date_payment[1] if damaged_date_payment
                             else spaced_date[1] if spaced_date else body.split(' ', 1)[0])
                value = _period_date(date_text, statement)
                if value:
                    fields['date'] = value
                else:
                    item['issues'].append(_DATE_UNREAD)
                    damaged_dates[item['id']] = date_text
                fields['date_column'] = str(cells[0]['column_index'])
                fields['description'] = (parsed[3] if parsed else damaged_date_payment[2] if damaged_date_payment
                                         else body[spaced_date.end():].strip() if spaced_date else body.partition(' ')[2])
                fields['counterparty'] = ''
                if parsed and parsed[2]:
                    fields['additional_printed_date'] = parsed[2]
                    # The first printed date remains the row date, just as on
                    # adjacent rows with secondary date text on a continuation
                    # line. Retain the other text without calling it a posting,
                    # value or transaction date. Unusual dates still need review.
                    if not _ordinary_additional_date(parsed[2], value):
                        item['issues'].append(_ADDITIONAL_UNREAD)
                pair = re.fullmatch(r'(' + _SPACED_MONEY + r')\s+(.+)', money)
                amount_text, balance_text = (pair[1], pair[2]) if pair else ('', '')
                if pair is None:
                    trailing = re.fullmatch(r'(.+)\s+(' + _SPACED_MONEY + r')', money)
                    if trailing:
                        amount_text, balance_text = trailing[1], trailing[2]
                if len(money_cells) == 2:
                    amount_text, balance_text = [c['expected_text'].strip() for c in money_cells]
                if voucher:
                    amount_text, balance_text = voucher['amount_text'], voucher['balance_text']
                separate_cells = (len(money_cells) == 2 and
                                  _box(money_cells[0])[2] <= _box(money_cells[1])[0])
                if separate_cells and (not voucher or not voucher['wrapped']):
                    # Geometry identifies both targets even when their digits
                    # fail parsing. Wrapped/merged cells are not crop targets.
                    fields['amount_column'] = str(money_cells[0]['column_index'])
                    fields['balance_column'] = str(money_cells[1]['column_index'])
                misread_sign = None
                try:
                    amount = _amount(amount_text, currency, separate_cell=separate_cells)
                    fields['amount_minor'] = str(abs(amount))
                    if not voucher or not voucher['wrapped']:
                        fields['amount_column'] = str(money_cells[0]['column_index'])
                    description = fields['description']
                    verb = re.sub(r'\s+', '', parsed[4] if parsed else damaged_date_payment[3]) if parsed or damaged_date_payment else None
                    misread = None if verb or not MISREAD_VERB_DIRECTION else _misread_verb(description)
                    conflict = (amount > 0 and (verb or misread) == 'Withdrawal' and 'Adjustment' not in description
                                or amount < 0 and (verb or misread) == 'Deposit')
                    if not conflict and verb is None and misread and amount:
                        # Decided below, once both printed balances are known.
                        misread_sign = amount
                    elif conflict or verb is None:
                        item['issues'].append(_DIRECTION_UNREAD)
                    else:
                        fields['direction'] = 'credit' if amount >= 0 else 'debit'
                except ValueError:
                    item['issues'].append('Check the transaction amount in the PDF. Its digits, sign or decimal point could not be read.')
                try:
                    fields['balance'] = str(_amount(balance_text, currency, separate_cell=separate_cells))
                    if not voucher or not voucher['wrapped']:
                        fields['balance_column'] = str(money_cells[-1]['column_index'])
                except ValueError:
                    item['issues'].append('Check the running balance in the PDF. It could not be read separately from the transaction amount.')
                if misread_sign is not None:
                    if (previous_balance is not None and 'balance' in fields
                            and int(fields['balance']) - previous_balance == misread_sign):
                        fields.update(direction='credit' if misread_sign > 0 else 'debit',
                                      direction_basis=DIRECTION_FROM_SIGN_AND_BALANCES)
                        item['kind'] = 'transaction'
                    else:
                        item['issues'].append(_DIRECTION_UNREAD)
                if previous_balance is not None and all(k in fields for k in ('balance', 'amount_minor', 'direction')):
                    movement = int(fields['amount_minor']) * (1 if fields['direction'] == 'credit' else -1)
                    delta = int(fields['balance']) - previous_balance - movement
                    fields['balance_difference_minor'] = str(delta)
                    if delta:
                        item['issues'].append('The running balance does not match this payment. Check the amount, balance or a missing row.')
                previous_balance = int(fields['balance']) if 'balance' in fields else None
                previous_payment = item
            elif previous_payment is not None:
                item['kind'] = 'continuation'
                previous_payment['fields']['description'] += '\n' + text
                previous_payment.setdefault('continuation_sources', []).append(dict(
                    page_number=source['page_number'], row_index=index, source_cells=cells))
            else:
                item.update(excluded=False, kind='unresolved')
                item['issues'].append('Check this line in the account section. It could not be linked to a transaction.')
                if not money_cells and not re.search(_WITHDRAWAL + '|' + _DEPOSIT, body):
                    notices.append(item)
    if MONEYLESS_NOTICES and notices:
        _moneyless_notices(result, notices)
    if ORDERED_DAMAGED_DATES and damaged_dates:
        _date_damaged_rows_in_order(result, damaged_dates, statement)
    issues = []
    for name in ('Opening Balance', 'Closing Balance'):
        controls = [r for r in result if r['kind'] == 'balance' and r['fields'].get('description') == name]
        if not controls and not (name == 'Closing Balance' and statement.get('account_closure')):
            issues.append(f'The {name.lower()} was not found for this account section. Check the PDF for a missing or unreadable page.')
    return dict(rows=result, issues=issues,
                no_activity_evidence=andrews_no_activity_evidence(sources, statement, result))


# Exact printed letters; only OCR spacing is ignored, as in the reader itself.
_QUIET_OPENING = re.compile(r'\d{2}/\d{2}ID\d{4}(?:BASESHARESAVINGS|FREECHECKING|VISAPAYMENT|[A-Z]+CLUB)PreviousBalance')
_QUIET_CLOSING = re.compile(r'\d{2}/\d{2}EndingBalance')
NO_ACTIVITY_METHOD = 'andrews-adjacent-endpoint-rows-v1'


def andrews_no_activity_evidence(sources, statement, rows):
    """Decide whether the printed page itself proves a section had no activity.

    Equal balances alone never establish no activity. This requires, on one
    page: the exact printed opening (Previous Balance) line with a readable
    date in the period, the exact printed Ending Balance line dated the period
    end, both balances readable
    and equal, nothing at all read between them, and no vertical room between
    them for an unread line (measured against this page's own line spacing).
    A failed or partial reading, a missing page or a section that crosses a
    page break stays unproven; the investigator's confirmation remains needed.
    Returns None when the section has payment candidates (not a quiet question).
    """
    if statement.get('assignment_only') or (statement.get('account_closure') and not CLOSURE_PROOF):
        return None
    if any(not row['excluded'] for row in rows):
        return None

    def held(reason, message, **extra):
        return dict(verified=False, method=NO_ACTIVITY_METHOD, reason=reason, message=message, **extra)

    if statement.get('account_closure'):
        return _closure_evidence(sources, statement, rows, held)

    scopes = statement.get('sources') or []
    if len(scopes) != 1:
        return held('section_spans_pages', 'This account section continues across pages. Check every page of this period before confirming that it contains no transactions.')
    scope = scopes[0]
    key = (scope['page_number'], scope['table_index'])
    source = next((s for s in sources if (s['page_number'], s['table_index']) == key), None)
    in_scope = {row['id']: row for row in rows if (row['page_number'], row['table_index']) == key
                and row['row_index'] in scope['row_indices']}
    balances = [row for row in in_scope.values() if row['kind'] == 'balance']
    openings = [row for row in balances if row['fields'].get('description') == 'Opening Balance']
    closings = [row for row in balances if row['fields'].get('description') == 'Closing Balance']
    if source is None or len(openings) != 1 or len(closings) != 1:
        return held('endpoint_missing', 'The opening or ending balance line of this section was not read. Check the page before confirming that it contains no transactions.', page_number=key[0])
    opening, closing = openings[0], closings[0]
    if len(in_scope) != 2:
        return held('rows_between_endpoints', 'Other lines were read inside this account section. Check them before confirming that it contains no transactions.', page_number=key[0])
    page = andrews_page(source, allow_unbranded=True)
    width = page['width'] if page else None

    def label(row):
        money = _money_cells(row, width)
        return money, ' '.join(c['expected_text'].strip() for c in row['cells'] if c not in money)

    source_rows = {row['row_index']: row for row in source['rows']}
    open_money, open_text = label(source_rows[opening['row_index']]) if page else ([], '')
    close_money, close_text = label(source_rows[closing['row_index']]) if page else ([], '')
    if (not page or len(open_money) != 1 or len(close_money) != 1
            or not _QUIET_OPENING.fullmatch(re.sub(r'\s+', '', open_text))
            or not (_QUIET_CLOSING.fullmatch(re.sub(r'\s+', '', close_text))
                    or closing['fields'].get('date_reading') == ENDING_DATE_IS_PERIOD_END
                    and re.fullmatch(r'\S+ Ending Balance', close_text))):
        return held('endpoint_label', 'The opening or ending balance line was not read exactly as printed. Check the page before confirming that it contains no transactions.', page_number=key[0])
    if 'balance' not in opening['fields'] or 'balance' not in closing['fields']:
        return held('endpoint_unreadable', 'An opening or ending balance could not be read. Check the page before confirming that it contains no transactions.', page_number=key[0])
    if opening['fields']['balance'] != closing['fields']['balance']:
        return held('endpoints_differ', 'The opening and ending balances differ, so money moved in this period. Check the page for transactions that were not read.', page_number=key[0])
    if opening['issues'] or closing['issues']:
        return held('endpoint_unreadable', 'An opening or ending balance line needs checking. Check the page before confirming that it contains no transactions.', page_number=key[0])
    # The section must run to the printed period end; its opening date must be
    # a readable date inside the period. No date is inferred.
    if (not opening['fields'].get('date') or closing['fields'].get('date') != statement.get('period_end')
            or opening['fields']['date'] > closing['fields']['date']):
        return held('endpoint_dates', 'The opening and ending balance dates do not cover the printed statement period. Check the page before confirming that it contains no transactions.', page_number=key[0])
    band = _adjacent_lines(sources, source, page, opening['row_index'], closing['row_index'],
                           [c for c in source_rows[opening['row_index']]['cells'] if c not in open_money],
                           [c for c in source_rows[closing['row_index']]['cells'] if c not in close_money], held)
    if band.get('verified') is False:
        return band
    first, second, space, pitch, distance = (band[k] for k in ('first', 'second', 'space', 'pitch', 'distance'))
    return dict(verified=True, method=NO_ACTIVITY_METHOD, reason='adjacent_equal_endpoints',
        message='The printed page shows this account section\'s opening balance line followed directly by its ending balance line at the statement end date, with equal balances and no line between them.',
        page_number=key[0], table_index=key[1], opening_row_id=opening['id'], closing_row_id=closing['id'],
        balance_minor=opening['fields']['balance'], period_start=statement.get('period_start'),
        opening_date=opening['fields']['date'], closing_date=closing['fields']['date'],
        period_end=statement.get('period_end'), opening_rect=first, closing_rect=second,
        page_size=space.get('page_size'), coordinate_space=space.get('space'),
        line_pitch=pitch, distance=distance,
        endpoint_methods=[(row.get('value_provenance') or {}).get('method') for row in (opening, closing)])


# Whether a closed share section can prove from its page that it had no
# activity (``_closure_evidence``). Reverse in one place.
CLOSURE_PROOF = True


def _closure_evidence(sources, statement, rows, held):
    """The page's proof that a closed section with a zero opening balance had no activity, or why not.

    Printed facts only, on one page: the exact opening (Previous Balance) line
    with a readable date in the period and a readable balance of exactly
    0.00, followed directly by the section's own ``Closed`` line dated inside
    the printed period, nothing read between them and no room for an unread
    line (as for an ending balance line). An account that opens at zero and
    closes with no payment printed ends at zero: no money moved and no
    closing balance is needed. Any other closed section stays the
    investigator's to confirm.
    """
    closure = statement['account_closure']
    scopes = statement.get('sources') or []
    if len(scopes) != 1:
        return held('section_spans_pages', 'This account section continues across pages. Check every page of this period before confirming that it contains no transactions.')
    scope = scopes[0]
    key = (scope['page_number'], scope['table_index'])
    source = next((s for s in sources if (s['page_number'], s['table_index']) == key), None)
    in_scope = {row['id']: row for row in rows if (row['page_number'], row['table_index']) == key
                and row['row_index'] in scope['row_indices']}
    openings = [row for row in in_scope.values() if row['kind'] == 'balance'
                and row['fields'].get('description') == 'Opening Balance']
    closings = [row for row in in_scope.values() if row['kind'] == 'balance'
                and row['fields'].get('description') == 'Closing Balance']
    closed = [row for row in in_scope.values() if row['fields'].get('account_closed_on')]
    if (source is None or len(openings) != 1 or closings or len(closed) != 1 or len(in_scope) != 2
            or (closure.get('page_number'), closure.get('table_index')) != key
            or closed[0]['row_index'] != closure.get('row_index')):
        return held('endpoint_missing', 'The opening balance line or the closing notice of this section was not read as printed. Check the page before confirming that it contains no transactions.', page_number=key[0])
    opening, notice = openings[0], closed[0]
    page = andrews_page(source, allow_unbranded=True)
    source_rows = {row['row_index']: row for row in source['rows']}
    money = _money_cells(source_rows[opening['row_index']], page['width']) if page else []
    label = ' '.join(c['expected_text'].strip() for c in source_rows[opening['row_index']]['cells'] if c not in money)
    if not page or len(money) != 1 or not _QUIET_OPENING.fullmatch(re.sub(r'\s+', '', label)):
        return held('endpoint_label', 'The opening balance line was not read exactly as printed. Check the page before confirming that it contains no transactions.', page_number=key[0])
    if 'balance' not in opening['fields'] or opening['issues']:
        return held('endpoint_unreadable', 'The opening balance could not be read. Check the page before confirming that it contains no transactions.', page_number=key[0])
    if opening['fields']['balance'] != '0':
        return held('closed_with_balance', 'This account opened with money in it and was closed, so money moved in this period. Check the page for transactions that were not read.', page_number=key[0])
    start, end, closed_on = statement.get('period_start'), statement.get('period_end'), closure.get('date')
    if (not opening['fields'].get('date') or not closed_on or not start or not end
            or not start <= opening['fields']['date'] <= closed_on <= end):
        return held('endpoint_dates', 'The opening line and the closing notice are not dated inside the printed statement period. Check the page before confirming that it contains no transactions.', page_number=key[0])
    band = _adjacent_lines(sources, source, page, opening['row_index'], notice['row_index'],
                           [c for c in source_rows[opening['row_index']]['cells'] if c not in money],
                           source_rows[notice['row_index']]['cells'], held)
    if band.get('verified') is False:
        return band
    space = band['space']
    return dict(verified=True, method=NO_ACTIVITY_METHOD, reason='closed_without_activity',
        message='The printed page shows this account section\'s opening balance of 0.00 followed directly by its closing notice inside the statement period, with no line between them.',
        page_number=key[0], table_index=key[1], opening_row_id=opening['id'], closing_row_id=None,
        closure_row_id=notice['id'], closure_date=closed_on, balance_minor='0',
        period_start=start, opening_date=opening['fields']['date'], period_end=end,
        opening_rect=band['first'], closing_rect=band['second'],
        page_size=space.get('page_size'), coordinate_space=space.get('space'),
        line_pitch=band['pitch'], distance=band['distance'],
        endpoint_methods=[(opening.get('value_provenance') or {}).get('method')])


# Whether a closed section proven without activity also offers the closing
# balance its proof fixes (``proven_closing``). Reverse in one place.
CLOSURE_CLOSING = True


def proven_closing(evidence):
    """The closing balance a closed section's own proof fixes, or None.

    Only for a verified ``closed_without_activity`` proof: the printed opening
    of exactly 0.00, the section's closing notice directly after it inside the
    period and no line between them. No balance is printed for such a section,
    so the value is never recorded as printed: its basis is the proof, and it
    is cited to the closing notice (row, page and position) and the opening
    line the proof names.
    """
    if (not CLOSURE_CLOSING or not isinstance(evidence, dict) or evidence.get('verified') is not True
            or evidence.get('reason') != 'closed_without_activity' or evidence.get('balance_minor') != '0'
            or not evidence.get('closure_row_id') or not evidence.get('opening_row_id')):
        return None
    return dict(balance_minor='0', printed=False, basis='closed_without_activity', method=evidence.get('method'),
        message='No closing balance is printed for this section. It opened at 0.00 and its closing notice follows '
                'directly, inside the statement period, with no payment between them, so it closed at 0.00.',
        cited_row_id=evidence['closure_row_id'], opening_row_id=evidence['opening_row_id'],
        closure_date=evidence.get('closure_date'), page_number=evidence.get('page_number'),
        table_index=evidence.get('table_index'), rect=evidence.get('closing_rect'),
        page_size=evidence.get('page_size'), coordinate_space=evidence.get('coordinate_space'))


def _adjacent_lines(sources, source, page, first_index, second_index, first_cells, second_cells, held):
    """``dict(first, second, space, pitch, distance)`` when two lines of a page are printed directly one after the other.

    No row is read between them, nothing read anywhere on the page lies in the
    band between their labels (``first_cells``, ``second_cells``), and there is
    no vertical room between them for an unread line, measured against this
    page's own line spacing. Otherwise the ``held`` reason.
    """
    key = (source['page_number'], source['table_index'])
    source_rows = {row['row_index']: row for row in source['rows']}
    ordered = sorted(source_rows)
    position = ordered.index(first_index)
    if position + 1 >= len(ordered) or ordered[position + 1] != second_index:
        return held('rows_between_endpoints', 'Other lines were read between the opening and ending balances. Check them before confirming that it contains no transactions.', page_number=key[0])

    def extent(cells):
        boxes = [_box(c) for c in cells]
        locators = [c.get('locator') or {} for c in cells]
        if not boxes or any(b is None for b in boxes) or len({(l.get('page'), str(l.get('page_size')), l.get('space')) for l in locators}) != 1:
            return None
        return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]

    # Positions of the printed labels: a money cell's box can be read taller
    # than its line, which would hide or invent room for an unread line.
    first = extent(first_cells)
    second = extent(second_cells)
    space = (source_rows[first_index]['cells'][0].get('locator') or {})
    # Measure spacing only among account-section lines, never the address block.
    body = [r for r in (source_rows[i] for i in ordered) if r['row_index'] >= page['body_start'] and r['cells']]
    first_section = next((i for i, r in enumerate(body) if _SHARE_LABEL.match(_text(r)) or _PREVIOUS.search(_text(r))), len(body))
    body = body[first_section:]
    tops = [e[1] for r in body if (e := extent(r['cells'])) is not None]
    steps = sorted(b - a for a, b in zip(tops, tops[1:]) if b > a)
    if first is None or second is None or len(steps) < 3 or second[1] <= first[1]:
        return held('line_spacing_unmeasured', 'The position of the lines on this page could not be measured. Check the page before confirming that it contains no transactions.', page_number=key[0])
    pitch = steps[len(steps) // 2]
    distance = second[1] - first[1]
    if distance * 2 > pitch * 3:
        return held('unread_band', 'There is space between the opening and ending balance lines where a line may not have been read. Check the page before confirming that it contains no transactions.',
                    page_number=key[0], line_pitch=pitch, distance=distance)
    # Nothing read on this page, in this or another table and whatever its
    # row numbering, may lie in the band between the two lines.
    for other in sources:
        if other['page_number'] != key[0]:
            continue
        for row in other['rows']:
            if other is source and row['row_index'] in (first_index, second_index):
                continue
            for cell in row['cells']:
                b = _box(cell)
                if b is None or first[3] < (b[1] + b[3]) / 2 < second[1]:
                    return held('rows_between_endpoints', 'Other text was read between the opening and ending balance lines. Check it before confirming that it contains no transactions.', page_number=key[0])
    return dict(first=first, second=second, space=space, pitch=pitch, distance=distance)


def _overlap(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0
    smaller = min((a[2]-a[0]) * (a[3]-a[1]), (b[2]-b[0]) * (b[3]-b[1]))
    return width * height / smaller if smaller > 0 else 0


def endpoint_balance_provenance(rows, page_locations):
    """Record where and how each printed opening/ending balance was read.

    Page, coordinates and the reading method come from the stored reading
    and its retained repair records. Nothing here supplies or changes a
    value; a balance that was not read keeps no value and says so.
    """
    spans = {loc.get('page_number'): loc for loc in (page_locations or []) if isinstance(loc, dict)}
    for row in rows:
        fields = row['fields']
        if row['kind'] != 'balance' or fields.get('description') not in ('Opening Balance', 'Closing Balance'):
            continue
        span = spans.get(row['page_number']) or {}
        records = [r for r in span.get('ocr_refinements') or [] if isinstance(r, dict)]
        page_reread = any(r.get('field') == 'statement_page_reading' and r.get('decision') == 'image_selected' for r in records)
        method = ('page_image_reading' if page_reread else 'page_ocr' if span.get('extraction_method') == 'tesseract_ocr'
                  else 'native_text' if span else 'unknown')
        column = fields.get('balance_column')
        cells = [c for c in row['source_cells'] if column is not None and str(c['column_index']) == column]
        result = dict(field='balance', role=fields['description'], page_number=row['page_number'],
                      status='read' if 'balance' in fields else 'unreadable', method=method)
        if len(cells) == 1 and _box(cells[0]):
            cell = cells[0]
            rect = _box(cell)
            result.update(rect=rect, page_size=cell['locator'].get('page_size'),
                          coordinate_space=cell['locator'].get('space'), printed_text=cell['expected_text'])
            for record in records:
                # A held cell cleared by the independent glyph reader: name it, and keep the
                # page reading it replaced beside the accepted value.
                if record.get('method') == 'statement_money_second_reader_repair' and record.get('decision') == 'repaired':
                    repaired = next((c for c in record.get('cells') or [] if isinstance(c.get('rect'), list)
                                     and len(c['rect']) == 4 and _overlap(c['rect'], rect) >= .5), None)
                    if repaired:
                        result.update(method='second_reader_repair', reread=dict(method=record['method'],
                            original_text=repaired.get('page_reading'), text=repaired.get('text'),
                            observations=len(repaired.get('observations') or []), reason=repaired.get('reason'),
                            second_reading=(repaired.get('second_reading') or {}).get('method')))
                        break
                # A held cell given the one printed reading (page or crop) that the
                # page's agreed controls pin: keep the page reading beside it.
                if record.get('method') == 'statement_money_pinned_reading' and record.get('decision') == 'repaired':
                    repaired = next((c for c in record.get('cells') or [] if isinstance(c.get('rect'), list)
                                     and len(c['rect']) == 4 and _overlap(c['rect'], rect) >= .5), None)
                    if repaired:
                        result.update(method='pinned_reading_repair', reread=dict(method=record['method'],
                            original_text=repaired.get('page_reading'), text=repaired.get('text'),
                            observations=len(repaired.get('observations') or []), reason=repaired.get('reason'),
                            accepted_reading=repaired.get('accepted_reading')))
                        break
                source_rect = ((record.get('source_locator') or {}).get('rect')
                               if record.get('method') == 'tesseract_native_statement_cell_consensus' else record.get('rect'))
                if (record.get('method') in ('tesseract_native_statement_cell_consensus', 'tesseract_amount_crop_consensus')
                        and record.get('field') == 'balance' and isinstance(source_rect, list) and len(source_rect) == 4
                        and _overlap(source_rect, rect) >= .5):
                    result.update(method='cell_crop_reread', reread=dict(method=record['method'],
                        original_text=record.get('original_text'), text=record.get('text'),
                        observations=len(record.get('observations') or []), reason=record.get('reason')))
                    break
        else:
            result['rect'] = None
        row['value_provenance'] = result
    return rows
