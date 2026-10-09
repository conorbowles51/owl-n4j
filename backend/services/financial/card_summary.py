"""Card account summaries: the printed movement totals between the previous and the new balance.

A card statement prints an account summary: the previous balance, the
payments and other credits, the purchases, cash advances, balance
transfers, fees and interest charged, and the new balance. The component
labels are data shared with the general statement engine
(``statement_engine_vocabulary``: ``LIABILITY_CREDIT_COMPONENTS`` and
``LIABILITY_DEBIT_COMPONENTS``); an issuer reader supplies only where its
summary box is printed (its heading and the heading of the box beside it).

Fail closed: when a period's summary prints components, the credit
components must equal the credit lines read and the debit components the
debit lines read, to the cent (a charge section the summary prints no line
for, fees or interest, is not part of what it totals). A component whose amount cannot be read, or
a total that differs, turns that summary line into an unresolved row with
the reason, so the period is held for a person. Nothing is derived from the
totals: they only check what was read.
"""
import re

from services.financial.locators import Locator, LocatorError
from services.financial.statement_engine_vocabulary import INDEX, label
from services.financial.statement_import_proposal import exact_amount

ROLES = ('credit_component', 'debit_component')


def _rectangle(cell, page):
    try:
        rectangle = Locator.from_json(cell['locator']).rectangle
        return rectangle if rectangle and rectangle.page_number == page else None
    except (LocatorError, ValueError, TypeError, KeyError):
        return None


def _amount(text, currency):
    """``(amount, confirmed)`` of a summary value cell (``$1,234.56``), or ``None`` when unreadable.

    A page reading the engine's crop check did not confirm carries one
    trailing ``?``; its amount is kept with ``confirmed=False``. Any other
    mark makes it unreadable.
    """
    raw = text.strip(' |[]')
    confirmed = not raw.endswith('?')
    raw = re.sub(r'^[=+\-]\s*', '', raw.removesuffix('?'))
    if not re.fullmatch(r'\$\s*\d[\d,]*\.\d{2}', raw):
        # This summary prints a dollar marker on every value; without it a
        # misread marker may have become a digit. Unreadable, never guessed.
        return None
    try:
        return int(exact_amount(raw, currency)), confirmed
    except ValueError:
        return None


# Glyphs a recognised text layer was measured to put in card summary values:
# letters for printed digits (as in the engine's Andrews money cells), ``S``
# for the leading dollar sign, and a comma for the decimal point.
_LOOKALIKES = {'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'l': '1', 'I': '1', 'i': '1', '|': '1', 'B': '8', 'S': '5',
               'Z': '2'}


def _lookalike_reading(text, currency):
    """The amount a summary value's page reading states once measured look-alike glyphs are read, or ``None``.

    Only a candidate: it is accepted when the confirmed lines and the other
    components fix exactly that amount (``check_summary``), never by itself.
    """
    raw = text.strip(' |[]').removesuffix('?')
    raw = re.sub(r'^([=+\-]\s*)?S', lambda m: (m[1] or '') + '$', raw)
    raw = ''.join(_LOOKALIKES.get(ch, ch) for ch in raw)
    raw = re.sub(r',(\d{2})$', r'.\1', raw)
    value = _amount(raw, currency)
    return value[0] if value else None


def summary_components(source, heading, beside, currency):
    """``[(role, row id, row, value, value cell key)]``: the component lines printed in this page's card summary box.

    ``heading`` and ``beside`` are the printed headings of the summary box and
    of the box printed to its right (compared folded, box border marks
    ignored). A line belongs to the box when its first cell starts left of
    the box beside, within one fifth of the page below the heading, and is a
    component label as a whole; its value is the first cell after the label
    once the printed sign marks between them are passed. The value is
    ``(amount, confirmed)``: ``confirmed`` is False for a page reading the
    crop check left unconfirmed (marked with one trailing ``?``) and ``None``
    for a page reading that states an amount only once measured look-alike
    glyphs are read (``(None, None)`` when not even then).
    """
    page = source['page_number']
    measured = [(row, [(cell, _rectangle(cell, page)) for cell in row['cells']]) for row in source['rows']]
    found = {name: [box for _, cells in measured for cell, box in cells
                    if box and label(cell['expected_text'].strip(' |[]')) == label(name)]
             for name in (heading, beside)}
    if len(found[heading]) != 1 or len(found[beside]) != 1:
        return []
    top, right = found[heading][0], found[beside][0]
    if (top.page_width, top.page_height) != (right.page_width, right.page_height) or right.x0 <= top.x1:
        return []
    lines = []
    for row, cells in measured:
        located = sorted(((cell, box) for cell, box in cells if box
                          and (box.page_width, box.page_height) == (top.page_width, top.page_height)),
                         key=lambda pair: pair[1].x0)
        if not located or located[0][1].x1 > right.x0 or not top.y1 <= located[0][1].y0 <= top.y1 + top.page_height // 5:
            continue
        role = next((r for r in ROLES if label(located[0][0]['expected_text']) in INDEX[r]), None)
        # The value is the first cell after the label once the printed sign
        # marks between them are passed; the box beside repeats other values.
        after = [cell for cell, _ in located[1:] if cell['expected_text'].strip() not in ('-', '+', ':', '=', '|')]
        if role and after:
            row_id = f"{source['page_number']}:{source['table_index']}:{row['row_index']}"
            text = after[0]['expected_text']
            key = (source['table_index'], row['row_index'], after[0]['column_index'])
            lines.append((role, row_id, row, _amount(text, currency) or (_lookalike_reading(text, currency), None), key))
    return lines


# Summary labels of the charge sections whose lines a statement lists under
# their own heading. A summary that prints no line for a section does not
# total it; its lines are then left out of that side's comparison.
_CHARGE_LABELS = {'fee': ('FEES CHARGED', 'FEES'), 'interest': ('INTEREST CHARGED', 'INTEREST')}
_SECTIONS = {'Fees': 'fee', 'Interest Charged': 'interest'}


def _charge_section(row):
    fields = row['fields']
    return fields.get('charge_group') or _SECTIONS.get(fields.get('printed_section'))


def compared_lines(rows, components):
    """The card lines a printed summary totals: all, except a charge section it prints no line for.

    ``components`` are this period's summary lines (``summary_components``).
    """
    printed = {label(line[2]['cells'][0]['expected_text']) for line in components}
    unprinted = {scope for scope, names in _CHARGE_LABELS.items() if not any(label(n) in printed for n in names)}
    return [r for r in rows if _charge_section(r) not in unprinted]


def check_summary(rows, sources, currency, heading, beside):
    """``rows`` with each card summary disagreement turned into an unresolved row.

    Applied once per period to all of its rows. A period with no summary
    component line keeps its rows unchanged. Rows that are already
    unreadable (a payment without amount or direction) are left to their own
    issues: the totals are compared only with complete readings.
    """
    lines = [line for source in sources for line in summary_components(source, heading, beside, currency)]
    if not lines:
        return rows
    included = [r for r in rows if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]
    if any(r['kind'] == 'unresolved' or not str(r['fields'].get('amount_minor') or '').isdigit()
           or r['fields'].get('direction') not in ('credit', 'debit') for r in included):
        return rows
    totalled = compared_lines(included, lines)
    read = {direction: sum(int(r['fields']['amount_minor']) for r in totalled if r['fields']['direction'] == direction)
            for direction in ('credit', 'debit')}
    by_id = {r['id']: r for r in rows}
    held = []
    for role, direction, name in (('credit_component', 'credit', 'payments and credits'),
                                  ('debit_component', 'debit', 'purchases, advances, fees and interest')):
        members = [(row_id, row, value) for r, row_id, row, value, _ in lines if r == role]
        if not members:
            continue
        others = [value[0] for _, _, value in members if value[1] is True]
        doubtful = [(row_id, row, value) for row_id, row, value in members if value[1] is not True]
        if len(doubtful) <= 1 and sum(others) + sum(value[0] or 0 for _, _, value in doubtful) == read[direction] \
                and all(value[0] is not None for _, _, value in doubtful):
            # Agrees. A total the crop check did not confirm (or whose page
            # reading needs its measured look-alike glyphs read) agrees only
            # when it is the one such total of its side and states exactly
            # the amount the confirmed lines and the other totals fix. It is
            # a control here, never a ledger value.
            continue
        if doubtful:
            held.extend((row_id, row, f'Check the printed {name} in the account summary. An amount could not be '
                                      'read, so the card lines read for this cycle cannot be compared with it.')
                        for row_id, row, _ in doubtful)
        else:
            held.append((members[0][0], members[0][1], f'The printed {name} in the account summary differ from '
                         'the card lines read for this cycle. Compare the summary with the transaction lines before importing.'))
    for row_id, row, message in held:
        item = by_id.get(row_id)
        if item is None:
            continue
        item.update(kind='unresolved', excluded=False,
                    fields=dict(description=' '.join(c['expected_text'] for c in row['cells'])[:300]),
                    issues=[*item.get('issues', []), message])
    return rows


# The card summary boxes, as printed headings (summary box, box beside it).
# Data, not code: an issuer whose summary prints these headings is checked.
SUMMARY_BOXES = (('SUMMARY OF ACCOUNT ACTIVITY', 'PAYMENT INFORMATION'),)
# Card layouts whose periods are checked against their printed summary here
# (Citi and Capital One readers check their own summaries).
CHECKED_LAYOUTS = ('merrick-card', 'credit-one-card')


PAYMENT_SIGN_PINNED = 'pinned_by_printed_controls'


def pin_payment_direction(rows, sources, currency):
    """A card payment line whose minus no reader read takes the credit direction its period's controls fix.

    The issuer prints every payment with a minus; OCR can lose a detached one
    (the reader then holds the line, ``payment_sign_unread``). Exactly one
    such line in the period may be decided, and only when every other line
    is complete, both printed balances are read, the balance equation
    (previous + charges - credits = new) holds with the line as a credit and
    not as a charge, and, when the summary prints its payments and credits,
    they equal the credit lines with it. The line then keeps its printed
    amount, is recorded with ``direction_basis`` and loses its hold; anything
    else leaves it held. The printed payment wording, the two balances and the
    summary are the facts that agree; no sign is read from the image.
    """
    payments = [r for r in rows if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]
    unread = [r for r in payments if r['fields'].get('payment_sign_unread')]
    if len(unread) != 1:
        return rows
    line = unread[0]
    others = [r for r in payments if r is not line]
    if (len(line['issues']) != 1 or not str(line['fields'].get('amount_minor') or '').isdigit()
            or not line['fields'].get('date')
            or any(r['issues'] or not str(r['fields'].get('amount_minor') or '').isdigit()
                   or r['fields'].get('direction') not in ('credit', 'debit') for r in others)):
        return rows
    balances = {r['fields'].get('description'): r['fields'].get('balance') for r in rows if r['kind'] == 'balance'}
    try:
        opening, closing = int(balances['Opening Balance']), int(balances['Closing Balance'])
    except (KeyError, TypeError, ValueError):
        return rows
    amount = int(line['fields']['amount_minor'])
    charges = sum(int(r['fields']['amount_minor']) for r in others if r['fields']['direction'] == 'debit')
    credits = sum(int(r['fields']['amount_minor']) for r in others if r['fields']['direction'] == 'credit')
    if opening + charges - credits - amount != closing or opening + charges + amount - credits == closing:
        return rows
    printed = [value for heading, beside in SUMMARY_BOXES for s in sources
               for role, _, _, value, _ in summary_components(s, heading, beside, currency) if role == 'credit_component']
    if printed and (any(v is None or v[0] is None or v[1] is not True for v in printed)
                    or sum(v[0] for v in printed) != credits + amount):
        return rows
    line['fields'].update(direction='credit', direction_basis=PAYMENT_SIGN_PINNED)
    line['issues'] = []
    return rows


def check_card_period(layout, rows, sources, currency):
    """``rows`` of one card period: a payment sign fixed by its controls, then its summary checked."""
    if layout not in CHECKED_LAYOUTS:
        return rows
    rows = pin_payment_direction(rows, sources, currency)
    for heading, beside in SUMMARY_BOXES:
        rows = check_summary(rows, sources, currency, heading, beside)
    return rows
