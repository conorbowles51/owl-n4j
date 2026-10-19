"""Recovery must rotate past busy cases without changing saved work."""
import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from threading import Event
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from postgres.models.case import Case
from postgres.models.financial_recovery import FinancialRecoveryRun as Run, FinancialRecoveryItem as Item, FinancialRecoveryRelease as Release
from services.financial import deployment_recovery as recovery
from services.financial.file_scope import mark_financial_workspace
from services.financial.recovery_campaigns import RecoveryCampaign
from tests.test_financial_deployment_recovery import f


def test_snapshot_failure_does_not_starve_existing_work_and_retries_same_cutoff(f, monkeypatch):
    campaign = RecoveryCampaign('synthetic-case-snapshot-isolation', initial_snapshot=True)
    monkeypatch.setattr(recovery, 'CAMPAIGNS', (campaign,))
    other_file = f.evidence('d' * 64)
    other_file.case_id = f.other_case.id
    mark_financial_workspace(other_file, user_id=f.user.id)
    f.db.commit()
    case_id, other_case_id = f.case.id, f.other_case.id
    existing_run_id = uuid5(NAMESPACE_URL, campaign.release + ':' + str(case_id))
    failing_run_id = uuid5(NAMESPACE_URL, campaign.release + ':' + str(other_case_id))
    with f.SessionLocal() as db:
        cutoff = recovery.activate(db, campaign.release)
        assert recovery.snapshot_case(db, case_id, cutoff, campaign)
        existing = list(db.scalars(select(Item).where(Item.run_id == existing_run_id)))
        existing_results = {item.id: dict(item.result) for item in existing}
        # Resuming a durable run must work without any in-memory registration.
        db.get(Run, existing_run_id).status = 'paused'
        db.commit()
        recovery.control(db, case_id, 'resume', run_id=existing_run_id)
    snapshot = recovery.snapshot_case
    attempts, cutoffs, visited = [], [], []
    turns = 0
    def flaky_snapshot(db, current_case_id, current_cutoff, current_campaign):
        attempts.append(current_case_id)
        cutoffs.append(current_cutoff)
        if current_case_id == other_case_id and attempts.count(other_case_id) == 1:
            # A failure after a partial flush must roll back before continuing.
            db.add(Run(id=failing_run_id, case_id=other_case_id, release=campaign.release, status='running'))
            db.flush()
            raise ValueError('Synthetic case snapshot failure')
        return snapshot(db, current_case_id, current_cutoff, current_campaign)
    def observed(_factory, item_id, _resolve):
        visited.append((turns, item_id))
    async def next_turn(_):
        nonlocal turns
        turns += 1
        with f.SessionLocal() as db:
            if turns == 1:
                assert db.get(Run, failing_run_id) is None
                assert {item_id for turn, item_id in visited if turn == 0} == set(existing_results)
            if turns == 2:
                assert db.get(Run, failing_run_id) is not None
        if turns == 3:
            raise asyncio.CancelledError()
    monkeypatch.setattr('postgres.session._get_session_local', lambda: f.SessionLocal)
    monkeypatch.setattr(recovery, 'snapshot_case', flaky_snapshot)
    monkeypatch.setattr(recovery, 'recover_one', observed)
    monkeypatch.setattr(recovery.asyncio, 'sleep', next_turn)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(recovery.run_recovery_forever())
    assert attempts.count(other_case_id) == 2  # Successful initialization stops future snapshot passes.
    assert attempts.count(case_id) == 2
    assert len(set(cutoffs)) == 1
    with f.SessionLocal() as db:
        assert db.get(Release, campaign.release).cutoff == cutoffs[0]
        assert len(list(db.scalars(select(Run).where(Run.release == campaign.release)))) == 2
        items = list(db.scalars(select(Item).where(Item.run_id.in_([existing_run_id, failing_run_id]))))
        assert len(items) == len(existing_results) + 1
        assert {item_id for _, item_id in visited} == {item.id for item in items}
        assert {item_id: db.get(Item, item_id).result for item_id in existing_results} == existing_results
        assert all(item.status == 'pending' for item in items)


def test_repeated_snapshot_failure_still_reaches_work_every_turn(f, monkeypatch):
    ids, _, _ = seed(f, monkeypatch)
    campaign = recovery.CAMPAIGNS[0]
    next_campaign = SimpleNamespace(release='synthetic-unaffected-snapshot')
    monkeypatch.setattr(recovery, 'CAMPAIGNS', (campaign, next_campaign))
    monkeypatch.setattr('postgres.session._get_session_local', lambda: f.SessionLocal)
    monkeypatch.setattr(recovery, 'activate', lambda *args: datetime.now(timezone.utc))
    case_attempts, work_attempts = [], []
    def failed_snapshot(_db, case_id, _cutoff, current_campaign):
        case_attempts.append((case_id, current_campaign.release))
        if current_campaign.release == campaign.release:
            raise ValueError('Synthetic permanent snapshot failure')
        return True
    monkeypatch.setattr(recovery, 'snapshot_case', failed_snapshot)
    monkeypatch.setattr(recovery, 'recover_one', lambda _factory, item_id, _resolve: work_attempts.append(item_id))
    turns = 0
    async def next_turn(_):
        nonlocal turns
        turns += 1
        if turns == 3:
            raise asyncio.CancelledError()
    monkeypatch.setattr(recovery.asyncio, 'sleep', next_turn)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(recovery.run_recovery_forever())
    assert work_attempts == ids + ids[:2]
    for case_id in (f.case.id, f.other_case.id):
        assert case_attempts.count((case_id, campaign.release)) == 3
        assert case_attempts.count((case_id, next_campaign.release)) == 3


@pytest.mark.parametrize('failure_stage', ['activation', 'case_list'])
def test_campaign_setup_failure_keeps_dispatching_and_reuses_activation_cutoff(f, monkeypatch, failure_stage):
    ids, _, _ = seed(f, monkeypatch)
    campaign = recovery.CAMPAIGNS[0]
    following = SimpleNamespace(release='synthetic-next-campaign')
    monkeypatch.setattr(recovery, 'CAMPAIGNS', (campaign, following))
    activated, snapshots, work = [], [], []
    original_activate = recovery.activate
    class CaseListFailureSession(Session):
        def scalars(self, statement, *args, **kwargs):
            if self.info.pop('fail_case_list', False):
                assert str(statement).startswith('SELECT cases.id')
                raise ValueError('Synthetic case enumeration failure')
            return super().scalars(statement, *args, **kwargs)
    factory = sessionmaker(bind=f.engine, class_=CaseListFailureSession)
    def activation(db, release):
        cutoff = original_activate(db, release)
        activated.append((release, cutoff))
        if release == campaign.release and sum(entry[0] == release for entry in activated) == 1:
            if failure_stage == 'activation':
                raise ValueError('Synthetic error after durable activation')
            db.info['fail_case_list'] = True
        return cutoff
    def snapshot(_db, case_id, _cutoff, manifest):
        snapshots.append((case_id, manifest.release))
        return True
    monkeypatch.setattr('postgres.session._get_session_local', lambda: factory)
    monkeypatch.setattr(recovery, 'activate', activation)
    monkeypatch.setattr(recovery, 'snapshot_case', snapshot)
    monkeypatch.setattr(recovery, 'recover_one', lambda _factory, item_id, _resolve: work.append(item_id))
    turns = 0
    async def next_turn(_):
        nonlocal turns
        turns += 1
        if turns == 1:
            assert work == ids[:2]
            assert len(snapshots) == 2
            assert all(release == following.release for _, release in snapshots)
        if turns == 3:
            raise asyncio.CancelledError()
    monkeypatch.setattr(recovery.asyncio, 'sleep', next_turn)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(recovery.run_recovery_forever())
    assert work == ids + ids[:2]
    for manifest in (campaign, following):
        cutoffs = [cutoff for release, cutoff in activated if release == manifest.release]
        assert len(cutoffs) == 2
        assert len(set(cutoffs)) == 1
        with factory() as db:
            assert db.get(Release, manifest.release).cutoff == cutoffs[0]


def test_worker_advances_past_two_skip_locked_case_results(f, monkeypatch):
    release = 'synthetic-starvation-probe'
    extra = f.evidence('d' * 64)
    other = f.evidence('e' * 64)
    other.case_id = f.other_case.id
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run = Run(id=uuid4(), case_id=f.case.id, release=release, status='running')
    second = Run(id=uuid4(), case_id=f.other_case.id, release=release, status='running')
    f.db.add_all([run, second]); f.db.flush()
    pending = []
    for index, (file, owner) in enumerate([(f.file, run), (extra, run), (other, second)]):
        item = Item(id=UUID(int=index + 1), run_id=owner.id, file_id=file.id, status='waiting', result={}, updated_at=old + timedelta(seconds=index))
        f.db.add(item); pending.append(item.id)
    f.db.commit()
    locked_id = f.case.id
    attempts = []
    class BusyCaseSession(Session):
        def scalar(self, statement, *args, **kwargs):
            locking = getattr(statement, '_for_update_arg', None)
            if locking is not None and locking.skip_locked and str(statement).startswith('SELECT cases.id'):
                if statement.compile().params.get('id_1') == locked_id:
                    return None  # Exact PostgreSQL SKIP LOCKED result, not a timeout.
            return super().scalar(statement, *args, **kwargs)
    factory = sessionmaker(bind=f.engine, class_=BusyCaseSession)
    monkeypatch.setattr('postgres.session._get_session_local', lambda: factory)
    monkeypatch.setattr(recovery, 'CAMPAIGNS', (SimpleNamespace(release=release),))
    monkeypatch.setattr(recovery, 'activate', lambda *args: datetime.now(timezone.utc))
    monkeypatch.setattr(recovery, 'snapshot_case', lambda *args: True)
    original = recovery.recover_one
    def observed(*args):
        attempts.append(args[1])
        if args[1] in pending[:2]:
            return original(*args)
        return None  # Reached unrelated work; this selection test admits nothing.
    monkeypatch.setattr(recovery, 'recover_one', observed)
    turns = 0
    async def stop_after_three_turns(_):
        nonlocal turns
        turns += 1
        if turns == 3:
            raise asyncio.CancelledError()
    monkeypatch.setattr(recovery.asyncio, 'sleep', stop_after_three_turns)
    try:
        asyncio.run(recovery.run_recovery_forever())
    except asyncio.CancelledError:
        pass
    assert attempts == pending + pending[:2]
    with factory() as db:
        assert [db.get(Item, id).status for id in pending] == ['waiting'] * 3



def seed(f, monkeypatch):
    release = 'synthetic-recovery-fairness'
    monkeypatch.setattr(recovery, 'CAMPAIGNS', (SimpleNamespace(release=release),))
    run = Run(id=uuid4(), case_id=f.case.id, release=release, status='running')
    other_run = Run(id=uuid4(), case_id=f.other_case.id, release=release, status='running')
    f.db.add_all([run, other_run]); f.db.flush()
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = []
    for index in range(3):
        file = f.evidence(f'{index + 10:064x}')
        owner = run if index < 2 else other_run
        file.case_id = owner.case_id
        item = Item(id=UUID(int=index + 1), run_id=owner.id, file_id=file.id,
            status='waiting', result={'retained': 'saved investigator work'},
            updated_at=old + timedelta(seconds=index))
        f.db.add(item); ids.append(item.id)
    f.db.commit()
    return ids, run.id, other_run.id


def test_rotation_reaches_tail_and_wraps_without_editing_receipts(f, monkeypatch):
    ids, run_id, other_run_id = seed(f, monkeypatch)
    with f.SessionLocal() as db:
        before = {id: (db.get(Item, id).status, db.get(Item, id).result, db.get(Item, id).updated_at) for id in ids}
        assert recovery.next_recovery_items(db) == ids[:2]
        assert recovery.next_recovery_items(db, ids[1]) == ids[2:]
        assert recovery.next_recovery_items(db, ids[2]) == ids[:2]
        assert recovery.next_recovery_items(db, UUID(int=999)) == ids[:2]
        assert {id: (db.get(Item, id).status, db.get(Item, id).result, db.get(Item, id).updated_at) for id in ids} == before
        assert db.get(Run, run_id).status == 'running'
    new_file = f.evidence('f' * 64)
    new_file.case_id = f.other_case.id
    f.db.add(Item(id=UUID(int=0), run_id=other_run_id, file_id=new_file.id,
        status='pending', result={}))
    f.db.commit()
    with f.SessionLocal() as db:
        assert recovery.next_recovery_items(db, ids[1]) == ids[2:]
        assert recovery.next_recovery_items(db, ids[2]) == [UUID(int=0), ids[0]]


def test_rotating_queue_preserves_pause_terminal_and_campaign_boundaries(f, monkeypatch):
    ids, _, other_id = seed(f, monkeypatch)
    with f.SessionLocal() as db:
        other = db.get(Run, other_id)
        other.status = 'paused'; db.commit()
        assert recovery.next_recovery_items(db, ids[1]) == ids[:2]
        other.status = 'running'; db.commit()
        assert recovery.next_recovery_items(db, ids[1]) == ids[2:]
        db.get(Item, ids[0]).status = 'review'; db.commit()
        assert recovery.next_recovery_items(db, ids[2]) == ids[1:]
        other.release = 'inactive-diagnostic-manifest'; db.commit()
        assert recovery.next_recovery_items(db, ids[1]) == ids[1:2]
        other.release = 'synthetic-recovery-fairness'; other.status = 'complete'; db.commit()
        assert recovery.next_recovery_items(db, ids[1]) == ids[1:2]
        db.get(Item, ids[1]).status = 'recovered'; db.commit()
        assert recovery.next_recovery_items(db, ids[2]) == []


@pytest.mark.parametrize('phase', ['work', 'snapshot'])
def test_worker_shutdown_waits_for_current_atomic_unit(f, monkeypatch, phase):
    ids, _, _ = seed(f, monkeypatch)
    monkeypatch.setattr('postgres.session._get_session_local', lambda: f.SessionLocal)
    monkeypatch.setattr(recovery, 'activate', lambda *args: datetime.now(timezone.utc))
    monkeypatch.setattr(recovery, 'snapshot_case', lambda *args: True)
    entered, release, finished = Event(), Event(), Event()
    attempts = []
    def writing(*args):
        attempts.append(args[1])
        entered.set()
        if not release.wait(5):
            raise AssertionError('Synthetic writer was not released')
        finished.set()
        return True if phase == 'snapshot' else None
    dispatched = []
    if phase == 'snapshot':
        monkeypatch.setattr(recovery, 'snapshot_case', writing)
        monkeypatch.setattr(recovery, 'recover_one', lambda *args: dispatched.append(args[1]))
    else:
        monkeypatch.setattr(recovery, 'recover_one', writing)
    async def scenario():
        task = asyncio.create_task(recovery.run_recovery_forever())
        try:
            for _ in range(1000):
                if entered.is_set():
                    break
                await asyncio.sleep(.005)
            assert entered.is_set()
            task.cancel()
            await asyncio.sleep(.01)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set()
            assert attempts == (ids[:1] if phase == 'work' else [min(f.case.id, f.other_case.id)])
            assert dispatched == []
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())
