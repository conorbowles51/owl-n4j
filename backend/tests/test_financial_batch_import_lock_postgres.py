"""Opt-in real PostgreSQL import/save checks in disposable synthetic schemas."""
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Event, current_thread
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.financial import FinancialTransaction as Payment
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item, FinancialImportOperation as Operation
from services.financial import import_batches as batches
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import StatementReviewDraft
from tests.test_financial_batch_import_finalization import accepted

pytestmark = pytest.mark.skipif(os.getenv('LOUPE_TEST_LOCAL_POSTGRES') != '1', reason='Requires isolated local PostgreSQL')


@pytest.fixture
def pg(accepted):
    # No application config or remote database fallback is permitted.
    url = make_url(os.environ['LOUPE_TEST_LOCAL_POSTGRES_URL'])
    assert (url.host, url.port, url.database) == ('127.0.0.1', 55434, 'loupe_local')
    schema = 'batch_import_concurrency_' + uuid4().hex
    admin = create_engine(url, connect_args={'connect_timeout': 2})
    engine = create_engine(url, connect_args={'connect_timeout': 2,
        'application_name': 'loupe-synthetic-batch-import',
        'options': '-csearch_path=' + schema + ' -cstatement_timeout=20000 -clock_timeout=5000'})
    f = accepted['f']
    f.db.commit()
    names = set(inspect(f.engine).get_table_names())
    tables = [table for table in Base.metadata.sorted_tables if table.name in names]
    try:
        with admin.begin() as db:
            assert db.scalar(text('SELECT current_database()')) == 'loupe_local'
            db.execute(text('CREATE SCHEMA ' + schema))
        with engine.connect() as db:
            assert db.scalar(text('SHOW search_path')) == schema
        Base.metadata.create_all(engine, tables=tables)
        with f.engine.connect() as source, engine.begin() as target:
            for table in tables:
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
        yield SimpleNamespace(engine=engine, SessionLocal=sessionmaker(bind=engine, autoflush=False),
            case_id=f.case.id, batch_id=accepted['batch'], item_id=accepted['item'], actor=f.actor,
            draft=StatementReviewDraft.model_validate(f.request()), operation_id=accepted['operation'])
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE'))
        admin.dispose()


def run(pg):
    batches._import_item(pg.SessionLocal, pg.case_id, pg.batch_id, pg.item_id, Path)


def state(pg):
    with pg.SessionLocal() as db:
        item = db.get(Item, pg.item_id)
        operation = db.scalar(select(Operation).where(Operation.batch_id == pg.batch_id))
        return dict(status=item.status, summary=deepcopy(item.summary),
            operation=str(operation.id), outcomes=deepcopy(operation.outcomes),
            payments=set(db.scalars(select(Payment.id))))


def test_standalone_save_and_group_confirmation_serialize_without_losing_edits(pg, monkeypatch):
    from services.financial import statement_progress
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch
    saved_lock, queue_attempt = Event(), Event()
    with pg.SessionLocal() as db:
        item = db.get(Item, pg.item_id)
        file_id = item.file_id
        item.status = 'ready'
        db.get(Batch, pg.batch_id).status = 'review'
        db.delete(db.get(Operation, pg.operation_id))
        db.commit()
        revision = batches.batch_status(db, case_id=pg.case_id, batch_id=pg.batch_id)['ready_revision']
    original = statement_progress.read_statement_import
    def reading(*args, **kwargs):
        saved_lock.set()  # save_progress already owns the evidence row here.
        assert queue_attempt.wait(3)
        return original(*args, **kwargs)
    def capture(conn, cursor, statement, parameters, context, many):
        if current_thread().name == 'synthetic-group-queue' and 'FROM evidence_files' in statement and 'FOR UPDATE' in statement:
            queue_attempt.set()
    def save():
        with pg.SessionLocal() as db:
            return statement_progress.save_progress(db, case_id=pg.case_id, evidence_file_id=file_id,
                request=pg.draft.model_copy(update={'holder': 'New synthetic holder'}),
                expected_review_revision='initial', actor=pg.actor)
    def queue():
        current_thread().name = 'synthetic-group-queue'
        with pg.SessionLocal() as db:
            with pytest.raises(PdfMappingError, match='ready statements changed'):
                batches.queue_import(db, case_id=pg.case_id, batch_id=pg.batch_id,
                    expected_revision=revision, actor=pg.actor)
    monkeypatch.setattr(statement_progress, 'read_statement_import', reading)
    event.listen(pg.engine, 'before_cursor_execute', capture)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            saving = pool.submit(save)
            assert saved_lock.wait(3)
            queuing = pool.submit(queue)
            assert saving.result(timeout=5)['request']['holder'] == 'New synthetic holder'
            queuing.result(timeout=5)
    finally:
        event.remove(pg.engine, 'before_cursor_execute', capture)
    with pg.SessionLocal() as db:
        assert db.get(Item, pg.item_id).status == 'ready'
        assert list(db.scalars(select(Payment.id))) == []


def test_concurrent_save_cannot_form_item_evidence_application_deadlock(pg, monkeypatch):
    entered, save_locked_evidence = Event(), Event()
    actual = batches.confirm_statement_import
    def confirm(**kwargs):
        entered.set()
        assert save_locked_evidence.wait(3)
        return actual(**kwargs)
    def capture(conn, cursor, statement, parameters, context, many):
        if current_thread().name == 'synthetic-batch-save' and 'FROM evidence_files' in statement and 'FOR UPDATE' in statement:
            save_locked_evidence.set()
    def save():
        current_thread().name = 'synthetic-batch-save'
        with pg.SessionLocal() as db:
            start = monotonic()
            with pytest.raises(PdfMappingError, match='already being imported'):
                batches.save_review(db, case_id=pg.case_id, batch_id=pg.batch_id,
                    item_id=pg.item_id, request=pg.draft, expected_review_revision=batches._digest({}))
            db.rollback()
            assert monotonic() - start < 2, 'Save must reject before the local 5s lock timeout.'
    monkeypatch.setattr(batches, 'confirm_statement_import', confirm)
    event.listen(pg.engine, 'after_cursor_execute', capture)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            importing = pool.submit(run, pg)
            assert entered.wait(3)
            saving = pool.submit(save)
            saving.result(timeout=4)
            importing.result(timeout=10)
    finally:
        event.remove(pg.engine, 'after_cursor_execute', capture)
    after = state(pg)
    assert after['status'] == 'imported' and len(after['payments']) == 12
    assert after['outcomes'][0]['status'] == 'imported' and after['operation'] == pg.operation_id


def test_two_workers_confirm_once_and_keep_first_durable_outcome(pg, monkeypatch):
    entered = Event()
    together = Barrier(2)
    actual = batches.confirm_statement_import
    receipts = []
    def confirm(**kwargs):
        entered.set()
        together.wait(timeout=5)
        receipt = actual(**kwargs)
        receipts.append(receipt)
        return receipt
    monkeypatch.setattr(batches, 'confirm_statement_import', confirm)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, pg)
        assert entered.wait(3)  # The first claim's transaction has been released.
        second = pool.submit(run, pg)
        first.result(timeout=15)
        second.result(timeout=15)
    after = state(pg)
    assert after['status'] == 'imported' and len(after['payments']) == 12
    assert sorted(receipt['created'] for receipt in receipts) == [False, True]
    assert len({receipt['source_document_id'] for receipt in receipts}) == 1
    assert len(after['outcomes']) == 1 and after['operation'] == pg.operation_id
    assert after['outcomes'][0]['status'] in ('imported', 'already_present')
    run(pg)
    assert state(pg) == after


def test_removal_after_admission_commits_before_finalizer_without_resurrection(pg, monkeypatch):
    from services.financial.import_removal import preview_removal, remove_imports
    from services.financial.transaction_query import list_transactions
    actual = batches.confirm_statement_import
    removed = None
    def confirm(**kwargs):
        nonlocal removed
        receipt = actual(**kwargs)
        with pg.SessionLocal() as db:
            preview = preview_removal(db, case_id=pg.case_id, batch_ids=[pg.batch_id])
            remove_imports(db, case_id=pg.case_id, actor=pg.actor, batch_ids=[pg.batch_id],
                expected_revision=preview['revision'])
        removed = state(pg)
        return receipt
    monkeypatch.setattr(batches, 'confirm_statement_import', confirm)
    run(pg)
    assert state(pg) == removed
    assert removed['status'] == 'removed' and len(removed['payments']) == 12
    with pg.SessionLocal() as db:
        assert list_transactions(db, pg.case_id) == []


# One active saved copy per statement (migration 20261002_one_active_statement).
# The disposable schema is built from the models, which carry the same deferred
# EXCLUDE constraint as the migration on PostgreSQL.

def _active_copies(db):
    from postgres.models.financial import FinancialSourceDocument as Source
    return list(db.scalars(select(Source).where(Source.document_type == 'statement_review', Source.status == 'admitted')))


def _clone_copy(db, document):
    """A second admitted copy of a saved statement under a run of its own."""
    from postgres.models.financial import FinancialIngestionRun as Run, FinancialSourceDocument as Source
    source_run = db.get(Run, document.ingestion_run_id)
    run_copy = Run(**{p.key: getattr(source_run, p.key) for p in Run.__mapper__.column_attrs if p.key != 'id'}, id=uuid4())
    db.add(run_copy)
    db.flush()
    copy = Source(**{p.key: deepcopy(getattr(document, p.key)) for p in Source.__mapper__.column_attrs
                     if p.key not in ('id', 'ingestion_run_id')}, id=uuid4(), ingestion_run_id=run_copy.id)
    db.add(copy)
    db.flush()
    return copy


def test_one_active_statement_constraint_is_a_deferred_exclusion(pg):
    from postgres.models.financial import ONE_ACTIVE_STATEMENT_CONSTRAINT
    with pg.engine.connect() as db:
        row = db.execute(text('SELECT contype, condeferrable, condeferred, pg_get_constraintdef(oid) FROM pg_constraint '
            'WHERE conname = :name AND connamespace = current_schema()::regnamespace'),
            dict(name=ONE_ACTIVE_STATEMENT_CONSTRAINT)).one()
    assert row[0] == 'x' and row[1] is True and row[2] is True
    assert 'EXCLUDE USING btree' in row[3] and 'statement_import_statement_id' in row[3]
    assert "financial_import_removal" in row[3] and 'DEFERRABLE INITIALLY DEFERRED' in row[3]


def test_second_active_copy_is_refused_at_commit_and_replacement_order_is_allowed(pg):
    from sqlalchemy.exc import IntegrityError
    from services.financial.statement_import import active_statement_conflict
    run(pg)
    with pg.SessionLocal() as db:
        [original] = _active_copies(db)
        _clone_copy(db, original)  # Deferred: the insert itself is accepted.
        with pytest.raises(IntegrityError) as refused:
            db.commit()
        assert active_statement_conflict(refused.value)
        db.rollback()
    with pg.SessionLocal() as db:
        [original] = _active_copies(db)
        replacement = _clone_copy(db, original)
        original.status, original.superseded_by_id = 'superseded', replacement.id
        db.commit()  # Insert first, supersede second: what a reread and recovery do.
        assert [d.id for d in _active_copies(db)] == [replacement.id]
    with pg.SessionLocal() as db:
        [current] = _active_copies(db)
        removed = _clone_copy(db, current)
        removed.metadata_ = {**removed.metadata_, 'financial_import_removal': {'synthetic': True}}
        other = _clone_copy(db, current)
        other.metadata_ = {**other.metadata_, 'statement_import_statement_id': 'synthetic-other-period'}
        db.commit()  # A removed copy and a different statement in the same file both coexist.


def test_losing_writer_under_the_real_constraint_returns_the_winners_receipt(pg, monkeypatch):
    from services.financial import statement_import
    actual = batches.confirm_statement_import
    winner = {}
    def first(**kwargs):
        winner.update(kwargs, receipt=actual(**kwargs))
        raise SystemExit('Synthetic: the other worker owns this outcome')
    monkeypatch.setattr(batches, 'confirm_statement_import', first)
    with pytest.raises(SystemExit):
        run(pg)
    monkeypatch.setattr(batches, 'confirm_statement_import', actual)
    before = state(pg)
    # The loser's first attempt reads as if the winner had not committed, as it
    # would without the Case row lock.  Only the database stops the second copy.
    real_existing, real_once = statement_import._existing_statement, statement_import._write_statement_import_once
    attempts = []
    def once(**kwargs):
        attempts.append(True)
        return real_once(**kwargs)
    monkeypatch.setattr(statement_import, '_write_statement_import_once', once)
    monkeypatch.setattr(statement_import, '_existing_statement',
        lambda *a, **k: None if len(attempts) <= 1 else real_existing(*a, **k))
    run(pg)
    after = state(pg)
    assert len(attempts) == 2
    assert after['status'] == 'imported' and after['outcomes'][0]['status'] == 'already_present'
    assert after['summary']['source_document_id'] == winner['receipt']['source_document_id']
    assert after['payments'] == before['payments'] and len(after['payments']) == 12
    with pg.SessionLocal() as db:
        assert len(_active_copies(db)) == 1


def test_migration_refuses_existing_duplicates_then_applies_and_downgrades(pg):
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from unittest.mock import patch
    path = Path(__file__).resolve().parents[1] / 'postgres/alembic/versions/20261002_one_active_statement.py'
    spec = importlib.util.spec_from_file_location('one_active_statement_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def apply(step):
        with pg.engine.begin() as conn, patch.object(migration, 'op', Operations(MigrationContext.configure(conn))):
            step()
    def present():
        with pg.engine.connect() as db:
            return db.scalar(text('SELECT count(*) FROM pg_constraint WHERE conname = :name '
                'AND connamespace = current_schema()::regnamespace'), dict(name=migration.CONSTRAINT))
    run(pg)
    apply(migration.downgrade)
    assert present() == 0
    with pg.SessionLocal() as db:
        [original] = _active_copies(db)
        copy = _clone_copy(db, original)
        db.commit()
        original_id, copy_id = original.id, copy.id
    with pytest.raises(RuntimeError) as refused:
        apply(migration.upgrade)
    assert str(original_id) in str(refused.value) and str(copy_id) in str(refused.value)
    assert present() == 0
    with pg.SessionLocal() as db:
        db.get(type(original), copy_id).status = 'superseded'
        db.commit()
    apply(migration.upgrade)
    assert present() == 1
    apply(migration.downgrade)
    assert present() == 0
