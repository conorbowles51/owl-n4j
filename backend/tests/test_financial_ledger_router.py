"""Tests for the ledger read router, mirroring ``test_financial_router``.

The handler is awaited directly rather than through a test client, and the
service call it delegates to is mocked, so these tests are about the
router's own responsibilities -- status-string validation, error
translation, response shape -- and not about the query logic underneath,
which ``test_financial_transaction_query`` already covers.
"""

import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException

from postgres.models.enums import LedgerStatus
from routers import financial_ledger
from services.financial.transaction_query import LedgerQueryError


class GetLedgerTransactionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_the_query_service_and_shapes_the_response(self):
        case_id = uuid.uuid4()
        fake_row = object()
        view_payload = {"key": "row-1"}

        class FakeView:
            def to_json(self):
                return view_payload

        with patch.object(
            financial_ledger, "list_transactions", return_value=[fake_row]
        ) as list_call, patch.object(
            financial_ledger, "to_view", return_value=FakeView()
        ) as to_view_call:
            result = await financial_ledger.get_ledger_transactions(
                case_id=case_id,
                account_id=None,
                ledger_status=None,
                start_date=None,
                end_date=None,
                db="fake-session",
            )

        self.assertEqual(
            result,
            {
                "case_id": str(case_id),
                "transactions": [view_payload],
                "total": 1,
            },
        )
        list_call.assert_called_once_with(
            "fake-session",
            case_id,
            account_id=None,
            ledger_status=None,
            start_date=None,
            end_date=None,
        )
        to_view_call.assert_called_once_with(fake_row)

    async def test_an_explicit_ledger_status_is_parsed_and_passed_through(self):
        case_id = uuid.uuid4()

        with patch.object(
            financial_ledger, "list_transactions", return_value=[]
        ) as list_call:
            await financial_ledger.get_ledger_transactions(
                case_id=case_id,
                account_id=None,
                ledger_status="quarantined",
                start_date=None,
                end_date=None,
                db="fake-session",
            )

        list_call.assert_called_once_with(
            "fake-session",
            case_id,
            account_id=None,
            ledger_status=LedgerStatus.quarantined,
            start_date=None,
            end_date=None,
        )

    async def test_an_unknown_ledger_status_is_a_400_not_a_500(self):
        with self.assertRaises(HTTPException) as ctx:
            await financial_ledger.get_ledger_transactions(
                case_id=uuid.uuid4(),
                account_id=None,
                ledger_status="not-a-real-status",
                start_date=None,
                end_date=None,
                db="fake-session",
            )

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_a_ledger_query_error_is_a_400(self):
        with patch.object(
            financial_ledger,
            "list_transactions",
            side_effect=LedgerQueryError("start_date is after end_date"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_ledger.get_ledger_transactions(
                    case_id=uuid.uuid4(),
                    account_id=None,
                    ledger_status=None,
                    start_date=None,
                    end_date=None,
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("start_date is after end_date", ctx.exception.detail)

    async def test_an_unexpected_error_is_a_500(self):
        with patch.object(
            financial_ledger,
            "list_transactions",
            side_effect=RuntimeError("db exploded"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_ledger.get_ledger_transactions(
                    case_id=uuid.uuid4(),
                    account_id=None,
                    ledger_status=None,
                    start_date=None,
                    end_date=None,
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()
