"""The batch review page (GET /statement-import/batches/{batch_id}) is a cached view.

Measured live 3 Nov on d5b330d1 batch 30231f0a (1,452 files): 14.2-52.8 s on every open (Server-Timing: inputs,
finish and comparison stages), the page's one-minute limit within reach. A read-only dry run on the live database
gave the same bytes through the view cache: 10.9 s to compute, 0.12 s from the kept copy (49494305 batch f6f7cd42:
3.2 s / 0.10 s). Its one input that is not a row, the review queue's own cached view (missing, an earlier copy or
current at the same rows), is left out of the kept part and added on every open.
"""
import os
import time
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from routers import financial_statement_import
from services.financial import import_batches, view_cache


def test_the_batch_review_route_adds_the_queue_lists_to_a_kept_part():
    endpoints = {route.path: route.endpoint for route in financial_statement_import.router.routes
                 if 'GET' in getattr(route, 'methods', ())}
    route = endpoints['/api/financial/statement-import/batches/{batch_id}']
    assert route is financial_statement_import.get_financial_batch
    kept = financial_statement_import.batch_without_queue_lists
    assert kept.__code__.co_filename.endswith('services/financial/view_cache.py')
    assert view_cache.handlers['batch-detail'] is kept


def test_the_batch_review_page_answers_304_when_the_browser_holds_the_same_bytes():
    """Each open answered the whole page (d5b330d1 30231f0a: 315 KB gzip) although nothing had changed."""
    page = {'batch': {'id': 'b'}, 'files': [{'id': 'f'}]}
    route = financial_statement_import.get_financial_batch
    with patch.object(financial_statement_import, 'batch_without_queue_lists', return_value=dict(page)):
        first = route(batch_id=uuid.uuid4(), case_id=uuid.uuid4(), offset=0, limit=100, only_problems=False,
                      review_group=None, db=None)
        assert first.status_code == 200 and first.headers['ETag'].startswith('W/"')
        assert first.headers['Cache-Control'] == 'private, no-cache'
        token = view_cache._if_none_match.set(first.headers['ETag'])
        try:
            again = route(batch_id=uuid.uuid4(), case_id=uuid.uuid4(), offset=0, limit=100, only_problems=False,
                          review_group=None, db=None)
        finally:
            view_cache._if_none_match.reset(token)
        assert again.status_code == 304 and not again.body
    with patch.object(financial_statement_import, 'batch_without_queue_lists',
                      return_value={**page, 'files': [{'id': 'g'}]}):
        token = view_cache._if_none_match.set(first.headers['ETag'])
        try:
            changed = route(batch_id=uuid.uuid4(), case_id=uuid.uuid4(), offset=0, limit=100, only_problems=False,
                            review_group=None, db=None)
        finally:
            view_cache._if_none_match.reset(token)
        assert changed.status_code == 200 and changed.headers['ETag'] != first.headers['ETag']
    # A kept part answered as updating is sent whole, never as 304.
    from fastapi.responses import Response
    import json as _json
    updating = Response(content=_json.dumps(page).encode(), media_type='application/json',
                        headers={view_cache.UPDATING_STATE_HEADER: 'updating', view_cache.UPDATING_AS_OF_HEADER: 'x'})
    with patch.object(financial_statement_import, 'batch_without_queue_lists', return_value=updating):
        token = view_cache._if_none_match.set(first.headers['ETag'])
        try:
            whole = route(batch_id=uuid.uuid4(), case_id=uuid.uuid4(), offset=0, limit=100, only_problems=False,
                          review_group=None, db=None)
        finally:
            view_cache._if_none_match.reset(token)
        assert whole.status_code == 200 and 'ETag' not in whole.headers
        assert whole.headers[view_cache.UPDATING_STATE_HEADER] == 'updating'


@contextmanager
def _recording():
    recording = view_cache._Recording(owner=None, snapshot='')
    token = view_cache._recording.set(recording)
    try:
        yield recording
    finally:
        view_cache._recording.reset(token)


class _Item:
    def __init__(self):
        self.id, self.file_id, self.statement_key, self.status = uuid.uuid4(), uuid.uuid4(), '', 'ready'


class _Session:
    def rollback(self):
        pass


def test_batch_provenance_that_fails_to_load_is_not_kept():
    with _recording() as recording, patch('services.activity_trail.batch_sources', side_effect=RuntimeError):
        class Db:
            def get(self, model, key):
                from types import SimpleNamespace
                return SimpleNamespace(case_id=case, actor={}, created_at=None)
        case = uuid.uuid4()
        assert financial_statement_import._batch_added(Db(), case, uuid.uuid4()) is None
    assert recording.keep is False


URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
needs_pg = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')
D5_FILES = 1452  # d5b330d1 batch 30231f0a


@pytest.fixture
def big_batch(tmp_path, monkeypatch):
    """A disposable schema with the real tables: one case and a batch the size of d5b330d1's largest (1,452 files,
    one statement each, all imported)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from postgres.base import Base
    import postgres.models  # noqa: F401 - every model registered
    from postgres.models.case import Case
    from postgres.models.user import User
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    admin = create_engine(URL)
    schema = 'batch_detail_cached_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    view_cache.clear(); view_cache._tables_cache.clear()
    try:
        for table in Base.metadata.sorted_tables:
            try:
                table.create(engine, checkfirst=True)
            except Exception:  # noqa: BLE001 - a table needing a type of its own (enums) that this view never reads
                pass
        Session = sessionmaker(bind=engine)
        with Session() as db:
            user = User(id=uuid.uuid4(), email='i@example.test', name='I', password_hash='-', global_role=GlobalRole.user, is_active=True)
            case = Case(id=uuid.uuid4(), title='Matter', created_by_user_id=user.id, owner_user_id=user.id)
            db.add_all([user, case]); db.commit()
            files = [EvidenceFile(id=uuid.uuid4(), case_id=case.id, original_filename=f'statement-{n}.pdf',
                                  stored_path=f'/e/{n}.pdf', sha256=f'{n:064d}') for n in range(D5_FILES)]
            db.add_all(files); db.commit()
            batch = FinancialImportBatch(id=uuid.uuid4(), case_id=case.id, created_by=user.id, status='review',
                actor=dict(name='I'), files=[dict(source_id=str(f.id), file_id=str(f.id), filename=f.original_filename,
                                                  status='checked') for f in files])
            db.add(batch); db.commit()
            db.add_all([FinancialImportBatchItem(id=uuid.uuid4(), batch_id=batch.id, file_id=f.id, statement_key='',
                status='imported', summary=dict(transaction_count=3, problem_count=0)) for f in files])
            db.commit()
            yield dict(Session=Session, case_id=case.id, batch_id=batch.id)
    finally:
        view_cache.clear(); view_cache._tables_cache.clear()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@needs_pg
def test_reopening_an_unchanged_batch_of_d5b330d1_size_computes_nothing(big_batch):
    from sqlalchemy import update
    from postgres.models.financial_import_batches import FinancialImportBatchItem
    route = financial_statement_import.get_financial_batch
    kwargs = dict(case_id=big_batch['case_id'], batch_id=big_batch['batch_id'], offset=0, limit=100,
                  only_problems=False, review_group=None)
    real = import_batches.batch_status
    calls = []

    def counted(*args, **kw):
        calls.append(1)
        return real(*args, **kw)

    with patch.object(import_batches, 'batch_status', counted):
        with big_batch['Session']() as db:
            first = route(**kwargs, db=db)
        started = time.perf_counter()
        with big_batch['Session']() as db:
            again = route(**kwargs, db=db)
        reopened = time.perf_counter() - started
        assert len(calls) == 1, 'the second open of an unchanged batch is answered from the kept copy'
        assert bytes(again.body) == bytes(first.body)
        # The queue's lists are read on every open, kept copy or not.
        with patch('services.financial.import_batches._as_the_queue_lists', return_value={'still_to_finish': 7}), \
                big_batch['Session']() as db:
            listed = route(**kwargs, db=db)
        assert len(calls) == 1 and b'"queue":{"still_to_finish":7}' in bytes(listed.body)
        assert reopened < 1.0, f'reopening took {reopened:.2f} s'
        assert b'"total":%d' % D5_FILES in bytes(first.body).replace(b' ', b'')
        # Any write to a row it read computes it again (never an out-of-date page).
        with big_batch['Session']() as db:
            db.execute(update(FinancialImportBatchItem).where(FinancialImportBatchItem.batch_id == big_batch['batch_id'])
                       .values(status='skipped').execution_options(synchronize_session=False))
            db.commit()
        with big_batch['Session']() as db:
            changed = route(**kwargs, db=db)
        assert len(calls) == 2
        assert bytes(changed.body) != bytes(first.body)



class QueueListsAddedLater(__import__('unittest').TestCase):
    """The page with the queue's lists added to its kept part equals the page computed in one go, for each answer the
    queue's view can give (none, an earlier copy, current), on a real prepared batch (the SQLite batch fixture)."""

    def setUp(self):
        import tests.test_financial_import_batches as batch_tests
        self.batches = batch_tests.BatchImportTests()
        self.batches.setUp()
        self.batch = self.batches.create()
        self.batches.advance(self.batch)
        self.f = self.batches.f

    def tearDown(self):
        self.batches.tearDown()

    def test_added_later_equals_computed_in_one_go(self):
        import json
        with self.f.SessionLocal() as db:
            whole = import_batches.batch_status(db, case_id=self.f.case.id, batch_id=self.batch)
        file_id = whole['items'][0]['file_id'] if whole['items'] else str(self.f.file.id)
        listing = {'entries': [{'id': 'q1', 'bucket': 'copies', 'file_ids': [file_id], 'statement_id': whole['items'][0].get('statement_id') or ''}] if whole['items'] else [],
                   'copy_files': []}
        for answer in ((None, False), (listing, True), (listing, False)):
            with patch('services.financial.review_queue.current_view', return_value=answer), \
                    patch('services.financial.review_queue._rechecked_by_recovery', return_value=[]):
                with self.f.SessionLocal() as db:
                    whole = import_batches.batch_status(db, case_id=self.f.case.id, batch_id=self.batch)
                with self.f.SessionLocal() as db:
                    part = json.loads(json.dumps(import_batches.batch_status(db, case_id=self.f.case.id, batch_id=self.batch, queue=False), default=str))
                    self.assertIsNone(part['statement_summary']['queue'])
                    later = import_batches.with_queue_lists(db, self.f.case.id, part)
            self.assertEqual(json.dumps(later, sort_keys=False, default=str), json.dumps(json.loads(json.dumps(whole, default=str)), sort_keys=False))
