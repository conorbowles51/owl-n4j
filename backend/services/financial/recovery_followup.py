"""One bounded repair of unresolved retained Financial work.

Batch membership alone does not establish financial content. Unknown historical
sources are not scheduled; explicit selections, admitted records, or a recognized
statement in retained geometry qualify. This never admits a new statement.
"""
from datetime import datetime, timezone
from collections import Counter
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry, IngestionLog
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryRun as Run, FinancialRecoveryItem as Item
from services.financial.file_scope import SCHEMA
from services.financial.file_visibility import financial_file_visibility
from services.financial.source_lineage import current_version


def _investigator(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        return None


def current_scope(session, versions):
    """Recognize an explicit reopening boundary, never a merely newer file.

    Process PDF afresh has a deterministic request tied to the exact removal.
    A restore has a case/file/revision audit entry. Removed ancestors stay in
    history; their rejected imports and retired batch items are not reopened.
    """
    current = current_version(versions)
    by_id = {str(version.id): version for version in versions}
    chain, seen, cursor = [], set(), current
    while cursor and str(cursor.id) not in seen:
        chain.append(cursor)
        seen.add(str(cursor.id))
        cursor = by_id.get((cursor.metadata_ or {}).get('statement_parent_evidence_id'))
    for version in chain:
        data = version.metadata_ or {}
        parent = by_id.get(data.get('statement_parent_evidence_id'))
        removal = (parent.metadata_ or {}).get('financial_import_removal') if parent else None
        actor = _investigator((data.get('statement_version_actor') or {}).get('user_id'))
        explicit_reset = bool(removal and data.get('statement_version_request') and data.get('statement_reset_revision') == removal.get('id') and version.sha256 == parent.sha256)
        if not removal or not removal.get('id') or not actor or (str(removal.get('restart_file_id')) != str(parent.id) and not explicit_reset):
            continue
        request = str(uuid5(NAMESPACE_URL,
            f"loupe-financial-reset:{current.case_id}:{removal['id']}:{current.sha256}"))
        if data.get('statement_version_request') != request and not explicit_reset:
            continue
        boundary = str(version.id)
        def descends(candidate):
            visited = set()
            while candidate and str(candidate.id) not in visited:
                if str(candidate.id) == boundary:
                    return True
                visited.add(str(candidate.id))
                candidate = by_id.get((candidate.metadata_ or {}).get('statement_parent_evidence_id'))
            return False
        return [candidate for candidate in versions if descends(candidate)], dict(
            kind='explicit_reset', boundary_file_id=boundary, request_id=data['statement_version_request'],
            removal_id=removal['id'], actor_id=actor)
    visibility = (current.metadata_ or {}).get('financial_file_visibility') or {}
    actor = _investigator((visibility.get('actor') or {}).get('user_id'))
    if visibility.get('removed') is False and visibility.get('revision') and actor:
        for extra in session.scalars(select(IngestionLog.extra).where(IngestionLog.case_id == current.case_id,
                IngestionLog.evidence_file_id == current.id)):
            if (extra.get('action') == 'financial_file_visibility' and extra.get('removed') is False
                    and extra.get('revision') == visibility['revision']
                    and _investigator((extra.get('actor') or {}).get('user_id')) == actor):
                # Restore deliberately retains earlier, separately hidden readings.
                restored = {str(value) for value in extra.get('reading_ids', [str(current.id)])}
                active = [candidate for candidate in versions if str(candidate.id) in restored and
                    financial_file_visibility(candidate)['financial_visibility_revision'] == visibility['revision']]
                if current in active:
                    return active, dict(kind='explicit_restore', boundary_file_id=str(current.id), revision=visibility['revision'])
    return versions, None


def repair_snapshot_available(session, case_id, release):
    run = session.scalar(select(Run).where(Run.case_id == case_id, Run.release == release))
    if run is None or run.status != 'complete' or session.scalar(select(Item.id).where(Item.run_id == run.id).limit(1)):
        return False
    log = session.scalar(select(IngestionLog.extra).where(IngestionLog.case_id == case_id,
        IngestionLog.extra['operation'].as_string() == 'statement_recovery_followup_snapshot',
        IngestionLog.extra['run_id'].as_string() == str(run.id)).limit(1))
    scope = (log or {}).get('scope') or {}
    return bool(scope.get('considered', 0) > 0 and scope.get('scheduled') == 0 and
        scope.get('protected') == scope['considered'])


def ignored_reading(file):
    dispositions = (file.metadata_ or {}).get('financial_duplicate_dispositions') or {}
    if not isinstance(dispositions, dict):
        return False
    return any(isinstance(value, dict) and value.get('status') == 'ignored' for value in dispositions.values())


def eligibility_context(session, case_id, cutoff, *, require_reopened=False):
    batches = list(session.scalars(select(Batch).where(Batch.case_id == case_id,
        Batch.created_at <= cutoff, Batch.status != 'removed').order_by(Batch.created_at.desc(), Batch.id)))
    protected = set(session.scalars(select(BatchItem.file_id).join(Batch, BatchItem.batch_id == Batch.id).where(
        Batch.case_id == case_id, Batch.status != 'removed',
        BatchItem.status.in_(('skipped', 'duplicate_ignored', 'removed')))))
    admitted = set(session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted')))
    return dict(batches=batches, protected=protected, admitted=admitted, excluded=Counter(), require_reopened=require_reopened)


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
    versions, reopened = current_scope(session, versions)
    identities = {file.id for file in versions}
    strings = {str(value) for value in identities}
    if (context['require_reopened'] and not reopened) or identities & context['protected'] or any(
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
    basis = ('existing_admitted_import' if identities & context['admitted'] else
        'explicit_selection' if selected else 'explicit_reopening' if reopened else None)
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
        followup_scope_ids=sorted(strings), reopening=reopened,
        failed_batches=failed, batch_retry_receipts=[])


def guard(session, item, file):
    if not item.result.get('followup'):
        return None
    identities = [UUID(value) for value in item.result['lineage_ids']]
    versions = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == file.case_id,
        EvidenceFile.id.in_(identities))))
    if item.result.get('reopening'):
        versions, reopened = current_scope(session, versions)
        if reopened != item.result['reopening'] or {str(version.id) for version in versions} != set(item.result['followup_scope_ids']):
            return 'review', 'The explicitly reopened reading changed after recovery was scheduled. Review its current history; saved work was kept.'
        identities = [version.id for version in versions]
    if any(ignored_reading(version) for version in versions):
        return 'kept', 'A statement in this reading was ignored as a duplicate. That decision and the other statement sections were retained.'
    if any(financial_file_visibility(version)['financial_removed'] or
           financial_file_visibility(version)['financial_imports_removed'] for version in versions):
        return 'kept', 'The investigator removed a source or its imports. Recovery left the retained history unchanged.'
    if session.scalar(select(BatchItem.id).join(Batch, BatchItem.batch_id == Batch.id).where(
            Batch.case_id == file.case_id, Batch.status != 'removed', BatchItem.file_id.in_(identities),
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
        BatchItem.file_id.in_([UUID(value) for value in item.result.get('followup_scope_ids', item.result['lineage_ids'])]),
        BatchItem.status.notin_(('imported', 'superseded_reading', 'removed')),
        BatchItem.review_request.is_not(None)).limit(1)))


def retry_failed_batches(session, item, file, *, prepared_readings=None):
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
        active_ids = item.result.get('followup_scope_ids', item.result['lineage_ids'])
        for key_name in ('source_id', 'file_id'):
            identifier = entry.get(key_name)
            if identifier and identifier not in active_ids and session.scalar(
                    select(EvidenceFile.id).where(EvidenceFile.id == UUID(identifier),
                        EvidenceFile.case_id == file.case_id)):
                return 'review', 'The batch points to a reading outside this verified source history or its explicitly reopened scope. Compare the original and retained reading before retrying; saved work was kept.'
        receipt = retry_file(session, case_id=file.case_id, batch_id=batch.id,
            source_id=UUID(reference['source_id']), _commit=False, _prepared_readings=prepared_readings)
        receipts.append({**reference, **receipt})
        item.result = {**item.result, 'batch_retry_receipts': receipts}
        # One reading/preparation handoff at a time across repeated batches.
        if receipt.get('queued') or receipt.get('action') == 'already_running':
            return 'waiting', receipt['message']
        return 'review', receipt['message']
    return None
