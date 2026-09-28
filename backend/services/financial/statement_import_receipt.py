"""Recover a committed statement receipt without repeating an import write."""
from sqlalchemy import select, func
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument as Source, FinancialTransaction as Row
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_import import _imported_account_id


def saved_receipt(session, *, case_id, evidence_file_id, request):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    signature = _digest(request.model_dump(mode='json'))
    matches = list(session.scalars(select(Source).where(Source.case_id == case_id,
        Source.evidence_file_id == evidence_file_id, Source.status == 'admitted',
        Source.sha256_at_ingestion == file.sha256,
        Source.metadata_['statement_import_request_sha256'].as_string() == signature)))
    matches = [source for source in matches if not (source.metadata_ or {}).get('financial_import_removal')]
    if len(matches) > 1:
        raise PdfMappingError('More than one saved receipt matches this review. Check the saved statements before continuing.', 409)
    result = None
    if matches:
        source = matches[0]
        metadata = source.metadata_ or {}
        count = session.scalar(select(func.count()).select_from(Row).where(
            Row.source_document_id == source.id, Row.ledger_status == 'admitted'))
        incomplete = sum(not r.get('resolved_transaction_id') for r in metadata.get('statement_incomplete_records', []))
        result = dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id),
            source_document_id=str(source.id), account_id=_imported_account_id(session, source.id),
            transaction_count=count, record_count=count + incomplete, incomplete_count=incomplete,
            issues=metadata.get('statement_import_issues', []), created=False, applied=True,
            account_closed_on=(metadata.get('statement_import_original', {}).get('metadata', {}).get('account_closure') or {}).get('date'))
    # Absence is deliberately not a failure verdict: the original request can
    # still be committing. The browser may poll but must not replay the write.
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), receipt=result)
