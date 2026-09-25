"""One bounded repair of unresolved retained Financial work.

Batch membership alone does not establish financial content. Unknown historical
sources are not scheduled; explicit selections, admitted records, or a recognized
statement in retained geometry qualify. This never admits a new statement.
"""
from datetime import datetime, timezone
from collections import Counter
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryRun as Run, FinancialRecoveryItem as Item
from services.financial.file_scope import SCHEMA
from services.financial.file_visibility import financial_file_visibility


def ignored_reading(file):
    dispositions = (file.metadata_ or {}).get('financial_duplicate_dispositions') or {}
    if not isinstance(dispositions, dict):
        return False
    return any(isinstance(value, dict) and value.get('status') == 'ignored' for value in dispositions.values())


def eligibility_context(session, case_id, cutoff):
    batches = list(session.scalars(select(Batch).where(Batch.case_id == case_id,
        Batch.created_at <= cutoff, Batch.status != 'removed').order_by(Batch.created_at.desc(), Batch.id)))
    protected = set(session.scalars(select(BatchItem.file_id).join(Batch, BatchItem.batch_id == Batch.id).where(
        Batch.case_id == case_id, BatchItem.status.in_(('skipped', 'duplicate_ignored', 'removed')))))
    admitted = set(session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted')))
    return dict(batches=batches, protected=protected, admitted=admitted, excluded=Counter())


def recognized_readers(session, file):
    # The catalog uses printed statement identity/header structure. No filename,
    # extension, folder name or generic extracted-text presence is a classifier.
    from services.financial.statement_reading_quality import sources_from_tables
    from services.financial.statement_import_catalog import statement_catalog
    try:
        sources = []
        for geometry in session.scalars(select(EvidenceTableGeometry).where(
                EvidenceTableGeometry.evidence_file_id == file.id).order_by(EvidenceTableGeometry.page_number)):
            sources.extend(sources_from_tables(geometry.payload or []))
        return sorted({statement['layout_id'] for statement in statement_catalog(sources)['statements']
            if statement.get('layout_id')})
    except (KeyError, TypeError, ValueError):
        # Broken legacy geometry is unknown content, not proof of a statement.
        # Keep it in the unconfirmed count rather than blocking other sources.
        return []


def qualify(session, versions, previous, context):
    identities = {file.id for file in versions}
    strings = {str(value) for value in identities}
    if identities & context['protected'] or any(
            ignored_reading(file) or
            financial_file_visibility(file)['financial_removed'] or
            financial_file_visibility(file)['financial_imports_removed'] for file in versions):
        context['excluded']['protected'] += 1
        return None
    failed = [dict(batch_id=str(batch.id), source_id=entry['source_id'])
        for batch in context['batches'] for entry in batch.files or []
        if entry.get('status') == 'error' and
        (entry.get('source_id') in strings or entry.get('file_id') in strings)]
    if not failed and (previous is None or previous.status != 'review'):
        context['excluded']['no_unresolved_work'] += 1
        return None
    selected = any((file.metadata_ or {}).get('financial_workspace', {}).get('schema') == SCHEMA
        and (file.metadata_ or {}).get('financial_workspace', {}).get('selected_by') for file in versions)
    basis = 'existing_admitted_import' if identities & context['admitted'] else 'explicit_selection' if selected else None
    readers = []
    if basis is None:
        for file in versions:
            readers = recognized_readers(session, file)
            if readers:
                basis = 'recognized_statement_content'
                break
    if basis is None:
        context['excluded']['unconfirmed_content'] += 1
        return None
    return dict(followup=True, eligibility_basis=basis, recognized_readers=readers,
        failed_batches=failed, batch_retry_receipts=[])


def guard(session, item, file):
    if not item.result.get('followup'):
        return None
    identities = [UUID(value) for value in item.result['lineage_ids']]
    versions = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == file.case_id,
        EvidenceFile.id.in_(identities))))
    if any(ignored_reading(version) for version in versions):
        return 'kept', 'A statement in this reading was ignored as a duplicate. That decision and the other statement sections were retained.'
    if any(financial_file_visibility(version)['financial_removed'] or
           financial_file_visibility(version)['financial_imports_removed'] for version in versions):
        return 'kept', 'The investigator removed a source or its imports. Recovery left the retained history unchanged.'
    if session.scalar(select(BatchItem.id).join(Batch, BatchItem.batch_id == Batch.id).where(
            Batch.case_id == file.case_id, BatchItem.file_id.in_(identities),
            BatchItem.status.in_(('skipped', 'duplicate_ignored', 'removed'))).limit(1)):
        return 'kept', 'An investigator left a statement unimported, ignored it as a duplicate, or removed it. That decision was retained.'
    # A previous paused campaign is an investigator choice, even when this one
    # was snapshotted later. Pending units in it also retain their sole owner.
    prior = session.execute(select(Item.status, Run.status).join(Run, Item.run_id == Run.id).where(
        Run.case_id == file.case_id, Run.id != item.run_id, Item.file_id.in_(identities),
        Run.status.in_(('running', 'paused')))).all()
    if any(run == 'paused' or status in ('pending', 'waiting', 'reading') for status, run in prior):
        return 'waiting', 'Waiting for the earlier recovery or its pause to finish. Existing work is unchanged.'
    if session.scalar(select(EvidenceFile.id).where(EvidenceFile.case_id == file.case_id,
            EvidenceFile.id.in_(identities), EvidenceFile.status == 'processing').limit(1)):
        return 'waiting', 'Waiting for the existing reading or AI ingestion. It has not been interrupted.'
    for reference in item.result.get('failed_batches', []):
        batch = session.scalar(select(Batch).where(Batch.id == UUID(reference['batch_id']), Batch.case_id == file.case_id))
        if batch is None or batch.status == 'removed':
            return 'kept', 'The earlier batch was removed. Recovery retained that choice.'
        if batch.status in ('paused', 'pausing'):
            return 'waiting', 'Waiting for the existing processing batch to be resumed. Its pause is unchanged.'
        lease = batch.lease_until
        if lease and lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        if batch.worker_token and lease and lease > datetime.now(timezone.utc):
            return 'waiting', 'Waiting for the current processing unit to finish. It has not been interrupted.'
    return None


def pending_saved_work(session, item, file):
    if not item.result.get('followup'):
        return False
    return bool(session.scalar(select(BatchItem.id).join(Batch, BatchItem.batch_id == Batch.id).where(
        Batch.case_id == file.case_id, Batch.status != 'removed',
        BatchItem.file_id.in_([UUID(value) for value in item.result['lineage_ids']]),
        BatchItem.status.notin_(('imported', 'superseded_reading', 'removed')),
        BatchItem.review_request.is_not(None)).limit(1)))


def retry_failed_batches(session, item, file):
    """Hand terminal failures to the existing durable Retry operation once.

The caller holds the case lock and commits the batch receipts together with the
campaign item. On restart, a receipt is checked instead of replayed. A fresh
reading remains subject to the ordinary saved-work guards and later review.
"""
    if not item.result.get('followup'):
        return None
    from services.financial.import_batches import retry_file
    receipts = list(item.result.get('batch_retry_receipts', []))
    done = {(entry['batch_id'], entry['source_id']) for entry in receipts}
    for reference in item.result.get('failed_batches', []):
        batch = session.scalar(select(Batch).where(Batch.id == UUID(reference['batch_id']),
            Batch.case_id == file.case_id).with_for_update())
        entry = next((entry for entry in (batch.files or []) if entry.get('source_id') == reference['source_id']), None) if batch else None
        if entry is None:
            return 'review', 'The earlier batch no longer contains this source. Open its current Financial review; saved work was kept.'
        key = (reference['batch_id'], reference['source_id'])
        if key in done:
            if entry.get('status') in ('waiting', 'processing'):
                return 'waiting', 'The failed batch is preparing its retained statement review. Saved work is unchanged.'
            if entry.get('status') == 'error':
                return 'review', (entry.get('recovery') or {}).get('message') or entry.get('error') or 'The reading still needs review. No second automatic retry was started.'
            continue
        if entry.get('status') != 'error':
            continue  # An investigator already resolved or restarted this entry.
        # Never substitute an independently uploaded file for a broken version
        # reference, even if it has the same name or happens to be in this case.
        for key_name in ('source_id', 'file_id'):
            identifier = entry.get(key_name)
            if identifier and identifier not in item.result['lineage_ids'] and session.scalar(
                    select(EvidenceFile.id).where(EvidenceFile.id == UUID(identifier),
                        EvidenceFile.case_id == file.case_id)):
                return 'review', 'The batch points to a reading outside this verified source history. Compare the original and retained reading before retrying; saved work was kept.'
        receipt = retry_file(session, case_id=file.case_id, batch_id=batch.id,
            source_id=UUID(reference['source_id']), _commit=False)
        receipts.append({**reference, **receipt})
        item.result = {**item.result, 'batch_retry_receipts': receipts}
        # One reading/preparation handoff at a time across repeated batches.
        if receipt.get('queued') or receipt.get('action') == 'already_running':
            return 'waiting', receipt['message']
        return 'review', receipt['message']
    return None
