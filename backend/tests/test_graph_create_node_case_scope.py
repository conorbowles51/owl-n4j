"""A hand-made entity or link is written inside its own case, and never replaces an entity already there."""
import unittest
from unittest.mock import patch

from routers import graph
from services.cypher_generator import generate_cypher_from_graph


def _create(run_read, name="Harbour Trust"):
    request = graph.CreateNodeRequest(name=name, type="Organization", case_id="case-a")
    with patch("services.neo4j_service.neo4j_service") as neo, patch.object(graph, "system_log_service"):
        neo.run_cypher_read.side_effect = run_read
        answer = graph.create_node(request, {"username": "someone"})
    return answer, neo


class GeneratedCypherStaysInItsCase(unittest.TestCase):
    def test_a_node_merges_on_its_key_and_case(self):
        cypher = generate_cypher_from_graph({"nodes": [{"key": "k", "name": "K", "type": "Person"}], "links": []}, "case-a")
        self.assertIn("MERGE (n:`Person` {key: 'k', case_id: 'case-a'})", cypher)

    def test_a_node_with_links_merges_on_its_key_and_case(self):
        cypher = generate_cypher_from_graph(
            {"nodes": [{"key": "k", "name": "K", "type": "Person"}], "links": [{"source": "k", "target": "m", "type": "KNOWS"}]},
            "case-a",
        )
        self.assertIn("MERGE (n:`Person` {key: 'k', case_id: 'case-a'})", cypher)
        self.assertIn("MATCH (a {key: 'k', case_id: 'case-a'}), (b {key: 'm', case_id: 'case-a'})", cypher)

    def test_a_link_finds_both_ends_in_its_case(self):
        cypher = generate_cypher_from_graph({"nodes": [], "links": [{"source": "k", "target": "m", "type": "KNOWS"}]}, "case-a")
        self.assertIn("MATCH (a {key: 'k', case_id: 'case-a'}), (b {key: 'm', case_id: 'case-a'})", cypher)

    def test_a_quote_in_the_case_id_stays_inside_the_string(self):
        cypher = generate_cypher_from_graph({"nodes": [{"key": "k", "name": "K", "type": "Person"}], "links": []}, "o'brien")
        self.assertIn("case_id: 'o\\'brien'})", cypher)


class CreateNodeRoute(unittest.TestCase):
    def test_a_new_name_keeps_its_plain_key(self):
        answer, neo = _create(lambda *a: [])
        self.assertTrue(answer.success)
        self.assertEqual(answer.node_key, "harbour-trust")
        self.assertIn("key: 'harbour-trust', case_id: 'case-a'", neo.run_cypher.call_args.args[0])

    def test_a_name_in_this_case_is_refused_and_nothing_is_written(self):
        answer, neo = _create(lambda *a: [{"case_id": "case-a", "name": "Harbour Trust", "type": "Person"}])
        self.assertFalse(answer.success)
        self.assertEqual(answer.error, '"Harbour Trust" is already in this case; nothing was changed.')
        neo.run_cypher.assert_not_called()

    def test_a_name_in_another_case_gets_a_key_of_its_own(self):
        answer, neo = _create(lambda *a: [{"case_id": "case-b", "name": "Harbour Trust", "type": "Organization"}])
        self.assertTrue(answer.success)
        self.assertRegex(answer.node_key, r"^harbour-trust-[0-9a-f]{8}$")
        written = neo.run_cypher.call_args.args[0]
        self.assertIn(f"key: '{answer.node_key}', case_id: 'case-a'", written)
        self.assertNotIn("key: 'harbour-trust'", written)


if __name__ == "__main__":
    unittest.main()
