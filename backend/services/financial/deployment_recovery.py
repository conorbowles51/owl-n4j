"""One retained snapshot per release, resumable per-file recovery.

This worker never retries the team's AI jobs or replaces an imported ledger.
It revisits the current statement reader against retained evidence, queues a
separate reading when needed, and appends only provably missing payments.
"""
import asyncio
import hashlib
import logging
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID, NAMESPACE_URL, uuid5
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_recovery import FinancialRecoveryRelease as Release, FinancialRecoveryRun as Run, FinancialRecoveryItem as Item
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from services.financial.decisions import Actor
from services.financial.file_scope import financial_file_ids
from services.financial.file_visibility import financial_file_visibility
from services.financial.source_lineage import lineage_groups, current_version
from services.financial.pdf_candidates import PdfMappingError
from services.financial.recovery_campaigns import CAMPAIGNS, INITIAL_RELEASE, manifest, source_reader_evidence

RELEASE = INITIAL_RELEASE
ACTOR = Actor(name='Loupe automatic statement recovery', email='statement-recovery@system.local')
PENDING = ('pending', 'waiting', 'reading')
log = logging.getLogger(__name__)


def activate(session, release_id=RELEASE):
    release = session.get(Release, release_id)
    if release:
        return release.cutoff
    release = Release(release=release_id, cutoff=datetime.now(timezone.utc))
    session.add(release)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    return session.get(Release, release_id).cutoff


def snapshot_case(session, case_id, cutoff, campaign=None):
    campaign = campaign or manifest(RELEASE)
    if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update(skip_locked=True)) is None:
        return False
    run_id = uuid5(NAMESPACE_URL, campaign.release + ':' + str(case_id))
    if session.get(Run, run_id):
        return True
    from services.financial import recovery_followup
    if campaign.repair_of and not recovery_followup.repair_snapshot_available(session, case_id, campaign.repair_of):
        return True
    ids = financial_file_ids(session, case_id=case_id)
    files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_(ids), EvidenceFile.created_at <= cutoff))) if ids else []
    if not files and campaign.initial_snapshot:
        return True
    versions_by_root = lineage_groups(files)
    selected = []
    followup = recovery_followup.eligibility_context(session, case_id, cutoff,
        require_reopened=bool(campaign.repair_of)) if campaign.unresolved_followup else None
    previous = list(session.scalars(select(Item).join(Run, Item.run_id == Run.id).where(
        Run.case_id == case_id, Run.release != campaign.release)
        .order_by(Item.updated_at.desc(), Item.id))) if not campaign.initial_snapshot else []
    for versions in versions_by_root.values():
        identifiers = {str(file.id) for file in versions}
        latest = next((item for item in previous if str(item.file_id) in identifiers or
            identifiers.intersection((item.result or {}).get('lineage_ids', []))), None)
        observed = None
        if campaign.source_probe:
            if latest is None or latest.status not in campaign.eligible_outcomes:
                continue
            observed = source_reader_evidence(session, current_version(versions), campaign)
        if campaign.unresolved_followup:
            qualification = recovery_followup.qualify(session, versions, latest, followup)
            if qualification:
                selected.append((versions, latest, qualification))
        elif campaign.eligible(latest, observed):
            selected.append((versions, latest, {}))
    # Record an empty selective snapshot too: a later file cannot silently enter
    # an already-completed campaign after its durable cutoff was established.
    run = Run(id=run_id, case_id=case_id, release=campaign.release, status='running' if selected else 'complete')
    session.add(run)
    session.flush()
    for versions, prior, qualification in selected:
        file = current_version(versions)
        session.add(Item(id=uuid5(run_id, str(file.id)), run_id=run_id, file_id=file.id,
            status='pending', result=dict(filename=file.original_filename,
                visibility_revision=financial_file_visibility(file)['financial_visibility_revision'],
                lineage_ids=[str(f.id) for f in versions], added=0,
                previous_item_id=str(prior.id) if prior else None,
                fresh_reading=bool(campaign.source_probe), source_probe=campaign.source_probe,
                readers=(prior.result or {}).get('readers', {}) if prior else {}, **qualification)))
    if campaign.unresolved_followup:
        scope = dict(considered=len(versions_by_root), scheduled=len(selected),
            **{key: followup['excluded'][key] for key in ('protected', 'no_unresolved_work', 'unconfirmed_content')})
        session.add(IngestionLog(case_id=case_id, level='info',
            message=f"Follow-up recovery scheduled {len(selected)} unresolved financial sources. "
                f"{followup['excluded']['unconfirmed_content']} unresolved sources need content confirmation; "
                f"{followup['excluded']['protected']} protected sources and "
                f"{followup['excluded']['no_unresolved_work']} sources without unresolved work were left unchanged.",
            extra=dict(operation='statement_recovery_followup_snapshot', release=campaign.release,
                run_id=str(run.id), scope=scope)))
    session.commit()
    return True


def _outcome(session, item, file, status, message, **values):
    item.status = status
    item.result = {**item.result, **values, 'message': message}
    session.add(IngestionLog(case_id=file.case_id, evidence_file_id=file.id,
        filename=file.original_filename, level='info', message=message,
        extra=dict(operation='deployment_statement_recovery', release=session.get(Run, item.run_id).release,
                   status=status, added=values.get('added', 0))))


def _guard(session, item, file):
    visibility = financial_file_visibility(file)
    if visibility['financial_removed'] or visibility['financial_imports_removed']:
        return 'kept', 'The investigator removed this source or its imports. Recovery left it unchanged.'
    if visibility['financial_visibility_revision'] != item.result['visibility_revision']:
        return 'review', 'The Financial file choice changed after recovery was scheduled. Review the source before retrying.'
    from services.financial.recovery_followup import guard
    if followup_guard := guard(session, item, file):
        return followup_guard
    ids = [UUID(value) for value in item.result['lineage_ids']]
    lineage_ids = {str(value) for value in ids}
    own_reading_request = str(uuid5(item.id, 'recovery-reading'))
    newer = session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == file.case_id,
        EvidenceFile.sha256 == file.sha256,
        EvidenceFile.metadata_['statement_root_evidence_id'].as_string().in_(lineage_ids),
        EvidenceFile.id.not_in(ids)))
    for version in newer:
        visibility = financial_file_visibility(version)
        if (version.metadata_ or {}).get('statement_version_request') != own_reading_request:
            return 'review', 'A newer statement reading was created after recovery was scheduled. Review that reading; saved work was kept.'
        if visibility['financial_removed'] or visibility['financial_imports_removed']:
            return 'kept', 'The recovery reading was removed by an investigator. That choice was retained.'
    ids = [UUID(value) for value in item.result.get('followup_scope_ids', item.result['lineage_ids'])]
    active_batches = session.scalars(select(Batch).where(Batch.case_id == file.case_id,
        Batch.status.in_(('preparing', 'pausing', 'paused'))))
    identities = {str(value) for value in ids}
    if any(any((entry.get('source_id') in identities or entry.get('file_id') in identities)
            and entry.get('status') not in ('checked', 'error') for entry in batch.files) for batch in active_batches):
        return 'waiting', 'Waiting for the existing processing batch. Its reading and pause choices are unchanged.'
    batches = session.execute(select(BatchItem.status, Batch.status).join(Batch, BatchItem.batch_id == Batch.id).where(
        Batch.case_id == file.case_id, Batch.status != 'removed', BatchItem.file_id.in_(ids))).all()
    if any(status == 'skipped' for status, _ in batches):
        return 'kept', 'An investigator chose to leave this statement unimported. That choice was retained.'
    if any(status == 'duplicate_ignored' for status, _ in batches):
        return 'kept', 'A duplicate statement was ignored. Restore its review explicitly before requesting another reading.'
    if any(status == 'pending_import' for status, _ in batches):
        return 'waiting', 'Waiting for an existing import to finish. It has not been interrupted.'
    if item.result.get('fresh_reading') and (any((version.metadata_ or {}).get('financial_review_progress')
            for version in session.scalars(select(EvidenceFile).where(EvidenceFile.id.in_(ids))))
            or session.scalar(select(BatchItem.id).join(Batch, BatchItem.batch_id == Batch.id).where(
                Batch.case_id == file.case_id, BatchItem.file_id.in_(ids), BatchItem.review_request.is_not(None)).limit(1))):
        return 'review', 'Saved investigator corrections remain on this reading. Compare them before requesting another reading.'
    if file.status == 'processing':
        return 'waiting', 'Waiting for the existing reading or AI ingestion. It has not been interrupted.'
    return None


def _verify_bytes(file, resolve_path):
    path = resolve_path(file.stored_path)
    if path is None or not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
        raise PdfMappingError('The original is unavailable for verification. Its saved records were kept.', 409)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != file.sha256:
        raise PdfMappingError('The source bytes do not match the evidence record. Review its history.', 409)


def recover_one(factory, item_id, resolve_path):
    """A case lock serializes corrections, removal and this additive commit."""
    from services.financial.runs import ingestion_run
    from services.financial.evidence_intake import has_financial_reading
    from services.financial.statement_import import read_statement_import
    from services.financial.recovery_additions import plan_additions, append_recovered
    from services.financial.statement_import_overlap import coverage_review
    with factory() as db:
        context = db.execute(select(Run.case_id, Item.file_id).join(Item, Item.run_id == Run.id).where(Item.id == item_id)).first()
    if not context:
        return
    case_id, file_id = context
    with factory() as db:
        if db.scalar(select(Case.id).where(Case.id == case_id).with_for_update(skip_locked=True)) is None:
            return
        item = db.get(Item, item_id)
        current_run = db.get(Run, item.run_id)
        if current_run.status != 'running' or item.status not in PENDING:
            return
        file = db.get(EvidenceFile, file_id)
        guard = _guard(db, item, file)
        target = db.get(EvidenceFile, UUID(item.result['reading_file_id'])) if item.result.get('reading_file_id') else None
        if not guard and target and target.status == 'processing':
            guard = ('reading', 'Reading the original in the background; saved work is unchanged.')
        if guard:
            changed = item.status != guard[0] or item.result.get('message') != guard[1]
            if changed:
                _outcome(db, item, file, *guard)
            item.updated_at = datetime.now(timezone.utc)
            db.commit()
            return
    # System attribution is explicit; no investigator is impersonated.
    with ingestion_run(case_id=case_id, session_factory=factory,
            config=dict(operation='deployment_statement_recovery', release=current_run.release, file_id=str(file_id))) as audit:
        with factory() as db:
            if db.scalar(select(Case.id).where(Case.id == case_id).with_for_update(skip_locked=True)) is None:
                return
            item = db.scalar(select(Item).where(Item.id == item_id).with_for_update())
            run = db.scalar(select(Run).where(Run.id == item.run_id).with_for_update())
            if run.status != 'running' or item.status not in PENDING:
                return
            file = db.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id, EvidenceFile.case_id == case_id).with_for_update())
            if not file:
                return
            guard = _guard(db, item, file)
            if guard:
                _outcome(db, item, file, *guard)
                db.commit()
                return
            from services.financial.recovery_followup import retry_failed_batches
            if retry_outcome := retry_failed_batches(db, item, file):
                _outcome(db, item, file, *retry_outcome)
                db.commit()
                return
            ids = [UUID(value) for value in item.result.get('followup_scope_ids', item.result['lineage_ids'])]
            documents = list(db.scalars(select(FinancialSourceDocument).where(
                FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.evidence_file_id.in_(ids),
                FinancialSourceDocument.status != 'superseded').with_for_update()))
            from services.financial.recovery_followup import pending_saved_work
            if documents and pending_saved_work(db, item, file):
                _outcome(db, item, file, 'review', 'Saved batch corrections remain to be reviewed. Compare them with the existing import before adding payments; the corrections and imported payments were kept.')
                db.commit()
                return
            marker = (file.metadata_ or {}).get('financial_workspace') or {}
            explicitly_batched = any(any(entry.get('source_id') in {str(value) for value in ids} for entry in batch.files)
                for batch in db.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')))
            recognized = item.result.get('eligibility_basis') in ('recognized_statement_content', 'explicit_reopening')
            if not documents and not marker.get('selected_by') and not explicitly_batched and not recognized:
                _outcome(db, item, file, 'review', 'Financial relevance needs a content check before automatic reading. The Evidence original is retained.')
                db.commit()
                return
            # This release repairs the statement reader. Other Financial formats
            # remain valid sources and are explicitly surfaced for their reader.
            if not file.original_filename.lower().endswith('.pdf'):
                _outcome(db, item, file, 'review', 'This Financial source needs its compatible reader. Open it in Evidence; it was not classified by its file type.')
                db.commit()
                return
            target = file
            if item.result.get('fresh_reading') and not item.result.get('reading_file_id'):
                return dict(needs_reading=True, case_id=case_id, file_id=file.id, item_id=item.id)
            if item.result.get('reading_file_id'):
                target = db.scalar(select(EvidenceFile).where(EvidenceFile.id == UUID(item.result['reading_file_id']), EvidenceFile.case_id == case_id))
                if target is None or target.sha256 != file.sha256:
                    _outcome(db, item, file, 'review', 'The retained recovery reading is unavailable. Open the original source.')
                    db.commit()
                    return
                if target.status == 'unprocessed':
                    return dict(needs_reading=True, case_id=case_id, file_id=file.id, item_id=item.id)
                if target.status == 'processing':
                    item.status = 'reading'
                    item.result = {**item.result, 'message': 'Reading the original in the background; saved work is unchanged.'}
                    db.commit()
                    return
                if target.status == 'failed':
                    _outcome(db, item, file, 'review', 'The recovery reading failed. Open the statement to inspect or retry it; saved work is unchanged.')
                    db.commit()
                    return
            if not has_financial_reading(db, target):
                # Engine submission happens separately, after this transaction.
                return dict(needs_reading=True, case_id=case_id, file_id=file.id, item_id=item.id)
            try:
                _verify_bytes(target, resolve_path)
                cache = {}
                first = read_statement_import(db, case_id=case_id, evidence_file_id=target.id, _cache=cache)
                choices = first.get('statement_choices') or []
                proposals = [read_statement_import(db, case_id=case_id, evidence_file_id=target.id,
                    statement_id=choice['id'], _cache=cache) for choice in choices] or [first]
                from services.financial.reading_recovery import reader_inventory
                item.result = {**item.result, 'readers': reader_inventory(proposals)}
                document_by_id = {str(doc.id): doc for doc in documents}
                matches = Counter((p.get('current_import') or {}).get('source_document_id') for p in proposals)
                results, added = [], 0
                for proposal in proposals:
                    result = dict(statement_id=proposal.get('statement_id'), added=0)
                    current = proposal.get('current_import') or {}
                    document = document_by_id.get(current.get('source_document_id'))
                    if document is None:
                        result.update(status='review', message='New reading ready to review. Confirm its account, currency and import; no earlier work was replaced.')
                        results.append(result)
                        continue
                    try:
                        if matches[str(document.id)] > 1:
                            raise PdfMappingError('Several new sections overlap one saved import. Compare the account sections before adding payments.', 409)
                        if document.sha256_at_ingestion != target.sha256:
                            raise PdfMappingError('The new reading and saved import have different source bytes.', 409)
                        from services.financial.import_batches import initial_request
                        raw = initial_request(proposal)
                        raw['replaces_source_document_id'] = str(document.id)
                        if coverage_review(db, case_id=case_id, file_id=target.id, request=raw)['candidates']:
                            raise PdfMappingError('Another statement overlaps this account and period. Compare the sources to avoid duplicates.', 409)
                        rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == case_id,
                            FinancialTransaction.source_document_id == document.id).with_for_update()))
                        plan = plan_additions(proposal, document, rows)
                        if plan['additions']:
                            from services.financial.recovery_additions import value_key
                            from services.financial.account_consolidation import expand_account_ids
                            account_ids = expand_account_ids(db, case_id, [UUID(document.metadata_['statement_account_id'])])
                            existing_values = {(str(row.transaction_date or row.posted_date or row.value_date or row.effective_date),
                                str(row.amount_minor), row.direction) for row in db.scalars(select(FinancialTransaction).where(
                                    FinancialTransaction.case_id == case_id, FinancialTransaction.account_id.in_(account_ids),
                                    FinancialTransaction.source_document_id != document.id,
                                    FinancialTransaction.currency == proposal['currency']))}
                            if any(value_key(row.model_dump()) in existing_values for row, _ in plan['additions']):
                                raise PdfMappingError('A recovered payment may already be saved from another statement for this account. Compare the sources first.', 409)
                        with db.begin_nested():
                            count = append_recovered(db, document=document, proposal=proposal, plan=plan,
                                run=audit, actor=ACTOR, release=run.release)
                        added += count
                        result.update(status='recovered' if count else 'unchanged', added=count,
                            source_document_id=str(document.id), message=f'{count} missing {"payment" if count == 1 else "payments"} added.' if count else 'Existing payments retained; no safe missing payments found.')
                    except (PdfMappingError, ValueError) as error:
                        result.update(status='review', message=str(error) if isinstance(error, PdfMappingError) else 'The new reading has incomplete or invalid payment fields. Review it beside the source.')
                    results.append(result)
                status = 'review' if any(r['status'] == 'review' for r in results) else 'recovered' if added else 'unchanged'
                _outcome(db, item, file, status, f'{added} missing {"payment" if added == 1 else "payments"} added. ' + (
                    'Some statement sections need review.' if status == 'review' else 'The earlier payments and investigator edits were retained.'),
                    added=item.result.get('added', 0) + added, sections=results, review_file_id=str(target.id))
                db.commit()
                audit.transaction_admitted(added)
            except (PdfMappingError, ValueError) as error:
                # No nested writer commits. Rollback any earlier scope additions
                # on an unexpected file-level validation problem.
                db.rollback()
                _record_failure(factory, item_id, str(error) if isinstance(error, PdfMappingError) else 'The new reading has incomplete or invalid statement fields. Open the source to review them.')


def _record_failure(factory, item_id, message):
    with factory() as db:
        context = db.execute(select(Run.case_id).join(Item, Item.run_id == Run.id).where(Item.id == item_id)).scalar_one_or_none()
        if context is None:
            return
        db.execute(select(Case.id).where(Case.id == context).with_for_update()).all()
        item = db.scalar(select(Item).where(Item.id == item_id).with_for_update())
        if item.status not in PENDING:
            return
        file = db.get(EvidenceFile, item.file_id)
        _outcome(db, item, file, 'review', message)
        db.commit()


async def start_reading(factory, request, resolve_path, process_files):
    from services.financial.statement_reprocessing import create_statement_version
    # The deterministic request reuses one internal reading after a restart.
    with factory() as db:
        db.execute(select(Case.id).where(Case.id == request['case_id']).with_for_update()).all()
        item = db.get(Item, request['item_id'])
        run = db.get(Run, item.run_id)
        if run.status != 'running' or item.status not in PENDING:
            return
        file = db.get(EvidenceFile, item.file_id)
        if _guard(db, item, file):
            return
        version = create_statement_version(db, case_id=request['case_id'], evidence_file_id=file.id,
            request_id=uuid5(item.id, 'recovery-reading'), actor=ACTOR, resolve_path=resolve_path)
        item = db.get(Item, request['item_id'])
        item.result = {**item.result, 'reading_file_id': str(version.id), 'review_file_id': str(version.id),
            'message': 'A separate reading is queued; the original and existing AI ingestion are retained.'}
        item.status = 'reading'
        db.commit()
        if version.status in ('unprocessed', 'failed'):
            await process_files(db, case_id=request['case_id'], file_ids=[version.id],
                preparation_mode='pdf_review', requested_by_user_id=None)


def _case_run(session, case_id, run_id=None, lock=False):
    query = select(Run).where(Run.case_id == case_id)
    if run_id is not None:
        query = query.where(Run.id == run_id)
    query = query.order_by(Run.created_at.desc(), Run.release.desc()).limit(1)
    return session.scalar(query.with_for_update() if lock else query)


def status(session, case_id, *, offset=0, limit=50, run_id=None):
    run = _case_run(session, case_id, run_id)
    if not run:
        return dict(run=None, items=[], total=0, counts={})
    counts = dict(session.execute(select(Item.status, func.count()).where(Item.run_id == run.id).group_by(Item.status)).all())
    rows = list(session.scalars(select(Item).where(Item.run_id == run.id).order_by(Item.file_id).offset(offset).limit(limit)))
    added = session.scalar(select(func.coalesce(func.sum(Item.result['added'].as_integer()), 0)).where(Item.run_id == run.id))
    history = [dict(id=str(prior.id), release=prior.release, status=prior.status) for prior in session.scalars(
        select(Run).where(Run.case_id == case_id, Run.id != run.id).order_by(Run.created_at.desc(), Run.release.desc()))]
    snapshot = session.scalar(select(IngestionLog.extra).where(IngestionLog.case_id == case_id,
        IngestionLog.extra['operation'].as_string() == 'statement_recovery_followup_snapshot',
        IngestionLog.extra['run_id'].as_string() == str(run.id)).limit(1))
    return dict(run=dict(id=str(run.id), release=run.release, status=run.status), previous_runs=history,
        scope=snapshot.get('scope') if snapshot else None, counts=counts, added=added,
        total=sum(counts.values()), items=[dict(id=str(item.id), file_id=str(item.file_id), status=item.status, **item.result) for item in rows])


def control(session, case_id, action, run_id=None):
    session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    run = _case_run(session, case_id, run_id, lock=True)
    if not run:
        raise PdfMappingError('No recovery run exists for this case.', 404)
    if run.status != 'complete':
        run.status = 'paused' if action == 'pause' else 'running'
        session.commit()
    return dict(status=run.status)


def next_recovery_items(session, after=None):
    """Rotate through durable pending units even when a busy case is skipped.

    A skipped Case lock does not change an item's saved timestamp. Selecting
    only the oldest timestamps repeatedly lets two locked units occupy every
    turn. Stable IDs provide a bounded cursor without modifying work or leases.
    Restarting the cursor is safe because each unit rechecks its durable state.
    """
    query = select(Item.id).join(Run, Item.run_id == Run.id).where(
        Run.release.in_([campaign.release for campaign in CAMPAIGNS]),
        Run.status == 'running', Item.status.in_(PENDING)).order_by(Item.id).limit(2)
    if after is not None:
        following = list(session.scalars(query.where(Item.id > after)))
        if following:
            return following
    return list(session.scalars(query))


async def run_recovery_forever():
    from postgres.session import _get_session_local
    from routers.evidence import _resolve_stored_path
    from services.evidence_processing_service import process_db_files
    from services.financial.import_batches import _finish_atomic
    initialized = False
    after = None
    while True:
        try:
            factory = _get_session_local()
            if not initialized:
                results = []
                for campaign in CAMPAIGNS:
                    with factory() as db:
                        cutoff = activate(db, campaign.release)
                        case_ids = list(db.scalars(select(Case.id).where(Case.created_at <= cutoff).order_by(Case.id)))
                    def initialize_case(case_id):
                        with factory() as db:
                            return snapshot_case(db, case_id, cutoff, campaign)
                    for case_id in case_ids:
                        results.append(await _finish_atomic(initialize_case, case_id))
                initialized = all(results)
            with factory() as db:
                ids = next_recovery_items(db, after)
            for item_id in ids:
                after = item_id
                try:
                    pending = await _finish_atomic(recover_one, factory, item_id, _resolve_stored_path)
                    if pending:
                        await start_reading(factory, pending, _resolve_stored_path, process_db_files)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception('A recovery file could not complete; saved work is retained')
                    await asyncio.to_thread(_record_failure, factory, item_id,
                        'Recovery could not complete this file. Open its statement to inspect the retained reading and retry.')
            with factory() as db:
                runs = list(db.scalars(select(Run).where(Run.release.in_([campaign.release for campaign in CAMPAIGNS]), Run.status == 'running').with_for_update(skip_locked=True)))
                for run in runs:
                    if not db.scalar(select(Item.id).where(Item.run_id == run.id, Item.status.in_(PENDING)).limit(1)):
                        run.status = 'complete'
                db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Statement recovery paused by an error; durable progress will resume')
        await asyncio.sleep(10)


def retry_item(session, case_id, item_id):
    session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    run = session.scalar(select(Run).join(Item, Item.run_id == Run.id).where(Run.case_id == case_id,
        Item.id == item_id).with_for_update(of=Run))
    item = session.scalar(select(Item).where(Item.id == item_id, Item.run_id == run.id).with_for_update()) if run else None
    if item is None:
        raise PdfMappingError('Recovery item not found in this case.', 404)
    if item.status == 'review':
        file = session.get(EvidenceFile, item.file_id)
        visibility = financial_file_visibility(file)
        if visibility['financial_removed'] or visibility['financial_imports_removed']:
            raise PdfMappingError('This source was removed. Restore it explicitly before requesting recovery.', 409)
        item.status = 'pending'
        result = {**item.result, 'visibility_revision': visibility['financial_visibility_revision'],
            'message': 'Recovery queued again. Saved work remains protected.'}
        target = session.get(EvidenceFile, UUID(result['reading_file_id'])) if result.get('reading_file_id') else None
        if target and target.status == 'failed':
            result.pop('reading_file_id', None)
        item.result = result
        run.status = 'running'
        session.commit()
    return dict(status=item.status)
