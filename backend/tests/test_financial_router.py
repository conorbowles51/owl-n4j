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
            result = await financial.get_financial_transactions(
                case_id="case-1",
                mode="transactions",
                types=None,
                start_date=None,
                end_date=None,
                categories=None,
            )

        self.assertEqual(result, response)
        get_transactions.assert_called_once_with(
            case_id="case-1",
            mode="transactions",
            types=None,
            start_date=None,
            end_date=None,
            categories=None,
        )


if __name__ == "__main__":
    unittest.main()
