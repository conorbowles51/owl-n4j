"""Bounded document-page nomination using investigator-selected column positions."""
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from services.financial.candidate_sources import read_candidate_source, suggest_candidate_rows
from services.financial.pdf_candidates import PdfMappingError
from services.financial.money import get_currency, MoneyError
MAX_SCAN_PAGES = 50
MAX_SUGGESTED_ROWS = 1000


def _under_amount_header(cell, header):
    """Require measured right-edge alignment in the same displayed PDF frame."""
    from services.financial.locators import Locator, LocatorCoherenceError
    try:
        value = Locator.from_json(cell.get('locator', {})).rectangle
        label = Locator.from_json(header.get('locator', {})).rectangle
    except (LocatorCoherenceError, TypeError, ValueError):
        return False
    return bool(value and label
        and (value.page_number, value.page_width, value.page_height)
            == (label.page_number, label.page_width, label.page_height)
        and value.y0 >= label.y1 and label.x0 <= value.x1 <= label.x1)


def propose_scan_columns(source, currency):
    """Rank source-backed co-occurrence; ties are explicitly unresolved."""
    from services.financial.source_dates import assess_date_text
    from services.financial.suspect_amounts import read_amount, TextOrigin
    dates, amounts, pairs = {}, {}, {}
    date_headers, amount_headers = set(), set()
    for row in source['rows'][:10]:
        for cell in row['cells']:
            label=' '.join(cell['expected_text'].lower().split())
            if label in ('date','transaction date','trans date','booking date','posting date','posted date','value date'):
                date_headers.add(cell['column_index'])
            if label in ('amount','debit','debits','credit','credits','money in','money out'):
                amount_headers.add(cell['column_index'])
    for row in source['rows']:
        possible_dates, possible_amounts = [], []
        for cell in row['cells']:
            text=cell['expected_text'];column=cell['column_index']
            if text not in dates:
                dates[text]=bool(assess_date_text(text,'unknown')['proposals'])
            if text not in amounts:
                try:
                    reading=read_amount(text,currency,TextOrigin.unknown).to_json()
                    amounts[text]='minor_units' in reading or bool(reading.get('proposals'))
                except MoneyError:
                    amounts[text]=False
            if dates[text]:possible_dates.append(column)
            if amounts[text]:possible_amounts.append(column)
        for d in possible_dates:
            for a in possible_amounts:
                if d!=a:pairs[(d,a)]=pairs.get((d,a),0)+1
    # Two separately labelled amount columns are not competing alternatives.
    # Require one coherent header row and consistent positions across repeats.
    split_headers=[]
    for header in source['rows'][:10]:
        labels={}
        for cell in header['cells']:
            label=' '.join(cell['expected_text'].lower().split())
            role=('debit' if label in ('debit','debits','money out') else
                  'credit' if label in ('credit','credits','money in') else
                  'date' if label in ('date','transaction date','trans date','booking date','posting date','posted date','value date') else None)
            if role:labels.setdefault(role,[]).append(cell)
        if all(len(labels.get(role,[]))==1 for role in ('date','debit','credit')):
            split_headers.append(labels)
    layouts={(h['date'][0]['column_index'],h['debit'][0]['column_index'],h['credit'][0]['column_index']) for h in split_headers}
    if len(layouts)==1:
        d,debit,credit=next(iter(layouts))
        if len({d,debit,credit})==3 and date_headers=={d} and amount_headers=={debit,credit} and any(pairs.get((d,a),0) for a in (debit,credit)):
            header=split_headers[0]
            return dict(date_column=d,amount_column=debit,additional_amount_columns=[credit],
                amount_headers=[header['debit'][0],header['credit'][0]],
                supporting_rows=sum(pairs.get((d,a),0) for a in (debit,credit)),header_support=3),None
    if len(layouts)>1:
        return None,'Separate money-in/out headers use conflicting positions. Inspect the page and choose positions manually.'
    ranked=sorted([dict(date_column=d,amount_column=a,supporting_rows=n,header_support=int(d in date_headers)+int(a in amount_headers)) for (d,a),n in pairs.items()],key=lambda p:(-p['supporting_rows'],-p['header_support'],p['date_column'],p['amount_column']))
    if not ranked:return None,'No date-and-amount column pair has source support.'
    first=ranked[0]
    if first['supporting_rows']<2 and first['header_support']<2:
        return None,'Only one row supports a layout and its column labels are not both recognised. Choose the positions manually.'
    if len(ranked)>1 and (ranked[1]['supporting_rows'],ranked[1]['header_support'])==(first['supporting_rows'],first['header_support']):
        return None,'Several date-and-amount column pairs have equal support. Inspect the page and choose the positions manually.'
    # Extracted column indices can shift when reference/description cells split.
    # Extend only one unambiguous winning layout, using a single measured Amount
    # header. Every supporting amount in both positions must align underneath it.
    generic_headers = [cell for row in source['rows'][:10] for cell in row['cells']
        if cell['expected_text'].strip().lower() == 'amount']
    if len(generic_headers) == 1:
        header = generic_headers[0]
        aligned = []
        for proposal in ranked:
            if proposal['date_column'] != first['date_column']:
                continue
            cells = [cell for row in source['rows']
                if any(c['column_index'] == first['date_column'] and dates.get(c['expected_text']) for c in row['cells'])
                for cell in row['cells'] if cell['column_index'] == proposal['amount_column'] and amounts.get(cell['expected_text'])]
            if cells and all(_under_amount_header(cell, header) for cell in cells):
                aligned.append(proposal['amount_column'])
        if first['amount_column'] in aligned and 1 < len(aligned) <= 8:
            first = {**first, 'additional_amount_columns': sorted(set(aligned) - {first['amount_column']}),
                'alignment_source': header,
                'supporting_rows': sum(pairs[(first['date_column'], a)] for a in aligned)}
    return first,None


_UNDATED_CHARGE_LABELS = frozenset((
    'interest charge on purchases', 'interest charge on cash advances',
    'interest charge on other balances', 'late payment fee', 'late fee',
    'annual fee', 'monthly maintenance fee', 'overdraft fee',
    'returned payment fee', 'cash advance fee', 'foreign transaction fee',
))


def suggest_undated_charges(source, currency):
    """Exact supported charge labels only; never infer timing or direction."""
    from services.financial.source_dates import assess_date_text
    from services.financial.suspect_amounts import read_amount, TextOrigin
    hints = []
    for row in source['rows']:
        labels = [c for c in row['cells'] if ' '.join(c['expected_text'].lower().split()).rstrip(':') in _UNDATED_CHARGE_LABELS]
        if len(labels) != 1:
            continue
        amounts = []
        for cell in row['cells']:
            if cell['column_index'] == labels[0]['column_index']:
                continue
            try:
                reading = read_amount(cell['expected_text'],currency,TextOrigin.unknown).to_json()
            except MoneyError:
                continue
            if 'minor_units' in reading or reading.get('proposals'):
                amounts.append(cell)
        # A decimal charge (for example 11.18) can also parse as a
        # month/day date. Do not discard a labelled charge merely because its
        # amount has that shape. A separate unambiguous date still excludes it;
        # overlapping interpretations stay unresolved for source review.
        amount_columns = {cell['column_index'] for cell in amounts}
        if not amounts or any(
            cell['column_index'] not in amount_columns
            and cell['column_index'] != labels[0]['column_index']
            and assess_date_text(cell['expected_text'], 'unknown')['proposals']
            for cell in row['cells']
        ):
            continue
        hints.append(dict(row_index=row['row_index'], label_source=labels[0], amount_sources=amounts,
            date_unknown=True, reason='Recognised charge label without an unambiguous source date. Review the amount, direction and statement scope; no date is inferred.' if len(amounts)==1 else
                'Recognised charge label without an unambiguous source date and several possible amount cells. Inspect the source; no amount or date is selected.'))
    return hints



def _transaction_section(source):
    """Use only an exact, uniquely bounded printed transaction section.

    This is a nomination scope, never a declaration that other rows are not
    transactions. Unsupported or repeated headings retain the whole-page scan.
    """
    import re
    def label(text):
        return ' '.join(text.lower().split())
    starts = [(row, cell) for row in source['rows'] for cell in row['cells']
              if label(cell['expected_text']) in ('transactions', 'transactions, payments and credits')]
    if len(starts) != 1:
        return source, None
    start_row, start_cell = starts[0]
    ends = [(row, cell) for row in source['rows'] for cell in row['cells']
            if row['row_index'] > start_row['row_index']
            and re.fullmatch(r'(?:20[0-9]{2} )?totals year-to-date', label(cell['expected_text']))]
    if len(ends) != 1:
        return source, None
    end_row, end_cell = ends[0]
    selected = [row for row in source['rows'] if start_row['row_index'] < row['row_index'] < end_row['row_index']]
    if not selected:
        return source, None
    return {**source, 'rows': selected}, dict(
        start_row=start_row['row_index'], end_row=end_row['row_index'],
        start_source=start_cell, end_source=end_cell,
        omitted_rows=len(source['rows']) - len(selected),
        limitation='Suggestions cover only rows between these exact printed headings. Other rows remain unchecked by this nomination scope; this does not establish complete extraction.')

def scan_candidate_pages(session, *, case_id, evidence_file_id, start_page, end_page, date_column, amount_column, currency, table_index=0, auto_columns=False):
    if type(auto_columns) is not bool or any(type(v) is not int for v in (start_page,end_page,table_index)) or start_page<1 or end_page<start_page or end_page-start_page+1>MAX_SCAN_PAGES:
        raise PdfMappingError('Choose an inclusive range of at most 50 PDF pages.',422)
    if table_index<0 or (not auto_columns and (any(type(v) is not int for v in (date_column,amount_column)) or min(date_column,amount_column)<0 or date_column==amount_column or max(date_column,amount_column)>63)):
        raise PdfMappingError('Choose distinct column positions between 1 and 64.',422)
    try:currency=get_currency(currency).code
    except MoneyError as exc:raise PdfMappingError(str(exc),422) from exc
    def version():
        return session.execute(select(EvidenceFile.sha256,EvidenceDocumentText.engine_job_id,EvidenceDocumentText.content_sha256).join(EvidenceDocumentText,
            EvidenceDocumentText.evidence_file_id==EvidenceFile.id).where(EvidenceFile.id==evidence_file_id,EvidenceFile.case_id==case_id)).first()
    before=version()
    if before is None:raise PdfMappingError('Prepared PDF not found in this case.',404)
    pages=[];total=0
    for page in range(start_page,end_page+1):
        try:
            source=read_candidate_source(session,case_id=case_id,evidence_file_id=evidence_file_id,page_number=page,table_index=table_index)
            nomination_source, section = _transaction_section(source) if auto_columns else (source, None)
            undated=suggest_undated_charges(nomination_source,currency)
            supplement=dict(undated_charges=undated,undated_checked_rows=len(nomination_source['rows']),source_section=section,source_revision=source['source_revision'],other_tables=max(0,source['table_count']-1))
            chosen,reason=propose_scan_columns(nomination_source,currency) if auto_columns else (dict(date_column=date_column,amount_column=amount_column),None)
            if chosen is None:
                pages.append(dict(page_number=page,checked=False,reason=reason,checked_rows=0,suggestions=[],**supplement))
                continue
            suggestions=[]
            for amount_position in [chosen['amount_column'],*chosen.get('additional_amount_columns',[])]:
                result=suggest_candidate_rows(session,case_id=case_id,evidence_file_id=evidence_file_id,page_number=page,table_index=table_index,
                    expected_revision=source['source_revision'],date_column=chosen['date_column'],amount_column=amount_position,currency=currency)
                header=next((h for h in chosen.get('amount_headers',[]) if h['column_index']==amount_position),None)
                for r in result['rows']:
                    if r['suggested'] and (not chosen.get('alignment_source') or _under_amount_header(r['amount_source'], chosen['alignment_source'])) and (section is None or section['start_row'] < r['row_index'] < section['end_row']):
                        item=dict(row_index=r['row_index'],date_source=r['date_source'],amount_source=r['amount_source'])
                        if header:item['amount_header_source']=header
                        suggestions.append(item)
            suggestions.sort(key=lambda r:(r['row_index'],r['amount_source']['column_index']))
        except PdfMappingError as exc:
            if exc.status_code==409:raise
            pages.append(dict(page_number=page,checked=False,reason=str(exc),checked_rows=0,suggestions=[]))
            continue
        total+=len(suggestions)
        if total>MAX_SUGGESTED_ROWS:raise PdfMappingError('More than 1,000 suggested rows. Narrow the page range; no partial scan was returned.',422)
        pages.append(dict(page_number=page,checked=True,reason=None,checked_rows=len(nomination_source['rows']) if section is not None else result['checked_rows'],suggestions=suggestions,chosen_columns=chosen,**supplement))
    undated_total=sum(len(p.get('undated_charges',[])) for p in pages)
    if undated_total>MAX_SUGGESTED_ROWS:raise PdfMappingError('More than1,000undated charge suggestions. Narrow the page range; no partial scan was returned.',422)
    if version()!=before:raise PdfMappingError('PDF preparation changed during the scan. Reload before reviewing suggestions.',409)
    return dict(case_id=str(case_id),evidence_file_id=str(evidence_file_id),start_page=start_page,end_page=end_page,table_index=table_index,
        date_column=None if auto_columns else date_column,amount_column=None if auto_columns else amount_column,auto_columns=auto_columns,currency=currency,pages=pages,suggested_rows=total,undated_charge_rows=undated_total,applied=False,
        limitation=('Per-page column proposals use co-occurring date/amount shapes and recognised labels; they do not establish column meaning or transaction status. Explicit separate debit/credit header columns are both checked and each original header is retained; labels are proposals, not verified account conventions. Ambiguous layouts remain unchecked. ' if auto_columns else '')+'Review suggestions under the selected column positions only. No rows are saved or admitted. Undated charge suggestions use a limited list of exact labels, separate from dated proposals; dates and directions remain unknown. Summary totals and APR figures are not nominated by this screen. Other undated transactions and unchecked pages can be missed. Open each page, inspect the original and explicitly choose readings; source revisions are rechecked on save.')
