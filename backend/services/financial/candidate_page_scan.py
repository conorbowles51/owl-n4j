"""Bounded document-page nomination using investigator-selected column positions."""
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from services.financial.candidate_sources import read_candidate_source, suggest_candidate_rows
from services.financial.pdf_candidates import PdfMappingError
from services.financial.money import get_currency, MoneyError
MAX_SCAN_PAGES = 50
MAX_SUGGESTED_ROWS = 1000


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
    ranked=sorted([dict(date_column=d,amount_column=a,supporting_rows=n,header_support=int(d in date_headers)+int(a in amount_headers)) for (d,a),n in pairs.items()],key=lambda p:(-p['supporting_rows'],-p['header_support'],p['date_column'],p['amount_column']))
    if not ranked:return None,'No date-and-amount column pair has source support.'
    first=ranked[0]
    if first['supporting_rows']<2 and first['header_support']<2:
        return None,'Only one row supports a layout and its column labels are not both recognised. Choose the positions manually.'
    if len(ranked)>1 and (ranked[1]['supporting_rows'],ranked[1]['header_support'])==(first['supporting_rows'],first['header_support']):
        return None,'Several date-and-amount column pairs have equal support. Inspect the page and choose the positions manually.'
    return first,None


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
            chosen,reason=propose_scan_columns(source,currency) if auto_columns else (dict(date_column=date_column,amount_column=amount_column),None)
            if chosen is None:
                pages.append(dict(page_number=page,checked=False,reason=reason,checked_rows=0,suggestions=[]))
                continue
            result=suggest_candidate_rows(session,case_id=case_id,evidence_file_id=evidence_file_id,page_number=page,table_index=table_index,
                expected_revision=source['source_revision'],date_column=chosen['date_column'],amount_column=chosen['amount_column'],currency=currency)
        except PdfMappingError as exc:
            if exc.status_code==409:raise
            pages.append(dict(page_number=page,checked=False,reason=str(exc),checked_rows=0,suggestions=[]))
            continue
        suggestions=[dict(row_index=r['row_index'],date_source=r['date_source'],amount_source=r['amount_source']) for r in result['rows'] if r['suggested']]
        total+=len(suggestions)
        if total>MAX_SUGGESTED_ROWS:raise PdfMappingError('More than 1,000 suggested rows. Narrow the page range; no partial scan was returned.',422)
        pages.append(dict(page_number=page,checked=True,reason=None,checked_rows=result['checked_rows'],source_revision=result['source_revision'],suggestions=suggestions,chosen_columns=chosen,other_tables=max(0,source['table_count']-1)))
    if version()!=before:raise PdfMappingError('PDF preparation changed during the scan. Reload before reviewing suggestions.',409)
    return dict(case_id=str(case_id),evidence_file_id=str(evidence_file_id),start_page=start_page,end_page=end_page,table_index=table_index,
        date_column=None if auto_columns else date_column,amount_column=None if auto_columns else amount_column,auto_columns=auto_columns,currency=currency,pages=pages,suggested_rows=total,applied=False,
        limitation=('Per-page column proposals use co-occurring date/amount shapes and recognised labels; they do not establish column meaning or transaction status. Ambiguous layouts remain unchecked. ' if auto_columns else '')+'Review suggestions under the selected column positions only. No rows are saved or admitted. Unchecked pages and undated transactions can be missed. Open each page, inspect the original and explicitly choose readings; source revisions are rechecked on save.')
