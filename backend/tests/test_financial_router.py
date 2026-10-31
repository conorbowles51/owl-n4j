import json
import unittest
from unittest.mock import patch

from routers import financial


class FinancialRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_financial_transactions_uses_neo4j_facade(self):
        response = {
            "transactions": [],
            "total": 0,
            "dataset_mode": "transactions",
            "uses_legacy_financial_model": False,
        }

        with patch.object(
            financial.neo4j_service,
            "get_financial_transactions",
            return_value=response,
        ) as get_transactions:
            result = financial.get_financial_transactions(
                case_id="case-1",
                mode="transactions",
                types=None,
                start_date=None,
                end_date=None,
                categories=None,
            )

        # The route writes the JSON body itself (view_cache.json_response): the same bytes FastAPI would.
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(result.body), response)
        get_transactions.assert_called_once_with(
            case_id="case-1",
            mode="transactions",
            types=None,
            start_date=None,
            end_date=None,
            categories=None,
        )

    def test_graph_records_are_a_graph_view_scoped_to_the_case_files_geometry(self):
        """Kept whole like every cached Financial view (2.2-2.7 s on d5b330d1 otherwise), with the graph's state and
        the case's files' table geometry in its fingerprint."""
        from services.financial import view_cache
        self.assertIs(view_cache.handlers["graph-records"], financial.get_financial_transactions)
        self.assertIn("graph-records", view_cache._GRAPH)
        self.assertEqual(view_cache._FILE_SCOPED["graph-records"], frozenset({"evidence_table_geometry"}))

    def test_records_whose_locators_failed_are_shown_but_not_kept(self):
        from services.financial import view_cache
        recording = view_cache._Recording(owner=None, snapshot=None)
        token = view_cache._recording.set(recording)
        try:
            with patch.object(financial.neo4j_service, "get_financial_transactions",
                              return_value={"transactions": [{"key": "t1"}], "total": 1}), \
                    patch.object(financial, "attach_transaction_locators", side_effect=RuntimeError("geometry")):
                result = financial.get_financial_transactions(case_id="case-1", mode="transactions", types=None,
                                                              start_date=None, end_date=None, categories=None, db=None)
        finally:
            view_cache._recording.reset(token)
        self.assertEqual(result["transactions"], [{"key": "t1"}])  # the plain result, encoded by the view
        self.assertFalse(recording.keep)

if __name__ == "__main__":
    unittest.main()
