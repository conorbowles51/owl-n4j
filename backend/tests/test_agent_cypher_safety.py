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

    def test_clamps_requested_limit_to_hard_cap(self):
        query = validate_readonly_cypher(
            "MATCH (n {case_id: $case_id}) RETURN n LIMIT 500",
            limit=500,
        )

        self.assertTrue(query.endswith("LIMIT 200"))

    def test_replaces_parameterized_limit_with_numeric_cap(self):
        query = validate_readonly_cypher(
            "MATCH (n {case_id: $case_id}) RETURN n LIMIT $limit",
            limit=25,
        )

        self.assertTrue(query.endswith("LIMIT 25"))
        self.assertNotIn("$limit", query)

    def test_rejects_fake_case_scope(self):
        with self.assertRaises(UnsafeCypherError):
            validate_readonly_cypher(
                "MATCH (n) WHERE $case_id IS NOT NULL RETURN n",
            )

    def test_rejects_unsupported_null_ordering(self):
        with self.assertRaises(UnsafeCypherError):
            validate_readonly_cypher(
                "MATCH (n {case_id: $case_id}) RETURN n ORDER BY n.date NULLS LAST",
            )

    def test_allows_semicolon_inside_string_literal(self):
        query = validate_readonly_cypher(
            "MATCH (n {case_id: $case_id}) RETURN 'a.txt; b.txt' AS sources",
            limit=10,
        )

        self.assertIn("'a.txt; b.txt'", query)

    def test_rejects_second_statement_after_semicolon(self):
        with self.assertRaises(UnsafeCypherError):
            validate_readonly_cypher(
                "MATCH (n {case_id: $case_id}) RETURN n; MATCH (m {case_id: $case_id}) RETURN m",
            )


if __name__ == "__main__":
    unittest.main()
