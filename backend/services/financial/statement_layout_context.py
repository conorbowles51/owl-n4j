"""Versioned, source-bound layout context; never a reviewed financial reading.

This deliberately narrow Capital One printed-card layout recognizer identifies
section/card references and possible full dates from the exact printed cycle.
It neither interprets credit-account signs nor creates account identities.
"""
import re
from datetime import date
from services.financial.source_dates import assess_date_text

_MONTHS = {name.lower(): index for index, names in enumerate((
    ('Jan', 'January'), ('Feb', 'February'), ('Mar', 'March'), ('Apr', 'April'),
    ('May',), ('Jun', 'June'), ('Jul', 'July'), ('Aug', 'August'),
    ('Sep', 'Sept', 'September'), ('Oct', 'October'), ('Nov', 'November'),
    ('Dec', 'December')), 1) for name in names}
_DATE = r'([A-Za-z]+)\.?\s+(\d{1,2}),\s+(20\d{2})'
_CYCLE = re.compile(r'^' + _DATE + r'\s+-\s+' + _DATE + r'\s*\|\s*(\d{1,2}) days in Billing Cycle$')
_SECTION = re.compile(r'^(.+?) #(\d{4}): (Payments, Credits and Adjustments|Transactions)$')


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


def statement_layout_context(rows):
    """Return None unless institution, unique cycle and printed card agree."""
    flat = [(r['row_index'], c) for r in rows for c in r['cells']]
    marks = [(i,c) for i,c in flat if c['expected_text'].strip() in (
        'Visit www.capitalone.com to see detailed transactions.',
        'Visit capitalone.com to see detailed transactions.')]
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
    cards = [(i,c) for i,c in flat if re.fullmatch(
        r'(?:Platinum MasterCard Account Ending in|Platinum Mastercard ending in|Platinum Card ending in|Platinum Card \| Platinum Mastercard ending in) \d{4}',
        c['expected_text'].strip())]
    if len(marks)!=1 or len(cycles)!=1 or len(cards)!=1:
        return None
    cycle_row, cycle_cell, (start,end), count_cell = cycles[0]
    def citation(row, cell):
        return dict(row_index=row, **cell)
    context=[];section=None;columns=None;header_row=None;header_cells=None
    for row in rows:
        if row['row_index'] <= max(cycle_row, marks[0][0], cards[0][0]):
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
        by_column={c['column_index']:c for c in cells}
        if len(by_column)!=len(cells) or not all(c in by_column for c in columns.values()):
            continue
        date_label='Date' if 'Date' in columns else 'Trans Date'
        date_cell=by_column[columns[date_label]]
        posting_cell=by_column[columns['Post Date']] if 'Post Date' in columns else None
        reading, possible = _dates_within(date_cell['expected_text'],start,end)
        if not reading['proposals']:
            continue
        section_row, section_cell, match = section
        context.append(dict(row_index=row['row_index'],card_ending=match[2],
            printed_section=match[3],section_source=citation(section_row,section_cell),
            date_source=citation(row['row_index'],date_cell),date_proposals=possible,
            date_label=date_label,date_header_source=citation(header_row,header_cells[date_label]),
            posting_date_source=citation(row['row_index'],posting_cell) if posting_cell else None,
            posting_date_proposals=_dates_within(posting_cell['expected_text'],start,end)[1] if posting_cell else [],
            posting_date_header_source=citation(header_row,header_cells['Post Date']) if posting_cell else None,
            description_source=citation(row['row_index'],by_column[columns['Description']]),
            amount_source=citation(row['row_index'],by_column[columns['Amount']]),
            direction=None,requires_source_review=True))
    return dict(layout_id='capital-one-platinum-card-sections',version=1,
        institution_source=citation(*marks[0]),printed_card_source=citation(*cards[0]),
        cycle_source=citation(cycle_row,cycle_cell),
        cycle_count_source=citation(cycle_row,count_cell) if count_cell else None,start_date=start.isoformat(),end_date=end.isoformat(),
        rows=context,applied=False,
        limitation='Printed section/card-ending context and possible dates only. A four-digit ending does not establish account identity. Date proposals assume the transaction belongs to the printed cycle; out-of-cycle dates remain unresolved. Amount, currency and credit-account direction require review. No fields are filled or transactions admitted.')
