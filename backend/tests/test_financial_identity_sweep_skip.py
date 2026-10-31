"""The reviewed identity sweep skips a case whose plan inputs and graph reads are unchanged.

Before: every 30 s round built every case's whole plan twice (once more under the graph lock), took the graph
marker lock (a write) and only then found the graph already current: d5b330d1 0.77 s per build, measured.
Now a case is skipped while the ledger inputs it reads (accounts, decisions, admitted payments) and the graph
reads its sync makes (marker revision, nodes on its keys) are unchanged; any change on either side, and every
FULL_SYNC_SECONDS regardless, takes the full path, which decides exactly as before.

Also: a payment link that names another case's account no longer stops the whole case with KeyError; it is
reported in the plan, the log and the status, and the case's other links are still drawn.
"""
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

from postgres.models.financial import FinancialTransaction
from services.financial import identity_graph as ig
from services.financial.account_identity import IdentityRequest, identity_state, save_identity
from services.financial.account_parties import AccountPartyRequest, account_parties, set_account_party


class _Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def single(self):
        return self.rows[0] if self.rows else None

    def data(self):
        return list(self.rows)

    def consume(self):
        return None


class FakeGraph:
    """Nodes by key (a list of label lists, so duplicates show) and the identity marker's revision."""

    def __init__(self):
        self.nodes, self.revision, self.staged, self.events = {}, None, None, []

    def run(self, query, parameters=None, **params):
        params = {**(parameters or {}), **params}
        text = getattr(query, 'text', query)
        if 'projection_lock' in text:
            self.events.append('marker_lock')
            return _Result([dict(revision=self.revision, digest=None, ledger_fingerprint=None, status=None)])
        if 'MATCH (m:FinancialIdentitySync {case_id:$case}) RETURN m.revision AS revision' in text:
            return _Result([dict(revision=self.revision, completed_at=None, status='current', waiting_revision=None,
                                 missing_payment_nodes=None, waiting_since=None, waiting_attempts=None,
                                 next_attempt_at=None)] if self.revision is not None else [])
        if 'WHERE n.key IN $keys' in text:
            return _Result([dict(key=k, labels=labels) for k in params['keys'] for labels in self.nodes.get(k, [])])
        if 'm.revision=$revision' in text:
            self.staged = params['revision']
        return _Result()

    @contextmanager
    def begin_transaction(self, timeout=None):
        graph = self
        self.events.append('begin')

        class Tx:
            def run(self, *args, **kwargs):
                return graph.run(*args, **kwargs)

            def commit(self):
                graph.revision = graph.staged or graph.revision
                graph.events.append('commit')

            def rollback(self):
                graph.events.append('rollback')
        yield Tx()


@pytest.fixture
def world(monkeypatch):
    from tests.test_financial_duplicates import DuplicateTestCase
    from postgres import session as sql_session
    fixture = DuplicateTestCase()
    fixture.setUp()
    fixture.make_copy(rows=tuple((n * 100, f"{n:02x}") for n in range(1, 4)))

    @contextmanager
    def background():
        with fixture.SessionLocal() as db:
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
    monkeypatch.setattr(sql_session, 'get_background_session', background)
    graph = FakeGraph()

    @contextmanager
    def session(**kwargs):
        yield graph
    monkeypatch.setitem(sys.modules, 'services.neo4j_service',
                        SimpleNamespace(neo4j_service=SimpleNamespace(session=session)))
    builds = []
    original = ig.identity_graph_plan
    def counted(db, case_id):
        builds.append(case_id)
        return original(db, case_id)
    monkeypatch.setattr(ig, 'identity_graph_plan', counted)
    # raising=False and getattr: the same tests run against the code before the skip existed, and fail there.
    monkeypatch.setattr(ig, 'SKIP_UNCHANGED', True, raising=False)
    forget = getattr(ig, 'forget_unchanged', lambda: None)
    forget()
    ig._deferred.clear()
    try:
        yield SimpleNamespace(f=fixture, graph=graph, builds=builds)
    finally:
        forget()
        ig._deferred.clear()
        fixture.tearDown()


def _round(w):
    """One sweep round for the case: (plan builds, graph marker locks taken)."""
    builds, locks = len(w.builds), w.graph.events.count('marker_lock')
    ig.synchronize_case(w.f.case.id)
    return len(w.builds) - builds, w.graph.events.count('marker_lock') - locks


def _settle(w):
    """First round draws, second finds it current and remembers it, third is skipped."""
    assert _round(w) == (2, 2)  # identity marker + ledger projection marker
    assert _round(w) == (2, 2)
    assert _round(w) == (0, 0)


def _touch(w, row, **metadata):
    # SQLite stamps updated_at to the second; move it explicitly so the change is visible in the same second.
    row.metadata_ = {**(row.metadata_ or {}), **metadata}
    flag_modified(row, 'metadata_')
    row.updated_at = datetime.now(timezone.utc) + timedelta(hours=1)
    w.f.db.commit()


def _entity_link(w, key='case-company-17'):
    f = w.f
    directory = account_parties(f.db, case_id=f.case.id)
    owned = set_account_party(f.db, case_id=f.case.id, request=AccountPartyRequest(
        expected_revision=directory['revision'], account_ids=[f.account.id], new_party_name='Example company',
        relationship={'role': 'controller'}, reason='Reviewed controller'), actor=f.actor)
    request = IdentityRequest(account_id=f.account.id, expected_revision=identity_state(f.db, f.case.id)['revision'],
        identifiers=[], entity_links=[{'party_id': owned['parties'][0]['id'], 'entity_key': key}],
        basis={'basis': 'investigator_knowledge'}, reason='Reviewed the company record')
    save_identity(f.db, case_id=f.case.id, request=request, actor=f.actor,
                  entity_lookup=lambda k, case: {'key': k})
    w.graph.nodes[key] = [['Organization']]


def test_an_unchanged_case_is_skipped_without_building_or_locking(world):
    _settle(world)
    for _ in range(5):
        assert _round(world) == (0, 0)


def test_switch_off_builds_every_round_as_before(world, monkeypatch):
    monkeypatch.setattr(ig, 'SKIP_UNCHANGED', False, raising=False)
    for _ in range(4):
        assert _round(world)[0] == 2


def test_a_ledger_change_is_caught_on_the_next_round(world):
    _settle(world)
    row = world.f.db.query(FinancialTransaction).filter_by(case_id=world.f.case.id).first()
    _touch(world, row, investigation_labels={'counterparty_link': {'kind': 'account', 'id': str(world.f.account.id)}})
    revision = world.graph.revision
    assert _round(world)[0] == 2
    assert world.graph.revision != revision  # the new payment link was drawn
    assert _round(world)[0] == 2
    assert _round(world) == (0, 0)


def test_a_new_identity_decision_is_caught_on_the_next_round(world):
    _settle(world)
    _entity_link(world)
    assert _round(world)[0] == 2
    assert _round(world)[0] == 2
    assert _round(world) == (0, 0)


@pytest.mark.parametrize('graph_write', ['entity deleted', 'entity merged away', 'duplicate entity', 'key collision',
                                          'marker removed'])
def test_each_kind_of_graph_write_is_caught_on_the_next_round(world, graph_write):
    _entity_link(world)
    _settle(world)
    account_key = ig.identity_graph_plan(world.f.db, world.f.case.id)['accounts'][0]['key']
    world.builds.clear()
    if graph_write == 'entity deleted':          # document or Cellebrite delete of the linked entity
        del world.graph.nodes['case-company-17']
    elif graph_write == 'entity merged away':    # merge keeps the other node's key
        del world.graph.nodes['case-company-17']
        world.graph.nodes['case-company-99'] = [['Organization']]
    elif graph_write == 'duplicate entity':
        world.graph.nodes['case-company-17'].append(['Organization'])
    elif graph_write == 'key collision':
        world.graph.nodes[account_key] = [['Person']]
    else:
        world.graph.revision = None
    if graph_write == 'marker removed':
        assert _round(world)[0] == 2
        assert world.graph.revision is not None
        return
    with pytest.raises(ValueError):  # the same refusal the old code gave every round
        ig.synchronize_case(world.f.case.id)
    assert str(world.f.case.id) not in getattr(ig, '_unchanged', {})


def test_a_full_sync_runs_at_least_every_full_sync_seconds(world):
    _settle(world)
    ig._unchanged[str(world.f.case.id)]['at'] -= ig.FULL_SYNC_SECONDS + 1  # noqa: the old code fails in _settle
    assert _round(world)[0] == 2
    assert _round(world) == (0, 0)


def test_a_case_waiting_for_payment_nodes_is_not_remembered(world, monkeypatch):
    row = world.f.db.query(FinancialTransaction).filter_by(case_id=world.f.case.id).first()
    _touch(world, row, investigation_labels={'counterparty_link': {'kind': 'account', 'id': str(world.f.account.id)}})
    real_run = world.graph.run
    def run(query, parameters=None, **params):
        if 'WHERE matches=0' in getattr(query, 'text', query):
            return _Result([dict(key=k) for k in params['keys']])
        return real_run(query, parameters, **params)
    world.graph.run = run
    assert _round(world)[0] == 2
    ig._deferred.clear()  # the backoff would hold it; the point here is the skip memory
    assert _round(world)[0] == 2
    assert str(world.f.case.id) not in getattr(ig, '_unchanged', {})


def test_a_link_to_another_cases_account_is_reported_and_the_rest_drawn(world, caplog):
    f = world.f
    rows = f.db.query(FinancialTransaction).filter_by(case_id=f.case.id).order_by(FinancialTransaction.id).all()
    assert len(rows) >= 2
    _touch(world, rows[0], investigation_labels={'counterparty_link': {'kind': 'account', 'id': str(f.other_account.id)}})
    _touch(world, rows[1], investigation_labels={'counterparty_link': {'kind': 'account', 'id': str(f.account.id)}})
    with caplog.at_level(logging.WARNING, logger=ig.log.name):
        plan = ig.identity_graph_plan(f.db, f.case.id)
    assert plan['out_of_case_links'] == [dict(payment_id=str(rows[0].id), ref_id=rows[0].ref_id,
                                              account_id=str(f.other_account.id))]
    assert [link['key'] for link in plan['payment_links']] == ['payment-identity:' + str(rows[1].id)]
    assert any('outside the case' in r.getMessage() for r in caplog.records)
    assert ig.synchronize_case(f.case.id)  # the case is still drawn
    status = ig.identity_graph_status(f.db, f.case.id)
    assert status['out_of_case_links'] == 1
