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


class DuplicateDecisionRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_writer_passes_authenticated_actor_and_reviewed_revisions(self):
        from types import SimpleNamespace
        from routers import financial_adjudication as router
        case_id, document_id, primary_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4(), name="Reviewer", email="reviewer@example.test")
        body = router.DuplicateDecisionRequest(action="exclude", reason="Confirmed copy",
            expected_revision="a" * 64, primary_id=primary_id, expected_primary_revision="b" * 64)
        with patch.object(router, "decide_duplicate", return_value={"applied": True}) as call:
            result = await router.record_duplicate_decision(document_id, body, case_id, user, "db")
        self.assertTrue(result["applied"])
        self.assertEqual(call.call_args.kwargs["actor"].user_id, user.id)
        self.assertEqual(call.call_args.kwargs["expected_primary_revision"], "b" * 64)
        self.assertEqual(call.call_args.kwargs["case_id"], case_id)

    async def test_refusal_and_uncertain_fault_are_distinct(self):
        from types import SimpleNamespace
        from routers import financial_adjudication as router
        from services.financial.duplicate_decisions import DuplicateDecisionError
        user = SimpleNamespace(id=uuid.uuid4(), name="Reviewer", email="reviewer@example.test")
        body = router.DuplicateDecisionRequest(action="restore", reason="Reviewed", expected_revision="a" * 64)
        for error, status in [(DuplicateDecisionError("Refresh the comparison"), 409), (RuntimeError("private detail"), 500)]:
            with self.subTest(status=status), patch.object(router, "decide_duplicate", side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    await router.record_duplicate_decision(uuid.uuid4(), body, uuid.uuid4(), user, "db")
                self.assertEqual(caught.exception.status_code, status)
                self.assertNotIn("private detail", caught.exception.detail)

    def test_writes_require_case_edit(self):
        from routers import financial_adjudication as router
        route = next(r for r in router.router.routes if r.path.endswith("/duplicate-decision"))
        calls = {dependency.call for dependency in route.dependant.dependencies}
        self.assertIn(router.get_current_db_user, calls)
        self.assertIn(router._require_adjudication_case_access, calls)
        self.assertEqual(router._adjudication_case_permission(None, {}), ("case", "edit"))
        self.assertEqual(route.methods, {"POST"})
