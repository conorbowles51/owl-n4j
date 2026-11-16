"""The Graph lists phone pairs busiest first from the count each COMMUNICATED link carries (lx-graphclarity B)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.neo4j.graph_service import _LINK_COLUMNS, GraphService
from tests.test_significant_projections import _Session, _packed


class PairContactTests(unittest.TestCase):
    def test_communicated_links_carry_their_total_and_other_links_do_not(self):
        captured = []
        nodes = [{"key": k, "name": k, "type": "PhoneIdentity", "confidence": None, "mentioned": None,
                  "aliases": None, "source_files": None} for k in ("phone-identity:a", "phone-identity:b")]
        links = [
            {"source": "phone-identity:a", "target": "phone-identity:b", "type": "COMMUNICATED", "weight": None, "contact": 21},
            {"source": "phone-identity:a", "target": "phone-identity:b", "type": "APPEARS_ON", "weight": None, "contact": None},
        ]
        with patch("services.neo4j.graph_service.driver.session",
                   return_value=_Session(captured, [_packed(nodes), _packed(links, _LINK_COLUMNS)])):
            graph = GraphService().get_graph_structure("case-1", entity_keys=["phone-identity:a", "phone-identity:b"])
        self.assertEqual(graph["links"][0]["contact"], 21)
        self.assertNotIn("contact", graph["links"][1])
        query = captured[1]["query"]
        for field in ("messages_ab", "messages_ba", "calls_ab", "calls_ba", "emails_ab", "emails_ba"):
            self.assertIn(f"r.{field}", query)
        self.assertIn("type(r) = 'COMMUNICATED'", query)


if __name__ == "__main__":
    unittest.main()
