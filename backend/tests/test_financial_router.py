import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

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

    async def test_export_pdf_checks_case_view_permission_and_sets_export_header(self):
        case_id = uuid4()
        user = SimpleNamespace(email="investigator@example.com", name="Investigator")

        with patch.object(
            financial,
            "check_case_access",
            return_value=(SimpleNamespace(title="Case Alpha"), None),
        ) as check_access, patch.object(
            financial.neo4j_service,
            "get_financial_transactions",
            return_value={"transactions": []},
        ), patch.object(
            financial,
            "render_financial_export",
            return_value={
                "content": b"export",
                "media_type": "application/pdf",
                "extension": "pdf",
                "export_id": "exp_123456789abc",
            },
        ) as render_export:
            response = await financial.export_financial_pdf(
                case_id=str(case_id),
                mode="transactions",
                case_name="Spoofed Name",
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
                current_user=user,
                db=object(),
            )

        check_access.assert_called_once()
        self.assertEqual(check_access.call_args.args[1], case_id)
        self.assertEqual(check_access.call_args.kwargs["required_permission"], ("case", "view"))
        self.assertEqual(render_export.call_args.args[1], "Case Alpha")
        self.assertEqual(response.headers["x-export-id"], "exp_123456789abc")

    async def test_export_pdf_denies_without_case_view_permission(self):
        case_id = uuid4()
        user = SimpleNamespace(email="investigator@example.com", name="Investigator")

        with patch.object(
            financial,
            "check_case_access",
            side_effect=CaseAccessDenied(),
        ), patch.object(financial.neo4j_service, "get_financial_transactions") as get_transactions:
            with self.assertRaises(HTTPException) as raised:
                await financial.export_financial_pdf(
                    case_id=str(case_id),
                    mode="transactions",
                    case_name="Case Alpha",
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
                    current_user=user,
                    db=object(),
                )

        self.assertEqual(raised.exception.status_code, 403)
        get_transactions.assert_not_called()


if __name__ == "__main__":
    unittest.main()
