"""Closing a forgotten batch, and release pause/resume restoring only batches a worker was working."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4, uuid5

import pytest
from sqlalchemy import func, select

from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import forgotten_batches as forgotten
from services.financial import import_batches as service
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_deployment_recovery import f  # noqa: F401  (fixture)

DECISION = 'Neil Byrne, 2026-11-01: forgotten October run, redundant'


def batch(f, status='preparing', statuses=(), *, held=False, age_minutes=60, actor_extra=None):
    row = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status=status,
        actor=dict(name=f.actor.name, **(actor_extra or {})),
        files=[dict(source_id=str(f.file.id), file_id=str(f.file.id), status='checked')])
    if held:
        row.worker_token = str(uuid4())
        row.lease_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    f.db.add(row)
    f.db.flush()
    for index, value in enumerate(statuses):
        f.db.add(Item(id=uuid5(row.id, f's{index}'), batch_id=row.id, file_id=f.file.id, statement_key=f's{index}',
            status=value, summary=dict(source_id=str(f.file.id))))
    f.db.commit()
    stamp = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    f.db.execute(Batch.__table__.update().where(Batch.id == row.id).values(updated_at=stamp))
    f.db.commit()
    return row.id


def state(f, batch_id):
    with f.SessionLocal() as db:
        row = db.get(Batch, batch_id)
        return row.status, dict(row.actor)


# Release pause / resume ------------------------------------------------------

def test_release_resumes_only_batches_a_worker_held_or_just_started(f):
    held = batch(f, held=True)
    fresh = batch(f, age_minutes=2)
    idle = batch(f, age_minutes=60 * 24 * 26)       # a forgotten October run left 'preparing'
    person = batch(f, status='paused')               # paused by a person before the release
    with f.SessionLocal() as db:
        paused = {row['batch_id']: row['kind'] for row in service.release_pause(db, 'r1')}
    assert paused == {str(held): 'held', str(fresh): 'fresh', str(idle): 'idle'}
    assert state(f, held)[0] == 'pausing' and state(f, idle)[0] == 'paused' and state(f, person)[0] == 'paused'
    # The worker finishes its statement and lets go.
    f.db.execute(Batch.__table__.update().where(Batch.id == held).values(status='paused', worker_token=None,
        lease_until=None))
    f.db.commit()
    with f.SessionLocal() as db:
        out = {row['batch_id']: row['action'] for row in service.release_resume(db, 'r1')}
    assert out == {str(held): 'resumed', str(fresh): 'resumed', str(idle): 'skipped'}
    assert state(f, held)[0] == state(f, fresh)[0] == 'preparing'
    assert state(f, idle)[0] == 'paused' and state(f, idle)[1]['release_pause']['left_paused']
    assert 'release_pause' not in state(f, held)[1]
    assert state(f, person) == ('paused', dict(name=f.actor.name))
    # A later release never resumes the idle one either.
    with f.SessionLocal() as db:
        assert service.release_resume(db, 'r2') == []
    assert state(f, idle)[0] == 'paused'


def test_a_person_pausing_after_the_release_paused_keeps_the_batch_paused(f):
    fresh = batch(f, age_minutes=1)
    with f.SessionLocal() as db:
        service.release_pause(db, 'r1')
        service.control_batch(db, case_id=f.case.id, batch_id=fresh, action='pause')
    with f.SessionLocal() as db:
        assert service.release_resume(db, 'r1') == []
    assert state(f, fresh)[0] == 'paused' and 'release_pause' not in state(f, fresh)[1]


def test_a_held_batch_still_finishing_is_reported_waiting_not_forced(f):
    held = batch(f, held=True)
    with f.SessionLocal() as db:
        service.release_pause(db, 'r1')
        assert [row['action'] for row in service.release_resume(db, 'r1')] == ['waiting']
    assert state(f, held)[0] == 'pausing'


# Close as forgotten ----------------------------------------------------------

def test_close_forgotten_previews_then_retires_without_touching_items_or_transactions(f):
    f.confirm_legacy()
    old = batch(f, status='paused', statuses=('imported', 'ready', 'attention', 'duplicate_ignored'))
    transactions = f.db.scalar(select(func.count()).select_from(FinancialTransaction))
    assert transactions
    with f.SessionLocal() as db:
        out = forgotten.close_forgotten_batch(db, case_id=f.case.id, batch_id=old, decision=DECISION)
    assert out['applied'] is False and out['transactions_withdrawn'] == 0
    assert out['left_unimported'] == dict(ready=1, attention=1) and out['decisions_only_in_this_batch'] == 1
    assert state(f, old)[0] == 'paused'
    with f.SessionLocal() as db:
        out = forgotten.close_forgotten_batch(db, case_id=f.case.id, batch_id=old, decision=DECISION, apply=True)
    status, actor = state(f, old)
    assert out['applied'] and status == 'removed'
    assert actor['closed_as_forgotten']['decision'] == DECISION
    assert actor['closed_as_forgotten']['previous_status'] == 'paused'
    with f.SessionLocal() as db:
        assert sorted(db.scalars(select(Item.status).where(Item.batch_id == old))) == [
            'attention', 'duplicate_ignored', 'imported', 'ready']
        assert db.scalar(select(func.count()).select_from(FinancialTransaction)) == transactions
        again = forgotten.close_forgotten_batch(db, case_id=f.case.id, batch_id=old, decision=DECISION, apply=True)
    assert again['already_closed'] and not again['applied']


def test_close_forgotten_refuses_a_held_batch_and_one_removed_with_its_imports(f):
    held = batch(f, held=True)
    removed = batch(f, status='removed')
    with f.SessionLocal() as db:
        with pytest.raises(PdfMappingError, match='still preparing'):
            forgotten.close_forgotten_batch(db, case_id=f.case.id, batch_id=held, decision=DECISION, apply=True)
        with pytest.raises(PdfMappingError, match='removed with its imports'):
            forgotten.close_forgotten_batch(db, case_id=f.case.id, batch_id=removed, decision=DECISION, apply=True)
        with pytest.raises(PdfMappingError, match='whose decision'):
            forgotten.close_forgotten_batch(db, case_id=f.case.id, batch_id=held, decision=' ')


def test_recovery_guard_reads_decisions_of_batches_closed_as_forgotten(f, monkeypatch):
    from services.financial import deployment_recovery as recovery
    from services.financial import recovery_followup
    from services.financial.file_visibility import financial_file_visibility
    monkeypatch.setattr(recovery_followup, 'guard', lambda *args: None)
    closed = batch(f, status='removed', statuses=('duplicate_ignored',),
        actor_extra=dict(closed_as_forgotten=dict(decision=DECISION)))
    item = SimpleNamespace(id=uuid4(), result=dict(lineage_ids=[str(f.file.id)],
        visibility_revision=financial_file_visibility(f.file)['financial_visibility_revision']))
    with f.SessionLocal() as db:
        file = db.get(type(f.file), f.file.id)
        assert recovery._guard(db, item, file)[0] == 'kept'
    # A batch removed with its imports (not closed as forgotten) carries nothing, as before.
    f.db.execute(Batch.__table__.update().where(Batch.id == closed).values(actor=dict(name='x')))
    f.db.commit()
    with f.SessionLocal() as db:
        file = db.get(type(f.file), f.file.id)
        guard = recovery._guard(db, item, file)
        assert guard is None or 'duplicate' not in guard[1]
