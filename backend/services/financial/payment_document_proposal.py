"""Read labelled wire-report details without creating an account or payment.

The original cells remain separate from suggested values. Missing labels and
redacted or damaged values are not reconstructed from nearby party references.
"""
import re
from datetime import date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_proposal import exact_amount

SCHEMA = 'loupe.financial.payment_document/1'
VERSION = 'wells-fargo-wire-review-v1'
_FIELDS = (
    ('wire_amount', 'Wire amount', 'Wire Amount:', 'amount'),
    ('value_date', 'Value date', 'Value Date:', 'date'),
    ('sending_party', 'Sending party name and address', 'Sending Party Name and Address:', 'text'),
    ('receiving_party', 'Receiving party name and address', 'Receiving Party Name and Address:', 'text'),
    ('beneficiary', 'Beneficiary name and address', 'Beneficiary Name and Address:', 'text'),
    ('transaction_reference', 'Transaction reference', 'Transaction Reference Number:', 'text'),
    ('completed_at', 'Completed timestamp', 'Completed Timestamp:', 'text'),
    ('instructed_amount', 'Instructed currency and amount', 'Instructed Currency/Amount:', 'text'),
    ('usd_equivalent', 'USD equivalent amount', 'USD Equivalent Amount:', 'amount'),
)


def _text(cell):
    return cell['expected_text'].strip()


def _position(cell):
    locator = cell.get('locator') or {}
    rect = locator.get('rect')
    size = locator.get('page_size')
    if (not isinstance(rect, list) or len(rect) != 4 or not isinstance(size, list)
            or len(size) != 2 or not all(type(v) is int for v in rect+size)
            or not 0 <= rect[0] < rect[2] <= size[0] or not 0 <= rect[1] < rect[3] <= size[1]):
        return None
    return rect, size


def _block(source, label):
    matches = [(i,c) for i,r in enumerate(source['rows']) for c in r['cells'] if _text(c) == label]
    if len(matches) != 1:
        return [], 'The printed label could not be identified uniquely. Check this detail in the PDF.'
    index, heading = matches[0]
    position = _position(heading)
    if position is None:
        return [], 'The position of this label could not be read. Check this detail in the PDF.'
    rect, size = position
    right = rect[0] >= size[0] / 2
    values = []
    for row in source['rows'][index+1:]:
        for cell in row['cells']:
            p = _position(cell)
            if p is None:
                return [], 'This field contains text without a reliable page position. Check it in the PDF.'
            box, dimensions = p
            if dimensions != size:
                return [], 'The field positions disagree. Check this detail in the PDF.'
            if (box[0] >= size[0]/2) != right:
                continue
            value = _text(cell)
            if value.endswith(':') or value.startswith(('Page:', 'Note:', 'Text:')):
                return values, ''
            # A full-width footer is not part of either labelled column.
            if box[0] < size[0]/2 < box[2]:
                return values, ''
            values.append(cell)
            if len(values) > 8:
                return [], 'The end of this field is unclear. Check this detail in the PDF.'
    return values, ''


def _date(value):
    match = re.fullmatch(r'(\d{2})/(\d{2})/(20\d{2})', value)
    if not match:
        return ''
    try:
        return date(int(match[3]), int(match[1]), int(match[2])).isoformat()
    except ValueError:
        return ''


def _unavailable(value):
    return (not value or re.fullmatch(r'N/?[AI]A?', value, re.I) is not None or
            re.search(r'[•█]{2,}|[xX]{3,}|\bredacted\b', value, re.I) is not None)


def propose_payment_document(sources):
    """Return None for other layouts. Identified but unsupported reports stop here."""
    titles = [(s,c) for s in sources for r in s['rows'] for c in r['cells']
              if _text(c) == 'Wire Transfer Detail Report'
              and (_position(c) is None or _position(c)[0][1] < _position(c)[1][1] * .15)]
    if not titles:
        return None
    empty = dict(schema=SCHEMA, version=VERSION, kind='wire_report', fields=[],
                 page_numbers=sorted({s['page_number'] for s in sources}), supported=False,
                 issues=[], creates_transactions=False)
    if len(titles) != 1 or len(sources) != 1:
        return dict(empty, issues=['This file contains more than one report or layout. Review each wire report as a separate PDF.'])
    source, title = titles[0]
    cells = [c for r in source['rows'] for c in r['cells']]
    if not any(_text(c) == 'WELLS FARGO BANK, N.A.' for c in cells) or _position(title) is None:
        return dict(empty, issues=['This wire-report layout is not supported yet. Open its original PDF to check the details.'])
    fields = []
    for key, label, printed_label, kind in _FIELDS:
        values, issue = _block(source, printed_label)
        raw = '\n'.join(_text(c) for c in values)
        value = raw
        issues = [issue] if issue else []
        if _unavailable(raw):
            value = ''
            issues.append('This detail is blank, unavailable or redacted in the reading. Leave it empty if the original does not show it.')
        elif kind == 'date':
            value = _date(raw)
            if not value:
                issues.append('The date could not be read. Check the original date in the PDF.')
        elif kind == 'amount':
            try:
                # This validates the decimal shape only. It does not identify
                # the wire currency from an equivalent-amount heading.
                if int(exact_amount(raw, 'USD')) < 0:
                    raise ValueError('negative')
            except ValueError:
                value = ''
                issues.append('The amount could not be read. Check every digit and separator in the PDF.')
        elif key == 'completed_at' and raw:
            timestamp = re.fullmatch(r'(\d{2}/\d{2}/20\d{2}) (\d{1,2}):(\d{2}) (AM|PM) ([A-Z]{2,5})', raw)
            if not timestamp or not _date(timestamp[1]) or not 1 <= int(timestamp[2]) <= 12 or int(timestamp[3]) > 59:
                value = ''
                issues.append('The completed timestamp could not be read. Check its date, time and time zone in the PDF.')
        fields.append(dict(key=key, label=label, input_type=kind, raw=raw, value=value,
                           printed_label=printed_label, source_cells=values, issues=issues))
    instructed = next(f for f in fields if f['key'] == 'instructed_amount')
    match = re.fullmatch(r'([A-Z]{3})\s*/\s*(.+)', instructed['raw'])
    currency = ''
    if match:
        from services.financial.money import get_currency, MoneyError
        try:
            get_currency(match[1])
            instructed_minor = exact_amount(match[2], match[1])
            wire = next(f for f in fields if f['key'] == 'wire_amount')
            equivalent = next(f for f in fields if f['key'] == 'usd_equivalent')
            # Only three agreeing USD readings establish this report's wire
            # currency. An instructed foreign amount may be before conversion.
            if (match[1] == 'USD' and instructed_minor == exact_amount(wire['value'], 'USD')
                    == exact_amount(equivalent['value'], 'USD')):
                currency = 'USD'
        except (MoneyError, ValueError):
            pass
    fields.insert(1, dict(key='currency', label='Wire currency', input_type='currency',
        printed_label='Instructed Currency/Amount:', raw=instructed['raw'], value=currency,
        source_cells=instructed['source_cells'],
        issues=[] if currency else ['Choose the wire currency after checking the PDF. A USD equivalent amount does not identify the original currency.']))
    return dict(empty, supported=True, fields=fields,
                issues=['Save the checked details as a finding, or link them to a payment already in this case. Saving this review does not add a payment to account totals.'],
                source_revision=_digest(dict(version=VERSION, sources=sources)))
