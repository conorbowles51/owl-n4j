"""Reader recovery: only held, unedited statements read by an affected engine revision."""
import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4, uuid5

import pytest
from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry, EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryItem as Item, FinancialRecoveryRun as Run
from services.financial import deployment_recovery as recovery
from services.financial import recovery_readers as readers
from services.financial.pdf_candidates import _digest
from services.financial.recovery_campaigns import (AFFECTED_EXTRACTION_SHA256, READER_RECOVERY,
    READER_RECOVERY_FLAG, READER_RECOVERY_RELEASE, manifest, reader_recovery_enabled)
from tests.test_financial_deployment_recovery import f  # noqa: F401  (fixture)

AFFECTED = AFFECTED_EXTRACTION_SHA256[-1]
CURRENT = hashlib.sha256((Path(__file__).resolve().parents[2] /
    'evidence-engine/app/pipeline/pdf_extraction.py').read_bytes()).hexdigest()


def set_reader(f, file_id, digest=AFFECTED):
    from tests.test_financial_pdf_processing_manifest import manifest as preparation_manifest
    document = f.db.get(EvidenceDocumentText, file_id)
    if digest is None:
        document.processing_manifest = None
    else:
        preparation = preparation_manifest()
        preparation['content']['source_files_sha256']['pdf_extraction.py'] = digest
        preparation['sha256'] = _digest(preparation['content'])
        document.processing_manifest = preparation
    f.db.commit()


def held_batch(f, *, statuses=('attention',), batch_status='review'):
    """A finished batch whose only file has periods in the given states."""
    batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status=batch_status,
        actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)),
        files=[dict(source_id=str(f.file.id), file_id=str(f.file.id), filename=f.file.original_filename,
            expected_revision='initial', status='checked')])
    f.db.add(batch)
    f.db.flush()
    items = []
    for index, status in enumerate(statuses):
        item = BatchItem(id=uuid5(batch.id, f'{f.file.id}:s{index}'), batch_id=batch.id, file_id=f.file.id,
            statement_key=f's{index}', status=status, summary=dict(source_id=str(f.file.id), revision='r'))
        f.db.add(item)
        items.append(item)
    f.db.commit()
    return batch, items


def selection(f):
    with f.SessionLocal() as db:
        selected, reasons = readers.candidates(db, f.case.id, READER_RECOVERY)
        return [entry['source_id'] for _, entry, _ in selected], reasons


def snapshot(f):
    with f.SessionLocal() as db:
        cutoff = recovery.activate(db, READER_RECOVERY_RELEASE)
        recovery.snapshot_case(db, f.case.id, cutoff, READER_RECOVERY)
        run = db.scalar(select(Run).where(Run.case_id == f.case.id, Run.release == READER_RECOVERY_RELEASE))
        return run.id, list(db.scalars(select(Item.id).where(Item.run_id == run.id)))


def entry_of(f, batch_id):
    with f.SessionLocal() as db:
        batch = db.get(Batch, batch_id)
        return batch.status, dict(batch.files[0])


def item_state(f, item_id):
    with f.SessionLocal() as db:
        item = db.get(Item, item_id)
        return item.status, dict(item.result)


# Registration and activation -------------------------------------------------

def test_campaign_is_registered_with_a_stable_release_and_off_by_default(monkeypatch):
    assert manifest(READER_RECOVERY_RELEASE) is READER_RECOVERY
    assert len(READER_RECOVERY_RELEASE) <= 64 and READER_RECOVERY.batch_reread
    monkeypatch.delenv(READER_RECOVERY_FLAG, raising=False)
    assert not reader_recovery_enabled()
    assert READER_RECOVERY not in recovery.scheduled_campaigns()
    for value in ('', '0', 'false', 'off', 'no', 'maybe'):
        assert not reader_recovery_enabled({READER_RECOVERY_FLAG: value})
    monkeypatch.setenv(READER_RECOVERY_FLAG, '1')
    assert recovery.scheduled_campaigns()[-1] is READER_RECOVERY
    assert recovery.scheduled_campaigns()[:-1] == recovery.CAMPAIGNS


def test_affected_revisions_are_exact_and_exclude_the_current_reader():
    assert CURRENT not in AFFECTED_EXTRACTION_SHA256
    assert len(set(AFFECTED_EXTRACTION_SHA256)) == len(AFFECTED_EXTRACTION_SHA256)
    assert all(len(value) == 64 and set(value) <= set('0123456789abcdef') for value in AFFECTED_EXTRACTION_SHA256)
    assert READER_RECOVERY.eligible(None, {'pdf_extraction.py': AFFECTED})
    assert not READER_RECOVERY.eligible(None, {'pdf_extraction.py': CURRENT})
    assert not READER_RECOVERY.eligible(None, {})


# Selection --------------------------------------------------------------------

def test_held_statement_from_an_affected_reader_is_selected_once(f):
    set_reader(f, f.file.id)
    held_batch(f, statuses=('attention', 'attention', 'superseded_reading'))
    assert selection(f)[0] == [str(f.file.id)]
    run_id, items = snapshot(f)
    assert len(items) == 1
    status, result = item_state(f, items[0])
    assert status == 'pending' and result['reader_recovery'] and len(result['held_items']) == 2
    assert result['extraction_sha256'] == AFFECTED
    snapshot(f)
    with f.SessionLocal() as db:
        assert len(list(db.scalars(select(Item.id).where(Item.run_id == run_id)))) == 1


def test_reader_gate_requires_a_recorded_affected_revision(f):
    held_batch(f)
    set_reader(f, f.file.id, None)
    assert selection(f) == ([], {'unrecorded_reader': 1})
    set_reader(f, f.file.id, CURRENT)
    assert selection(f) == ([], {'reader_not_affected': 1})
    set_reader(f, f.file.id, 'b' * 64)
    assert selection(f) == ([], {'reader_not_affected': 1})


def test_never_selects_statements_with_investigator_edits(f):
    set_reader(f, f.file.id)
    _, items = held_batch(f, statuses=('attention', 'attention'))
    items[1].review_request = dict(holder='Typed by the investigator')
    f.db.commit()
    assert selection(f) == ([], {'investigator_edits': 1})
    items[1].review_request = None
    f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_review_progress': {'': dict(request={})}}
    f.db.commit()
    assert selection(f) == ([], {'investigator_edits': 1})


@pytest.mark.parametrize('status,reason', [
    ('imported', 'saved_import'), ('pending_import', 'saved_import'), ('skipped', 'investigator_decision'),
    ('duplicate_ignored', 'investigator_decision'), ('removed', 'investigator_decision'),
    ('assigned', 'investigator_decision'), ('ready', 'not_all_held')])
def test_any_saved_import_decision_or_ready_period_protects_the_whole_file(f, status, reason):
    set_reader(f, f.file.id)
    held_batch(f, statuses=('attention', status))
    assert selection(f) == ([], {reason: 1})


def test_admitted_imports_duplicate_decisions_and_removals_are_protected(f):
    set_reader(f, f.file.id)
    held_batch(f)
    f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_duplicate_dispositions': {'': dict(status='ignored')}}
    f.db.commit()
    assert selection(f) == ([], {'duplicate_decision': 1})
    system = dict(status='not_duplicate', actor=dict(name='System'))
    for decided in (dict(system, actor=dict(user_id=str(f.user.id), name='Investigator')),
                    dict(system, history=[dict(status='ignored', actor=dict(name='System'))])):
        f.file.metadata_ = {**f.file.metadata_, 'financial_duplicate_dispositions': {'': decided}}
        f.db.commit()
        assert selection(f) == ([], {'duplicate_decision': 1})
    f.file.metadata_ = {**f.file.metadata_, 'financial_duplicate_dispositions': {'': system}}
    f.db.commit()
    assert selection(f)[1] == {'eligible': 1}
    f.file.metadata_ = {**f.file.metadata_, 'financial_duplicate_dispositions': {},
        'financial_file_visibility': dict(removed=True, revision='r2')}
    f.db.commit()
    assert selection(f) == ([], {'removed': 1})
    f.file.metadata_ = {**f.file.metadata_, 'financial_file_visibility': dict(removed=False, revision='r3'),
        'financial_import_removal': dict(id='x')}
    f.db.commit()
    assert selection(f) == ([], {'removed': 1})
    metadata = dict(f.file.metadata_)
    metadata.pop('financial_import_removal')
    f.file.metadata_ = metadata
    f.db.commit()
    assert selection(f)[1] == {'eligible': 1}
    receipt = f.confirm_legacy()
    with f.SessionLocal() as db:
        assert db.get(FinancialSourceDocument, __import__('uuid').UUID(receipt['source_document_id'])).status == 'admitted'
    selected, reasons = selection(f)
    assert selected == [] and set(reasons) <= {'saved_import', 'duplicate_decision'}
    metadata = dict(f.db.get(EvidenceFile, f.file.id).metadata_)
    metadata.pop('financial_duplicate_dispositions', None)
    f.db.get(EvidenceFile, f.file.id).metadata_ = metadata
    f.db.commit()
    assert selection(f) == ([], {'saved_import': 1})


def test_unfinished_standalone_and_shared_files_are_left_alone(f):
    set_reader(f, f.file.id)
    batch, _ = held_batch(f)
    for change, reason in ((dict(status='waiting'), 'not_prepared'), (dict(status='error'), 'not_prepared'),
                           (dict(standalone_import=True), 'standalone_import')):
        batch.files = [{**batch.files[0], **change}]
        f.db.commit()
        assert selection(f) == ([], {reason: 1})
    batch.files = [{**batch.files[0], 'status': 'checked', 'standalone_import': False}]
    f.db.add(Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review', actor=batch.actor,
        files=[dict(batch.files[0])]))
    f.db.commit()
    assert selection(f)[1] == {'several_batches': 2}


# Execution ----------------------------------------------------------------------

def test_hand_off_uses_the_batch_reading_path_and_is_idempotent(f):
    set_reader(f, f.file.id)
    batch, _ = held_batch(f)
    _, (item_id,) = snapshot(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, entry = entry_of(f, batch.id)
    assert status == 'preparing' and entry['status'] == 'waiting'
    assert entry['recovery']['fresh_reading'] and entry['recovery']['action'] == 'reader_recovery'
    assert entry['recovery']['read_from_file_id'] == str(f.file.id)
    attempt = entry['recovery']['attempt_id']
    assert item_state(f, item_id)[0] == 'waiting'
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert entry_of(f, batch.id)[1]['recovery']['attempt_id'] == attempt
    assert item_state(f, item_id)[0] == 'reading'


def test_an_edit_saved_after_scheduling_is_never_overwritten(f):
    set_reader(f, f.file.id)
    batch, items = held_batch(f)
    _, (item_id,) = snapshot(f)
    items[0].review_request = dict(holder='Typed after scheduling')
    f.db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = item_state(f, item_id)
    assert status == 'kept' and result['kept_reason'] == 'investigator_edits'
    batch_status, entry = entry_of(f, batch.id)
    assert batch_status == 'review' and entry['status'] == 'checked' and 'recovery' not in entry
    with f.SessionLocal() as db:
        assert db.get(BatchItem, items[0].id).review_request == dict(holder='Typed after scheduling')


def test_a_paused_batch_stays_paused(f):
    set_reader(f, f.file.id)
    batch, _ = held_batch(f)
    _, (item_id,) = snapshot(f)
    batch.status = 'paused'
    f.db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert item_state(f, item_id)[0] == 'waiting'
    batch_status, entry = entry_of(f, batch.id)
    assert batch_status == 'paused' and entry['status'] == 'checked' and 'recovery' not in entry


def test_end_to_end_new_reading_retires_only_the_unedited_held_period(f):
    """The batch worker reads a new version; the held period is retired, not edited."""
    from services.financial import import_batches
    set_reader(f, f.file.id)
    batch, (held,) = held_batch(f)
    _, (item_id,) = snapshot(f)
    with f.SessionLocal() as db:
        admitted = set(db.scalars(select(FinancialSourceDocument.id).where(FinancialSourceDocument.status == 'admitted')))
    recovery.recover_one(f.SessionLocal, item_id, Path)

    async def process_files(session, *, case_id, file_ids, preparation_mode, force_reprocess, requested_by_user_id):
        for file_id in file_ids:
            job = uuid4()
            old = session.get(EvidenceDocumentText, f.file.id)
            session.add(EvidenceDocumentText(evidence_file_id=file_id, engine_job_id=job, content=old.content,
                content_sha256=old.content_sha256, character_count=old.character_count,
                source_locations=old.source_locations, processing_manifest=None))
            for geometry in session.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == f.file.id)):
                session.add(EvidenceTableGeometry(evidence_file_id=file_id, page_number=geometry.page_number,
                    engine_job_id=job, payload=geometry.payload))
            session.get(EvidenceFile, file_id).status = 'processed'
        session.commit()
        return dict(job_ids=[str(uuid4()) for _ in file_ids])

    for _ in range(4):
        asyncio.run(import_batches.advance_batch(f.SessionLocal, batch.id, Path, process_files))
        if entry_of(f, batch.id)[1]['status'] == 'checked':
            break
    _, entry = entry_of(f, batch.id)
    assert entry['status'] == 'checked' and entry['file_id'] != str(f.file.id)
    with f.SessionLocal() as db:
        assert db.get(BatchItem, held.id).status == 'superseded_reading'
        assert db.get(BatchItem, held.id).review_request is None
        version = db.get(EvidenceFile, __import__('uuid').UUID(entry['file_id']))
        assert version.metadata_['statement_parent_evidence_id'] == str(f.file.id)
        assert version.metadata_['statement_version_request'] == entry['recovery']['attempt_id']
        fresh = list(db.scalars(select(BatchItem).where(BatchItem.batch_id == batch.id, BatchItem.file_id == version.id)))
        assert fresh
        assert set(db.scalars(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.status == 'admitted'))) == admitted  # nothing admitted
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = item_state(f, item_id)
    assert status == 'recovered' and result['review_file_id'] == entry['file_id'], result
    assert sum(result['periods'].values()) == len(fresh)
