"""lx-agentquick F: entity search reads aliases and every word of a multi-word query (the tool says it covers aliases;
the Cypher read only name, key, summary and notes as one phrase)."""
import unittest
from unittest.mock import patch

import importlib

GS = importlib.import_module("services.neo4j.graph_service")


class FakeSession:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return []


class SearchNodesAliases(unittest.TestCase):
    def test_the_query_covers_aliases_and_each_word(self):
        session = FakeSession()
        with patch.object(GS.driver, "session", lambda *a, **k: session):
            GS.GraphService().search_nodes("Elkmere  Mortgage", limit=5, case_id="c1")
        query, params = session.calls[0]
        self.assertEqual(params["terms"], ["elkmere", "mortgage"])
        self.assertEqual(params["search_lower"], "elkmere  mortgage")
        self.assertIn("n.aliases", query)
        self.assertIn("ALL(t IN $terms", query)
        self.assertIn("n.case_id = $case_id", query)  # still scoped to the case

    def test_a_single_word_still_works(self):
        session = FakeSession()
        with patch.object(GS.driver, "session", lambda *a, **k: session):
            GS.GraphService().search_nodes("Kell", case_id="c1")
        self.assertEqual(session.calls[0][1]["terms"], ["kell"])


if __name__ == "__main__":
    unittest.main()
