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
    reader_recovery_enabled, reader_release_id)
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
    assert campaign.release == reader_release_id(CURRENT) and len(campaign.release) <= 64
    assert campaign.release.startswith(READER_RELEASE_PREFIX)
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


def test_statements_with_investigator_edits_are_selected_to_carry_them_unless_switched_off(f, monkeypatch):
    from services.financial import reread_carry
    set_reader(f, f.file.id)
    _, items = held_batch(f, statuses=('attention', 'attention'))
    items[1].review_request = dict(holder='Typed by the investigator')
    f.db.commit()
    assert selection(f) == ([str(f.file.id)], {'eligible': 1})
    monkeypatch.setattr(reread_carry, 'CARRY_EDITS', False)
    assert selection(f) == ([], {'investigator_edits': 1})
    items[1].review_request = None
    f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_review_progress': {'': dict(request={})}}
    f.db.commit()
    assert selection(f) == ([], {'investigator_edits': 1})
    monkeypatch.setattr(reread_carry, 'CARRY_EDITS', True)
    assert selection(f) == ([str(f.file.id)], {'eligible': 1})


@pytest.mark.parametrize('status,reason', [
    ('pending_import', 'saved_import'), ('skipped', 'investigator_decision'),
    ('duplicate_ignored', 'investigator_decision'), ('removed', 'investigator_decision'),
    ('assigned', 'investigator_decision'), ('ready', 'not_all_held')])
def test_any_saved_import_decision_or_ready_period_protects_the_whole_file(f, status, reason):
    set_reader(f, f.file.id)
    held_batch(f, statuses=('attention', status))
    assert selection(f) == ([], {reason: 1})


def test_a_statement_saved_without_edits_no_longer_protects_the_held_ones_of_its_file(f, monkeypatch):
    """SETTLED_SIBLINGS: the saved statement is left alone; only the held one is read again."""
    set_reader(f, f.file.id)
    held_batch(f, statuses=('attention', 'imported'))
    assert selection(f)[1] == {'eligible': 1}
    monkeypatch.setattr(readers, 'SETTLED_SIBLINGS', False)
    assert selection(f) == ([], {'saved_import': 1})


def test_a_stale_ready_listing_of_a_saved_statement_does_not_protect_but_any_other_ready_one_does(f):
    """Another batch lists, as ready, the statement this original already saved (it can never be saved again)."""
    set_reader(f, f.file.id)
    older, newer = two_batch_original(f, second_statuses=())
    with f.SessionLocal() as db:
        db.add(BatchItem(id=uuid5(older.id, f'{f.file.id}:s1'), batch_id=older.id, file_id=f.file.id,
            statement_key='s1', status='imported', summary=dict(source_id=str(f.file.id), revision='r')))
        db.add(BatchItem(id=uuid5(newer.id, f'{f.file.id}:s1'), batch_id=newer.id, file_id=f.file.id,
            statement_key='s1', status='ready', summary=dict(source_id=str(f.file.id), revision='r')))
        db.commit()
    selected, reasons = selection(f)
    assert selected == [str(f.file.id)] and reasons == {'eligible': 2}
    with f.SessionLocal() as db:
        db.get(BatchItem, uuid5(newer.id, f'{f.file.id}:s1')).statement_key = 's2'
        db.commit()
    assert selection(f) == ([], {'not_all_held': 2})


def test_a_copy_the_system_set_aside_does_not_protect_but_a_persons_decision_does(f, monkeypatch):
    set_reader(f, f.file.id)
    held_batch(f, statuses=('attention', 'duplicate_ignored'))
    system = dict(status='ignored', actor=dict(name='System'),
                  history=[dict(status='needs_comparison', actor=dict(name='System'))])
    for value, expected in ((system, {'eligible': 1}),
                            (dict(system, actor=dict(name='Investigator', user_id=str(f.user.id))), {'duplicate_decision': 1}),
                            (dict(system, history=[dict(status='retained', actor=dict(user_id=str(f.user.id)))]), {'duplicate_decision': 1}),
                            (dict(status='ignored'), {'duplicate_decision': 1}),  # no recorded actor: a person's
                            (dict(system, status='restored'), {'duplicate_decision': 1})):
        f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_duplicate_dispositions': {'s1': value}}
        f.db.commit()
        assert selection(f)[1] == expected, value
    f.file.metadata_ = {**f.file.metadata_, 'financial_duplicate_dispositions': {'s1': system}}
    f.db.commit()
    monkeypatch.setattr(readers, 'SETTLED_SIBLINGS', False)
    assert selection(f) == ([], {'duplicate_decision': 1})


def test_admitted_imports_duplicate_decisions_and_removals_are_protected(f):
    set_reader(f, f.file.id)
    held_batch(f)
    f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_duplicate_dispositions': {'': dict(status='ignored')}}
    f.db.commit()
    assert selection(f) == ([], {'duplicate_decision': 1})
    system = dict(status='not_duplicate', actor=dict(name='System'))
    for decided in (dict(system, actor=dict(user_id=str(f.user.id), name='Investigator')),
                    dict(system, history=[dict(status='ignored')])):
        f.file.metadata_ = {**f.file.metadata_, 'financial_duplicate_dispositions': {'': decided}}
        f.db.commit()
        assert selection(f) == ([], {'duplicate_decision': 1})
    # A set-aside the System made by itself is a projection the new reading recomputes (SETTLED_SIBLINGS).
    f.file.metadata_ = {**f.file.metadata_, 'financial_duplicate_dispositions': {'': dict(system,
        history=[dict(status='ignored', actor=dict(name='System'))])}}
    f.db.commit()
    assert selection(f)[1] == {'eligible': 1}
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


def test_an_edit_saved_after_scheduling_is_never_overwritten(f, monkeypatch):
    from services.financial import reread_carry
    monkeypatch.setattr(reread_carry, 'CARRY_EDITS', False)
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
                                           ('pending_import', 'saved_import'), ('skipped', 'investigator_decision')])
def test_work_in_any_batch_of_the_original_protects_it_everywhere(f, change, reason, monkeypatch):
    from services.financial import reread_carry
    monkeypatch.setattr(reread_carry, 'CARRY_EDITS', False)  # edits carried: see the carry tests
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


def test_a_processing_file_counts_as_being_read_only_while_an_engine_job_works_on_it(f):
    from sqlalchemy import text
    f.db.execute(text('CREATE TABLE jobs (id TEXT PRIMARY KEY, source_evidence_file_id CHAR(32), status TEXT, paused BOOLEAN)'))
    readers._jobs_visible.clear()
    try:
        f.file.status = 'processing'
        f.db.commit()
        # The stuck file: still "processing", its engine job long failed. It must not hold re-reads back.
        f.db.execute(text("INSERT INTO jobs VALUES ('a', :file, 'failed', 0)"), dict(file=f.file.id.hex))
        f.db.commit()
        assert readers.evidence_being_read(f.db) == 0
        readers._busy.clear()
        f.db.execute(text("UPDATE jobs SET status = 'pending', paused = 1"))
        f.db.commit()
        assert readers.evidence_being_read(f.db) == 0  # paused work is not being read
        readers._busy.clear()
        f.db.execute(text("UPDATE jobs SET paused = 0"))
        f.db.commit()
        assert readers.evidence_being_read(f.db) == 1  # queued or running work still holds re-reads back
        readers._busy.clear()
        f.db.execute(text("UPDATE jobs SET status = 'extracting_entities'"))
        f.db.commit()
        assert readers.evidence_being_read(f.db) == 1
    finally:
        readers._jobs_visible.clear()
        readers._busy.clear()


# Selection rules and restarts (aq-b-santander) -------------------------------------

def test_a_change_to_the_selection_rules_is_a_new_release_of_the_same_engine(f, monkeypatch):
    """The snapshot is once per release id: new selection rules on an unchanged engine must snapshot again."""
    from services.financial import recovery_campaigns
    set_reader(f, f.file.id, AFFECTED)
    held_batch(f)
    first = reader_campaign()
    assert [run.release for run in engine_snapshot(f, first)] == [first.release]
    monkeypatch.setattr(recovery_campaigns, 'READER_SELECTION', 'held-selection-test')
    second = reader_campaign()
    assert second.current_readers == first.current_readers and second.release != first.release
    runs = engine_snapshot(f, second)
    assert [run.release for run in runs] == [first.release, second.release]


def _restart(f, *, removed_at, batch_made, reading_made=None, removal=True, hidden=True):
    """The original removed (imports and/or file list) at ``removed_at``; a later batch holds a newer reading of it."""
    from datetime import datetime, timezone
    from services.evidence_db_storage import EvidenceDBStorage
    reading = EvidenceDBStorage.add_files(f.db, f.case.id, [dict(original_filename='version.pdf',
        stored_path=f.file.stored_path, sha256=f.file.sha256, size=f.file.size)], folder_id=f.file.folder_id,
        created_by_id=f.user.id)[0]
    reading.status = 'processed'
    old = f.db.get(EvidenceDocumentText, f.file.id)
    f.db.add(EvidenceDocumentText(evidence_file_id=reading.id, engine_job_id=old.engine_job_id, content=old.content,
        content_sha256=old.content_sha256, character_count=old.character_count,
        source_locations=old.source_locations, processing_manifest=old.processing_manifest))
    f.db.flush()
    set_reader(f, reading.id)
    stamp = removed_at.isoformat() if removed_at else None
    metadata = dict(f.file.metadata_ or {})
    if removal:
        metadata['financial_import_removal'] = dict(id='reset-1', restart_file_id=str(f.file.id),
            **({'at': stamp} if stamp else {}))
    if hidden:
        metadata['financial_file_visibility'] = dict(removed=True, revision='reset-1', **({'changed_at': stamp} if stamp else {}))
    f.file.metadata_ = metadata
    reading.created_at = reading_made or batch_made
    batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review', created_at=batch_made,
        actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)),
        files=[dict(source_id=str(f.file.id), file_id=str(reading.id), filename='version.pdf',
            expected_revision='reset-1', status='checked')])
    f.db.add(batch)
    f.db.flush()
    f.db.add(BatchItem(id=uuid5(batch.id, f'{reading.id}:s0'), batch_id=batch.id, file_id=reading.id,
        statement_key='s0', status='attention', summary=dict(source_id=str(f.file.id), revision='r')))
    f.db.commit()
    return batch, reading


def test_a_restart_after_removal_is_read_again_when_its_new_batch_holds_it(f):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    _restart(f, removed_at=now - timedelta(days=30), batch_made=now - timedelta(days=1))
    with f.SessionLocal() as db:
        selected, reasons = readers.candidates(db, f.case.id, reader_campaign())
    assert reasons == {'eligible': 1} and len(selected) == 1


@pytest.mark.parametrize('case', ['removed_after_batch', 'removed_after_reading', 'no_time', 'reading_removed',
                                  'switched_off', 'same_file'])
def test_a_removal_is_still_protected_unless_it_provably_preceded_the_restart(f, monkeypatch, case):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    removed, made, reading_made = now - timedelta(days=30), now - timedelta(days=1), None
    if case == 'removed_after_batch':
        removed = now
    if case == 'removed_after_reading':
        reading_made = now - timedelta(days=40)
    if case == 'switched_off':
        monkeypatch.setattr(readers, 'RESTARTED_AFTER_REMOVAL', False)
    if case == 'same_file':
        set_reader(f, f.file.id)
        f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_import_removal': dict(id='x', at=removed.isoformat())}
        f.db.commit()
        held_batch(f)
    else:
        _, reading = _restart(f, removed_at=None if case == 'no_time' else removed, batch_made=made,
                              reading_made=reading_made)
        if case == 'reading_removed':
            reading.metadata_ = {**(reading.metadata_ or {}), 'financial_file_visibility': dict(removed=True, revision='r9')}
            f.db.commit()
    with f.SessionLocal() as db:
        selected, reasons = readers.candidates(db, f.case.id, reader_campaign())
    assert selected == [] and reasons == {'removed': 1}


def test_a_restart_with_investigator_work_stays_protected(f, monkeypatch):
    from services.financial import reread_carry
    monkeypatch.setattr(reread_carry, 'CARRY_EDITS', False)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    batch, reading = _restart(f, removed_at=now - timedelta(days=30), batch_made=now - timedelta(days=1))
    item = f.db.get(BatchItem, uuid5(batch.id, f'{reading.id}:s0'))
    item.review_request = dict(holder='Typed by the investigator')
    f.db.commit()
    with f.SessionLocal() as db:
        selected, reasons = readers.candidates(db, f.case.id, reader_campaign())
    assert selected == [] and reasons == {'investigator_edits': 1}


def _copy_reading(f):
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
    return process_files


def test_end_to_end_a_saved_statement_of_the_file_is_never_saved_again_by_the_new_reading(f):
    """SETTLED_SIBLINGS safety: the held statement is read again; the saved one is not admitted a second time."""
    from services.financial import import_batches, queue_save
    from services.financial.statement_import import read_statement_import
    set_reader(f, f.file.id)
    receipt = f.confirm_legacy()
    # Saved by the System's automatic save: its recorded dispositions carry the System, not a person.
    f.db.refresh(f.file)
    metadata = dict(f.file.metadata_ or {})
    metadata['financial_duplicate_dispositions'] = {key: {**value, 'actor': dict(name='System')} for key, value in
        (metadata.get('financial_duplicate_dispositions') or {}).items()}
    f.file.metadata_ = metadata
    f.db.commit()
    with f.SessionLocal() as db:
        key = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id).get('statement_id') or ''
        admitted = set(db.scalars(select(FinancialSourceDocument.id).where(FinancialSourceDocument.status == 'admitted')))
    assert admitted
    batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review',
        actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)),
        files=[dict(source_id=str(f.file.id), file_id=str(f.file.id), filename=f.file.original_filename,
            expected_revision='initial', status='checked')])
    f.db.add(batch)
    f.db.flush()
    f.db.add_all([BatchItem(id=uuid5(batch.id, f'{f.file.id}:{key}'), batch_id=batch.id, file_id=f.file.id,
            statement_key=key, status='imported', summary=dict(source_id=str(f.file.id), revision='r',
            source_document_id=receipt['source_document_id'])),
        BatchItem(id=uuid5(batch.id, f'{f.file.id}:held'), batch_id=batch.id, file_id=f.file.id,
            statement_key='held', status='attention', summary=dict(source_id=str(f.file.id), revision='r'))])
    f.db.commit()
    with f.SessionLocal() as db:
        selected, reasons = readers.candidates(db, f.case.id, reader_campaign())
    assert reasons == {'eligible': 1}
    campaign = reader_campaign()
    with f.SessionLocal() as db:
        cutoff = recovery.activate(db, campaign.release)
        recovery.snapshot_case(db, f.case.id, cutoff, campaign)
        (item_id,) = list(db.scalars(select(Item.id).join(Run, Item.run_id == Run.id).where(Run.release == campaign.release)))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert entry_of(f, batch.id)[1]['status'] == 'waiting'
    for _ in range(6):
        asyncio.run(import_batches.advance_batch(f.SessionLocal, batch.id, Path, _copy_reading(f)))
        if entry_of(f, batch.id)[1]['status'] == 'checked' and entry_of(f, batch.id)[0] != 'preparing':
            break
    _, entry = entry_of(f, batch.id)
    assert entry['status'] == 'checked' and entry['file_id'] != str(f.file.id), entry
    for _ in range(3):
        queue_save.sweep_save(f.SessionLocal, budget_seconds=None)
        asyncio.run(import_batches.advance_batch(f.SessionLocal, batch.id, Path, _copy_reading(f)))
    with f.SessionLocal() as db:
        assert db.get(BatchItem, uuid5(batch.id, f'{f.file.id}:{key}')).status == 'imported'  # untouched
        assert db.get(BatchItem, uuid5(batch.id, f'{f.file.id}:held')).status == 'superseded_reading'
        twins = list(db.scalars(select(BatchItem).where(BatchItem.batch_id == batch.id,
            BatchItem.file_id == __import__('uuid').UUID(entry['file_id']))))
        # The new reading recognises the saved statement as the one already admitted (same record), so it is
        # listed as saved without a second admission.
        assert twins and all(twin.status != 'pending_import' and (twin.status != 'imported' or
            __import__('uuid').UUID(twin.summary['source_document_id']) in admitted) for twin in twins), \
            [(twin.statement_key, twin.status) for twin in twins]
        assert set(db.scalars(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.status == 'admitted'))) == admitted


def test_end_to_end_a_copy_the_system_set_aside_does_not_stop_the_batch_reading_again(f):
    """The batch's own fresh-reading guard (import_batches._prepare_retry) agrees with the selection."""
    from services.financial import import_batches
    set_reader(f, f.file.id)
    batch, (held, copy) = held_batch(f, statuses=('attention', 'duplicate_ignored'))
    f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_duplicate_dispositions': {
        's1': dict(status='ignored', actor=dict(name='System'))}}
    f.db.commit()
    campaign = reader_campaign()
    with f.SessionLocal() as db:
        recovery.snapshot_case(db, f.case.id, recovery.activate(db, campaign.release), campaign)
        (item_id,) = list(db.scalars(select(Item.id).join(Run, Item.run_id == Run.id).where(Run.release == campaign.release)))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    for _ in range(6):
        asyncio.run(import_batches.advance_batch(f.SessionLocal, batch.id, Path, _copy_reading(f)))
        if entry_of(f, batch.id)[1]['status'] in ('checked', 'error'):
            break
    _, entry = entry_of(f, batch.id)
    assert entry['status'] == 'checked' and entry['file_id'] != str(f.file.id), entry.get('error')
    with f.SessionLocal() as db:
        assert db.get(BatchItem, copy.id).status == 'duplicate_ignored'
        assert db.get(BatchItem, held.id).status == 'superseded_reading'


@pytest.mark.parametrize('holds', [False, True])
def test_a_failed_batch_file_holding_nothing_does_not_keep_the_original_from_being_read_again(f, monkeypatch, holds):
    """FAILED_MEMBER_IDLE: the other batch's failed preparation is left as it is; the held statements are read."""
    set_reader(f, f.file.id)
    older, newer = two_batch_original(f, second_statuses=())
    newer.files = [{**newer.files[0], 'status': 'error', 'error': 'failed'}]
    if holds:
        f.db.add(BatchItem(id=uuid5(newer.id, f'{f.file.id}:x'), batch_id=newer.id, file_id=f.file.id,
            statement_key='x', status='attention', summary=dict(source_id=str(f.file.id), revision='r')))
    f.db.commit()
    selected, reasons = selection(f)
    if holds:  # a failed file that still lists statements is not idle: nothing changes
        assert selected == [] and reasons == {'not_prepared': 1, 'several_batches': 1}
        return
    assert selected == [str(f.file.id)] and reasons == {'eligible': 2}
    with monkeypatch.context() as off:
        off.setattr(readers, 'FAILED_MEMBER_IDLE', False)
        assert selection(f) == ([], {'not_prepared': 1, 'several_batches': 1})
    _, (item_id,) = snapshot(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    (_, first), (status, second) = entry_of(f, older.id), entry_of(f, newer.id)
    assert first['status'] == 'waiting' and first['recovery']['action'] == 'reader_recovery'
    assert second['status'] == 'error' and 'recovery' not in second  # left exactly as it was


def test_a_held_copy_of_a_period_another_original_saved_is_left_for_comparison(f, monkeypatch):
    """COPY_OF_SAVED_PROTECTS: other bytes already saved this account and period; no new reading may save it."""
    from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
    from services.evidence_db_storage import EvidenceDBStorage
    set_reader(f, f.file.id)
    receipt = f.confirm_legacy()
    with f.SessionLocal() as db:
        period = db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == __import__('uuid').UUID(receipt['source_document_id'])))
        account = db.get(FinancialAccount, period.account_id)
        start, end = period.period_start.isoformat(), period.period_end.isoformat()
        number = account.identifier_as_printed or account.identifier_normalised
    other = EvidenceDBStorage.add_files(f.db, f.case.id, [dict(original_filename='other.pdf', stored_path=f.file.stored_path,
        sha256='e' * 64, size=1)], folder_id=f.file.folder_id, created_by_id=f.user.id)[0]
    f.db.flush()
    document = f.db.get(FinancialSourceDocument, __import__('uuid').UUID(receipt['source_document_id']))
    document.evidence_file_id = other.id  # the period was saved from other bytes
    f.db.commit()
    metadata = dict(f.db.get(EvidenceFile, f.file.id).metadata_ or {})
    metadata.pop('financial_duplicate_dispositions', None)
    f.db.get(EvidenceFile, f.file.id).metadata_ = metadata
    f.db.commit()
    _, (held,) = held_batch(f)
    with f.SessionLocal() as db:
        db.get(BatchItem, held.id).summary = dict(source_id=str(f.file.id), revision='r', period_start=start,
            period_end=end, account=number)
        db.commit()
    assert selection(f) == ([], {'copy_of_saved': 1})
    with f.SessionLocal() as db:
        db.get(BatchItem, held.id).summary = dict(source_id=str(f.file.id), revision='r', period_start=start,
            period_end=end, account='999')  # another account: not a copy of it
        db.commit()
    assert selection(f)[1] == {'eligible': 1}
    with f.SessionLocal() as db:
        db.get(BatchItem, held.id).summary = dict(source_id=str(f.file.id), revision='r', period_start=start,
            period_end=end, account=number)
        db.commit()
    with f.SessionLocal() as db:
        db.get(BatchItem, held.id).summary = dict(source_id=str(f.file.id), revision='r', period_start=start,
            period_end=end, account='x' + number[-6:])  # an older reading that misread the leading digits
        db.commit()
    assert selection(f) == ([], {'copy_of_saved': 1})
    document = f.db.get(FinancialSourceDocument, __import__('uuid').UUID(receipt['source_document_id']))
    document.evidence_file_id = f.file.id  # saved from these same bytes under another statement key
    f.db.commit()
    selected, reasons = selection(f)
    assert selected == [] and set(reasons) <= {'copy_of_saved', 'saved_import'}
    document.evidence_file_id = other.id
    f.db.commit()
    monkeypatch.setattr(readers, 'COPY_OF_SAVED_PROTECTS', False)
    assert selection(f)[1] == {'eligible': 1}


def _worked_batch(f):
    """A held statement of f.file carrying an investigator's saved progress and the same batch draft."""
    from services.financial.import_batches import initial_request
    from services.financial.statement_import import read_statement_import
    set_reader(f, f.file.id)
    with f.SessionLocal() as db:
        proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id)
    key = proposal.get('statement_id') or ''
    request = initial_request(proposal)
    request['holder'] = 'Typed by the investigator'
    row = next(r for r in request['rows'] if not r['excluded'])
    row['description'] = 'Corrected by the investigator'
    row['reason'] = 'Printed text was cut off'
    saved_by = dict(user_id=str(f.user.id), name='Investigator')
    f.file.metadata_ = {**(f.file.metadata_ or {}), 'financial_review_progress': {key: dict(request=request,
        review_revision='rev', saved_at='2026-10-01T00:00:00+00:00', saved_by=saved_by)}}
    batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review',
        actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)),
        files=[dict(source_id=str(f.file.id), file_id=str(f.file.id), filename=f.file.original_filename,
            expected_revision='initial', status='checked')])
    f.db.add(batch)
    f.db.flush()
    item = BatchItem(id=uuid5(batch.id, f'{f.file.id}:{key}'), batch_id=batch.id, file_id=f.file.id,
        statement_key=key, status='attention', review_request=request,
        summary=dict(source_id=str(f.file.id), revision=proposal['revision'], review_saved_by=saved_by))
    f.db.add(item)
    f.db.commit()
    return batch, item.id, key, request, row['id']


def _run_reread(f, batch):
    from services.financial import import_batches
    campaign = reader_campaign()
    with f.SessionLocal() as db:
        cutoff = recovery.activate(db, campaign.release)
        recovery.snapshot_case(db, f.case.id, cutoff, campaign)
        (item_id,) = list(db.scalars(select(Item.id).join(Run, Item.run_id == Run.id).where(Run.release == campaign.release)))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    return item_id


def _advance(f, batch):
    from services.financial import import_batches
    for _ in range(6):
        asyncio.run(import_batches.advance_batch(f.SessionLocal, batch.id, Path, _copy_reading(f)))
        if entry_of(f, batch.id)[1]['status'] in ('checked', 'error') and entry_of(f, batch.id)[0] != 'preparing':
            break
    return entry_of(f, batch.id)[1]


def test_end_to_end_a_new_reading_carries_the_investigators_work_unchanged(f):
    """Neil 2026-10-24: re-read statements with saved work, keeping every edit; both readings stay in history."""
    batch, old_id, key, request, edited_row = _worked_batch(f)
    with f.SessionLocal() as db:
        admitted = set(db.scalars(select(FinancialSourceDocument.id).where(FinancialSourceDocument.status == 'admitted')))
    _run_reread(f, batch)
    assert entry_of(f, batch.id)[1].get('recovery', {}).get('carry_work')
    entry = _advance(f, batch)
    assert entry['status'] == 'checked' and entry['file_id'] != str(f.file.id), entry
    with f.SessionLocal() as db:
        old = db.get(BatchItem, old_id)
        assert old.status == 'superseded_reading' and old.review_request == request  # her draft kept in history
        assert db.get(EvidenceFile, f.file.id).metadata_['financial_review_progress'][key]['request'] == request
        version = db.get(EvidenceFile, __import__('uuid').UUID(entry['file_id']))
        (new_key, record), = version.metadata_['financial_review_progress'].items()
        assert record['saved_by']['name'] == 'Investigator' and record['carried_by']['name'] == 'System'
        assert record['carried_from']['evidence_file_id'] == str(f.file.id) and record['carried_from']['statement_id'] == key
        carried = record['request']
        assert carried['holder'] == 'Typed by the investigator'
        row = next(r for r in carried['rows'] if r['description'] == 'Corrected by the investigator')
        assert row['reason'] == 'Printed text was cut off'
        fresh = list(db.scalars(select(BatchItem).where(BatchItem.batch_id == batch.id, BatchItem.file_id == version.id)))
        assert [item.review_request for item in fresh] == [carried]
        assert fresh[0].summary['reread_carry']['carried'] is True
        assert fresh[0].status in ('ready', 'attention')
        # Her edits are never saved by System: nothing new is admitted without a person.
        assert set(db.scalars(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.status == 'admitted'))) == admitted


def test_work_saved_after_the_reread_was_scheduled_is_never_carried_unseen(f):
    batch, old_id, key, request, _ = _worked_batch(f)
    _run_reread(f, batch)
    with f.SessionLocal() as db:
        item = db.get(BatchItem, old_id)
        item.review_request = {**request, 'holder': 'Typed after scheduling'}
        db.commit()
    entry = _advance(f, batch)
    with f.SessionLocal() as db:
        item = db.get(BatchItem, old_id)
        assert item.review_request['holder'] == 'Typed after scheduling' and item.status == 'attention'
        assert entry['file_id'] == str(f.file.id) or not db.get(EvidenceFile, __import__('uuid').UUID(
            entry['file_id'])).metadata_.get('financial_review_progress')


def test_rows_that_do_not_line_up_are_not_carried_and_the_period_stays_held(f):
    from services.financial import reread_carry
    from services.financial.statement_import import read_statement_import
    batch, old_id, key, request, _ = _worked_batch(f)
    with f.SessionLocal() as db:
        proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id)
    stale = {**request, 'expected_revision': 'f' * 64, 'rows': [{**r, 'id': 'gone-' + r['id']} for r in request['rows']]}
    with pytest.raises(reread_carry.NotCarried) as error:
        reread_carry.carry(proposal, stale, proposal)
    assert error.value.reason == 'rows_not_aligned'
    same, audit = reread_carry.carry(proposal, request, proposal)
    assert audit['baseline'] == 'exact' and same['holder'] == 'Typed by the investigator'
