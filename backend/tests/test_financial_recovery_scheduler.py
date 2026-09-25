"""Recovery must rotate past busy cases without changing saved work."""
import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
from threading import Event
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from postgres.models.case import Case
from postgres.models.financial_recovery import FinancialRecoveryRun as Run, FinancialRecoveryItem as Item
from services.financial import deployment_recovery as recovery
from tests.test_financial_deployment_recovery import f


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


def test_worker_shutdown_waits_for_current_atomic_unit(f, monkeypatch):
    ids, _, _ = seed(f, monkeypatch)
    monkeypatch.setattr('postgres.session._get_session_local', lambda: f.SessionLocal)
    monkeypatch.setattr(recovery, 'activate', lambda *args: datetime.now(timezone.utc))
    monkeypatch.setattr(recovery, 'snapshot_case', lambda *args: True)
    entered, release, finished = Event(), Event(), Event()
    attempts = []
    def writing(_factory, item_id, _resolve):
        attempts.append(item_id)
        entered.set()
        if not release.wait(5):
            raise AssertionError('Synthetic writer was not released')
        finished.set()
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
            assert attempts == ids[:1]
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())
