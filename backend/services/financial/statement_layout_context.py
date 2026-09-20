"""Versioned, source-bound layout context; never a reviewed financial reading.

This deliberately narrow Capital One printed-card layout recognizer identifies
section/card references and possible full dates from the exact printed cycle.
It neither interprets credit-account signs nor creates account identities.
"""
import re
from datetime import date, timedelta
from services.financial.source_dates import assess_date_text
from services.financial.card_table_columns import card_row_columns, has_unmapped_card_amount

_MONTHS = {name.lower(): index for index, names in enumerate((
    ('Jan', 'January'), ('Feb', 'February'), ('Mar', 'March'), ('Apr', 'April'),
    ('May',), ('Jun', 'June'), ('Jul', 'July'), ('Aug', 'August'),
    ('Sep', 'Sept', 'September'), ('Oct', 'October'), ('Nov', 'November'),
    ('Dec', 'December')), 1) for name in names}
_DATE = r'([A-Za-z]+)\.?\s+(\d{1,2}),\s+(20\d{2})'
_CYCLE = re.compile(r'^' + _DATE + r'\s+-\s+' + _DATE + r'\s*\|\s*(\d{1,2}) days in Billing Cycle$')
_SECTION = re.compile(r'^(.+?) #(\d{4}): (Payments, Credits and Adjustments|Transactions)$')
CAPITAL_ONE_CARD_HEADING = re.compile(
    r'(?:Platinum MasterCard Account Ending in|Platinum Mastercard ending in|Platinum Card ending in|'
    r'World Elite Mastercard Account Ending in|World Elite MasterCard Account Ending in|'
    r'Quicksilver Credit Card \| World Elite Mastercard ending in|'
    r'(?:Platinum Card|Secured Card|Platinum Secured Card) \| Platinum Mastercard ending in) (\d{4})')


def _cycle(text):
    match = _CYCLE.fullmatch(text)
    if not match:
        return None
    try:
        a, b = [date(int(match[i+2]), _MONTHS[match[i].lower()], int(match[i+1])) for i in (1,4)]
    except (ValueError, KeyError):
        return None
    days = (b-a).days
    if not 0 <= days <= 62 or int(match[7]) != days + 1:
        return None
    return a, b


def _dates_within(text, start, end):
    reading=assess_date_text(text,'unknown')
    possible=set()
    for proposal in reading['proposals']:
        if 'iso_date' in proposal:
            value=date.fromisoformat(proposal['iso_date'])
            if start<=value<=end:possible.add(value.isoformat())
        elif 'month' in proposal and 'day' in proposal:
            for year in range(start.year,end.year+1):
                try:value=date(year,proposal['month'],proposal['day'])
                except ValueError:continue
                if start<=value<=end:possible.add(value.isoformat())
    return reading, sorted(possible)


def card_row_dates(text, posting_text, start, end):
    """Keep both printed dates; a valid posting can anchor a recent purchase.

    A purchase shortly before the cycle can post inside it. Resolve its printed
    month/day against that posting date, at most 31 days earlier. More distant,
    invalid, ambiguous or reversed dates still need review.
    """
    reading, possible = _dates_within(text, start, end)
    postings = _dates_within(posting_text, start, end)[1] if posting_text else []
    basis = 'printed_cycle'
    if len(postings) == 1:
        posted = date.fromisoformat(postings[0])
        if possible:
            possible = [value for value in possible if value <= posted.isoformat()]
        else:
            possible = _dates_within(text, posted - timedelta(days=31), min(start - timedelta(days=1), posted))[1]
            if possible:
                basis = 'printed_posting_date'
    return reading, possible, postings, basis


def statement_layout_context(rows, *, continuation_statement=None):
    """Return None unless institution, unique cycle and printed card agree."""
    flat = [(r['row_index'], c) for r in rows for c in r['cells']]
    marks = [(i,c) for i,c in flat if c['expected_text'].strip() in (
        'Visit www.capitalone.com to see detailed transactions.',
        'Visit capitalone.com to see detailed transactions.')]
    if continuation_statement is not None and marks:
        return None  # This fallback only handles the verified continuation layout.
    cycles = []
    for row in rows:
        cells = row['cells']
        for index, cell in enumerate(cells):
            reading = _cycle(cell['expected_text'].strip())
            count_source = None
            if reading is None and index+1 < len(cells):
                following = cells[index+1]
                if following['column_index'] == cell['column_index']+1:
                    reading = _cycle(cell['expected_text'].strip()+' '+following['expected_text'].strip())
                    if reading: count_source = following
            if reading:
                cycles.append((row['row_index'],cell,reading,count_source))
    cards = [(i,c) for i,c in flat if CAPITAL_ONE_CARD_HEADING.fullmatch(c['expected_text'].strip())]
    if len(cycles)!=1 or len(cards)!=1:
        return None
    cycle_row, cycle_cell, (start,end), count_cell = cycles[0]
    continuation = None
    if not marks and continuation_statement:
        headings = [(i, c) for i, c in flat if c['expected_text'].strip() == 'Transactions (Continued)']
        totals = [(i, c, match) for i, c in flat if (match := re.fullmatch(r'(.+?) #(\d{4}): Total (Transactions)', c['expected_text'].strip()))]
        card = CAPITAL_ONE_CARD_HEADING.fullmatch(cards[0][1]['expected_text'].strip())[1]
        if (len(headings) == len(totals) == 1 and headings[0][0] < totals[0][0]
                and totals[0][2][2] == card == continuation_statement.get('account_reference', '')[-4:]
                and continuation_statement.get('layout_id') == 'capital-one-card'
                and (start.isoformat(), end.isoformat()) == (continuation_statement.get('period_start'), continuation_statement.get('period_end'))):
            continuation = (headings[0], totals[0])
    if len(marks) != 1 and not continuation:
        return None
    def citation(row, cell):
        return dict(row_index=row, **cell)
    context=[];unresolved=[];section=continuation[1] if continuation else None;columns=None;header_row=None;header_cells=None
    section_start = continuation[0][0] if continuation else marks[0][0]
    for row in rows:
        if row['row_index'] <= max(cycle_row, section_start, cards[0][0]):
            continue
        cells=row['cells'];labels=[_SECTION.fullmatch(c['expected_text'].strip()) for c in cells]
        sections=[(c,m) for c,m in zip(cells,labels) if m]
        if sections:
            section = (row['row_index'], *sections[0]) if len(sections)==1 else None
            columns=None
            continue
        if any(re.search(r'(?:^|: )Total\b',c['expected_text'].strip(),re.IGNORECASE) or c['expected_text'].strip() in ('Fees','Interest Charged','Totals Year-to-Date') for c in cells):
            section=None;columns=None
            continue
        if section is None:
            continue
        header_options = [('Date','Description','Amount'),('Trans Date','Post Date','Description','Amount')]
        matched_headers = []
        for names in header_options:
            labels = {label:[c for c in cells if c['expected_text'].strip()==label] for label in names}
            if all(len(v)==1 for v in labels.values()):
                matched_headers.append({label:values[0] for label,values in labels.items()})
        if len(matched_headers)==1:
            header_cells=matched_headers[0];header_row=row['row_index']
            columns={label:cell['column_index'] for label,cell in header_cells.items()}
            continue
        if len(matched_headers)>1:
            columns=None
            continue
        if columns is None:
            continue
        mapped = card_row_columns(cells, header_cells)
        if mapped is None:
            if has_unmapped_card_amount(cells, header_cells):
                unresolved.append(row['row_index'])
            continue
        mapped_columns, descriptions = mapped
        date_label='Date' if 'Date' in columns else 'Trans Date'
        date_cell=mapped_columns[date_label]
        posting_cell=mapped_columns.get('Post Date')
        reading, possible, postings, basis = card_row_dates(date_cell['expected_text'],
            posting_cell['expected_text'] if posting_cell else None, start, end)
        # Printed columns and the account section can identify a payment even
        # when OCR loses its date. Keep its other fields and flag the date.
        if not reading['proposals'] and not (mapped_columns['Amount']['expected_text'].strip()
                and any(cell['expected_text'].strip() for cell in descriptions)):
            continue
        section_row, section_cell, match = section
        context.append(dict(row_index=row['row_index'],card_ending=match[2],
            printed_section=match[3],section_source=citation(section_row,section_cell),
            date_source=citation(row['row_index'],date_cell),date_proposals=possible,date_basis=basis,
            date_label=date_label,date_header_source=citation(header_row,header_cells[date_label]),
            posting_date_source=citation(row['row_index'],posting_cell) if posting_cell else None,
            posting_date_proposals=postings,
            posting_date_header_source=citation(header_row,header_cells['Post Date']) if posting_cell else None,
            description_source=citation(row['row_index'],mapped_columns['Description']),
            description_sources=[citation(row['row_index'],cell) for cell in descriptions],
            amount_source=citation(row['row_index'],mapped_columns['Amount']),
            direction=None,requires_source_review=True))
    return dict(layout_id='capital-one-platinum-card-sections',version=1,
        institution_source=citation(*(cards[0] if continuation else marks[0])),printed_card_source=citation(*cards[0]),
        cycle_source=citation(cycle_row,cycle_cell),
        cycle_count_source=citation(cycle_row,count_cell) if count_cell else None,start_date=start.isoformat(),end_date=end.isoformat(),
        rows=context,unresolved_rows=unresolved,applied=False,
        limitation='Printed sections and possible dates only. A transaction just before this cycle can use its separately printed posting date to identify the year, up to 31 days earlier. Both dates and all source cells are retained. A four-digit ending is a partial account reference. No transactions are imported by this layout view.')
