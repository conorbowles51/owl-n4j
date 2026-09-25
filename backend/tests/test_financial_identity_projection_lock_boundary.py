"""Projection snapshots release SQL locks before touching the graph driver."""
from contextlib import contextmanager
from types import SimpleNamespace
import sys

import pytest
from sqlalchemy import event

from services.financial import identity_graph as projection


class Result:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows or []

    def single(self):
        return self.row

    def data(self):
        return self.rows

    def consume(self):
        return None


class Graph:
    def __init__(self, check=lambda: None):
        self.check, self.events = check, []
        self.revision = None
        self.staged = None
        self.committed = False
        self.closed = False
        self.before_marker = lambda: None
        self.after_validation = lambda: None
        self.missing = []

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *args):
        self.check()

    def run(self, query, **params):
        self.check()
        text = str(query)
        if text.startswith('CREATE CONSTRAINT'):
            assert query.timeout == projection.GRAPH_TRANSACTION_TIMEOUT
            self.events.append('constraint')
        elif 'projection_lock=' in text:
            self.before_marker()
            self.events.append('marker_lock')
            return Result({'revision': self.revision})
        elif 'm.revision=$revision' in text:
            self.staged = params['revision']
        elif 'WHERE matches=0' in text:
            return Result(rows=self.missing)
        elif 'WHERE matches <> 1' in text:
            self.after_validation()
        return Result()

    @contextmanager
    def begin_transaction(self, **kwargs):
        assert kwargs == {'timeout': projection.GRAPH_TRANSACTION_TIMEOUT}
        self.check()
        self.events.append('begin')
        self.staged, self.committed, self.closed = None, False, False
        try:
            yield self
        except BaseException:
            self.rollback()
            raise
        else:
            # Neo4j commits a normal context exit, including `return False`.
            if not self.closed:
                self.commit()
        finally:
            self.events.append('commit' if self.committed else 'rollback')

    def commit(self):
        self.check()
        self.revision = self.staged
        self.committed = True
        self.closed = True

    def rollback(self):
        self.check()
        self.closed = True


def plan(revision):
    return dict(case_id='synthetic-case', revision=revision, accounts=[], parties=[],
        links=[], entity_links=[], account_links=[], payment_links=[])


@pytest.fixture
def source(monkeypatch):
    from tests.test_financial_duplicates import DuplicateTestCase
    from postgres import session as sql_session
    fixture = DuplicateTestCase()
    fixture.setUp()
    live, acquired = set(), []

    @contextmanager
    def snapshot():
        with fixture.SessionLocal() as db:
            live.add(db)
            def observe(state):
                if getattr(state.statement, '_for_update_arg', None) is not None:
                    acquired.append(str(state.statement))
            event.listen(db, 'do_orm_execute', observe)
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                live.remove(db)

    monkeypatch.setattr(sql_session, 'get_background_session', snapshot)
    try:
        yield fixture, live, acquired
    finally:
        fixture.tearDown()


def test_case_snapshot_transaction_is_closed_during_every_graph_operation(source, monkeypatch):
    fixture, live, acquired = source
    expected = projection.identity_graph_plan(fixture.db, fixture.case.id)
    def no_sql():
        assert not live
    graph = Graph(no_sql)
    def session(**kwargs):
        no_sql()
        assert kwargs == {'connection_acquisition_timeout': projection.GRAPH_CONNECTION_TIMEOUT}
        return graph
    monkeypatch.setitem(sys.modules, 'services.neo4j_service', SimpleNamespace(
        neo4j_service=SimpleNamespace(session=session)))
    assert projection.synchronize_case(fixture.case.id)
    assert graph.revision == expected['revision']
    assert len(acquired) == 2  # Initial and graph-lock-protected revalidation.
    assert all('FOR UPDATE' in statement for statement in acquired)
    assert not live


def test_graph_connection_failure_cannot_retain_case_snapshot_transaction(source, monkeypatch):
    fixture, live, _ = source
    def unavailable(**kwargs):
        assert not live
        raise TimeoutError('Synthetic graph unavailable')
    monkeypatch.setitem(sys.modules, 'services.neo4j_service', SimpleNamespace(
        neo4j_service=SimpleNamespace(session=unavailable)))
    with pytest.raises(TimeoutError, match='Synthetic'):
        projection.synchronize_case(fixture.case.id)
    assert not live


def test_old_snapshot_waiting_behind_newer_projection_does_not_overwrite_it():
    graph = Graph()
    current = {'revision': 'old'}
    def newer_wins():
        graph.revision = 'new'
        current['revision'] = 'new'
    graph.before_marker = newer_wins
    def is_current():
        assert graph.events[-1] == 'marker_lock'
        return current['revision'] == 'old'
    assert not projection.apply_identity_graph(graph, plan('old'), is_current=is_current)
    assert graph.revision == 'new'
    assert graph.events[-1] == 'rollback'


def test_busy_or_changed_source_revalidation_rolls_back_without_projecting():
    graph = Graph()
    assert not projection.apply_identity_graph(graph, plan('old'), is_current=lambda: False)
    assert graph.revision is None
    assert graph.events == ['constraint', 'begin', 'marker_lock', 'rollback']


def test_source_changes_during_projection_leave_old_revision_detectably_pending():
    graph = Graph()
    current = {'revision': 'old'}
    graph.after_validation = lambda: current.update(revision='new')
    assert projection.apply_identity_graph(graph, plan('old'),
        is_current=lambda: current['revision'] == 'old')
    assert graph.revision == 'old' != current['revision']
    assert projection.apply_identity_graph(graph, plan('new'), is_current=lambda: True)
    assert graph.revision == current['revision']
    assert not projection.apply_identity_graph(graph, plan('new'), is_current=lambda: True)


def test_missing_payment_nodes_do_not_claim_completed_identity_revision():
    graph = Graph()
    graph.missing = [{'key': 'synthetic-pending-payment'}]
    assert projection.apply_identity_graph(graph, plan('old'), is_current=lambda: True)
    assert graph.revision is None
