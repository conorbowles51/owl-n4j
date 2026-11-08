"""The warm-up computes the review page of every large batch, so its first open after a release is not computed.

Measured live 2026-11-08 14:41-14:42, first open after the 14:25 release: batch 30231f0a (2,254 statements) 34.2 s,
f6f7cd42 (1,320) 10.0 s; neither had been opened in the day before, so the warm-up's visited list did not have them."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import routers.financial_statement_import as fsi
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    FinancialImportBatch.__table__.create(engine)
    FinancialImportBatchItem.__table__.create(engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def _batch(db, case_id, statements, status='review'):
    now = datetime.now(timezone.utc)
    batch = FinancialImportBatch(id=uuid.uuid4(), case_id=case_id, created_by=uuid.uuid4(), status=status, files=[],
                                 actor={}, created_at=now, updated_at=now)
    db.add(batch)
    db.flush()
    for n in range(statements):
        db.add(FinancialImportBatchItem(id=uuid.uuid4(), batch_id=batch.id, file_id=uuid.uuid4(), statement_key=str(n),
                                        status='ready', summary={}, created_at=now, updated_at=now))
    db.commit()
    return batch.id


def test_the_large_batches_of_the_case_largest_first_never_removed_ones(db, monkeypatch):
    monkeypatch.setattr(fsi, 'LARGE_BATCH_STATEMENTS', 3)
    case, other = uuid.uuid4(), uuid.uuid4()
    big = _batch(db, case, 5)
    edge = _batch(db, case, 3)
    _batch(db, case, 2)
    _batch(db, case, 9, status='removed')
    _batch(db, other, 7)
    assert fsi.large_batches(db, case) == [big, edge]


def test_each_large_batch_is_computed_with_the_routes_own_parameters(db, monkeypatch):
    """The route calls batch_without_queue_lists(batch_id=UUID, case_id=UUID): the same cached-view key."""
    monkeypatch.setattr(fsi, 'LARGE_BATCH_STATEMENTS', 2)
    case = uuid.uuid4()
    first, second = _batch(db, case, 4), _batch(db, case, 2)
    _batch(db, case, 1)
    calls = []
    monkeypatch.setattr(fsi, 'batch_without_queue_lists', lambda **kw: calls.append(kw))
    fsi.warm_large_batches(case_id=case, db=db)
    assert [(c['batch_id'], c['case_id']) for c in calls] == [(first, case), (second, case)]
    assert all(isinstance(c['batch_id'], uuid.UUID) and isinstance(c['case_id'], uuid.UUID) for c in calls)
    calls.clear()
    fsi.warm_large_batches(case_id=str(case), db=db)  # the warm-up may pass the case as text
    assert [c['case_id'] for c in calls] == [case, case]


def test_a_failing_batch_does_not_stop_the_next_and_is_reported(db, monkeypatch):
    monkeypatch.setattr(fsi, 'LARGE_BATCH_STATEMENTS', 1)
    case = uuid.uuid4()
    bad, good = _batch(db, case, 3), _batch(db, case, 2)
    seen = []

    def view(**kw):
        seen.append(kw['batch_id'])
        if kw['batch_id'] == bad:
            raise ValueError('boom')
    monkeypatch.setattr(fsi, 'batch_without_queue_lists', view)
    with pytest.raises(RuntimeError, match='1 of 2'):
        fsi.warm_large_batches(case_id=case, db=db)
    assert seen == [bad, good]

