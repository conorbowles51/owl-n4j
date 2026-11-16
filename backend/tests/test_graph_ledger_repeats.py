"""The Graph page leaves out the document model's copies of ledger payments and says how many (followups,
16 Nov 2026: the demo case drew 215 of its statement payments twice, once as the ledger row and once or twice
as the model's reading of the same line)."""
import unittest
from unittest.mock import patch

from services.neo4j.graph_service import GraphService
from services.neo4j.timeline_service import timeline_service


def _graph():
    return {
        "nodes": [{"key": "ledger-rent", "type": "FinancialTransaction"}, {"key": "model-rent", "type": "Transaction"},
                  {"key": "model-deposit", "type": "Transaction"}, {"key": "kell", "type": "Person"}],
        "links": [{"source": "model-rent", "target": "kell", "type": "PAID"},
                  {"source": "ledger-rent", "target": "kell", "type": "PAID"},
                  {"source": "kell", "target": "model-rent", "type": "MENTIONED_IN"}],
    }


class DropLedgerRepeatsTests(unittest.TestCase):
    def test_a_model_copy_of_a_ledger_row_and_its_links_are_left_out_and_counted(self):
        with patch.object(timeline_service, "ledger_repeat_keys", return_value=["model-rent"]):
            out = GraphService().drop_ledger_repeats("case-1", _graph())
        self.assertEqual([n["key"] for n in out["nodes"]], ["ledger-rent", "model-deposit", "kell"])
        self.assertEqual(out["links"], [{"source": "ledger-rent", "target": "kell", "type": "PAID"}])
        self.assertEqual(out["ledger_repeats_hidden"], 1)

    def test_a_model_payment_the_ledger_lacks_stays(self):
        with patch.object(timeline_service, "ledger_repeat_keys", return_value=[]):
            out = GraphService().drop_ledger_repeats("case-1", _graph())
        self.assertEqual(len(out["nodes"]), 4)
        self.assertEqual(len(out["links"]), 3)
        self.assertEqual(out["ledger_repeats_hidden"], 0)

    def test_the_capped_read_takes_them_out_of_its_total(self):
        graph = {**_graph(), "total_node_count": 10}
        with patch.object(timeline_service, "ledger_repeat_keys", return_value=["model-rent", "model-off-screen"]):
            out = GraphService().drop_ledger_repeats("case-1", graph)
        self.assertEqual(out["total_node_count"], 8)
        self.assertEqual(out["ledger_repeats_hidden"], 2)

    def test_the_significant_scope_counts_only_its_own(self):
        with patch.object(timeline_service, "ledger_repeat_keys", return_value=["model-rent", "elsewhere"]):
            out = GraphService().drop_ledger_repeats("case-1", {**_graph(), "total_node_count": 4},
                                                     entity_keys=["model-rent", "kell"])
        self.assertEqual(out["ledger_repeats_hidden"], 1)
        self.assertEqual(out["total_node_count"], 3)


class GraphRouteTests(unittest.TestCase):
    def test_only_the_graph_page_asks_for_it_and_its_read_has_a_key_of_its_own(self):
        from routers import graph
        plain_key, _ = graph._graph_read("case-1", "all", None, True, None, None)
        page_key, compute = graph._graph_read("case-1", "all", None, True, None, None, hide_ledger_repeats=True)
        self.assertNotEqual(plain_key, page_key)
        with patch.object(graph.neo4j_service, "get_graph_structure", return_value=_graph()), \
                patch.object(timeline_service, "ledger_repeat_keys", return_value=["model-rent"]):
            self.assertEqual(compute()["ledger_repeats_hidden"], 1)

    def test_the_dated_read_leaves_them_out_too(self):
        from routers import graph
        with patch.object(graph.neo4j_service, "get_graph_structure", return_value=_graph()), \
                patch.object(timeline_service, "ledger_repeat_keys", return_value=["model-rent"]), \
                patch.object(graph.system_log_service, "log"):
            out = graph.get_graph(case_id="case-1", start_date="2023-01-01", end_date=None, lightweight=True,
                                  limit=None, sort_by=None, phone_cap=False, scope="all", hide_ledger_repeats=True,
                                  request=None, db=None, user={})
        self.assertEqual(out["ledger_repeats_hidden"], 1)
        self.assertNotIn("model-rent", [n["key"] for n in out["nodes"]])


if __name__ == "__main__":
    unittest.main()
