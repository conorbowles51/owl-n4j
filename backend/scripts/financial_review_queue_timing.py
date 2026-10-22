"""Review queue timing on a synthetic large case (test fixture, SQLite; the PostgreSQL fingerprint is simulated).

Run from backend/: python3 scripts/financial_review_queue_timing.py 250   (files x 4 statements). Never touches a configured database.
"""
import sys, time, json, inspect
sys.path.insert(0, '.')
from unittest.mock import patch
from tests.test_financial_review_queue import QueueReadTests
from tests import financial_large_queue as large
import importlib
from services.financial import review_queue as rq
sfs = importlib.import_module("services.financial.statement_file_status")
t = QueueReadTests('test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies'); t.setUp()
f = t.f
n = int(sys.argv[1]) if len(sys.argv) > 1 else 250
exp = large.build(f, files=n); print('synthetic', exp)
state = {'fp': ('a',)}
paged = 'limit' in inspect.signature(rq.case_review_queue).parameters
def call(**kw):
    with f.SessionLocal() as db:
        s = time.perf_counter(); q = rq.case_review_queue(db, case_id=f.case.id, **kw)
        body = json.dumps(q, default=str)
        return round(time.perf_counter()-s, 3), len(body), q.get('refreshing')
with patch.object(sfs, 'status_fingerprint', lambda session, case_id: state['fp']):
    print('cold (first open)        ', call())
    print('warm, unchanged          ', call())
    if paged:
        print('warm, page of 100        ', call(limit=100))
        print('counts only (limit=0)    ', call(limit=0))
    state['fp'] = ('b',)
    print('after a change (poll, unpaged) ', call())
    if paged:
        state['fp'] = ('b2',)
        print('after a change (paged poll)    ', call(limit=100, stale_ok=True))
    if paged:
        time.sleep(3)
        print('rebuilt in background, page 100 ', call(limit=100, stale_ok=True))
        state['fp'] = ('c',)
        print('after a change, fresh=1  ', call(limit=100))
t.tearDown()
