"""The reviewed identity sweep waits for payment nodes with backoff, visibly.

Before: a case whose payments were not in the graph was fully rewritten every
30-second round, forever, with nothing saying why.  Now the marker records what
it is waiting for, the sweep defers the case with exponential backoff, and the
ledger projection wakes it as soon as the payments are drawn.
"""
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from services.financial import identity_graph


class _Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def consume(self):
        return None

    def single(self):
        return self.rows[0] if self.rows else None

    def data(self):
        return list(self.rows)


class ScriptedGraph:
    def __init__(self, *, missing=(), marker_revision=None, status_row=None):
        self.missing = list(missing)
        self.marker_revision = marker_revision
        self.status_row = status_row
        self.statements = []
        self.committed = 0

    def _run(self, query, params):
        text = getattr(query, 'text', query)
        self.statements.append((text, params))
        if 'projection_lock' in text:
            return _Result([dict(revision=self.marker_revision)])
        if 'OPTIONAL MATCH (n:FinancialTransaction' in text:
            return _Result([dict(key=k) for k in self.missing])
        if 'RETURN m.revision AS revision' in text:
            return _Result([self.status_row] if self.status_row else [])
        return _Result()

    def run(self, query, parameters=None, **kwargs):
        return self._run(query, {**(parameters or {}), **kwargs})

    @contextmanager
    def begin_transaction(self, timeout=None):
        graph = self

        class Tx:
            def run(self, query, parameters=None, **kwargs):
                return graph._run(query, {**(parameters or {}), **kwargs})

            def commit(self):
                graph.committed += 1

            def rollback(self):
                pass
        yield Tx()

    def texts(self):
        return [t for t, _ in self.statements]


def _plan(case='case-1', revision='rev-1'):
    return dict(case_id=case, revision=revision, accounts=[], parties=[], links=[], entity_links=[],
                account_links=[], payment_links=[dict(key='payment-identity:1', source='TX-AAAA', target='financial-party:p',
                                                      direction='debit', recorded_identity='{}')])


@pytest.fixture(autouse=True)
def clean_deferrals():
    identity_graph._deferred.clear()
    yield
    identity_graph._deferred.clear()


def test_missing_payment_nodes_record_a_visible_waiting_status_and_defer():
    graph = ScriptedGraph(missing=['TX-AAAA'])
    assert identity_graph.apply_identity_graph(graph, _plan()) is True
    waiting = [p for t, p in graph.statements if 'm.waiting_since' in t]
    assert len(waiting) == 1
    assert waiting[0]['status'] == identity_graph.WAITING_FOR_PAYMENTS
    assert waiting[0]['missing'] == 1 and waiting[0]['attempts'] == 1
    assert waiting[0]['delay'] == identity_graph.SWEEP_RETRY_BASE_SECONDS
    # The revision is not marked complete while payments are missing.
    assert not any('m.revision=$revision' in t for t in graph.texts())
    state = identity_graph.sweep_deferral('case-1')
    assert state['reason'] == identity_graph.WAITING_FOR_PAYMENTS
    assert state['missing_payment_nodes'] == 1
    assert identity_graph._is_deferred('case-1')


def test_waiting_backoff_grows_and_is_capped():
    graph = ScriptedGraph(missing=['TX-AAAA'])
    delays = []
    for _ in range(8):
        identity_graph.apply_identity_graph(graph, _plan())
        delays.append([p for t, p in graph.statements if 'm.waiting_since' in t][-1]['delay'])
    assert delays[:4] == [60, 120, 240, 480]
    assert max(delays) == identity_graph.SWEEP_RETRY_CAP_SECONDS
    assert delays[-1] == identity_graph.SWEEP_RETRY_CAP_SECONDS


def test_completion_clears_the_wait_and_marks_current():
    identity_graph.apply_identity_graph(ScriptedGraph(missing=['TX-AAAA']), _plan())
    graph = ScriptedGraph(missing=[])
    assert identity_graph.apply_identity_graph(graph, _plan()) is True
    done = [t for t in graph.texts() if 'm.revision=$revision' in t]
    assert len(done) == 1 and "m.status='current'" in done[0] and 'REMOVE m.missing_payment_nodes' in done[0]
    assert identity_graph.sweep_deferral('case-1') is None


def test_already_current_revision_clears_a_stale_deferral():
    identity_graph._defer('case-1', 'failed', error='earlier')
    assert identity_graph.apply_identity_graph(ScriptedGraph(marker_revision='rev-1'), _plan()) is False
    assert identity_graph.sweep_deferral('case-1') is None


@pytest.fixture
def sweep(monkeypatch):
    calls = []
    behaviour = {'raise': None}
    @contextmanager
    def session():
        yield SimpleNamespace(scalars=lambda statement: ['case-1', 'case-2'])
    from postgres import session as sql_session
    monkeypatch.setattr(sql_session, 'get_background_session', session)
    def synchronize(case_id):
        calls.append(case_id)
        if behaviour['raise'] and case_id == 'case-1':
            raise behaviour['raise']
        return True
    monkeypatch.setattr(identity_graph, 'synchronize_case', synchronize)
    return calls, behaviour


def test_sweep_skips_a_deferred_case_until_its_backoff_elapses(sweep):
    calls, _ = sweep
    identity_graph._defer('case-1', identity_graph.WAITING_FOR_PAYMENTS, missing=3)
    identity_graph.sync_saved_identities()
    assert calls == ['case-2']
    identity_graph._deferred['case-1']['next_due'] = 0.0   # backoff elapsed
    identity_graph.sync_saved_identities()
    assert calls == ['case-2', 'case-1', 'case-2']


def test_projection_wakes_a_waiting_case_on_the_next_sweep(sweep):
    calls, _ = sweep
    identity_graph._defer('case-1', identity_graph.WAITING_FOR_PAYMENTS, missing=3)
    identity_graph.payment_nodes_changed('case-1')
    identity_graph.sync_saved_identities()
    assert calls == ['case-1', 'case-2']


def test_failures_back_off_instead_of_retrying_every_round(sweep, caplog):
    calls, behaviour = sweep
    behaviour['raise'] = ValueError('A connected case entity is missing or ambiguous.')
    for _ in range(5):
        identity_graph.sync_saved_identities()
    # One attempt, then deferred for the remaining rounds; other cases continue.
    assert calls.count('case-1') == 1
    assert calls.count('case-2') == 5
    state = identity_graph.sweep_deferral('case-1')
    assert state['reason'] == 'failed' and 'ambiguous' in state['last_error']
    assert state['retry_in_seconds'] > 0
    assert sum(1 for r in caplog.records if r.exc_info) <= 1


def test_status_reports_waiting_for_payments(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(identity_graph, 'identity_graph_plan', lambda db, case_id: plan)
    row = dict(revision=None, completed_at=None, status=identity_graph.WAITING_FOR_PAYMENTS, waiting_revision='rev-1',
               missing_payment_nodes=7, waiting_since='2026-10-02T00:00:00Z', waiting_attempts=3,
               next_attempt_at='2026-10-02T00:04:00Z')
    graph = ScriptedGraph(status_row=row)
    @contextmanager
    def session(**kwargs):
        yield graph
    monkeypatch.setitem(sys.modules, 'services.neo4j_service',
                        SimpleNamespace(neo4j_service=SimpleNamespace(session=session)))
    status = identity_graph.identity_graph_status(None, 'case-1')
    assert status['status'] == 'waiting_for_payments'
    assert status['missing_payment_nodes'] == 7
    assert status['attempts'] == 3
    # A newer decision revision is ordinary pending work, not a wait.
    graph.status_row = {**row, 'waiting_revision': 'rev-0'}
    assert identity_graph.identity_graph_status(None, 'case-1')['status'] == 'pending'
