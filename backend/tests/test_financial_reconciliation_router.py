"""Tests for the reconciliation router, mirroring ``test_financial_ledger_router``.

The handlers are awaited directly rather than through a test client, and the
service calls they delegate to are mocked, so these are about the router's own
responsibilities: which permission each verb resolves to, status-string
validation, error translation, and response shape.  The arithmetic and the
sweep are covered by ``test_financial_reconcile`` and
``test_financial_reconcile_case``.

Three of the router's choices are load bearing and are held here rather than
left to a docstring.

*The permission is taken from the verb.*  The read is ``case:view`` and the
recompute is ``case:edit``.  A route added to this router later inherits the
bar its verb implies, so the test asserts the mapping for methods the router
does not currently serve as well as the two it does.

*A refusal is not an error.*  A sweep that found no periods, and a sweep in
which every period refused, both come back ``200``.  Those are facts about the
case, and an interface has to render them beside the ledger rather than in an
error path.  Only a failed write is a ``500``.

*An unknown status is a ``400`` that names the valid words.*  Including
``not_attempted``, which is the status a caller most needs to be able to ask
for and the one least likely to be guessed.
"""

import unittest
import uuid
from datetime import date
from unittest.mock import patch

from fastapi import HTTPException

from postgres.models.enums import ReconciliationStatus
from routers import financial_reconciliation
from services.financial.reconcile_case import (
    CaseOutcome,
    CaseReconciliation,
    PeriodOutcome,
    PeriodReconciliation,
    ReconciliationQueryError,
)


class FakeRequest:
    """Only ``.method`` is read by the resolver under test."""

    def __init__(self, method: str):
        self.method = method


def period_result(outcome: PeriodOutcome = PeriodOutcome.balanced):
    return PeriodReconciliation(
        period_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        currency="GBP",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        outcome=outcome,
        stored_status=outcome.value,
        identity=None,
        reason=None,
    )


class PermissionResolutionTests(unittest.TestCase):
    def test_safe_methods_resolve_to_case_view(self):
        for method in ("GET", "HEAD", "OPTIONS"):
            with self.subTest(method=method):
                self.assertEqual(
                    financial_reconciliation._reconciliation_case_permission(
                        FakeRequest(method), {}
                    ),
                    ("case", "view"),
                )

    def test_every_other_method_resolves_to_case_edit(self):
        # PUT, PATCH and DELETE are not served today.  The assertion is that a
        # route added later cannot land on the reading permission by accident.
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(
                    financial_reconciliation._reconciliation_case_permission(
                        FakeRequest(method), {}
                    ),
                    ("case", "edit"),
                )


class GetCaseReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_the_query_service_and_shapes_the_response(self):
        case_id = uuid.uuid4()
        fake_row = object()
        view_payload = {"period_id": "period-1"}

        class FakeView:
            def to_json(self):
                return view_payload

        with patch.object(
            financial_reconciliation,
            "list_period_reconciliations",
            return_value=[fake_row],
        ) as list_call, patch.object(
            financial_reconciliation,
            "to_reconciliation_view",
            return_value=FakeView(),
        ) as view_call:
            result = await financial_reconciliation.get_case_reconciliation(
                case_id=case_id,
                account_id=None,
                reconciliation_status=None,
                limit=None,
                db="fake-session",
            )

        self.assertEqual(
            result,
            {
                "case_id": str(case_id),
                "periods": [view_payload],
                "total": 1,
            },
        )
        list_call.assert_called_once_with(
            "fake-session",
            case_id,
            account_id=None,
            reconciliation_status=None,
            limit=None,
        )
        view_call.assert_called_once_with(fake_row)

    async def test_no_status_filter_means_every_status_not_a_default(self):
        """A ledger nobody has reconciled must not present itself as reconciled."""
        with patch.object(
            financial_reconciliation,
            "list_period_reconciliations",
            return_value=[],
        ) as list_call:
            await financial_reconciliation.get_case_reconciliation(
                case_id=uuid.uuid4(),
                account_id=None,
                reconciliation_status=None,
                limit=None,
                db="fake-session",
            )

        self.assertIsNone(list_call.call_args.kwargs["reconciliation_status"])

    async def test_an_explicit_status_is_parsed_and_passed_through(self):
        case_id = uuid.uuid4()
        account_id = uuid.uuid4()

        with patch.object(
            financial_reconciliation,
            "list_period_reconciliations",
            return_value=[],
        ) as list_call:
            await financial_reconciliation.get_case_reconciliation(
                case_id=case_id,
                account_id=account_id,
                reconciliation_status="not_attempted",
                limit=25,
                db="fake-session",
            )

        list_call.assert_called_once_with(
            "fake-session",
            case_id,
            account_id=account_id,
            reconciliation_status=ReconciliationStatus.not_attempted,
            limit=25,
        )

    async def test_an_unknown_status_is_a_400_naming_the_valid_words(self):
        with self.assertRaises(HTTPException) as ctx:
            await financial_reconciliation.get_case_reconciliation(
                case_id=uuid.uuid4(),
                account_id=None,
                reconciliation_status="reconciled",
                limit=None,
                db="fake-session",
            )

        self.assertEqual(ctx.exception.status_code, 400)
        for status in ReconciliationStatus:
            self.assertIn(status.value, ctx.exception.detail)

    async def test_a_reconciliation_query_error_is_a_400(self):
        with patch.object(
            financial_reconciliation,
            "list_period_reconciliations",
            side_effect=ReconciliationQueryError("limit must be positive"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_reconciliation.get_case_reconciliation(
                    case_id=uuid.uuid4(),
                    account_id=None,
                    reconciliation_status=None,
                    limit=0,
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("limit must be positive", ctx.exception.detail)

    async def test_an_unexpected_error_is_a_500(self):
        with patch.object(
            financial_reconciliation,
            "list_period_reconciliations",
            side_effect=RuntimeError("db exploded"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_reconciliation.get_case_reconciliation(
                    case_id=uuid.uuid4(),
                    account_id=None,
                    reconciliation_status=None,
                    limit=None,
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 500)


class RunCaseReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_completed_sweep_is_returned_whole(self):
        case_id = uuid.uuid4()
        account_id = uuid.uuid4()
        outcome = CaseReconciliation(
            case_id=case_id,
            outcome=CaseOutcome.completed,
            periods=(
                period_result(PeriodOutcome.balanced),
                period_result(PeriodOutcome.unbalanced),
            ),
            reason=None,
        )

        with patch.object(
            financial_reconciliation, "reconcile_case", return_value=outcome
        ) as run_call:
            result = await financial_reconciliation.run_case_reconciliation(
                case_id=case_id,
                account_id=account_id,
                db="fake-session",
            )

        run_call.assert_called_once_with(
            "fake-session", case_id, account_id=account_id
        )
        self.assertEqual(result, outcome.as_dict())
        self.assertEqual(result["outcome"], "completed")
        self.assertTrue(result["applied"])
        self.assertEqual(result["counts"]["unbalanced"], 1)
        self.assertEqual(len(result["periods"]), 2)

    async def test_a_case_holding_no_periods_is_a_200_not_a_404(self):
        """A case with nothing to reconcile is a fact, not a failed request."""
        outcome = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.no_periods,
            periods=(),
            reason=None,
        )

        with patch.object(
            financial_reconciliation, "reconcile_case", return_value=outcome
        ):
            result = await financial_reconciliation.run_case_reconciliation(
                case_id=outcome.case_id, account_id=None, db="fake-session"
            )

        self.assertEqual(result["outcome"], "no_periods")
        self.assertFalse(result["applied"])
        self.assertEqual(result["total"], 0)

    async def test_a_sweep_of_nothing_but_refusals_is_a_200(self):
        """Every period refusing is a finding about the data, not a fault."""
        outcome = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.completed,
            periods=(period_result(PeriodOutcome.refused),),
            reason=None,
        )

        with patch.object(
            financial_reconciliation, "reconcile_case", return_value=outcome
        ):
            result = await financial_reconciliation.run_case_reconciliation(
                case_id=outcome.case_id, account_id=None, db="fake-session"
            )

        self.assertEqual(result["outcome"], "completed")
        self.assertFalse(result["applied"])
        self.assertEqual(result["counts"]["refused"], 1)

    async def test_a_failed_write_is_a_500_carrying_the_reason(self):
        outcome = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.write_failed,
            periods=(),
            reason="database is locked",
        )

        with patch.object(
            financial_reconciliation, "reconcile_case", return_value=outcome
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_reconciliation.run_case_reconciliation(
                    case_id=outcome.case_id, account_id=None, db="fake-session"
                )

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "database is locked")


class RouteRegistrationTests(unittest.TestCase):
    """The read and the recompute are separate routes on separate verbs."""

    def test_the_router_exposes_a_get_read_and_a_post_recompute(self):
        served = {
            (route.path, frozenset(route.methods))
            for route in financial_reconciliation.router.routes
        }

        self.assertIn(
            ("/api/financial/reconciliation", frozenset({"GET"})), served
        )
        self.assertIn(
            ("/api/financial/reconciliation/run", frozenset({"POST"})), served
        )

    def test_the_read_path_is_not_also_served_by_a_writing_verb(self):
        for route in financial_reconciliation.router.routes:
            if route.path != "/api/financial/reconciliation":
                continue
            self.assertEqual(set(route.methods), {"GET"})


if __name__ == "__main__":
    unittest.main()
