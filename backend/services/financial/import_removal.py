"""Withdraw financial imports while retaining original evidence and cited history."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import FinancialSourceDocument as Source, FinancialTransaction as Transaction, FinancialStatementPeriod as Period
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial.pdf_candidates import PdfMappingError, _digest


def _selection(session, case_id, batch_ids, file_ids, lock=False):
    if not batch_ids and not file_ids:
        raise PdfMappingError('Select batches or statement files to remove.', 422)
    if lock:
        session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    # A worker may have changed metadata already loaded in this session. Both
    # preview and confirmation must fingerprint current persisted state.
    batches_query = select(Batch).where(Batch.case_id == case_id).order_by(Batch.id).execution_options(populate_existing=True)
    batches = list(session.scalars(batches_query.with_for_update().execution_options(populate_existing=True) if lock else batches_query))
    chosen = [b for b in batches if b.id in set(batch_ids) and b.status != 'removed']
    if {b.id for b in chosen} != set(batch_ids):
        raise PdfMappingError('A selected batch is unavailable in this case. Refresh the batch list.', 409)
    ids = set(file_ids)
    for batch in chosen:
        ids.update(UUID(f['file_id']) for f in batch.files)
        ids.update(UUID(f['source_id']) for f in batch.files)
    query = select(EvidenceFile).where(EvidenceFile.case_id == case_id).order_by(EvidenceFile.id).execution_options(populate_existing=True)
    files = list(session.scalars(query.with_for_update().execution_options(populate_existing=True) if lock else query))
    selected = [f for f in files if f.id in ids]
    if {f.id for f in selected} != ids or any(not f.original_filename.lower().endswith('.pdf') for f in selected):
        raise PdfMappingError('A selected PDF is unavailable in this case.', 404)
    # Include prior readings and duplicate copies: otherwise the next ingestion
    # could silently adopt the same old import through its content hash.
    hashes = {f.sha256 for f in selected}
    affected = [f for f in files if f.sha256 in hashes]
    affected_ids = {str(f.id) for f in affected}
    related = [b for b in batches if b.status != 'removed' and
               any(f['file_id'] in affected_ids or f['source_id'] in affected_ids for f in b.files)]
    source_query = select(Source).where(Source.case_id == case_id,
        Source.evidence_file_id.in_([f.id for f in affected])).order_by(Source.id).execution_options(populate_existing=True)
    sources = list(session.scalars(source_query.with_for_update().execution_options(populate_existing=True) if lock else source_query))
    row_query = select(Transaction).where(Transaction.case_id == case_id,
        Transaction.source_document_id.in_([s.id for s in sources])).order_by(Transaction.id).execution_options(populate_existing=True)
    rows = list(session.scalars(row_query.with_for_update().execution_options(populate_existing=True) if lock else row_query))
    return affected, related, sources, rows


def preview_removal(session, *, case_id, batch_ids=(), file_ids=(), lock=False):
    files, batches, sources, rows = _selection(session, case_id, batch_ids, file_ids, lock)
    now = datetime.now(timezone.utc)
    busy = [b for b in batches if b.worker_token and b.lease_until and
            (b.lease_until.replace(tzinfo=timezone.utc) if b.lease_until.tzinfo is None else b.lease_until) > now]
    processing = [f for f in files if f.status == 'processing']
    active = [s for s in sources if s.status == 'admitted']
    active_ids = {s.id for s in active}
    payments = sum(r.source_document_id in active_ids and r.ledger_status == 'admitted' and
                   r.superseded_by_id is None for r in rows)
    incomplete = sum(sum(not r.get('resolved_transaction_id') for r in
        (s.metadata_ or {}).get('statement_incomplete_records', [])) for s in active)
    periods = list(session.scalars(select(Period.id).where(Period.case_id == case_id,
        Period.source_document_id.in_(active_ids)).order_by(Period.id)))
    # Bind confirmation to exactly the state shown, including concurrent edits.
    revision = _digest(dict(case_id=str(case_id),
        files=[(str(f.id), f.status, f.metadata_) for f in files],
        batches=[(str(b.id), b.status, b.files, str(b.updated_at)) for b in batches],
        sources=[(str(s.id), s.status, s.metadata_) for s in sources],
        rows=[(str(r.id), r.ledger_status, str(r.superseded_by_id), r.metadata_) for r in rows]))
    representatives = {}
    for file in files:
        representatives.setdefault(file.sha256, file)
    affected_ids = {str(f.id) for f in files}
    archived = sum(all(f['file_id'] in affected_ids or f['source_id'] in affected_ids for f in b.files) for b in batches)
    return dict(case_id=str(case_id), revision=revision, archived_batch_count=archived, updated_batch_count=len(batches) - archived, file_count=len(representatives),
        reading_count=len(files), transaction_count=payments, incomplete_count=incomplete,
        statement_count=len(periods), batch_count=len(batches),
        files=[dict(id=str(f.id), filename=f.original_filename) for f in representatives.values()],
        batches=[dict(id=str(b.id), file_count=len(b.files)) for b in batches],
        can_remove=not busy and not processing,
        blocked_reason='Processing is still running for these files or a related batch. Wait for it to finish, then refresh this preview.' if busy or processing else None)


def remove_imports(session, *, case_id, batch_ids=(), file_ids=(), expected_revision, actor):
    preview = preview_removal(session, case_id=case_id, batch_ids=batch_ids, file_ids=file_ids, lock=True)
    if preview['revision'] != expected_revision:
        raise PdfMappingError('These imports changed since the preview. Refresh the preview before removing them.', 409)
    if not preview['can_remove']:
        raise PdfMappingError(preview['blocked_reason'], 409)
    files, batches, sources, rows = _selection(session, case_id, batch_ids, file_ids)
    removal = dict(id=str(uuid4()), at=datetime.now(timezone.utc).isoformat(),
        actor=dict(user_id=str(actor.user_id), name=actor.name, email=actor.email))
    representatives = {}
    for file in files:
        representatives.setdefault(file.sha256, file)
    for file in files:
        metadata = deepcopy(file.metadata_ or {})
        metadata['financial_import_removal'] = {**removal, 'restart_file_id': str(representatives[file.sha256].id)}
        metadata['financial_file_visibility'] = dict(removed=True, revision=removal['id'],
            changed_at=removal['at'], actor=removal['actor'])
        file.metadata_ = metadata
        session.add(IngestionLog(case_id=case_id, evidence_file_id=file.id, filename=file.original_filename,
            level='info', message='Removed financial imports and saved preparation from active Financial. Original PDF and cited history retained.',
            extra=dict(action='financial_import_removal', **removal)))
    for source in sources:
        source.metadata_ = {**(source.metadata_ or {}), 'financial_import_removal': {
            **removal, 'previous_status': source.status}}
        source.status = 'rejected'
    for row in rows:
        row.metadata_ = {**(row.metadata_ or {}), 'financial_import_removal': {
            **removal, 'previous_status': row.ledger_status, 'previous_quarantine_reason': row.quarantine_reason}}
        row.ledger_status = 'rejected'
        row.quarantine_reason = None
    affected_ids = {str(f.id) for f in files}
    for batch in batches:
        removed_files = [f for f in batch.files if f['file_id'] in affected_ids or f['source_id'] in affected_ids]
        remaining = [f for f in batch.files if f not in removed_files]
        batch.actor = {**(batch.actor or {}), 'financial_removal_history': [
            *(batch.actor or {}).get('financial_removal_history', []), {**removal, 'files': removed_files}]}
        if remaining:
            batch.files = remaining
        else:
            batch.status = 'removed'
        batch.worker_token, batch.lease_until = None, None
        # Unselected statements in a shared batch keep their saved reviews and
        # can still be imported. Removed items remain only as retained history.
        for item in session.scalars(select(Item).where(Item.batch_id == batch.id)):
            if str(item.file_id) in affected_ids:
                item.status = 'removed'
    session.commit()
    return {**preview, 'removal_id': removal['id'], 'removed': True,
        'restart_file_ids': [str(f.id) for f in representatives.values()]}
