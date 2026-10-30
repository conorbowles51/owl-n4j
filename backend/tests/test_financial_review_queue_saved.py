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
