"""Identity validation retains cross-label collision and exact-target checks."""
from unittest import TestCase
from services.financial.identity_graph import validate_graph_targets


class Graph:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def run(self, query, **params):
        if 'db.labels()' in query:  # no labels listed: the single label-less read, as before
            return Graph([])
        self.calls.append((query, params))
        return self

    def data(self):
        return self.rows


def plan():
    return dict(case_id='synthetic-case', accounts=[{'key': 'account'}],
                parties=[{'key': 'party'}], entity_links=[{'target': 'entity'}])


class IdentityTargetTests(TestCase):
    def test_one_read_preserves_all_requested_keys_and_case_scope(self):
        graph = Graph([{'key': 'entity', 'labels': ['Person']},
                       {'key': 'account', 'labels': ['FinancialAccount', 'Entity']}])
        validate_graph_targets(graph, plan())  # Missing party may be created.
        self.assertEqual(len(graph.calls), 1)
        self.assertEqual(graph.calls[0][1], dict(case='synthetic-case', keys=['account', 'entity', 'party']))

    def test_missing_and_duplicate_external_targets_are_refused(self):
        for rows in ([], [{'key': 'entity', 'labels': ['Person']}] * 2):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
                validate_graph_targets(Graph(rows), plan())

    def test_wrong_label_and_duplicate_financial_keys_are_refused(self):
        target = [{'key': 'entity', 'labels': ['Person']}]
        for rows in ([{'key': 'account', 'labels': ['Person']}],
                     [{'key': 'party', 'labels': ['FinancialAccount']}],
                     [{'key': 'account', 'labels': ['FinancialAccount']}] * 2):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, 'conflicts'):
                validate_graph_targets(Graph(target + rows), plan())

    def test_empty_plan_does_not_scan_graph(self):
        graph = Graph([])
        validate_graph_targets(graph, dict(case_id='synthetic-case', accounts=[], parties=[], entity_links=[]))
        self.assertEqual(graph.calls, [])


class LabelledGraph:
    """Lists labels, then answers the per-label read: one row per (node, label) as a UNION ALL returns them."""

    def __init__(self, nodes, labels):
        self.nodes, self.labels, self.queries = nodes, labels, []

    def run(self, query, **params):
        self.queries.append((query, params))
        if 'db.labels()' in query:
            return _Rows([{'label': label} for label in self.labels])
        assert 'MATCH (n {case_id' not in query  # never the whole-graph scan when labels are listed
        return _Rows([dict(id=node['id'], key=node['key'], labels=node['labels'])
                      for label in self.labels for node in self.nodes
                      if label in node['labels'] and node['key'] in params['keys']])


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def data(self):
        return self.rows


class IndexedTargetReadTests(TestCase):
    """The label-less read was an AllNodesScan (81,290 nodes on live, per case, every 30 s)."""

    def test_one_indexed_branch_per_label_and_a_multi_label_node_counts_once(self):
        graph = LabelledGraph([dict(id='1', key='entity', labels=['Person', 'Entity']),
                               dict(id='2', key='account', labels=['FinancialAccount'])],
                              ['Entity', 'FinancialAccount', 'Odd`Label', 'Person'])
        validate_graph_targets(graph, plan())  # would raise 'ambiguous' if node 1 counted twice
        query, params = graph.queries[1]
        self.assertEqual(query.count('UNION ALL'), 3)
        self.assertIn('MATCH (n:`Odd``Label`)', query)
        self.assertEqual(params, dict(case='synthetic-case', keys=['account', 'entity', 'party']))

    def test_two_nodes_on_one_key_are_still_refused(self):
        graph = LabelledGraph([dict(id='1', key='entity', labels=['Person']),
                               dict(id='2', key='entity', labels=['Organization']),
                               dict(id='3', key='account', labels=['FinancialAccount'])],
                              ['FinancialAccount', 'Organization', 'Person'])
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
            validate_graph_targets(graph, plan())

    def test_a_collision_under_any_label_is_still_refused(self):
        graph = LabelledGraph([dict(id='1', key='entity', labels=['Person']),
                               dict(id='2', key='account', labels=['FinancialAccount']),
                               dict(id='3', key='account', labels=['Vehicle'])],
                              ['FinancialAccount', 'Person', 'Vehicle'])
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            validate_graph_targets(graph, plan())
