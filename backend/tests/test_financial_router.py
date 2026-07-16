import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from routers import financial
from services.case_service import CaseAccessDenied


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

    async def test_export_financial_pdf_sets_headers_and_checks_case_access(self):
        case_id = str(uuid4())
        rendered = {
            "content": b"%PDF",
            "media_type": "application/pdf",
            "extension": "pdf",
        }

        with (
            patch.object(financial, "check_case_access") as check_access,
            patch.object(financial.neo4j_service, "get_financial_transactions", return_value={"transactions": []}),
            patch.object(financial, "render_financial_export", return_value=rendered),
        ):
            response = await financial.export_financial_pdf(
                case_id=case_id,
                mode="transactions",
                case_name='Case "Alpha"\r\nRésumé',
                categories=None,
                start_date=None,
                end_date=None,
                entity_key=None,
                entity_name=None,
                entity=None,
                search=None,
                search_header=None,
                from_entities=None,
                to_entities=None,
                include_entity_notes=False,
                current_user=SimpleNamespace(id="user-1"),
                db=object(),
            )

        check_access.assert_called_once()
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertNotIn("\r", response.headers["content-disposition"])
        self.assertNotIn("\n", response.headers["content-disposition"])
        self.assertIn("filename*=UTF-8''", response.headers["content-disposition"])

    async def test_export_financial_pdf_permission_denied_does_not_fetch_transactions(self):
        with (
            patch.object(financial, "check_case_access", side_effect=CaseAccessDenied("denied")),
            patch.object(financial.neo4j_service, "get_financial_transactions") as get_transactions,
        ):
            with self.assertRaises(HTTPException) as caught:
                await financial.export_financial_pdf(
                    case_id=str(uuid4()),
                    mode="transactions",
                    case_name="Case",
                    categories=None,
                    start_date=None,
                    end_date=None,
                    entity_key=None,
                    entity_name=None,
                    entity=None,
                    search=None,
                    search_header=None,
                    from_entities=None,
                    to_entities=None,
                    include_entity_notes=False,
                    current_user=object(),
                    db=object(),
                )

        self.assertEqual(caught.exception.status_code, 403)
        get_transactions.assert_not_called()


if __name__ == "__main__":
    unittest.main()
