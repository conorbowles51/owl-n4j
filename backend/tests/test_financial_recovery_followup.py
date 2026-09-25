import asyncio
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryItem as Item, FinancialRecoveryRun as Run
from services.financial import deployment_recovery as recovery, import_batches
from services.financial.recovery_campaigns import FOLLOWUP_RELEASE, manifest
from tests.test_financial_deployment_recovery import f, partial_import, rows, outcome


def finish_old(f, state='review'):
    with f.SessionLocal() as db:
        recovery.snapshot_case(db, f.case.id, recovery.activate(db))
        run = db.scalar(select(Run).where(Run.case_id == f.case.id))
        run.status = 'complete'
        for item in db.scalars(select(Item).where(Item.run_id == run.id)):
            item.status = state if item.file_id == f.file.id else 'unchanged'
            item.result = {**item.result, 'message': 'Earlier reader needs review.'}
        db.commit()
        return run.id


def followup(f):
    with f.SessionLocal() as db:
        campaign = manifest(FOLLOWUP_RELEASE)
        recovery.snapshot_case(db, f.case.id, recovery.activate(db, FOLLOWUP_RELEASE), campaign)
        run = db.scalar(select(Run).where(Run.release == FOLLOWUP_RELEASE, Run.case_id == f.case.id))
        return list(db.scalars(select(Item.id).where(Item.run_id == run.id)))


def failed_batch(f, *, status='review', file_id=None, source_id=None):
    batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status=status,
        files=[dict(source_id=str(source_id or f.file.id), file_id=str(file_id or f.file.id),
            filename='Synthetic statement.pdf', status='error', error='Statement not found in this case.')],
        actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.user.id)))
    f.db.add(batch)
    f.db.commit()
    return batch.id


def test_followup_revisits_old_review_additively_once_and_keeps_old_receipt(f):
    source = partial_import(f)
    before = {row.id for row in rows(f, source)}
    with f.SessionLocal() as db:
        row = db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == source))
        row.metadata_ = {**(row.metadata_ or {}), 'investigator_note': 'Keep this note'}
        noted = row.id
        db.commit()
    old = finish_old(f)
    [item_id] = followup(f)
    assert followup(f) == [item_id]
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'recovered', outcome(f, item_id)
    assert before < {row.id for row in rows(f, source)}
    count = len(rows(f, source))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert len(rows(f, source)) == count
    with f.SessionLocal() as db:
        assert db.get(Run, old).status == 'complete'
        assert db.scalar(select(Item).where(Item.run_id == old, Item.file_id == f.file.id)).status == 'review'
        assert db.get(FinancialTransaction, noted).metadata_['investigator_note'] == 'Keep this note'
        assert len(db.get(FinancialSourceDocument, source).metadata_['statement_recovery_additions']) == 1


@pytest.mark.parametrize('old_status', ['unchanged', 'recovered', 'kept'])
def test_successful_or_preserved_sources_are_not_swept_into_followup(f, old_status):
    finish_old(f, old_status)
    assert followup(f) == []
    # The durable empty snapshot is not changed by a later failure.
    failed_batch(f)
    assert followup(f) == []


def test_old_batch_presence_or_pdf_filename_does_not_establish_financial_content(f):
    f.file.metadata_ = {}
    f.db.commit()
    failed_batch(f)
    finish_old(f)
    assert followup(f) == []
    with f.SessionLocal() as db:
        scope = recovery.status(db, f.case.id)['scope']
        assert scope['unconfirmed_content'] == 1 and scope['scheduled'] == 0
        assert scope['considered'] == scope['no_unresolved_work'] + scope['unconfirmed_content']


def test_recognized_retained_statement_qualifies_without_selection_marker(f):
    from tests.test_financial_recovery_campaigns import install_affected_andrews
    install_affected_andrews(f, damaged=False)
    f.file.metadata_ = {}
    f.db.commit()
    failed_batch(f)
    [item_id] = followup(f)
    state, result = outcome(f, item_id)
    assert state == 'pending'
    assert result['eligibility_basis'] == 'recognized_statement_content'
    assert result['recognized_readers'] == ['andrews-share-statement']
    assert not result['fresh_reading']


@pytest.mark.parametrize('protected', ['skipped', 'duplicate_ignored', 'removed', 'hidden', 'imports_removed'])
def test_investigator_dispositions_are_excluded_at_snapshot(f, protected):
    batch_id = failed_batch(f)
    if protected == 'hidden':
        f.file.metadata_ = {**f.file.metadata_, 'financial_file_visibility': {'removed': True, 'revision': 'removed'}}
    elif protected == 'imports_removed':
        f.file.metadata_ = {**f.file.metadata_, 'financial_import_removal': {'id': 'synthetic'}}
    else:
        f.db.add(BatchItem(id=uuid4(), batch_id=batch_id, file_id=f.file.id,
            statement_key='synthetic', status=protected, summary={}))
    f.db.commit()
    assert followup(f) == []


def test_stale_batch_error_rebuilds_retained_review_preserving_draft_and_no_engine_or_import(f):
    batch_id = failed_batch(f)
    batch = f.db.get(Batch, batch_id)
    import_batches.prepare_reviews(f.db, batch, batch.files[0])
    item = f.db.scalar(select(BatchItem).where(BatchItem.batch_id == batch_id))
    draft = import_batches.initial_request(f.preview())
    draft['holder'] = 'Corrected investigator holder'
    item.review_request = deepcopy(draft)
    identity = item.id
    f.db.commit()
    [recovery_id] = followup(f)
    recovery.recover_one(f.SessionLocal, recovery_id, Path)
    state, result = outcome(f, recovery_id)
    assert state == 'waiting'
    assert len(result['batch_retry_receipts']) == 1
    receipt = result['batch_retry_receipts'][0]
    assert receipt['action'] == 'check_statements' and receipt['queued']
    recovery.recover_one(f.SessionLocal, recovery_id, Path)
    assert outcome(f, recovery_id)[1]['batch_retry_receipts'] == result['batch_retry_receipts']
    engine = AsyncMock()
    asyncio.run(import_batches.advance_batch(f.SessionLocal, batch_id, Path, engine))
    engine.assert_not_awaited()
    recovery.recover_one(f.SessionLocal, recovery_id, Path)
    assert outcome(f, recovery_id)[0] == 'review'
    with f.SessionLocal() as db:
        batch = db.get(Batch, batch_id)
        assert batch.files[0]['status'] == 'checked'
        assert batch.files[0]['recovery']['attempt_id'] == receipt['attempt_id']
        assert db.get(BatchItem, identity).review_request == draft
        assert list(db.scalars(select(FinancialTransaction))) == []


@pytest.mark.parametrize('paused', ['batch', 'prior_recovery', 'reading'])
def test_followup_waits_for_paused_or_active_work_without_changing_it(f, paused):
    old = finish_old(f)
    batch_id = failed_batch(f)
    [item_id] = followup(f)
    with f.SessionLocal() as db:
        if paused == 'batch':
            db.get(Batch, batch_id).status = 'paused'
        elif paused == 'prior_recovery':
            db.get(Run, old).status = 'paused'
        else:
            db.get(EvidenceFile, f.file.id).status = 'processing'
        db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'waiting'
    assert outcome(f, item_id)[1]['batch_retry_receipts'] == []
    with f.SessionLocal() as db:
        assert db.get(Batch, batch_id).files[0]['status'] == 'error'
        assert not db.get(Batch, batch_id).files[0].get('recovery')


def test_failed_retry_is_not_automatically_repeated(f):
    batch_id = failed_batch(f)
    [item_id] = followup(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    with f.SessionLocal() as db:
        batch = db.get(Batch, batch_id)
        entry = batch.files[0]
        batch.files = [{**entry, 'status': 'error', 'error': 'Still unreadable',
            'recovery': {**entry['recovery'], 'stage': 'failed', 'message': 'Still unreadable'}}]
        db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    state, result = outcome(f, item_id)
    assert state == 'review' and result['message'] == 'Still unreadable'
    assert len(result['batch_retry_receipts']) == 1


def test_missing_original_in_batch_is_actionable_without_queueing(f):
    batch_id = failed_batch(f, source_id=uuid4())
    [item_id] = followup(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    state, result = outcome(f, item_id)
    assert state == 'review'
    assert result['batch_retry_receipts'][0]['action'] == 'source_unavailable'
    assert not result['batch_retry_receipts'][0]['queued']
    assert 'Restore the original' in result['message']
    with f.SessionLocal() as db:
        assert db.get(Batch, batch_id).files[0]['status'] == 'error'


def test_batch_handoff_and_recovery_receipt_roll_back_together(f):
    from services.financial.recovery_followup import retry_failed_batches
    batch_id = failed_batch(f)
    [item_id] = followup(f)
    with f.SessionLocal() as db:
        item = db.get(Item, item_id)
        result = retry_failed_batches(db, item, db.get(EvidenceFile, f.file.id))
        assert result[0] == 'waiting' and item.result['batch_retry_receipts']
        db.rollback()
    with f.SessionLocal() as db:
        assert db.get(Batch, batch_id).files[0]['status'] == 'error'
        assert db.get(Item, item_id).result['batch_retry_receipts'] == []


@pytest.mark.parametrize('before_snapshot', [True, False])
def test_single_statement_duplicate_ignore_protects_whole_reading(f, before_snapshot):
    batch_id = failed_batch(f)
    if not before_snapshot:
        [item_id] = followup(f)
    f.file.metadata_ = {**f.file.metadata_, 'financial_duplicate_dispositions': {
        'one-period-in-mixed-file': {'status': 'ignored', 'signature': 'synthetic'}}}
    f.db.commit()
    if before_snapshot:
        assert followup(f) == []
    else:
        recovery.recover_one(f.SessionLocal, item_id, Path)
        assert outcome(f, item_id)[0] == 'kept'
    with f.SessionLocal() as db:
        assert db.get(Batch, batch_id).files[0]['status'] == 'error'
        assert not db.get(Batch, batch_id).files[0].get('recovery')


def test_unverified_same_case_prepared_reference_never_retried(f):
    unrelated = f.evidence('b' * 64)
    unrelated.status = 'failed'
    f.db.commit()
    batch_id = failed_batch(f, file_id=unrelated.id)
    [item_id] = followup(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    state, result = outcome(f, item_id)
    assert state == 'review' and 'outside this verified source history' in result['message']
    assert not result['batch_retry_receipts']
    with f.SessionLocal() as db:
        assert db.get(Batch, batch_id).files[0]['status'] == 'error'
        assert db.get(EvidenceFile, unrelated.id).status == 'failed'


def test_pending_batch_corrections_prevent_additive_write(f):
    source = partial_import(f)
    batch_id = failed_batch(f)
    batch = f.db.get(Batch, batch_id)
    import_batches.prepare_reviews(f.db, batch, batch.files[0])
    item = f.db.scalar(select(BatchItem).where(BatchItem.batch_id == batch_id))
    draft = import_batches.initial_request(f.preview())
    draft['holder'] = 'Pending investigator correction'
    item.review_request = deepcopy(draft)
    item.status = 'attention'
    f.db.commit()
    [item_id] = followup(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    engine = AsyncMock()
    asyncio.run(import_batches.advance_batch(f.SessionLocal, batch_id, Path, engine))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    state, result = outcome(f, item_id)
    assert state == 'review' and 'Saved batch corrections' in result['message']
    assert len(rows(f, source)) == 11
    with f.SessionLocal() as db:
        assert db.get(BatchItem, item.id).review_request == draft


def test_followup_preserves_explicit_excluded_payment(f):
    request = f.request()
    next(row for row in reversed(request['rows']) if not row['excluded'])['excluded'] = True
    source = UUID(f.confirm_legacy(request)['source_document_id'])
    before = {row.id for row in rows(f, source)}
    finish_old(f)
    [item_id] = followup(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'review'
    assert {row.id for row in rows(f, source)} == before


def test_failed_reading_handoff_does_not_start_a_second_engine_job(f):
    f.file.status = 'failed'
    f.db.commit()
    batch_id = failed_batch(f)
    [item_id] = followup(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[1]['batch_retry_receipts'][0]['action'] == 'retry_reading'
    async def process(db, **kwargs):
        assert kwargs['file_ids'] == [f.file.id]
        db.get(EvidenceFile, f.file.id).status = 'processing'
        db.commit()
        return {'job_ids': ['synthetic-retained-reading-job']}
    engine = AsyncMock(side_effect=process)
    asyncio.run(import_batches.advance_batch(f.SessionLocal, batch_id, Path, engine))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    engine.assert_awaited_once()
    state, result = outcome(f, item_id)
    assert state == 'waiting' and len(result['batch_retry_receipts']) == 1
    assert not result.get('reading_file_id')


@pytest.mark.parametrize('status', ['skipped', 'duplicate_ignored', 'removed'])
def test_late_batch_disposition_stops_followup(f, status):
    batch_id = failed_batch(f)
    [item_id] = followup(f)
    f.db.add(BatchItem(id=uuid4(), batch_id=batch_id, file_id=f.file.id,
        statement_key='synthetic', status=status, summary={}))
    f.db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'kept'
    with f.SessionLocal() as db:
        assert not db.get(Batch, batch_id).files[0].get('recovery')


def test_followup_keeps_pending_manual_addition_and_its_identity(f):
    from services.financial.manual_statement_payment import append_payment, ManualStatementPayment
    from services.financial.statement_details import read_statement_details
    source = partial_import(f)
    with f.SessionLocal() as db:
        view = read_statement_details(db, case_id=f.case.id, source_id=source)
    request_id = uuid4()
    append_payment(session_factory=f.SessionLocal, case_id=f.case.id, source_id=source, actor=f.actor,
        request=ManualStatementPayment(request_id=request_id, expected_revision=view['revision'], row=dict(
            id='manual:' + str(request_id), excluded=False, manual_page=1, date='2023-12-28',
            description='Investigator added missing payment', counterparty='Synthetic supplier', amount_minor='27000000',
            direction='debit', balance_minor=None, reason='')))
    before = {row.id for row in rows(f, source)}
    with f.SessionLocal() as db:
        metadata = db.get(FinancialSourceDocument, source).metadata_
        pending = deepcopy(metadata['statement_incomplete_records'])
        additions = deepcopy(metadata['statement_manual_additions'])
    finish_old(f)
    [item_id] = followup(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'review'
    assert {row.id for row in rows(f, source)} == before
    with f.SessionLocal() as db:
        metadata = db.get(FinancialSourceDocument, source).metadata_
        assert metadata['statement_incomplete_records'] == pending
        assert metadata['statement_manual_additions'] == additions


def test_unreadable_legacy_geometry_is_counted_unknown_without_blocking_snapshot(f):
    f.file.metadata_ = {}
    geometry = f.db.get(EvidenceTableGeometry, (f.file.id, 1))
    geometry.payload = [{'table': {'values': [{'text': 'Broken retained cell'}]}}]
    f.db.commit()
    failed_batch(f)
    assert followup(f) == []
    with f.SessionLocal() as db:
        scope = recovery.status(db, f.case.id)['scope']
        assert set(scope) == {'considered', 'scheduled', 'protected', 'no_unresolved_work', 'unconfirmed_content'}
        assert scope['unconfirmed_content'] == 1
        assert scope['scheduled'] == scope['protected'] == 0
        assert scope['considered'] == sum(value for key, value in scope.items() if key != 'considered')
