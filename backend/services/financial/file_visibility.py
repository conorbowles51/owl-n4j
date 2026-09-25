"""Case-wide financial file-list choices, retaining the underlying evidence."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.pdf_candidates import PdfMappingError


def _removal_guard(session, case_id, files):
    """Explain why membership cannot change; never stop or alter any work."""
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    ids = {file.id for file in files}
    identifiers = {str(value) for value in ids}
    if any(file.status == 'processing' for file in files):
        raise PdfMappingError('This file or one of its retained readings is still processing. Wait for the reading to finish before removing it from Financial. No job was stopped.', 409)
    from services.financial.active_recovery import active_recovery_file_ids
    if active_recovery_file_ids(session, case_id=case_id, file_ids=ids):
        raise PdfMappingError('Statement recovery for this file or one of its retained readings is queued or active. Wait for recovery to finish or pause it before removing this file from Financial. No recovery work was stopped.', 409)
    pending = session.scalar(select(Item.id).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id.in_(ids),
        Item.status == 'pending_import').limit(1))
    if pending:
        raise PdfMappingError('An import for this file is pending. Check its import result before removing it from Financial. No import was cancelled.', 409)
    now = datetime.now(timezone.utc)
    for batch in session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')):
        related = [entry for entry in batch.files or [] if any(entry.get(key) in identifiers
                   for key in ('source_id', 'file_id'))]
        if not related:
            continue
        lease = batch.lease_until
        if lease is not None and lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        # A live lease can belong to another file in the same batch. Finished
        # files with no pending import are safe to hide without stopping it.
        if (batch.worker_token and lease and lease > now and any(
                entry.get('status') not in ('checked', 'error') for entry in related)) or any(
                entry.get('status') in ('waiting', 'processing') for entry in related):
            raise PdfMappingError('This file is queued or being processed in a financial batch. Finish its preparation before removing it from Financial. The batch and its saved reviews are unchanged.', 409)
    sources = select(FinancialSourceDocument.id).where(FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.evidence_file_id.in_(ids))
    has_period = session.scalar(select(FinancialStatementPeriod.id).where(
        FinancialStatementPeriod.case_id == case_id,
        FinancialStatementPeriod.source_document_id.in_(sources)).limit(1))
    has_payment = session.scalar(select(FinancialTransaction.id).where(
        FinancialTransaction.case_id == case_id,
        FinancialTransaction.source_document_id.in_(sources)).limit(1))
    has_import = session.scalar(select(FinancialSourceDocument.id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.evidence_file_id.in_(ids),
        FinancialSourceDocument.status == 'admitted').limit(1))
    if has_period or has_payment or has_import:
        raise PdfMappingError('This file or one of its retained readings already has imported financial records. Open its transactions or statement review to correct them. Use Remove imports only if you intend to withdraw those saved records; removing a file from this list does not do that.', 409)


def financial_file_visibility(file):
    value = (getattr(file, "metadata_", None) or {}).get('financial_file_visibility') or {}
    return dict(financial_imports_removed=bool((getattr(file, 'metadata_', None) or {}).get('financial_import_removal')),
                financial_removed=value.get('removed') is True,
                financial_visibility_changed_at=value.get('changed_at'),
                financial_visibility_revision=value.get('revision', 'initial'))


def require_financial_file(file):
    if financial_file_visibility(file)['financial_removed']:
        raise PdfMappingError('This file was removed from Financial. Restore it from Removed files in Statements & accounts before reviewing or importing it.', 409)


def set_financial_file_visibility(session, *, case_id, evidence_file_id, removed, expected_revision, actor):
    # Use the same lock order as statement confirmation, so removal cannot race
    # an import and leave newly imported payments behind an absent file.
    session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    from services.financial.source_lineage import lineage_groups
    candidates = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)
        .order_by(EvidenceFile.id).execution_options(populate_existing=True)))
    family = next((versions for versions in lineage_groups(candidates).values()
                   if any(file.id == evidence_file_id for file in versions)), [])
    files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_([file.id for file in family])).order_by(EvidenceFile.id)
        .with_for_update().execution_options(populate_existing=True)))
    file = next((file for file in files if file.id == evidence_file_id), None)
    if file is None:
        raise PdfMappingError('File not found in this case.', 404)
    if not removed and (file.metadata_ or {}).get('financial_import_removal'):
        raise PdfMappingError('These imports were removed. Use Process PDF afresh to start without the old readings or reviews.', 409)
    current = financial_file_visibility(file)
    if current['financial_removed'] == removed:
        return dict(case_id=str(case_id), evidence_file_id=str(file.id), **current)
    if current['financial_visibility_revision'] != expected_revision:
        raise PdfMappingError('Another user changed this file. Refresh files before changing it again.', 409)
    if removed:
        _removal_guard(session, case_id, files)
    # Hide the explicit reading family together, otherwise an older reading
    # becomes the active card. Independent equal-hash uploads are not related.
    # Restore only members hidden by this action, keeping earlier removals intact.
    affected = [item for item in files if not financial_file_visibility(item)['financial_removed']] if removed else [
        item for item in files if financial_file_visibility(item)['financial_removed'] and
        financial_file_visibility(item)['financial_visibility_revision'] == expected_revision]
    if any((item.metadata_ or {}).get('financial_import_removal') for item in affected):
        raise PdfMappingError('These imports were removed. Use Process PDF afresh to start without the old readings or reviews.', 409)
    revision = str(uuid4())
    changed_at = datetime.now(timezone.utc).isoformat()
    actor_data = dict(user_id=str(actor.user_id), name=actor.name, email=actor.email)
    for item in affected:
        item.metadata_ = {**(item.metadata_ or {}), 'financial_file_visibility': dict(
            removed=removed, revision=revision, changed_at=changed_at, actor=actor_data)}
        session.add(IngestionLog(case_id=case_id, evidence_file_id=item.id,
            filename=item.original_filename, level='info',
            message='Removed file from Financial; original and saved reviews retained in Evidence.' if removed else 'Restored file to Financial with its saved reviews.',
            extra=dict(action='financial_file_visibility', removed=removed, revision=revision, actor=actor_data,
                requested_file_id=str(file.id), reading_ids=[str(version.id) for version in affected])))
    session.commit()
    return dict(case_id=str(case_id), evidence_file_id=str(file.id),
        **financial_file_visibility(file))
