import unittest

from services.cypher_generator import format_properties, generate_cypher_from_graph


class CypherGeneratorTests(unittest.TestCase):
    def test_boolean_true_serialises_as_true(self):
        props = format_properties({"active": True})

        self.assertIn("active: true", props)
        self.assertNotIn("active: 1", props)

    def test_boolean_false_serialises_as_false(self):
        props = format_properties({"verified": False})

        self.assertIn("verified: false", props)
        self.assertNotIn("verified: 0", props)

    def test_integer_properties_remain_numeric(self):
        props = format_properties({"count": 5})

        self.assertIn("count: 5", props)
        self.assertNotIn("count: '5'", props)
        self.assertNotIn("count: true", props)
        self.assertNotIn("count: false", props)

    def test_float_properties_remain_numeric(self):
        props = format_properties({"score": 3.5})

        self.assertIn("score: 3.5", props)
        self.assertNotIn("score: '3.5'", props)
        self.assertNotIn("score: true", props)
        self.assertNotIn("score: false", props)

    def test_boolean_and_integer_side_by_side(self):
        props = format_properties(
            {
                "active": True,
                "count": 5,
                "verified": False,
                "score": 3.5,
            }
        )

        self.assertIn("active: true", props)
        self.assertIn("count: 5", props)
        self.assertIn("verified: false", props)
        self.assertIn("score: 3.5", props)
        self.assertNotIn("active: 1", props)
        self.assertNotIn("verified: 0", props)

    def test_generate_cypher_from_graph_preserves_bool_in_node(self):
        graph_data = {
            "nodes": [
                {
                    "key": "node-1",
                    "id": "node-1",
                    "name": "Node 1",
                    "type": "Person",
                    "properties": {
                        "active": True,
                        "verified": False,
                        "count": 5,
                        "score": 3.5,
                    },
                }
            ],
            "links": [],
        }

        cypher = generate_cypher_from_graph(graph_data, case_id="case-1")

        self.assertIn("active: true", cypher)
        self.assertIn("verified: false", cypher)
        self.assertIn("count: 5", cypher)
        self.assertIn("score: 3.5", cypher)
        self.assertNotIn("active: 1", cypher)
        self.assertNotIn("verified: 0", cypher)

    def test_generate_cypher_from_graph_preserves_bool_in_relationship(self):
        graph_data = {
            "nodes": [],
            "links": [
                {
                    "source": "node-1",
                    "target": "node-2",
                    "type": "KNOWS",
                    "properties": {
                        "active": True,
                        "verified": False,
                        "count": 5,
                        "score": 3.5,
                    },
                }
            ],
        }

        cypher = generate_cypher_from_graph(graph_data, case_id="case-1")

        self.assertIn("active: true", cypher)
        self.assertIn("verified: false", cypher)
        self.assertIn("count: 5", cypher)
        self.assertIn("score: 3.5", cypher)
        self.assertNotIn("active: 1", cypher)
        self.assertNotIn("verified: 0", cypher)

    def test_boolean_not_misdetected_as_int_subclass(self):
        self.assertIsInstance(True, int)

        props = format_properties({"flag": True, "amount": 1})

        self.assertIn("flag: true", props)
        self.assertIn("amount: 1", props)
        self.assertNotIn("flag: 1", props)


if __name__ == "__main__":
    unittest.main()
