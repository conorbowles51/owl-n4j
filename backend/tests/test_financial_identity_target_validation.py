"""Identity validation retains cross-label collision and exact-target checks."""
from unittest import TestCase
from services.financial.identity_graph import validate_graph_targets


class Graph:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def run(self, query, **params):
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
