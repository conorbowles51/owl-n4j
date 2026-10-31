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

    def test_graph_records_a_browser_already_holds_are_answered_304(self):
        """d5b330d1's records are 2.9 MB gzipped per visit of the Other financial records tab."""
        from services.financial import view_cache
        response = {"transactions": [{"key": "t1", "amount": 5.0}], "total": 1}

        def get():
            with patch.object(financial.neo4j_service, "get_financial_transactions", return_value=response):
                return financial.get_financial_transactions(case_id="case-1", mode="transactions", types=None,
                                                            start_date=None, end_date=None, categories=None, db=None)
        first = get()
        self.assertEqual(first.headers["cache-control"], "private, no-cache")
        token = view_cache._if_none_match.set(first.headers["etag"])
        try:
            again = get()
            self.assertEqual((again.status_code, again.body), (304, b""))
            response["total"] = 2
            changed = get()
        finally:
            view_cache._if_none_match.reset(token)
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed.headers["etag"], first.headers["etag"])


if __name__ == "__main__":
    unittest.main()
