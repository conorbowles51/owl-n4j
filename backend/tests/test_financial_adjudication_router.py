"""Tests for the adjudication write router, mirroring ``test_financial_ledger_router``.

The handler is awaited directly rather than through a test client, and the
service call it delegates to is mocked, so these tests are about the router's
own responsibilities -- what it passes down, which outcomes become error
statuses and which do not, and what permission it asks for -- and not about
the adjudication itself, which ``test_financial_quarantine_row`` covers
against a real database.

The distinction worth holding onto here is between a refusal and an error.  A
row that is already quarantined on computed grounds, or a reason left blank,
comes back as a 200 carrying the word ``refused``, because it is a fact about
the row that belongs on the screen beside it.  Only a row the caller may not
see and a database fault become 4xx and 5xx, and the first of those is worded
identically whether the row is in another case or does not exist at all.

The file admission route is held to the same distinction and to one more of its
own: it takes no parameter by which a caller could say what the router found,
so the tests below assert what the handler passes down and not merely what it
returns.  A route that accepted the finding would let a request write its own
account of what was overruled into the permanent record.
"""

import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException

from routers import financial_adjudication
from services.financial.admit_file import FileAdmission, FileAdmissionOutcome
from services.financial.quarantine_row import (
    RowAdjudication,
    RowAdjudicationOutcome,
)


def _result(
    transaction_id,
    outcome,
    *,
    reason=None,
    ledger_status=None,
    quarantine_reason=None,
    adjudication_id=None,
    rescues_period=None,
):
    return RowAdjudication(
        transaction_id=str(transaction_id),
        outcome=outcome,
        reason=reason,
        ledger_status=ledger_status,
        quarantine_reason=quarantine_reason,
        adjudication_id=adjudication_id,
        rescues_period=rescues_period,
    )


def _admission(
    file_id,
    outcome,
    *,
    reason=None,
    file_name=None,
    route_outcome=None,
    detected_format=None,
    claimants=(),
    adjudication_id=None,
):
    return FileAdmission(
        file_id=str(file_id),
        outcome=outcome,
        reason=reason,
        file_name=file_name,
        route_outcome=route_outcome,
        detected_format=detected_format,
        claimants=claimants,
        adjudication_id=adjudication_id,
    )


class PermissionResolverTests(unittest.TestCase):
    def test_every_route_asks_for_the_case_edit_permission(self):
        # Not evidence:upload, which is what ingest asks for: nothing is added
        # to the case here, an existing row's standing is changed.
        resolved = financial_adjudication._adjudication_case_permission(
            request=None, payload={}
        )
        self.assertEqual(resolved, ("case", "edit"))

    def test_the_router_is_mounted_under_the_financial_prefix(self):
        self.assertEqual(financial_adjudication.router.prefix, "/api/financial")

    def test_every_route_is_a_post_against_the_thing_it_adjudicates(self):
        """Written as an exhaustive comparison rather than a membership check.

        A route added to this module inherits ``case:edit`` unconditionally
        from the resolver above, which is the safe direction for a mistake in
        the permission to fall but means nothing else notices the addition.
        Comparing the whole set makes a new route fail here, where whoever
        added it has to say what it is.
        """
        routes = {
            route.path: sorted(route.methods)
            for route in financial_adjudication.router.routes
        }
        self.assertEqual(
            routes,
            {
                "/api/financial/transactions/{transaction_id}/quarantine": [
                    "POST"
                ],
                "/api/financial/transactions/{transaction_id}/release": ["POST"],
                "/api/financial/files/{file_id}/admit": ["POST"],
                "/api/financial/documents/{document_id}/duplicate-decision": ["POST"],
            },
        )


class QuarantineTransactionRowTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_service_is_called_with_the_row_case_actor_and_reason(self):
        case_id = uuid.uuid4()
        transaction_id = uuid.uuid4()
        user = object()

        with patch.object(
            financial_adjudication,
            "quarantine_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.quarantined,
                ledger_status="quarantined",
                quarantine_reason="adjudicated",
                adjudication_id="event-1",
                # Set here so this test also holds the route to carrying the
                # finding out to the interface.  A response that dropped it
                # would leave a statement that balances only because this row
                # left it, with nothing on screen saying so.
                rescues_period=True,
            ),
        ) as call:
            result = await financial_adjudication.quarantine_transaction_row(
                transaction_id=transaction_id,
                case_id=case_id,
                reason="Duplicate of the wire on the facing page",
                current_user=user,
                db="fake-session",
            )

        call.assert_called_once_with(
            "fake-session",
            case_id=case_id,
            transaction_id=transaction_id,
            actor=user,
            reason="Duplicate of the wire on the facing page",
        )
        self.assertEqual(
            result,
            {
                "transaction_id": str(transaction_id),
                "outcome": "quarantined",
                "applied": True,
                "reason": None,
                "ledger_status": "quarantined",
                "quarantine_reason": "adjudicated",
                "adjudication_id": "event-1",
                "rescues_period": True,
            },
        )

    async def test_a_refusal_is_returned_not_raised(self):
        # A row already held on computed grounds is a fact about the row, and
        # the person asking needs to read it next to the row rather than in an
        # error dialog.
        transaction_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "quarantine_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.refused,
                reason="Transaction is already quarantined on other grounds",
                ledger_status="quarantined",
                quarantine_reason="unreconciled_period",
            ),
        ):
            result = await financial_adjudication.quarantine_transaction_row(
                transaction_id=transaction_id,
                case_id=uuid.uuid4(),
                reason="Looks wrong",
                current_user=object(),
                db="fake-session",
            )

        self.assertEqual(result["outcome"], "refused")
        self.assertFalse(result["applied"])
        self.assertIn("already quarantined", result["reason"])
        self.assertIsNone(result["adjudication_id"])

    async def test_an_unchanged_row_is_returned_and_claims_no_decision(self):
        transaction_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "quarantine_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.unchanged,
                reason="Transaction is already quarantined by adjudication",
                ledger_status="quarantined",
                quarantine_reason="adjudicated",
            ),
        ):
            result = await financial_adjudication.quarantine_transaction_row(
                transaction_id=transaction_id,
                case_id=uuid.uuid4(),
                reason="Duplicate",
                current_user=object(),
                db="fake-session",
            )

        self.assertEqual(result["outcome"], "unchanged")
        self.assertFalse(result["applied"])
        self.assertIsNone(result["adjudication_id"])

    async def test_a_row_the_caller_may_not_see_is_a_404(self):
        transaction_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "quarantine_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.not_found,
                reason="Transaction not found in this case",
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_adjudication.quarantine_transaction_row(
                    transaction_id=transaction_id,
                    case_id=uuid.uuid4(),
                    reason="Duplicate",
                    current_user=object(),
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(
            ctx.exception.detail, "Transaction not found in this case"
        )

    async def test_a_write_fault_is_a_500(self):
        transaction_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "quarantine_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.write_failed,
                reason="connection lost",
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_adjudication.quarantine_transaction_row(
                    transaction_id=transaction_id,
                    case_id=uuid.uuid4(),
                    reason="Duplicate",
                    current_user=object(),
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 500)


class ReleaseTransactionRowTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_service_is_called_with_the_row_case_actor_and_reason(self):
        case_id = uuid.uuid4()
        transaction_id = uuid.uuid4()
        user = object()

        with patch.object(
            financial_adjudication,
            "release_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.released,
                ledger_status="admitted",
                adjudication_id="event-2",
            ),
        ) as call:
            result = await financial_adjudication.release_transaction_row(
                transaction_id=transaction_id,
                case_id=case_id,
                reason="Second copy confirmed to be a different payment",
                current_user=user,
                db="fake-session",
            )

        call.assert_called_once_with(
            "fake-session",
            case_id=case_id,
            transaction_id=transaction_id,
            actor=user,
            reason="Second copy confirmed to be a different payment",
        )
        self.assertEqual(
            result,
            {
                "transaction_id": str(transaction_id),
                "outcome": "released",
                "applied": True,
                "reason": None,
                "ledger_status": "admitted",
                "quarantine_reason": None,
                "adjudication_id": "event-2",
                # A release puts a row back; nothing was removed, so there is
                # no effect on a period to report.
                "rescues_period": None,
            },
        )

    async def test_releasing_a_row_that_was_never_held_is_a_refusal_not_an_error(
        self,
    ):
        transaction_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "release_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.refused,
                reason="Transaction is admitted, nothing to release",
                ledger_status="admitted",
            ),
        ):
            result = await financial_adjudication.release_transaction_row(
                transaction_id=transaction_id,
                case_id=uuid.uuid4(),
                reason="Let it back in",
                current_user=object(),
                db="fake-session",
            )

        self.assertEqual(result["outcome"], "refused")
        self.assertFalse(result["applied"])
        self.assertIn("nothing to release", result["reason"])

    async def test_a_row_the_caller_may_not_see_is_a_404(self):
        transaction_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "release_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.not_found,
                reason="Transaction not found in this case",
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_adjudication.release_transaction_row(
                    transaction_id=transaction_id,
                    case_id=uuid.uuid4(),
                    reason="Let it back in",
                    current_user=object(),
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_a_write_fault_is_a_500(self):
        transaction_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "release_case_row",
            return_value=_result(
                transaction_id,
                RowAdjudicationOutcome.write_failed,
                reason="connection lost",
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_adjudication.release_transaction_row(
                    transaction_id=transaction_id,
                    case_id=uuid.uuid4(),
                    reason="Let it back in",
                    current_user=object(),
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 500)


class AdmitFileTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_service_is_called_with_the_file_case_actor_and_reason(self):
        case_id = uuid.uuid4()
        file_id = uuid.uuid4()
        user = object()

        with patch.object(
            financial_adjudication,
            "admit_case_file",
            return_value=_admission(
                file_id,
                FileAdmissionOutcome.admitted,
                reason="Ledger cannot parse it; index the text.",
                file_name="january-statement.xml",
                route_outcome="native",
                detected_format="camt053",
                claimants=("camt053",),
                adjudication_id="event-3",
            ),
        ) as call:
            result = await financial_adjudication.admit_file_to_document_pipeline(
                file_id=file_id,
                case_id=case_id,
                reason="Ledger cannot parse it; index the text.",
                current_user=user,
                db="fake-session",
            )

        call.assert_called_once_with(
            "fake-session",
            case_id=case_id,
            file_id=file_id,
            actor=user,
            reason="Ledger cannot parse it; index the text.",
            resolve_path=financial_adjudication._resolve_stored_path,
        )
        self.assertEqual(
            result,
            {
                "file_id": str(file_id),
                "outcome": "admitted",
                "admitted": True,
                "routed_to": "document_pipeline",
                "reason": "Ledger cannot parse it; index the text.",
                "file_name": "january-statement.xml",
                "route_outcome": "native",
                "detected_format": "camt053",
                "claimants": ["camt053"],
                "adjudication_id": "event-3",
            },
        )

    async def test_the_handler_takes_no_parameter_for_what_the_router_found(self):
        """The property the route exists to protect.

        If a request could state the outcome, the format, or the claimants,
        then the permanent record of what a person overruled would be whatever
        the caller typed.  Asserted against the signature rather than against a
        response, because a parameter that is merely ignored today is one a
        later edit can start honouring.
        """
        import inspect

        parameters = set(
            inspect.signature(
                financial_adjudication.admit_file_to_document_pipeline
            ).parameters
        )
        self.assertEqual(
            parameters,
            {"file_id", "case_id", "reason", "current_user", "db"},
        )

    async def test_a_refusal_is_returned_not_raised(self):
        file_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "admit_case_file",
            return_value=_admission(
                file_id,
                FileAdmissionOutcome.refused,
                reason="a decision needs a stated reason",
                file_name="january-statement.xml",
                route_outcome="native",
                detected_format="camt053",
                claimants=("camt053",),
            ),
        ):
            result = await financial_adjudication.admit_file_to_document_pipeline(
                file_id=file_id,
                case_id=uuid.uuid4(),
                reason=" ",
                current_user=object(),
                db="fake-session",
            )

        self.assertEqual(result["outcome"], "refused")
        self.assertFalse(result["admitted"])
        self.assertEqual(result["routed_to"], "held")
        # The finding survives the refusal, so the interface does not have to
        # ask a second time and get a second answer.
        self.assertEqual(result["route_outcome"], "native")

    async def test_a_file_the_router_was_not_holding_is_not_an_error(self):
        """It can be processed with no decision at all, which is not a failure."""
        file_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "admit_case_file",
            return_value=_admission(
                file_id,
                FileAdmissionOutcome.nothing_to_override,
                reason="the router is not holding this file",
                file_name="letter.txt",
                route_outcome="not_native",
            ),
        ):
            result = await financial_adjudication.admit_file_to_document_pipeline(
                file_id=file_id,
                case_id=uuid.uuid4(),
                reason="Send it anyway",
                current_user=object(),
                db="fake-session",
            )

        self.assertEqual(result["outcome"], "nothing_to_override")
        self.assertFalse(result["admitted"])
        self.assertIsNone(result["adjudication_id"])

    async def test_a_file_the_caller_may_not_see_is_a_404(self):
        file_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "admit_case_file",
            return_value=_admission(
                file_id,
                FileAdmissionOutcome.not_found,
                reason="no such file in this case",
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_adjudication.admit_file_to_document_pipeline(
                    file_id=file_id,
                    case_id=uuid.uuid4(),
                    reason="Index the text",
                    current_user=object(),
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "no such file in this case")

    async def test_a_write_fault_is_a_500(self):
        file_id = uuid.uuid4()

        with patch.object(
            financial_adjudication,
            "admit_case_file",
            return_value=_admission(
                file_id,
                FileAdmissionOutcome.write_failed,
                reason="connection lost",
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial_adjudication.admit_file_to_document_pipeline(
                    file_id=file_id,
                    case_id=uuid.uuid4(),
                    reason="Index the text",
                    current_user=object(),
                    db="fake-session",
                )

        self.assertEqual(ctx.exception.status_code, 500)


class RespondHelperTests(unittest.TestCase):
    """The two response helpers are not interchangeable, and must not become so.

    They branch on identity against different enums.  If one were ever pointed
    at the other's results, ``not_found`` and ``write_failed`` would stop
    matching and a missing row would come back as a 200 -- so this asserts the
    pairing directly rather than trusting the call sites.
    """

    def test_the_row_helper_does_not_recognise_a_file_outcome(self):
        result = _admission(uuid.uuid4(), FileAdmissionOutcome.not_found)
        self.assertEqual(
            financial_adjudication._respond(result)["outcome"], "not_found"
        )

    def test_the_file_helper_does_not_recognise_a_row_outcome(self):
        result = _result(uuid.uuid4(), RowAdjudicationOutcome.not_found)
        self.assertEqual(
            financial_adjudication._respond_admission(result)["outcome"],
            "not_found",
        )


class NotFoundWordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_routes_word_a_missing_row_identically(self):
        # A row in another case and a row that does not exist must be
        # indistinguishable from outside, or asking becomes a way to learn
        # what a case the caller cannot see contains.
        transaction_id = uuid.uuid4()
        details = []

        for name, handler in (
            (
                "quarantine_case_row",
                financial_adjudication.quarantine_transaction_row,
            ),
            ("release_case_row", financial_adjudication.release_transaction_row),
        ):
            with patch.object(
                financial_adjudication,
                name,
                return_value=_result(
                    transaction_id,
                    RowAdjudicationOutcome.not_found,
                    reason="Transaction not found in this case",
                ),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await handler(
                        transaction_id=transaction_id,
                        case_id=uuid.uuid4(),
                        reason="Any reason",
                        current_user=object(),
                        db="fake-session",
                    )
            details.append((ctx.exception.status_code, ctx.exception.detail))

        self.assertEqual(details[0], details[1])


if __name__ == "__main__":
    unittest.main()
