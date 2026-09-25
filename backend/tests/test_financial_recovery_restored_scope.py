import asyncio
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry, IngestionLog
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryRun as Run, FinancialRecoveryItem as Item
from services.financial import deployment_recovery as recovery, import_batches
from services.financial.recovery_campaigns import FOLLOWUP_RELEASE, RESTORED_REPAIR_RELEASE, manifest
from services.financial.recovery_followup import current_scope
from services.financial.import_removal import preview_removal, remove_imports
from services.financial.evidence_intake import prepare_existing_financial_file
from services.financial.file_visibility import set_financial_file_visibility, financial_file_visibility
from tests.test_financial_deployment_recovery import f, outcome
from tests.test_financial_recovery_followup import failed_batch, finish_old


def snapshot(f, release):
    with f.SessionLocal() as db:
        recovery.snapshot_case(db, f.case.id, recovery.activate(db, release), manifest(release))
        run = db.scalar(select(Run).where(Run.case_id == f.case.id, Run.release == release))
        return run.id if run else None


def seed_all_protected(f):
    # Model the deployed v1 bug's durable empty snapshot, leaving its history
    # intact. Other fixture sources are immaterial to the synthetic incident.
    run_id = snapshot(f, FOLLOWUP_RELEASE)
    with f.SessionLocal() as db:
        for item in db.scalars(select(Item).where(Item.run_id == run_id)):
            db.delete(item)
        db.get(Run, run_id).status = 'complete'
        log = db.scalar(select(IngestionLog).where(
            IngestionLog.extra['run_id'].as_string() == str(run_id),
            IngestionLog.extra['operation'].as_string() == 'statement_recovery_followup_snapshot'))
        log.extra = {**log.extra, 'scope': dict(considered=1, scheduled=0, protected=1,
            no_unresolved_work=0, unconfirmed_content=0)}
        db.commit()
    return run_id


def reset_reading(f):
    old_import = UUID(f.confirm()['source_document_id'])
    batch_id = failed_batch(f)
    batch = f.db.get(Batch, batch_id)
    import_batches.prepare_reviews(f.db, batch, batch.files[0])
    preview = preview_removal(f.db, case_id=f.case.id, file_ids=[f.file.id])
    removed = remove_imports(f.db, case_id=f.case.id, file_ids=[f.file.id],
        expected_revision=preview['revision'], actor=f.actor)
    fresh = asyncio.run(prepare_existing_financial_file(f.db, case_id=f.case.id,
        evidence_file_id=f.file.id, expected_revision=removed['removal_id'], actor=f.actor,
        resolve_path=Path, process_files=AsyncMock(return_value={'job_ids': ['synthetic']})))
    new = f.db.get(EvidenceFile, UUID(fresh['evidence_file_id']))
    old_text = f.db.get(EvidenceDocumentText, f.file.id)
    job_id = uuid4()
    f.db.add(EvidenceDocumentText(evidence_file_id=new.id, content=old_text.content,
        content_sha256=old_text.content_sha256, character_count=old_text.character_count,
        engine_job_id=job_id, source_locations=deepcopy(old_text.source_locations)))
    geometry = f.db.get(EvidenceTableGeometry, (f.file.id, 1))
    f.db.add(EvidenceTableGeometry(evidence_file_id=new.id, page_number=1,
        engine_job_id=job_id, payload=deepcopy(geometry.payload)))
    new.status = 'processed'
    f.db.commit()
    new_batch = failed_batch(f, source_id=new.id, file_id=new.id)
    return new, batch_id, new_batch, old_import


def test_actual_explicit_reset_repairs_current_batch_without_resurrecting_removed_work(f):
    finish_old(f)
    fresh, old_batch, new_batch, old_import = reset_reading(f)
    prior = seed_all_protected(f)
    run_id = snapshot(f, RESTORED_REPAIR_RELEASE)
    assert run_id == snapshot(f, RESTORED_REPAIR_RELEASE)
    with f.SessionLocal() as db:
        item = db.scalar(select(Item).where(Item.run_id == run_id))
        assert item.file_id == fresh.id
        assert item.result['followup_scope_ids'] == [str(fresh.id)]
        assert item.result['reopening']['kind'] == 'explicit_reset'
        assert len(item.result['lineage_ids']) == 2
        item_id = item.id
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'waiting'
    engine = AsyncMock()
    asyncio.run(import_batches.advance_batch(f.SessionLocal, new_batch, Path, engine))
    engine.assert_not_awaited()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'review'  # new statements still need confirmation
    with f.SessionLocal() as db:
        assert db.get(Batch, new_batch).files[0]['status'] == 'checked'
        assert db.get(Batch, old_batch).status == 'removed'
        assert db.get(FinancialSourceDocument, old_import).status == 'rejected'
        assert all(row.ledger_status == 'rejected' for row in db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == old_import)))
        assert financial_file_visibility(db.get(EvidenceFile, f.file.id))['financial_removed']
        assert db.get(Run, prior).status == 'complete'
        assert not db.scalar(select(Item.id).where(Item.run_id == prior))
        assert len(outcome(f, item_id)[1]['batch_retry_receipts']) == 1
    f.db.expire_all()
    removal_id = f.file.metadata_['financial_import_removal']['id']
    repeated_engine = AsyncMock()
    repeated = asyncio.run(prepare_existing_financial_file(f.db, case_id=f.case.id,
        evidence_file_id=f.file.id, expected_revision=removal_id, actor=f.actor,
        resolve_path=Path, process_files=repeated_engine))
    assert repeated['evidence_file_id'] == str(fresh.id)
    repeated_engine.assert_not_awaited()


@pytest.mark.parametrize('reverse', [False, True])
def test_batch_crossing_reopened_boundary_never_retries_removed_history(f, reverse):
    finish_old(f)
    fresh, _, batch_id, _ = reset_reading(f)
    f.file.status = 'failed'
    f.db.delete(f.db.get(EvidenceTableGeometry, (f.file.id, 1)))
    batch = f.db.get(Batch, batch_id)
    entry = {**batch.files[0], 'source_id': str(f.file.id if reverse else fresh.id),
        'file_id': str(fresh.id if reverse else f.file.id), 'status': 'error'}
    batch.files = [entry]
    f.db.commit()
    seed_all_protected(f)
    run_id = snapshot(f, RESTORED_REPAIR_RELEASE)
    with f.SessionLocal() as db:
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = outcome(f, item_id)
    assert status == 'review'
    assert 'reopened scope' in result['message']
    assert not result['batch_retry_receipts']
    with f.SessionLocal() as db:
        assert db.get(Batch, batch_id).files[0]['status'] == 'error'
        assert not db.get(Batch, batch_id).files[0].get('recovery')


@pytest.mark.parametrize('field', ['statement_version_request', 'statement_version_actor'])
def test_late_reset_receipt_drift_stops_before_retry(f, field):
    finish_old(f)
    fresh, _, _, _ = reset_reading(f)
    seed_all_protected(f)
    run_id = snapshot(f, RESTORED_REPAIR_RELEASE)
    with f.SessionLocal() as db:
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))
        file = db.get(EvidenceFile, fresh.id)
        file.metadata_ = {**file.metadata_, field: str(uuid4()) if field == 'statement_version_request'
            else {'user_id': str(uuid4())}}
        db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = outcome(f, item_id)
    assert status == 'review'
    assert 'reopened reading changed' in result['message']
    assert not result['batch_retry_receipts']


@pytest.mark.parametrize('status', ['running', 'paused'])
def test_earlier_campaign_retains_ownership_of_reopened_reading(f, status):
    finish_old(f)
    fresh, _, _, _ = reset_reading(f)
    seed_all_protected(f)
    run_id = snapshot(f, RESTORED_REPAIR_RELEASE)
    with f.SessionLocal() as db:
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))
        prior = Run(id=uuid4(), case_id=f.case.id, release='synthetic-earlier-owner', status=status)
        db.add(prior)
        db.flush()
        db.add(Item(id=uuid4(), run_id=prior.id, file_id=fresh.id, status='pending', result={}))
        db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = outcome(f, item_id)
    assert status == 'waiting'
    assert 'earlier recovery' in result['message']
    assert not result['batch_retry_receipts']


@pytest.mark.parametrize('decision', ['skipped', 'duplicate_ignored', 'removed', 'direct_ignore', 'processing', 'paused'])
def test_current_or_late_decision_on_reopened_branch_still_protects_work(f, decision):
    finish_old(f)
    fresh, _, batch_id, _ = reset_reading(f)
    seed_all_protected(f)
    run_id = snapshot(f, RESTORED_REPAIR_RELEASE)
    with f.SessionLocal() as db:
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))
        if decision == 'direct_ignore':
            file = db.get(EvidenceFile, fresh.id)
            file.metadata_ = {**file.metadata_, 'financial_duplicate_dispositions': {'': {'status': 'ignored'}}}
        elif decision == 'processing':
            db.get(EvidenceFile, fresh.id).status = 'processing'
        elif decision == 'paused':
            db.get(Batch, batch_id).status = 'paused'
        else:
            db.add(BatchItem(id=uuid4(), batch_id=batch_id, file_id=fresh.id,
                statement_key='synthetic', status=decision, summary={}))
        db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == ('waiting' if decision in ('processing', 'paused') else 'kept')
    assert not outcome(f, item_id)[1]['batch_retry_receipts']


def test_newer_visible_version_without_valid_reset_provenance_does_not_override_removal(f):
    finish_old(f)
    fresh, _, _, _ = reset_reading(f)
    fresh.metadata_ = {**fresh.metadata_, 'statement_version_request': str(uuid4())}
    f.db.commit()
    _, reopening = current_scope(f.db, [f.file, fresh])
    assert reopening is None
    seed_all_protected(f)
    run_id = snapshot(f, RESTORED_REPAIR_RELEASE)
    with f.SessionLocal() as db:
        assert not db.scalar(select(Item.id).where(Item.run_id == run_id))


def test_actual_restore_audit_reopens_only_that_restore_group(f):
    finish_old(f)
    # First retain an older separately hidden version; a later hide/restore
    # must not turn that unrelated historical hiding into a global veto.
    from services.financial.statement_reprocessing import create_statement_version
    old = create_statement_version(f.db, case_id=f.case.id, evidence_file_id=f.file.id,
        request_id=uuid4(), actor=f.actor, resolve_path=Path)
    old.metadata_ = {**old.metadata_, 'financial_file_visibility': {'removed': True, 'revision': 'older-action'}}
    f.db.commit()
    hidden = set_financial_file_visibility(f.db, case_id=f.case.id, evidence_file_id=f.file.id,
        removed=True, expected_revision='initial', actor=f.actor)
    restored = set_financial_file_visibility(f.db, case_id=f.case.id, evidence_file_id=f.file.id,
        removed=False, expected_revision=hidden['financial_visibility_revision'], actor=f.actor)
    f.db.refresh(f.file)
    versions, reopening = current_scope(f.db, [f.file, old])
    assert [version.id for version in versions] == [f.file.id]
    assert reopening['kind'] == 'explicit_restore'
    assert reopening['revision'] == restored['financial_visibility_revision']
    seed_all_protected(f)
    run_id = snapshot(f, RESTORED_REPAIR_RELEASE)
    with f.SessionLocal() as db:
        assert db.scalar(select(Item).where(Item.run_id == run_id)).file_id == f.file.id


def test_visible_metadata_without_matching_restore_audit_is_not_a_reopening(f):
    f.file.metadata_ = {**f.file.metadata_, 'financial_file_visibility': {
        'removed': False, 'revision': str(uuid4()), 'actor': {'user_id': str(f.actor.user_id)}}}
    f.db.commit()
    _, reopening = current_scope(f.db, [f.file])
    assert reopening is None


@pytest.mark.parametrize('change', ['running', 'paused', 'has_item', 'some_scheduled', 'not_all_protected'])
def test_repair_never_replays_other_campaign_outcomes(f, change):
    finish_old(f)
    prior = seed_all_protected(f)
    with f.SessionLocal() as db:
        run = db.get(Run, prior)
        if change in ('running', 'paused'):
            run.status = change
        elif change == 'has_item':
            db.add(Item(id=uuid4(), run_id=prior, file_id=f.file.id, status='recovered', result={}))
        else:
            log = db.scalar(select(IngestionLog).where(IngestionLog.extra['run_id'].as_string() == str(prior)))
            scope = {**log.extra['scope'], 'protected': 0,
                'scheduled': 1 if change == 'some_scheduled' else 0,
                'no_unresolved_work': 0 if change == 'some_scheduled' else 1}
            log.extra = {**log.extra, 'scope': scope}
        db.commit()
    assert snapshot(f, RESTORED_REPAIR_RELEASE) is None
