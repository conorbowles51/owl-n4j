"""Tests for the ledger read router, mirroring ``test_financial_router``.

The handler is awaited directly rather than through a test client, and the
service call it delegates to is mocked, so these tests are about the
router's own responsibilities -- status-string validation, error
translation, response shape -- and not about the query logic underneath,
which ``test_financial_transaction_query`` already covers.
"""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    LedgerStatus,
)
from routers import financial_ledger
from services.financial.decision_log import (
    DEFAULT_DECISION_LIMIT,
    MAX_DECISION_LIMIT,
    DecisionLogError,
    DecisionPage,
)
from services.financial.proof_standing import (
    ClassStanding,
    ProofStanding,
    ProofStandingError,
)
from services.financial.transaction_query import LedgerQueryError


class GetLedgerTransactionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_the_query_service_and_shapes_the_response(self):
        case_id = uuid.uuid4()
        fake_row = SimpleNamespace(account=object())
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
        to_view_call.assert_called_once_with(fake_row, account=fake_row.account)

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


class GetCaseDecisionsTests(unittest.IsolatedAsyncioTestCase):
    """The decision log's first reader over HTTP.

    Same shape as the two classes above: the service is mocked and the handler
    awaited directly, so what is under test is the router's own work --
    turning two query strings into members of closed vocabularies, translating
    the service's refusals, and handing the page back without reshaping it.
    ``test_financial_decision_log`` covers the query itself.
    """

    async def _call(self, **overrides):
        params = {
            "case_id": uuid.uuid4(),
            "subject_type": None,
            "subject_id": None,
            "decision": None,
            "limit": DEFAULT_DECISION_LIMIT,
            "offset": 0,
            "db": "fake-session",
        }
        params.update(overrides)
        return await financial_ledger.get_case_decisions(**params)

    async def test_defaults_ask_the_service_for_the_whole_case(self):
        case_id = uuid.uuid4()
        page = DecisionPage(
            case_id=str(case_id), decisions=(), total=0, limit=100, offset=0
        )

        with patch.object(
            financial_ledger, "list_case_decisions", return_value=page
        ) as service:
            result = await self._call(case_id=case_id)

        service.assert_called_once_with(
            "fake-session",
            case_id,
            subject_type=None,
            subject_id=None,
            decision=None,
            limit=DEFAULT_DECISION_LIMIT,
            offset=0,
        )
        self.assertEqual(result["case_id"], str(case_id))
        self.assertEqual(result["decisions"], [])
        self.assertEqual(result["total"], 0)

    async def test_both_vocabularies_are_parsed_before_the_service_sees_them(self):
        case_id = uuid.uuid4()
        subject_id = uuid.uuid4()
        page = DecisionPage(
            case_id=str(case_id), decisions=(), total=0, limit=25, offset=5
        )

        with patch.object(
            financial_ledger, "list_case_decisions", return_value=page
        ) as service:
            await self._call(
                case_id=case_id,
                subject_type="transaction",
                subject_id=subject_id,
                decision="quarantine_row",
                limit=25,
                offset=5,
            )

        service.assert_called_once_with(
            "fake-session",
            case_id,
            subject_type=AdjudicationSubject.transaction,
            subject_id=subject_id,
            decision=AdjudicationDecision.quarantine_row,
            limit=25,
            offset=5,
        )

    async def test_an_unknown_subject_type_is_a_400_naming_the_valid_values(self):
        with patch.object(financial_ledger, "list_case_decisions") as service:
            with self.assertRaises(HTTPException) as ctx:
                await self._call(subject_type="transactions")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("subject_type", ctx.exception.detail)
        self.assertIn("statement_period", ctx.exception.detail)
        # The refusal happens before the read, so a misspelled filter cannot
        # come back as an unfiltered page.
        service.assert_not_called()

    async def test_an_unknown_decision_is_a_400_naming_the_valid_values(self):
        with patch.object(financial_ledger, "list_case_decisions") as service:
            with self.assertRaises(HTTPException) as ctx:
                await self._call(decision="released")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("decision", ctx.exception.detail)
        self.assertIn("release_row", ctx.exception.detail)
        service.assert_not_called()

    async def test_a_decision_log_error_is_a_400_carrying_its_own_words(self):
        with patch.object(
            financial_ledger,
            "list_case_decisions",
            side_effect=DecisionLogError("offset cannot be negative, got -1"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await self._call(offset=-1)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("offset cannot be negative", ctx.exception.detail)

    async def test_an_unexpected_error_is_a_500(self):
        with patch.object(
            financial_ledger,
            "list_case_decisions",
            side_effect=RuntimeError("db exploded"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await self._call()

        self.assertEqual(ctx.exception.status_code, 500)

    async def test_a_limit_over_the_cap_reaches_the_service_rather_than_a_422(self):
        """The cap is the service's rule and is applied there, not here.

        Declaring ``le=MAX_DECISION_LIMIT`` on the query parameter would turn a
        request the service serves -- capped, with the applied limit reported
        back -- into a validation failure. This pins that the route does not
        do that.
        """
        case_id = uuid.uuid4()
        asked = MAX_DECISION_LIMIT * 10
        page = DecisionPage(
            case_id=str(case_id),
            decisions=(),
            total=0,
            limit=MAX_DECISION_LIMIT,
            offset=0,
        )

        with patch.object(
            financial_ledger, "list_case_decisions", return_value=page
        ) as service:
            result = await self._call(case_id=case_id, limit=asked)

        self.assertEqual(service.call_args.kwargs["limit"], asked)
        # And what comes back reports the limit that was actually applied,
        # not the one that was asked for.
        self.assertEqual(result["limit"], MAX_DECISION_LIMIT)

    async def test_the_page_is_handed_back_whole_including_truncation(self):
        """The response is the page's own dict, not a shape rebuilt here.

        A router that rebuilt the response would be free to drop ``truncated``,
        and a history that stops without saying it stopped is the one failure
        this read must not have.
        """
        case_id = uuid.uuid4()
        page = DecisionPage(
            case_id=str(case_id), decisions=(), total=40, limit=10, offset=0
        )

        with patch.object(
            financial_ledger, "list_case_decisions", return_value=page
        ):
            result = await self._call(case_id=case_id, limit=10)

        self.assertEqual(result, page.as_dict())
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total"], 40)
        self.assertEqual(result["offset"], 0)


def _standing(case_id) -> ProofStanding:
    """A census with one class in it, enough to check the route's own work."""
    return ProofStanding(
        case_id=str(case_id),
        classes=(
            ClassStanding(
                proof_class="p3",
                documents=2,
                transactions=7,
                admits_automatically=False,
                requires_adjudication=True,
                may_produce_ledger_rows=True,
                counts_toward_totals=False,
            ),
        ),
        documents=2,
        transactions=7,
        documents_requiring_adjudication=2,
        transactions_requiring_adjudication=7,
        counted_classes=("p0", "p1", "p2"),
    )


class GetCaseProofStandingTests(unittest.IsolatedAsyncioTestCase):
    """The first reader of ``requires_adjudication`` over HTTP.

    Same shape as the three classes above. What is under test is that the
    route asks for the case and nothing else, hands the census back whole,
    and does not turn a stored-data failure into a caller's error.
    ``test_financial_proof_standing`` covers the counting itself.
    """

    async def test_it_asks_the_service_for_the_case_and_nothing_else(self):
        case_id = uuid.uuid4()
        standing = _standing(case_id)

        with patch.object(
            financial_ledger, "case_proof_standing", return_value=standing
        ) as service:
            result = await financial_ledger.get_case_proof_standing(
                case_id=case_id, db="fake-session"
            )

        # Positionally, with no keyword arguments at all: the counted set is
        # the ledger's own and is not selectable from a request.
        service.assert_called_once_with("fake-session", case_id)
        self.assertEqual(result["case_id"], str(case_id))

    async def test_the_census_is_handed_back_whole(self):
        """The response is the census's own dict, not a shape rebuilt here.

        A router that rebuilt it would be free to drop the per-class
        permissions, leaving counts against two-character labels that a reader
        cannot interpret -- which is the failure this read exists to prevent.
        """
        case_id = uuid.uuid4()
        standing = _standing(case_id)

        with patch.object(
            financial_ledger, "case_proof_standing", return_value=standing
        ):
            result = await financial_ledger.get_case_proof_standing(
                case_id=case_id, db="fake-session"
            )

        self.assertEqual(result, standing.as_dict())
        self.assertEqual(result["documents_requiring_adjudication"], 2)
        self.assertEqual(result["transactions_requiring_adjudication"], 7)
        self.assertEqual(result["counted_classes"], ["p0", "p1", "p2"])
        self.assertTrue(result["classes"][0]["requires_adjudication"])

    async def test_a_proof_standing_error_is_a_500_and_not_a_400(self):
        """Pins the difference this route's docstring turns on.

        The route sends the service nothing but a case, so the only refusal it
        can provoke is a stored class outside the vocabulary. No request caused
        that and no request can fix it, so answering 400 would tell the caller
        to change something it did not do.
        """
        with patch.object(
            financial_ledger,
            "case_proof_standing",
            side_effect=ProofStandingError(
                "financial_transactions holds proof_class 'p9'"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_ledger.get_case_proof_standing(
                    case_id=uuid.uuid4(), db="fake-session"
                )

        self.assertEqual(ctx.exception.status_code, 500)

    async def test_an_unexpected_error_is_a_500(self):
        with patch.object(
            financial_ledger,
            "case_proof_standing",
            side_effect=RuntimeError("db exploded"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_ledger.get_case_proof_standing(
                    case_id=uuid.uuid4(), db="fake-session"
                )

        self.assertEqual(ctx.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()
