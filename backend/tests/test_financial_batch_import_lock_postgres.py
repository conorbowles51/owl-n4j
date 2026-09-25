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
