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
    READER_RECOVERY_FLAG, READER_RECOVERY_RELEASE, READER_RELEASE_PREFIX, manifest, reader_campaign,
    reader_recovery_enabled)
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


@pytest.fixture(autouse=True)
def free_engine():
    """No evidence counted as being read elsewhere unless a test says so."""
    readers._busy.clear()
    yield
    readers._busy.clear()


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
        return [entry['source_id'] for _, entry, _, _ in selected], reasons


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

def test_engine_release_campaign_is_on_by_default_and_named_by_the_deployed_engine(monkeypatch):
    assert manifest(READER_RECOVERY_RELEASE) is READER_RECOVERY  # history: still resolvable
    monkeypatch.delenv(READER_RECOVERY_FLAG, raising=False)
    assert reader_recovery_enabled()
    campaign = recovery.scheduled_campaigns()[-1]
    assert recovery.scheduled_campaigns()[:-1] == recovery.CAMPAIGNS
    assert campaign.release == READER_RELEASE_PREFIX + CURRENT[:32] and len(campaign.release) <= 64
    assert campaign.batch_reread and campaign.current_readers == {'pdf_extraction.py': CURRENT}
    assert manifest(campaign.release).current_readers == campaign.current_readers
    for value in ('0', 'false', 'off', 'no', ' OFF '):
        assert not reader_recovery_enabled({READER_RECOVERY_FLAG: value})
        monkeypatch.setenv(READER_RECOVERY_FLAG, value)
        assert recovery.scheduled_campaigns() == recovery.CAMPAIGNS
    for value in ('', '1', 'on', 'yes'):
        assert reader_recovery_enabled({READER_RECOVERY_FLAG: value})


def test_engine_release_campaign_selects_any_other_recorded_engine_source():
    campaign = reader_campaign()
    assert campaign.eligible(None, {'pdf_extraction.py': AFFECTED})
    assert campaign.eligible(None, {'pdf_extraction.py': 'b' * 64})  # no hand-kept list needed
    assert not campaign.eligible(None, {'pdf_extraction.py': CURRENT})
    assert not campaign.eligible(None, {'pdf_extraction.py': None}) and not campaign.eligible(None, {})
    unknown = reader_campaign(READER_RELEASE_PREFIX + 'x')
    unknown_current = type(unknown)(unknown.release, current_readers={'pdf_extraction.py': None}, batch_reread=True)
    assert not unknown_current.eligible(None, {'pdf_extraction.py': AFFECTED})


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
    # The second batch holds the file but no period of it: nothing to re-prepare there.
    assert selection(f)[1] == {'eligible': 2}


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


# Engine releases ------------------------------------------------------------------

def engine_snapshot(f, campaign):
    with f.SessionLocal() as db:
        cutoff = recovery.activate(db, campaign.release)
        recovery.snapshot_case(db, f.case.id, cutoff, campaign)
        return list(db.scalars(select(Run).where(Run.case_id == f.case.id).order_by(Run.created_at)))


def test_each_engine_release_is_one_run_per_case_and_unchanged_code_starts_none(f, monkeypatch):
    from services.financial import recovery_campaigns
    set_reader(f, f.file.id, AFFECTED)
    held_batch(f)
    first = reader_campaign()
    runs = engine_snapshot(f, first)
    assert [run.release for run in runs] == [first.release]
    with f.SessionLocal() as db:
        (item,) = db.scalars(select(Item).where(Item.run_id == runs[0].id))
        assert item.status == 'pending' and item.result['extraction_sha256'] == AFFECTED
    # A restart on unchanged code: the same release, no second run or item.
    assert [run.release for run in engine_snapshot(f, reader_campaign())] == [first.release]
    # The next engine release: a second run; the statement not yet handed off moves to it.
    monkeypatch.setattr(recovery_campaigns, '_engine_digest', ['c' * 64])
    second = reader_campaign()
    assert second.release != first.release and second.release.startswith(READER_RELEASE_PREFIX)
    runs = engine_snapshot(f, second)
    assert [run.release for run in runs] == [first.release, second.release]
    with f.SessionLocal() as db:
        earlier = db.get(Item, item.id)
        assert earlier.status == 'kept' and earlier.result['kept_reason'] == 'newer_release'
        assert [i.file_id for i in db.scalars(select(Item).where(Item.run_id == runs[1].id))] == [f.file.id]


def test_a_reading_made_by_todays_engine_is_never_scheduled(f):
    set_reader(f, f.file.id, CURRENT)
    held_batch(f)
    runs = engine_snapshot(f, reader_campaign())
    assert runs[0].status == 'complete'
    with f.SessionLocal() as db:
        assert not list(db.scalars(select(Item).where(Item.run_id == runs[0].id)))


def two_batch_original(f, *, second_statuses=('attention',)):
    """The same original prepared in two finished batches (the live several-batches shape)."""
    from datetime import timedelta
    older, items = held_batch(f)
    newer = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review', actor=older.actor,
        files=[dict(older.files[0])])
    f.db.add(newer)
    f.db.flush()
    older.created_at = newer.created_at - timedelta(days=2)
    for index, status in enumerate(second_statuses):
        f.db.add(BatchItem(id=uuid5(newer.id, f'{f.file.id}:s{index}'), batch_id=newer.id, file_id=f.file.id,
            statement_key=f's{index}', status=status, summary=dict(source_id=str(f.file.id), revision='r')))
    f.db.commit()
    return older, newer


def test_an_original_in_several_batches_is_read_once_and_each_batch_prepares_from_it(f):
    set_reader(f, f.file.id)
    older, newer = two_batch_original(f)
    selected, reasons = selection(f)
    assert selected == [str(f.file.id)] and reasons == {'eligible': 2}
    _, (item_id,) = snapshot(f)
    _, result = item_state(f, item_id)
    assert {m['batch_id'] for m in result['members']} == {str(older.id), str(newer.id)}
    assert result['batch_id'] == str(newer.id) and len(result['held_items']) == 2
    recovery.recover_one(f.SessionLocal, item_id, Path)
    (_, first), (_, second) = entry_of(f, older.id), entry_of(f, newer.id)
    # One earlier reading, one attempt: the batches' retry path makes one new version for both.
    assert first['recovery']['attempt_id'] == second['recovery']['attempt_id']
    assert first['status'] == second['status'] == 'waiting'
    status, result = item_state(f, item_id)
    assert status == 'waiting' and len(result['handoff']['batches']) == 2


@pytest.mark.parametrize('change,reason', [('edit', 'investigator_edits'), ('ready', 'not_all_held'),
                                           ('imported', 'saved_import')])
def test_work_in_any_batch_of_the_original_protects_it_everywhere(f, change, reason):
    set_reader(f, f.file.id)
    older, newer = two_batch_original(f, second_statuses=('attention', 'attention'))
    with f.SessionLocal() as db:
        item = db.get(BatchItem, uuid5(newer.id, f'{f.file.id}:s1'))
        if change == 'edit':
            item.review_request = dict(holder='Typed by the investigator')
        else:
            item.status = change
        db.commit()
    assert selection(f) == ([], {reason: 2})


def test_an_original_another_batch_took_after_scheduling_is_left(f):
    set_reader(f, f.file.id)
    older, newer = two_batch_original(f)
    _, (item_id,) = snapshot(f)
    f.db.add(Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review', actor=older.actor,
        files=[dict(older.files[0])]))
    f.db.commit()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = item_state(f, item_id)
    assert status == 'kept' and result['kept_reason'] == 'several_batches'
    assert entry_of(f, older.id)[1]['status'] == entry_of(f, newer.id)[1]['status'] == 'checked'


def test_hand_offs_are_bounded_and_wait_for_other_evidence_to_be_read(f, monkeypatch):
    set_reader(f, f.file.id)
    batch, _ = held_batch(f)
    _, (item_id,) = snapshot(f)
    monkeypatch.setattr(readers, 'READ_AGAIN_AT_ONCE', 1)
    monkeypatch.setattr(readers, 'in_flight', lambda session: 1)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = item_state(f, item_id)
    assert status == 'waiting' and 'Waiting its turn' in result['message'] and 'handoff' not in result
    assert entry_of(f, batch.id)[1]['status'] == 'checked'
    monkeypatch.setattr(readers, 'in_flight', lambda session: 0)
    readers._busy.update(at=__import__('time').monotonic(), count=3)  # an upload is being ingested
    recovery.recover_one(f.SessionLocal, item_id, Path)
    status, result = item_state(f, item_id)
    assert status == 'waiting' and 'other evidence' in result['message']
    readers._busy.clear()
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert item_state(f, item_id)[0] == 'waiting' and entry_of(f, batch.id)[1]['status'] == 'waiting'
    assert 'handoff' in item_state(f, item_id)[1]


def test_scheduled_statements_count_as_being_rechecked_in_the_queue(f):
    from services.financial.review_queue import REREAD_BUCKETS, _rechecked_by_recovery
    set_reader(f, f.file.id)
    held_batch(f)
    snapshot(f)
    entries = [dict(bucket='waiting', file_ids=[str(f.file.id)]), dict(bucket='ready', file_ids=[str(f.file.id)]),
               dict(bucket='waiting', file_ids=[str(uuid4())])]
    with f.SessionLocal() as db:
        _rechecked_by_recovery(db, f.case.id, entries)
    assert [e['bucket'] for e in entries] == ['rechecking', 'ready', 'waiting'] and 'ready' not in REREAD_BUCKETS
