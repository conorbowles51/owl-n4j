"""The review queue's whole-case view is saved for the other worker and the next start, and reused only at the
same fingerprint (measured live 2026-10-30: the first read after a start took 54.1 s on d5b330d1)."""
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.financial import review_queue, view_cache


class _Session:
    def __init__(self, writes=False):
        self.writes = writes
        self.rolled_back = 0

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name='sqlite'))

    def connection(self):
        return object()

    def rollback(self):
        self.rolled_back += 1


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_cache, 'code_identity', lambda: 'code-1')
    monkeypatch.setattr(view_cache, '_saved_scope', lambda connection: (dict(format=1, database='db', code='code-1'), 100))
    monkeypatch.setattr(view_cache, 'SAVE_MIN_SECONDS', 0.0)
    monkeypatch.setattr(view_cache, 'UPDATING_MIN_SECONDS', 0.0)
    state = dict(fingerprint=(('batches', '1', 5), ('items', '2', 7)), builds=0)
    monkeypatch.setattr(review_queue, 'queue_fingerprint', lambda session, case_id: state['fingerprint'])

    def compute(session, case_id):
        state['builds'] += 1
        return dict(entries=[dict(id='a', bucket='waiting', amount=1.5, pages=[1, 2])], unread=3, built=state['builds'])
    monkeypatch.setattr(review_queue, '_compute', compute)
    review_queue._cache.clear()
    yield state
    review_queue._cache.clear()


def _new_process():
    review_queue._cache.clear()  # what a restart or the other worker starts with


def test_a_built_view_is_reused_from_disk_by_another_process(store):
    case = uuid4()
    first, _ = review_queue._view(_Session(), case)
    _new_process()
    again, refreshing = review_queue._view(_Session(), case)
    assert store['builds'] == 1 and not refreshing
    assert again == first and type(again['entries'][0]['amount']) is float


def test_a_changed_fingerprint_builds_again(store):
    case = uuid4()
    review_queue._view(_Session(), case)
    _new_process()
    store['fingerprint'] = (('batches', '1', 6), ('items', '2', 7))
    view, _ = review_queue._view(_Session(), case)
    assert store['builds'] == 2 and view['built'] == 2


def test_a_writing_transaction_does_not_save(store, monkeypatch):
    import importlib
    row_versions = importlib.import_module('services.financial.row_versions')
    monkeypatch.setattr(row_versions, 'own_write_floor', lambda session: 123)
    case = uuid4()
    review_queue._view(_Session(), case)
    _new_process()
    review_queue._view(_Session(), case)
    assert store['builds'] == 2


def test_a_view_that_does_not_read_back_exactly_is_not_saved(store, monkeypatch):
    monkeypatch.setattr(review_queue, '_compute', lambda session, case_id: (store.__setitem__('builds', store['builds'] + 1)
                        or dict(entries=[dict(id='a', pages=(1, 2))], unread=0)))
    case = uuid4()
    review_queue._view(_Session(), case)
    _new_process()
    review_queue._view(_Session(), case)
    assert store['builds'] == 2  # a tuple would come back as a list: never saved


def test_another_code_identity_does_not_reuse(store, monkeypatch):
    case = uuid4()
    review_queue._view(_Session(), case)
    _new_process()
    monkeypatch.setattr(view_cache, '_saved_scope', lambda connection: (dict(format=1, database='db', code='code-2'), 100))
    review_queue._view(_Session(), case)
    assert store['builds'] == 2


def test_the_warm_up_builds_without_counting_a_read_and_ends_its_transaction(store):
    case = uuid4()
    session = _Session()
    review_queue._recent_reads.clear()
    review_queue.warm(case_id=case, db=session)
    assert str(case) not in review_queue._recent_reads and session.rolled_back == 1
    _new_process()
    review_queue._view(_Session(), case)
    assert store['builds'] == 1


def test_a_decision_draft_or_mapping_changes_the_queue_key(monkeypatch):
    """The queue reads review drafts, candidate mappings and adjudications besides the register's rows (review
    2026-10-30): a change to any of them is a new key, so neither the memory nor the saved copy is reused."""
    import importlib
    status = importlib.import_module('services.financial.statement_file_status')
    monkeypatch.setattr(status, 'status_fingerprint', lambda session, case_id: (('batches', 1, 'x'),))
    extra = {'rows': [('decisions', 3, 'a'), ('drafts', 0, None), ('mappings', 0, None)]}

    class Session:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))

        def execute(self, statement, parameters):
            assert {'financial_statement_review_drafts', 'financial_candidate_mappings', 'adjudications'} <= set(
                str(statement).split())
            return list(extra['rows'])
    before = review_queue.queue_fingerprint(Session(), uuid4())
    extra['rows'] = [('decisions', 4, 'b'), ('drafts', 0, None), ('mappings', 0, None)]
    assert review_queue.queue_fingerprint(Session(), uuid4()) != before
    assert ('batches', 1, 'x') in before


def test_a_write_to_a_batchs_files_changes_the_queue_key_on_postgresql():
    """The register keys batches by id and status only (a batch's files list takes reader stamps after a release);
    the queue reads the files list itself (files being prepared or read again, held files waiting for a recheck), so
    a change there must be a new queue key, or a saved queue would be served after it."""
    import os
    import uuid
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    url = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires an explicit local PostgreSQL test connection')
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1) if url.startswith('postgresql://') else url
    schema = 'queue_key_' + uuid.uuid4().hex[:8]
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        with engine.begin() as connection:
            for table in ('financial_statement_periods', 'financial_source_documents', 'financial_accounts',
                          'financial_transactions', 'evidence_files', 'workspace_entries', 'workspace_entry_links',
                          'financial_candidate_mappings', 'adjudications'):
                connection.execute(text(f'CREATE TABLE {table} (id uuid PRIMARY KEY, case_id uuid)'))
            connection.execute(text('CREATE TABLE financial_import_batches (id uuid PRIMARY KEY, case_id uuid, '
                                    'status text, files jsonb)'))
            connection.execute(text('CREATE TABLE financial_import_batch_items (id uuid PRIMARY KEY, batch_id uuid)'))
            connection.execute(text('CREATE TABLE evidence_document_texts (evidence_file_id uuid)'))
            connection.execute(text('CREATE TABLE evidence_table_geometry (evidence_file_id uuid, page_number int)'))
            connection.execute(text('CREATE TABLE financial_statement_review_drafts (evidence_file_id uuid, case_id uuid)'))
        case, batch = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO financial_import_batches VALUES (:b, :c, 'review', "
                                    "'[{\"file_id\": \"f1\", \"status\": \"checked\"}]')"), dict(b=batch, c=case))

        def key():
            with Session(engine) as session:
                return review_queue.queue_fingerprint(session, case)
        before = key()
        assert before == key()
        with engine.begin() as connection:
            connection.execute(text("UPDATE financial_import_batches SET files = "
                                    "'[{\"file_id\": \"f1\", \"status\": \"processing\"}]' WHERE id = :b"), dict(b=batch))
        assert key() != before, 'a file the queue shows as being read again must not be served from the old key'
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def test_after_a_restart_a_changed_queue_is_answered_from_its_saved_copy_while_the_refresh_builds_it(store, tmp_path):
    """Measured 2026-10-31 07:05: the d5b330d1 queue took 38.2 s for a person while the background re-warm built the
    same queue. A reader that can show an updating answer gets the previous saved queue at once and its start time;
    the build is asked of the host's refresh process (an ask file), not done in the request."""
    from services.financial import view_refresh
    case = uuid4()
    before = time.time()
    review_queue._view(_Session(), case)
    _new_process()
    store['fingerprint'] = (('batches', '1', 6), ('items', '2', 7))
    token = review_queue.previous_as_of.set(0.0)
    try:
        view, refreshing = review_queue._view(_Session(), case, stale_ok=True, updating=True)
        assert refreshing and view['built'] == 1 and store['builds'] == 1
        assert before - 1 <= review_queue.previous_as_of.get() <= time.time()
    finally:
        review_queue.previous_as_of.reset(token)
    [(path, ask)] = view_refresh._open_asks('code-1')
    assert ask['key'] == ['review-queue', '{"case_id": "%s"}' % case]
    # The refresh builds and saves the current queue; that answers the ask, and the next reader gets it current.
    assert review_queue.refresh(_Session(), case)
    assert not path.exists() and store['builds'] == 2
    _new_process()
    view, refreshing = review_queue._view(_Session(), case, stale_ok=True, updating=True)
    assert not refreshing and view['built'] == 2


def test_a_reader_that_does_not_show_updating_never_gets_an_old_saved_queue(store):
    """Review 2026-10-31: the cross-case status line and paged reads just after a person's own save show no
    updating bar; a saved queue of any age must not reach them as if built moments ago."""
    case = uuid4()
    review_queue._view(_Session(), case)
    _new_process()
    store['fingerprint'] = (('batches', '1', 6), ('items', '2', 7))
    view, refreshing = review_queue._view(_Session(), case, stale_ok=True)
    assert not refreshing and view['built'] == 2


def test_past_the_updating_limit_the_reader_builds_the_queue_itself(store):
    from services.financial import view_refresh
    case = uuid4()
    review_queue._view(_Session(), case)
    store['fingerprint'] = (('batches', '1', 6), ('items', '2', 7))
    review_queue._view(_Session(), case, stale_ok=True)
    [(path, ask)] = view_refresh._open_asks('code-1')
    view_refresh._write(path, {**ask, 'asked': time.time() - view_cache.UPDATING_MAX_SECONDS - 1})
    view, refreshing = review_queue._view(_Session(), case, stale_ok=True)
    assert not refreshing and view['built'] == 2


def test_the_queue_route_marks_an_answer_from_the_previous_queue_as_updating(monkeypatch):
    from fastapi import Response
    from routers import financial_statement_import as routes
    from services.financial import review_queue as queue_module
    seen = {}

    def fake(db, **kwargs):
        seen.update(kwargs)
        queue_module.previous_as_of.set(1793430000.0)
        return dict(refreshing=True, as_of='later')
    monkeypatch.setattr(queue_module, 'case_review_queue', fake)
    token = view_cache._accepts_updating.set(True)
    try:
        response = Response()
        routes.financial_review_queue(case_id=uuid4(), file_id=[], limit=None, offset=0, page_list='waiting',
                                      issue=None, fresh=None, db=object(), response=response)
    finally:
        view_cache._accepts_updating.reset(token)
    assert seen['stale_ok'] is True and seen['updating'] is True, 'an unpaged read from the page no longer waits'
    assert response.headers['x-financial-view-state'] == 'updating'
    assert response.headers['x-financial-view-as-of'] == '2026-10-31T07:00:00+00:00'
    seen.clear()
    routes.financial_review_queue(case_id=uuid4(), file_id=[], limit=None, offset=0, page_list='waiting',
                                  issue=None, fresh=None, db=object(), response=Response())
    assert seen['stale_ok'] is False and seen['updating'] is False, 'other callers still wait for a current queue'


def test_a_queue_that_built_fast_is_built_for_the_reader_not_shown_as_updating(store, monkeypatch):
    """Review 2026-10-31 (7ece7931 F1): the release warm-up now saves every queue, however fast; a queue that built
    in under UPDATING_MIN_SECONDS is built again for the reader after a change, as a cached view is."""
    monkeypatch.setattr(view_cache, 'UPDATING_MIN_SECONDS', 1.0)
    case = uuid4()
    review_queue._view(_Session(), case)
    _new_process()
    store['fingerprint'] = (('batches', '1', 6), ('items', '2', 7))
    view, refreshing = review_queue._view(_Session(), case, stale_ok=True, updating=True)
    assert not refreshing and view['built'] == 2
