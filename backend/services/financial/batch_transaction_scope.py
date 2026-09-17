"""Resolve exactly the source documents imported by a case-scoped batch."""
from uuid import UUID
from sqlalchemy import select, func, or_
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from services.financial.pdf_candidates import PdfMappingError, _digest


def imported_batch_scope(session, *, case_id, batch_id):
    batch = session.scalar(select(FinancialImportBatch).where(
        FinancialImportBatch.id == batch_id, FinancialImportBatch.case_id == case_id))
    if batch is None:
        raise PdfMappingError('Financial processing batch not found in this case.', 404)
    items = list(session.scalars(select(FinancialImportBatchItem).where(
        FinancialImportBatchItem.batch_id == batch_id, FinancialImportBatchItem.status == 'imported')))
    file_ids = {i.file_id for i in items}
    try:
        receipt_ids = {UUID(i.summary['source_document_id']) for i in items if i.summary.get('source_document_id')}
    except (ValueError, TypeError) as exc:
        raise PdfMappingError('An imported statement reference is invalid. Open the batch to inspect its import history.', 409) from exc
    # Also support batches completed before receipts were retained on their
    # items. Match the exact file and period, never every source in that file.
    sources = list(session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id, or_(FinancialSourceDocument.evidence_file_id.in_(file_ids),
            FinancialSourceDocument.id.in_(receipt_ids))))) if file_ids else []
    by_id = {str(s.id): s for s in sources}
    by_period = {}
    for source in sources:
        if 'statement_import_statement_id' in (source.metadata_ or {}):
            key = (source.evidence_file_id, (source.metadata_ or {}).get('statement_import_statement_id') or '')
            by_period.setdefault(key, []).append(source)
    selected = set()
    for item in items:
        receipt_id = item.summary.get('source_document_id')
        if receipt_id:
            source = by_id.get(receipt_id)
            if source is None:
                raise PdfMappingError('An imported statement source is unavailable. Open the batch to inspect its import history.', 409)
            selected.add(receipt_id)
        else:
            matches = by_period.get((item.file_id, item.statement_key), [])
            if len(matches) != 1:
                raise PdfMappingError('This earlier batch does not identify one source for each imported statement. Open its statements individually to inspect their transactions.', 409)
            selected.add(str(matches[0].id))
    source_ids = sorted(selected)
    counts = session.execute(select(FinancialTransaction.account_id, func.count(),
        func.min(FinancialTransaction.ordering_date), func.max(FinancialTransaction.ordering_date))
        .where(FinancialTransaction.case_id == case_id,
               FinancialTransaction.source_document_id.in_([UUID(s) for s in source_ids]),
               FinancialTransaction.ledger_status == 'admitted')
        .group_by(FinancialTransaction.account_id)).all() if source_ids else []
    dates = [d for row in counts for d in row[2:] if d is not None]
    return dict(case_id=str(case_id), batch_id=str(batch_id),
        revision=_digest(dict(batch_id=str(batch_id), source_document_ids=source_ids)),
        source_document_ids=source_ids, statement_count=len(items),
        transaction_count=sum(row[1] for row in counts), account_ids=sorted(str(row[0]) for row in counts),
        start_date=min(dates).isoformat() if dates else None, end_date=max(dates).isoformat() if dates else None)
