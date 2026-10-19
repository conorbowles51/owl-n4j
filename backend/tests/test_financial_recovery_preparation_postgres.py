"""Opt-in PostgreSQL concurrency checks in a disposable synthetic schema."""
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Event
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument as Source, FinancialTransaction as Row
from postgres.models.financial_recovery import FinancialRecoveryItem as Item, FinancialRecoveryRun as Run
from services.financial import deployment_recovery as recovery, recovery_preparation as preparation
from tests.test_financial_deployment_recovery import f, partial_import, snapshot

pytestmark = pytest.mark.skipif(os.getenv('LOUPE_TEST_LOCAL_POSTGRES') != '1', reason='Requires isolated local PostgreSQL')


@pytest.fixture
def pg(f):
    # Never fall back to DATABASE_URL or the application's live configuration.
    url = make_url(os.environ['LOUPE_TEST_LOCAL_POSTGRES_URL'])
    assert (url.host, url.port, url.database) == ('127.0.0.1', 55434, 'loupe_local')
    schema = 'recovery_concurrency_' + uuid4().hex
    admin = create_engine(url, connect_args={'connect_timeout': 2})
    engine = create_engine(url, connect_args={'connect_timeout': 2,
        'application_name': 'loupe-synthetic-recovery-concurrency',
        'options': '-csearch_path=' + schema + ' -cstatement_timeout=20000 -clock_timeout=5000'})
    source_id = partial_import(f)
    item_id = snapshot(f)
    f.db.commit()
    names = set(inspect(f.engine).get_table_names())
    tables = [table for table in Base.metadata.sorted_tables if table.name in names]
    try:
        with admin.begin() as connection:
            assert connection.scalar(text('SELECT current_database()')) == 'loupe_local'
            connection.execute(text('CREATE SCHEMA ' + schema))
        with engine.connect() as connection:
            assert connection.scalar(text('SHOW search_path')) == schema
        Base.metadata.create_all(engine, tables=tables)
        with f.engine.connect() as original, engine.begin() as destination:
            for table in tables:
                values = [dict(row) for row in original.execute(select(table)).mappings()]
                if values:
                    destination.execute(table.insert(), values)
        yield SimpleNamespace(engine=engine, SessionLocal=sessionmaker(bind=engine, autoflush=False),
            case_id=f.case.id, file_id=f.file.id, source_id=source_id, item_id=item_id)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE'))
        admin.dispose()


def saved(pg):
    with pg.SessionLocal() as db:
        item = db.get(Item, pg.item_id)
        return set(db.scalars(select(Row.id).where(Row.source_document_id == pg.source_id))), item.status, db.get(Run, item.run_id).status


@pytest.mark.parametrize('stage', ['bytes', 'parser'])
def test_pause_commits_during_slow_preparation_then_resume_adds_once(pg, monkeypatch, stage):
    from services.financial import statement_import
    entered, release = Event(), Event()
    module, attribute = (recovery, '_verify_bytes') if stage == 'bytes' else (statement_import, 'read_statement_import')
    original = getattr(module, attribute)
    def slow(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(15)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, attribute, slow)
    before = saved(pg)[0]
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(recovery.recover_one, pg.SessionLocal, pg.item_id, Path)
        try:
            assert entered.wait(10)
            start = monotonic()
            with pg.SessionLocal() as db:
                assert recovery.control(db, pg.case_id, 'pause')['status'] == 'paused'
            assert monotonic() - start < 2
        finally:
            release.set()
        work.result(timeout=15)
    assert saved(pg) == (before, 'pending', 'paused')
    with pg.SessionLocal() as db:
        recovery.control(db, pg.case_id, 'resume')
    recovery.recover_one(pg.SessionLocal, pg.item_id, Path)
    after = saved(pg)
    assert before < after[0] and len(after[0]) == len(before) + 1 and after[1] == 'recovered'
    recovery.recover_one(pg.SessionLocal, pg.item_id, Path)
    assert saved(pg) == after


@pytest.mark.parametrize('change', ['geometry', 'saved_source', 'excluded_payment'])
def test_committed_external_input_change_invalidates_inflight_preparation(pg, monkeypatch, change):
    from services.financial import statement_import
    original = statement_import.read_statement_import
    changed = False
    before = saved(pg)[0]
    def read(*args, **kwargs):
        nonlocal changed
        value = original(*args, **kwargs)
        if not changed:
            changed = True
            with pg.SessionLocal() as writer:
                if change == 'geometry':
                    page = writer.get(EvidenceTableGeometry, (pg.file_id, 1))
                    payload = deepcopy(page.payload)
                    payload[0]['table']['values'][0]['text'] += ' revised'
                    page.payload = payload
                elif change == 'saved_source':
                    source = writer.get(Source, pg.source_id)
                    source.metadata_ = {**source.metadata_, 'investigator_note': 'Keep the new note'}
                else:
                    row = writer.scalar(select(Row).where(Row.source_document_id == pg.source_id))
                    row.ledger_status = 'superseded'
                writer.commit()
        return value
    monkeypatch.setattr(statement_import, 'read_statement_import', read)
    recovery.recover_one(pg.SessionLocal, pg.item_id, Path)
    assert saved(pg) == (before, 'pending', 'running')


@pytest.mark.parametrize('locked_input', ['evidence', 'text', 'geometry'])
def test_final_freeze_yields_without_waiting_for_extraction_writer(pg, monkeypatch, locked_input):
    original = preparation.prepare_readings
    writer = pg.SessionLocal()
    before = saved(pg)[0]
    def prepared(*args, **kwargs):
        result = original(*args, **kwargs)
        if locked_input == 'evidence':
            writer.execute(select(EvidenceFile.id).where(EvidenceFile.id == pg.file_id).with_for_update()).all()
        elif locked_input == 'text':
            writer.execute(update(EvidenceDocumentText).where(EvidenceDocumentText.evidence_file_id == pg.file_id)
                .values(extracted_at=text('now()')))
        else:
            writer.execute(update(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == pg.file_id)
                .values(extracted_at=text('now()')))
        return result
    monkeypatch.setattr(preparation, 'prepare_readings', prepared)
    try:
        start = monotonic()
        recovery.recover_one(pg.SessionLocal, pg.item_id, Path)
        assert monotonic() - start < 3
        assert saved(pg) == (before, 'pending', 'running')
        with pg.SessionLocal() as db:
            assert recovery.control(db, pg.case_id, 'pause')['status'] == 'paused'
    finally:
        writer.rollback()
        writer.close()


def test_extraction_cannot_change_frozen_inputs_before_atomic_commit(pg, monkeypatch):
    original = preparation.lock_inputs
    started = Event()
    future = None
    def write():
        with pg.SessionLocal() as writer:
            started.set()
            writer.execute(update(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == pg.file_id)
                .values(extracted_at=text('now()')))
            writer.commit()
    with ThreadPoolExecutor(max_workers=1) as pool:
        def locked(*args, **kwargs):
            nonlocal future
            result = original(*args, **kwargs)
            assert result
            future = pool.submit(write)
            assert started.wait(3)
            from concurrent.futures import TimeoutError
            with pytest.raises(TimeoutError):
                future.result(timeout=.15)
            return result
        monkeypatch.setattr(preparation, 'lock_inputs', locked)
        before = saved(pg)[0]
        recovery.recover_one(pg.SessionLocal, pg.item_id, Path)
        future.result(timeout=5)
    assert len(saved(pg)[0]) == len(before) + 1


@pytest.mark.parametrize('held_record', ['run', 'item'])
def test_final_entry_yields_to_recovery_record_owner_and_releases_case(pg, monkeypatch, held_record):
    original = preparation.prepare_readings
    owner = pg.SessionLocal()
    before = saved(pg)
    def prepared(*args, **kwargs):
        result = original(*args, **kwargs)
        if held_record == 'run':
            run_id = owner.get(Item, pg.item_id).run_id
            owner.execute(select(Run.id).where(Run.id == run_id).with_for_update()).all()
        else:
            owner.execute(select(Item.id).where(Item.id == pg.item_id).with_for_update()).all()
        return result
    monkeypatch.setattr(preparation, 'prepare_readings', prepared)
    try:
        start = monotonic()
        recovery.recover_one(pg.SessionLocal, pg.item_id, Path)
        assert monotonic() - start < 3
        assert saved(pg) == before
        with pg.SessionLocal() as other:
            assert other.scalar(select(Case.id).where(Case.id == pg.case_id)
                .with_for_update(nowait=True)) == pg.case_id
    finally:
        owner.rollback()
        owner.close()
    with pg.SessionLocal() as other:
        assert recovery.control(other, pg.case_id, 'pause')['status'] == 'paused'


def test_two_prepared_workers_commit_only_one_addition(pg, monkeypatch):
    original = preparation.prepare_readings
    barrier = Barrier(2)
    first_prepared = Event()
    def prepared(*args, **kwargs):
        result = original(*args, **kwargs)
        first_prepared.set()
        barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(preparation, 'prepare_readings', prepared)
    before = saved(pg)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        workers = [pool.submit(recovery.recover_one, pg.SessionLocal, pg.item_id, Path)]
        assert first_prepared.wait(10)
        workers.append(pool.submit(recovery.recover_one, pg.SessionLocal, pg.item_id, Path))
        for worker in workers:
            worker.result(timeout=15)
    assert len(saved(pg)[0]) == len(before) + 1
    with pg.SessionLocal() as db:
        assert len(db.get(Source, pg.source_id).metadata_['statement_recovery_additions']) == 1
