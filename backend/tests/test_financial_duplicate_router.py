import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException
from routers import financial_ledger
from services.financial.duplicate_query import DuplicateQueryLimitError


class DuplicateRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_case_and_whole_response_are_preserved(self):
        case_id = uuid.uuid4()
        payload = {"case_id": str(case_id), "documents": 0, "compared": 0,
                   "groups": [], "skipped": []}
        with patch.object(financial_ledger, "list_duplicate_candidates", return_value=payload) as call:
            self.assertEqual(await financial_ledger.get_duplicate_candidates(case_id, "db"), payload)
        call.assert_called_once_with("db", case_id)

    async def test_limit_is_explicit_and_fault_does_not_expose_database_details(self):
        for error, status in [(DuplicateQueryLimitError("Too many documents"), 422),
                              (RuntimeError("private database detail"), 500)]:
            with self.subTest(status=status), patch.object(
                financial_ledger, "list_duplicate_candidates", side_effect=error
            ):
                with self.assertRaises(HTTPException) as caught:
                    await financial_ledger.get_duplicate_candidates(uuid.uuid4(), "db")
                self.assertEqual(caught.exception.status_code, status)
                self.assertNotIn("private database detail", caught.exception.detail)

    def test_route_inherits_authenticated_case_view_permission(self):
        route = next(r for r in financial_ledger.router.routes if r.path == "/api/financial/duplicates")
        calls = {dependency.call for dependency in route.dependant.dependencies}
        self.assertIn(financial_ledger.get_current_db_user, calls)
        self.assertIn(financial_ledger._require_ledger_case_access, calls)
        self.assertEqual(financial_ledger._ledger_case_permission(None, {}), ("case", "view"))
        self.assertEqual(route.methods, {"GET"})
