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
from services.financial.model_work import origin_field


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
    listed = set()
    for batch in chosen:
        listed.update(UUID(f['file_id']) for f in batch.files)
        listed.update(UUID(f['source_id']) for f in batch.files)
    query = select(EvidenceFile).where(EvidenceFile.case_id == case_id).order_by(EvidenceFile.id).execution_options(populate_existing=True)
    files = list(session.scalars(query.with_for_update().execution_options(populate_existing=True) if lock else query))
    present = {f.id for f in files}
    # A file chosen by name must exist. A batch may still list PDFs deleted
    # from Evidence before deletes checked Financial (5 batches in one case,
    # 1 Nov): their records went with them, so the rest of the batch stays
    # removable and the missing entries are taken out with it.
    ids |= listed & present
    selected = [f for f in files if f.id in ids]
    if {f.id for f in selected} != ids or any(not f.original_filename.lower().endswith('.pdf') for f in selected):
        raise PdfMappingError('A selected PDF is unavailable in this case.', 404)
    gone = {str(i) for i in listed - present}
    # Include prior readings and duplicate copies: otherwise the next ingestion
    # could silently adopt the same old import through its content hash.
    hashes = {f.sha256 for f in selected}
    affected = [f for f in files if f.sha256 in hashes]
    affected_ids = {str(f.id) for f in affected}
    chosen_ids = {b.id for b in chosen}
    # PDFs already deleted are taken out only of the batches chosen; another batch listing them is not
    # pulled into this removal.
    related = [b for b in batches if b.status != 'removed' and (b.id in chosen_ids or
               any(f['file_id'] in affected_ids or f['source_id'] in affected_ids for f in b.files))]
    source_query = select(Source).where(Source.case_id == case_id,
        Source.evidence_file_id.in_([f.id for f in affected])).order_by(Source.id).execution_options(populate_existing=True)
    sources = list(session.scalars(source_query.with_for_update().execution_options(populate_existing=True) if lock else source_query))
    row_query = select(Transaction).where(Transaction.case_id == case_id,
        Transaction.source_document_id.in_([s.id for s in sources])).order_by(Transaction.id).execution_options(populate_existing=True)
    rows = list(session.scalars(row_query.with_for_update().execution_options(populate_existing=True) if lock else row_query))
    return affected, related, sources, rows, gone


def preview_removal(session, *, case_id, batch_ids=(), file_ids=(), lock=False):
    files, batches, sources, rows, gone = _selection(session, case_id, batch_ids, file_ids, lock)
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
    session.flush()
    from services.financial.brokerage_ledger import after_cash_rows_changed
    for source in sources:  # their trades and holdings leave the ledger with them (lx-brokerage)
        after_cash_rows_changed(session, source.id)
    affected_ids = {str(f.id) for f in files} | gone
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
    files, batches, sources, rows, gone = _selection(session, case_id, batch_ids, file_ids)
    removal = dict(id=str(uuid4()), at=datetime.now(timezone.utc).isoformat(),
        actor=dict(user_id=str(actor.user_id), name=actor.name, email=actor.email, **origin_field(actor)))
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
    session.flush()
    from services.financial.brokerage_ledger import after_cash_rows_changed
    for source in sources:  # their trades and holdings leave the ledger with them (lx-brokerage)
        after_cash_rows_changed(session, source.id)
    affected_ids = {str(f.id) for f in files} | gone
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


def financial_hold(session, *, case_id, file_ids):
    """What Financial still holds from these evidence files, or None when it holds nothing.

    A PDF is held while an admitted statement was read from it, or from a
    prepared reading an open import batch lists with it (either way round).
    Deleting it would take those payments out with no withdrawal recorded, or,
    for an original whose prepared reading is a separate file, leave them in the
    totals with no original to open. Remove imports releases the hold. A file
    only listed in a batch, with nothing imported, is not held (a batch whose
    PDFs were deleted stays removable). Non-PDF sources have no Remove imports
    path, so they are not held and their own statements go with them as before.
    """
    ids = {str(value) for value in file_ids}
    if not ids:
        return None
    pdfs = {str(i) for i, name in session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_([UUID(value) for value in ids])))
        if (name or '').lower().endswith('.pdf')}
    if not pdfs:
        return None
    linked = {value: {value} for value in pdfs}
    batches_of = {value: set() for value in pdfs}
    for batch in session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')):
        for entry in batch.files or []:
            keys = {entry.get('file_id'), entry.get('source_id')} - {None}
            for value in keys & pdfs:
                linked[value] |= keys
                batches_of[value].add(batch.id)
    readings = []
    for value in set().union(*linked.values()):
        try:
            readings.append(UUID(value))
        except ValueError:
            continue
    sources = list(session.scalars(select(Source).where(Source.case_id == case_id,
        Source.evidence_file_id.in_(readings), Source.status == 'admitted')))
    admitted = {str(s.evidence_file_id) for s in sources}
    held = sorted(value for value in pdfs if linked[value] & admitted)
    if not held:
        return None
    holding = [s for s in sources if any(str(s.evidence_file_id) in linked[value] for value in held)]
    payments = len(list(session.scalars(select(Transaction.id).where(Transaction.case_id == case_id,
        Transaction.source_document_id.in_([s.id for s in holding]), Transaction.ledger_status == 'admitted',
        Transaction.superseded_by_id.is_(None)))))
    names = sorted(session.scalars(select(EvidenceFile.original_filename).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_([UUID(value) for value in held]))))
    return dict(file_ids=held, filenames=names, batch_count=len(set().union(*(batches_of[v] for v in held))),
        statement_count=len(holding), payment_count=payments)


def financial_hold_message(hold):
    """Plain words for a refused evidence delete: what Financial holds and how to release it."""
    count = len(hold['file_ids'])
    shown = ', '.join(hold['filenames'][:3]) + (f' and {count - 3} more' if count > 3 else '')
    subject = f'{shown} is' if count == 1 else f'{count} of these files ({shown}) are'
    parts = []
    if hold['payment_count']:
        parts.append(f"{hold['payment_count']} payment{'s' if hold['payment_count'] != 1 else ''} from "
                     f"{'it' if count == 1 else 'them'} count in this case's totals")
    if hold['batch_count']:
        parts.append(f"{'it is' if count == 1 else 'they are'} in {hold['batch_count']} Financial import "
                     f"batch{'es' if hold['batch_count'] != 1 else ''}")
    return (f"{subject} still in Financial: {' and '.join(parts) or 'a statement was imported from it'}. "
            "Nothing was deleted. To delete, first remove the imports in Financial (Statements & accounts: select the "
            "file, then Review removal); the original stays in Evidence until you delete it here.")
