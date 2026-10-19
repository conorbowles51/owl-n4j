"""The identity sync and the ledger projection never create one account twice."""
from contextlib import contextmanager

from services.financial import graph_followup
from services.financial import identity_graph


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
    def __init__(self):
        self.queries = []

    def run(self, query, **params):
        self.queries.append(str(getattr(query, 'text', query)))
        if 'WHERE n.key IN $keys' in self.queries[-1]:
            return Result(rows=[dict(key='ACC-1', labels=['FinancialAccount'])])
        if 'RETURN m.revision AS revision' in self.queries[-1]:
            return Result({'revision': None})
        return Result()

    @contextmanager
    def begin_transaction(self, **kwargs):
        yield self

    def rollback(self):
        pass

    def commit(self):
        pass


def test_identity_sync_takes_the_projection_lock_before_touching_accounts():
    graph = Graph()
    plan = dict(case_id='case-1', revision='r1', accounts=[dict(key='ACC-1')], parties=[], links=[],
                entity_links=[], account_links=[], payment_links=[])
    identity_graph.apply_identity_graph(graph, plan)
    own = next(i for i, q in enumerate(graph.queries) if 'MERGE (m:FinancialIdentitySync' in q)
    ledger = graph.queries.index(graph_followup._LOCK_MARKER)
    first_account = next(i for i, q in enumerate(graph.queries) if 'WHERE n.key IN $keys' in q or 'MERGE (n:FinancialAccount' in q)
    assert own < ledger < first_account
