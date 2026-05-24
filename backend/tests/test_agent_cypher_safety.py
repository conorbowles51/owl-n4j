import unittest

from services.agent.cypher_safety import UnsafeCypherError, validate_readonly_cypher


class AgentCypherSafetyTests(unittest.TestCase):
    def test_requires_case_id_parameter(self):
        with self.assertRaises(UnsafeCypherError):
            validate_readonly_cypher("MATCH (n) RETURN n LIMIT 10")

    def test_rejects_write_keywords(self):
        with self.assertRaises(UnsafeCypherError):
            validate_readonly_cypher(
                "MATCH (n {case_id: $case_id}) SET n.name = 'bad' RETURN n"
            )

    def test_appends_limit_when_missing(self):
        query = validate_readonly_cypher(
            "MATCH (n {case_id: $case_id}) RETURN n",
            limit=25,
        )

        self.assertTrue(query.endswith("LIMIT 25"))

    def test_clamps_existing_limit(self):
        query = validate_readonly_cypher(
            "MATCH (n {case_id: $case_id}) RETURN n LIMIT 500",
            limit=50,
        )

        self.assertTrue(query.endswith("LIMIT 50"))


if __name__ == "__main__":
    unittest.main()
