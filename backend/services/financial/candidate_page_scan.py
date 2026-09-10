"""Bounded document-page nomination using investigator-selected column positions."""
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from services.financial.candidate_sources import read_candidate_source, suggest_candidate_rows
from services.financial.pdf_candidates import PdfMappingError
from services.financial.money import get_currency, MoneyError
MAX_SCAN_PAGES = 50
MAX_SUGGESTED_ROWS = 1000


def scan_candidate_pages(session, *, case_id, evidence_file_id, start_page, end_page, date_column, amount_column, currency, table_index=0):
    if any(type(v) is not int for v in (start_page,end_page,date_column,amount_column,table_index)) or start_page<1 or end_page<start_page or end_page-start_page+1>MAX_SCAN_PAGES:
        raise PdfMappingError('Choose an inclusive range of at most 50 PDF pages.',422)
    if min(date_column,amount_column,table_index)<0 or date_column==amount_column or max(date_column,amount_column)>63:
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
            result=suggest_candidate_rows(session,case_id=case_id,evidence_file_id=evidence_file_id,page_number=page,table_index=table_index,
                expected_revision=source['source_revision'],date_column=date_column,amount_column=amount_column,currency=currency)
        except PdfMappingError as exc:
            if exc.status_code==409:raise
            pages.append(dict(page_number=page,checked=False,reason=str(exc),checked_rows=0,suggestions=[]))
            continue
        suggestions=[dict(row_index=r['row_index'],date_source=r['date_source'],amount_source=r['amount_source']) for r in result['rows'] if r['suggested']]
        total+=len(suggestions)
        if total>MAX_SUGGESTED_ROWS:raise PdfMappingError('More than 1,000 suggested rows. Narrow the page range; no partial scan was returned.',422)
        pages.append(dict(page_number=page,checked=True,reason=None,checked_rows=result['checked_rows'],source_revision=result['source_revision'],suggestions=suggestions))
    if version()!=before:raise PdfMappingError('PDF preparation changed during the scan. Reload before reviewing suggestions.',409)
    return dict(case_id=str(case_id),evidence_file_id=str(evidence_file_id),start_page=start_page,end_page=end_page,table_index=table_index,
        date_column=date_column,amount_column=amount_column,currency=currency,pages=pages,suggested_rows=total,applied=False,
        limitation='Review suggestions under the selected column positions only. No rows are saved or admitted. Unchecked pages and undated transactions can be missed. Open each page, inspect the original and explicitly choose readings; source revisions are rechecked on save.')
