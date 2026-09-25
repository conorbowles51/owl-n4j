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


class AgentCypherBindingScopeTests(unittest.TestCase):
    def test_rejects_every_unproved_binding_or_hidden_query(self):
        queries = [
            "MATCH (allowed {case_id: $case_id}) MATCH (foreign) RETURN foreign",
            "MATCH (n {case_id: $case_id}) RETURN n // comment\r UNION MATCH (other) RETURN other",
            "MATCH (n) WHERE true /* /* nested */ AND n.case_id = $case_id AND 1 */ AND true RETURN n",
            "MATCH (n) WHERE true // comment\u2028 AND n.case_id = $case_id\n RETURN n",

            "MATCH (allowed {case_id: $case_id}), (foreign) RETURN foreign",
            "MATCH (allowed {case_id: $case_id}) OPTIONAL MATCH (foreign) RETURN foreign",
            "MATCH (allowed {case_id: $case_id})-[:RELATED]->(foreign) RETURN foreign",
            "MATCH (allowed {case_id: $case_id})-[:RELATED]->() RETURN count(*)",
            "MATCH (n) WHERE n.case_id = $case_id OR true RETURN n",
            "MATCH (n) WHERE NOT n.case_id = $case_id RETURN n",
            "MATCH (n) WHERE CASE WHEN n.active THEN false AND n.case_id = $case_id AND false ELSE true END RETURN n",
            "MATCH (n) WHERE (n.case_id = $case_id) IS NOT NULL RETURN n",
            "MATCH (n) WHERE n.case_id = $case_id XOR true RETURN n",
            "MATCH (n) WHERE (n.case_id = $case_id AND n.active = true) OR n.active = false RETURN n",
            "MATCH (n) WHERE n.name = 'n.case_id = $case_id' RETURN n",
            "MATCH (n) /* n.case_id = $case_id */ RETURN n",
            "MATCH (n {metadata: {case_id: $case_id}}) RETURN n",
            "MATCH (n {case_id: $case_id, case_id: 'other'}) RETURN n",
            "MATCH (n {case_id: $case_id}) RETURN n UNION MATCH (other) RETURN other",
            "MATCH (n {case_id: $case_id}) WITH 1 AS n MATCH (other) RETURN other",
            "WITH $case_id AS case_id MATCH (n) RETURN n",
            "UNWIND $nodes AS n RETURN n, $case_id",
            "MATCH (n {case_id: $case_id}) RETURN [(n)-->(other) | other]",
            "MATCH (n {case_id: $case_id}) RETURN COUNT { MATCH (other) RETURN other }",
            "MATCH (n {case_id: $case_id}) WHERE EXISTS { MATCH (other) } RETURN n",
            "MATCH (n {case_id: $case_id}) WHERE n.active = true AND (n)-->() RETURN n",
            "MATCH (n {case_id: $case_id}) RETURN CASE WHEN (n)-->() THEN 1 ELSE 0 END",
            "MATCH p=(n {case_id: $case_id})-[*]->(m {case_id: $case_id}) RETURN p",
            "MATCH p=shortestPath((n {case_id: $case_id})-[*]->(m)) RETURN p",
            "MATCH (n {case_id: $case_id}) RETURN apoc.cypher.runFirstColumn($query, $params, true)",
            "MATCH (n {case_id: $case_id}) RETURN customRead($query)",
            "MATCH (`n` {case_id: $case_id}) RETURN `n`",
            "MATCH (a {case_id:$case_id})-[r {case_id:$other_case}]->(b {case_id:$case_id}) RETURN properties(r)",
            "MATCH p=(a {case_id:$case_id})-[r]->(b {case_id:$case_id}) RETURN p",
            "MATCH p=(a {case_id:$case_id})-[r]->(b {case_id:$case_id}) RETURN relationships(p)",
            "MATCH (a {case_id:$case_id})-->(b {case_id:$case_id}) RETURN count(*)",
            "MATCH (a {case_id:$case_id})-[:RELATED]->(b {case_id:$case_id}) RETURN b",
            "MATCH (a {case_id:$case_id})-[r]->(b {case_id:$case_id}) WHERE r.case_id = $case_id OR true RETURN r",
            "MATCH (a {case_id:$case_id})-[r]->(b {case_id:$case_id}) WHERE CASE WHEN a.active THEN true AND r.case_id = $case_id AND true ELSE true END RETURN r",
            "MATCH (n) WHERE n.CASE_ID = $case_id RETURN n",
            "MATCH (n) WHERE n.case_id = $CASE_ID RETURN n",
            "MATCH (n) WHERE N.case_id = $case_id RETURN n",
            "MATCH (n) OPTIONAL MATCH (m {case_id: $case_id}) WHERE n.case_id = $case_id RETURN n",
        ]
        for query in queries:
            with self.subTest(query=query), self.assertRaises(UnsafeCypherError):
                validate_readonly_cypher(query)

    def test_preserves_explicitly_scoped_joins_and_scalar_aggregates(self):
        queries = [
            "MATCH (n:Person {case_id: $case_id}) RETURN n",
            "MATCH (n:Person) WHERE n.case_id = $case_id RETURN n",
            "MATCH (n) WHERE $case_id = n.case_id RETURN n",
            "MATCH (n) WHERE (n.case_id = $case_id) AND n.name CONTAINS 'example' RETURN n.name",
            "MATCH (n) WHERE (n.case_id = $case_id AND n.active = true) OR (n.case_id = $case_id AND n.active = false) RETURN n",
            "MATCH (a {case_id: $case_id}), (b {case_id: $case_id}) RETURN a.name, b.name",
            "MATCH (a {case_id: $case_id})-[r:RELATED {case_id: $case_id}]->(b {case_id: $case_id}) RETURN a, r, b",
            "MATCH (a)-[r:RELATED]->(b) WHERE a.case_id = $case_id AND b.case_id = $case_id AND r.case_id = $case_id RETURN a.name, type(r), b.name",
            "MATCH (a {case_id: $case_id}) OPTIONAL MATCH (a)-[:RELATED {case_id: $case_id}]->(b) WHERE b.case_id = $case_id RETURN a, b",
            "MATCH (a {case_id: $case_id}) MATCH (a)<-[r:RELATED {case_id: $case_id}]-(b {case_id: $case_id}) RETURN a, b, r",
            "MATCH p=(a {case_id: $case_id})-[{case_id: $case_id}]->(b {case_id: $case_id})-[{case_id: $case_id}]-(c {case_id: $case_id}) RETURN nodes(p), relationships(p)",
            "MATCH ({case_id: $case_id})-[{case_id: $case_id}]->(b {case_id: $case_id}) RETURN count(b)",
            "MATCH (n {case_id: $case_id}) RETURN n.kind AS kind, count(*) AS total ORDER BY total DESC",
            "MATCH (n {case_id: $case_id}) WHERE toLower(n.name) CONTAINS 'sample' RETURN coalesce(n.name, 'Unknown'), sum(n.amount)",
            "MATCH (n {case_id: $case_id}) WHERE CASE WHEN n.active THEN true ELSE false END RETURN CASE WHEN n.name IS NULL THEN 'Unknown' ELSE n.name END",
            "MATCH (n {case_id: $case_id}) RETURN 'https://example.test/MATCH//; UNION' AS url",
            "MATCH p=(a {case_id:$case_id})-[r]->(b {case_id:$case_id}) WHERE r.case_id=$case_id RETURN p, relationships(p)",
            "MATCH (a {case_id:$case_id})-[r {case_id:$case_id}]->(a) RETURN r",
            "MATCH (n {case_id: $case_id}) // real comment\n RETURN n.name",
        ]
        for query in queries:
            with self.subTest(query=query):
                self.assertTrue(validate_readonly_cypher(query, limit=12).endswith("LIMIT 12"))

    def test_tool_syntax_repair_preserves_literals_and_comment_boundaries(self):
        from services.agent.cypher_safety import repair_common_cypher
        query = "MATCH (a {case_id:$case_id}) // comment\n RETURN count(a) AS total, 'NULLS LAST; LIMIT $rows' AS text ORDER BY total NULLS LAST LIMIT $rows"
        repaired = repair_common_cypher(query)
        self.assertIn("// comment\n RETURN", repaired)
        self.assertIn("'NULLS LAST; LIMIT $rows'", repaired)
        self.assertTrue(validate_readonly_cypher(repaired, limit=9).endswith("LIMIT 9"))
        self.assertTrue(validate_readonly_cypher(repair_common_cypher(query + ";"), limit=9).endswith("LIMIT 9"))
        unsafe = "MATCH (a {case_id:$case_id}) // comment\n MATCH (foreign) RETURN foreign"
        with self.assertRaises(UnsafeCypherError):
            validate_readonly_cypher(repair_common_cypher(unsafe))

    def test_strings_and_comments_cannot_bypass_the_row_cap(self):
        for query in (
            "MATCH (n {case_id: $case_id}) RETURN 'LIMIT 1' AS text",
            "MATCH (n {case_id: $case_id}) RETURN n // LIMIT 1",
        ):
            with self.subTest(query=query):
                self.assertTrue(validate_readonly_cypher(query, limit=8).endswith("\nLIMIT 8"))
        with self.assertRaises(UnsafeCypherError):
            validate_readonly_cypher("MATCH (n {case_id: $case_id}) RETURN n LIMIT 1 + 100000")

    def test_accepted_boolean_filters_cannot_be_true_for_a_foreign_node(self):
        # Independent truth-table oracle: the case equality is false for a
        # foreign node. Other properties may be either true or false. No query
        # is executed, and rejection of a harder but safe expression is allowed.
        from itertools import product
        expressions = [
            ("n.case_id = $case_id", (False, False)),
            ("NOT (n.case_id = $case_id)", (True, True)),
            ("n.active", (False, True)),
            ("true", (True, True)),
            ("false", (False, False)),
        ]
        operations = {
            "AND": lambda left, right: left and right,
            "OR": lambda left, right: left or right,
            "XOR": lambda left, right: left != right,
        }
        first_level = []
        for (left, left_values), (right, right_values), operator in product(expressions, expressions, operations):
            values = tuple(operations[operator](a, b) for a, b in zip(left_values, right_values))
            first_level.append((f"({left} {operator} {right})", values))
        accepted = 0
        for (left, left_values), (right, right_values), operator in product(first_level, expressions, operations):
            expression = f"({left} {operator} ({right}))"
            with self.subTest(expression=expression):
                try:
                    validate_readonly_cypher(f"MATCH (n) WHERE {expression} RETURN n")
                except UnsafeCypherError:
                    continue
                accepted += 1
                self.assertFalse(any(operations[operator](a, b) for a, b in zip(left_values, right_values)))
        self.assertGreater(accepted, 0)

    def test_rejection_never_opens_a_driver_session_and_case_parameter_cannot_be_overridden(self):
        from unittest.mock import MagicMock, patch
        from services.agent.cypher_safety import run_readonly_cypher
        with patch("services.agent.cypher_safety.driver") as driver:
            with self.assertRaises(UnsafeCypherError):
                run_readonly_cypher("MATCH (n {case_id: $case_id}) MATCH (other) RETURN other", case_id="synthetic-case")
            driver.session.assert_not_called()
            tx = MagicMock()
            tx.run.return_value = [{"count": 0}]
            driver.session.return_value.__enter__.return_value.execute_read.side_effect = lambda work: work(tx)
            self.assertEqual(run_readonly_cypher("MATCH (n {case_id: $case_id}) RETURN count(n) AS count", case_id="synthetic-case", params={"case_id": "other-case"}), [{"count": 0}])
            self.assertEqual(tx.run.call_args.args[1]["case_id"], "synthetic-case")


if __name__ == "__main__":
    unittest.main()
