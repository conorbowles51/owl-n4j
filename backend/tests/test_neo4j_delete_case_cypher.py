"""delete_case_data runs its batched deletes in the scoped CALL form (Neo4j 5.26 deprecates importing WITH)."""
import re
import unittest
from unittest.mock import MagicMock

from services.neo4j import driver as singleton


class DeleteCaseCypher(unittest.TestCase):
    def test_batched_deletes_use_the_scoped_call(self):
        neo = type(singleton).__new__(type(singleton))
        session = MagicMock()
        neo._driver = MagicMock()
        neo._driver.session.return_value.__enter__.return_value = session
        session.run.return_value.single.return_value = {"count": 3}

        out = neo.delete_case_data("case-1")

        sent = [c.args[0] for c in session.run.call_args_list]
        batched = [q for q in sent if "IN TRANSACTIONS" in q]
        self.assertEqual(len(batched), 2)
        self.assertTrue(any("CALL (r) { DELETE r }" in q for q in batched), batched)
        self.assertTrue(any("CALL (n) { DETACH DELETE n }" in q for q in batched), batched)
        self.assertFalse([q for q in sent if re.search(r"CALL\s*\{\s*WITH", q)])
        self.assertEqual((out["nodes_deleted"], out["relationships_deleted"]), (3, 3))


if __name__ == "__main__":
    unittest.main()
