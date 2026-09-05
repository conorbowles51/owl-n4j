"""Tests for the ingest router, mirroring ``test_financial_ledger_router``.

The handler is awaited directly rather than through a test client, and the
service it delegates to is mocked, so these tests are about the router's own
responsibilities -- building the window, translating outcomes into status
codes, response shape -- and not about the reading underneath, which
``test_financial_native_precheck`` covers.

Two of the assertions here are the reason the file exists rather than being
folded into the service suite.

The first is that only ``not_found`` becomes an error status.  Every other
failing outcome is a description of a real file and belongs on the screen
beside the files that read cleanly; returning 400 for an unparseable statement
would put it in the browser's error path, where the person sees a failed
request instead of a fact about their evidence.

The second is that the window is required and never defaulted.  A default would
decide which century a two-digit year names, silently, in the one place the
document gives no help -- and a case carries no date range to take one from.
"""

import datetime
import types
import unittest
import uuid
from inspect import signature
from unittest.mock import patch

from fastapi import HTTPException

from routers import financial_ingest
from services.financial.native import CenturyWindow
from services.financial.native_ingest_file import FileIngestion, IngestOutcome
from services.financial.native_precheck import FilePrecheck, PrecheckOutcome

D = datetime.date


def result_of(outcome, **kw) -> FilePrecheck:
    kw.setdefault("file_id", "file-1")
    return FilePrecheck(outcome=outcome, **kw)


def ingestion_of(outcome, **kw) -> FileIngestion:
    kw.setdefault("file_id", "file-1")
    return FileIngestion(outcome=outcome, **kw)


def request_to(path: str):
    """The one attribute the permission resolver reads.

    A real ``Request`` needs an ASGI scope to construct and the resolver looks
    at nothing else, so building one would test Starlette.
    """
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


class PrecheckEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.case_id = uuid.uuid4()
        self.file_id = uuid.uuid4()

    async def call(self, **kw):
        kw.setdefault("case_id", self.case_id)
        kw.setdefault("file_id", self.file_id)
        kw.setdefault("window_start", D(2020, 1, 1))
        kw.setdefault("window_end", D(2024, 12, 31))
        kw.setdefault("default_currency", None)
        kw.setdefault("db", "fake-session")
        return await financial_ingest.precheck_financial_file(**kw)

    async def test_it_delegates_to_the_service_and_returns_its_description(self):
        described = result_of(PrecheckOutcome.readable, detected_format="camt053")

        with patch.object(
            financial_ingest, "precheck_case_file", return_value=described
        ) as call:
            result = await self.call()

        self.assertEqual(result, described.as_dict())
        self.assertEqual(call.call_args.args, ("fake-session",))
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["case_id"], self.case_id)
        self.assertEqual(kwargs["file_id"], self.file_id)

    async def test_the_window_is_built_from_the_two_required_dates(self):
        with patch.object(
            financial_ingest,
            "precheck_case_file",
            return_value=result_of(PrecheckOutcome.readable),
        ) as call:
            await self.call(window_start=D(2019, 6, 1), window_end=D(2024, 5, 31))

        window = call.call_args.kwargs["window"]
        self.assertEqual(window, CenturyWindow(D(2019, 6, 1), D(2024, 5, 31)))

    async def test_the_path_resolver_is_the_one_evidence_uploads_use(self):
        """A second copy of the resolver would diverge from the first."""
        from routers.evidence import _resolve_stored_path

        with patch.object(
            financial_ingest,
            "precheck_case_file",
            return_value=result_of(PrecheckOutcome.readable),
        ) as call:
            await self.call()

        self.assertIs(call.call_args.kwargs["resolve_path"], _resolve_stored_path)

    async def test_a_window_wider_than_a_century_is_a_400(self):
        """Past a century a two-digit year names two years and nothing says which."""
        with self.assertRaises(HTTPException) as ctx:
            await self.call(window_start=D(1900, 1, 1), window_end=D(2024, 12, 31))
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_a_backwards_window_is_a_400(self):
        with self.assertRaises(HTTPException) as ctx:
            await self.call(window_start=D(2024, 1, 1), window_end=D(2020, 1, 1))
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_a_file_outside_the_case_is_a_404(self):
        with patch.object(
            financial_ingest,
            "precheck_case_file",
            return_value=result_of(
                PrecheckOutcome.not_found, reason="no such file in this case"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await self.call()

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "no such file in this case")

    async def test_an_unreadable_file_is_a_200_describing_it(self):
        """The file is real and the person needs to see it beside the others.

        This is the assertion that fails against the tempting implementation
        where anything other than ``readable`` raises.
        """
        for outcome in (
            PrecheckOutcome.unrecognised,
            PrecheckOutcome.ambiguous,
            PrecheckOutcome.out_of_window,
            PrecheckOutcome.unattributable,
            PrecheckOutcome.unreadable,
        ):
            with self.subTest(outcome=outcome.value):
                with patch.object(
                    financial_ingest,
                    "precheck_case_file",
                    return_value=result_of(outcome, reason="because"),
                ):
                    result = await self.call()
                self.assertEqual(result["outcome"], outcome.value)
                self.assertFalse(result["would_ingest"])
                self.assertEqual(result["reason"], "because")

    async def test_an_unexpected_service_failure_is_a_500(self):
        with patch.object(
            financial_ingest,
            "precheck_case_file",
            side_effect=RuntimeError("database gone"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await self.call()
        self.assertEqual(ctx.exception.status_code, 500)

    async def test_the_default_currency_is_passed_through_untouched(self):
        with patch.object(
            financial_ingest,
            "precheck_case_file",
            return_value=result_of(PrecheckOutcome.readable),
        ) as call:
            await self.call(default_currency="GBP")
        self.assertEqual(call.call_args.kwargs["default_currency"], "GBP")


class IngestEndpointTests(unittest.IsolatedAsyncioTestCase):
    """The write half.  Same shape of test, one more status code.

    The interesting assertion is the same one as on precheck and for the same
    reason: almost nothing here is an error.  A file whose rows name an account
    it never introduced is a real file with a real defect, and the person
    sending it needs to see that sentence next to the files that went in, not a
    failed request.
    """

    def setUp(self) -> None:
        self.case_id = uuid.uuid4()
        self.file_id = uuid.uuid4()
        self.user = object()

    async def call(self, **kw):
        kw.setdefault("case_id", self.case_id)
        kw.setdefault("file_id", self.file_id)
        kw.setdefault("window_start", D(2020, 1, 1))
        kw.setdefault("window_end", D(2024, 12, 31))
        kw.setdefault("default_currency", None)
        kw.setdefault("document_type", None)
        kw.setdefault("institution_name", None)
        kw.setdefault("current_user", self.user)
        kw.setdefault("db", FakeSession())
        return await financial_ingest.ingest_financial_file(**kw)

    async def test_it_delegates_to_the_service_and_returns_its_description(self):
        stored = ingestion_of(
            IngestOutcome.stored,
            run_id="run-1",
            document_id="doc-1",
            detected_format="camt053",
            transactions_stored=12,
        )

        with patch.object(
            financial_ingest, "ingest_case_file", return_value=stored
        ) as call:
            result = await self.call()

        self.assertEqual(result, stored.as_dict())
        self.assertTrue(result["stored"])
        self.assertEqual(result["transactions_stored"], 12)
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["case_id"], self.case_id)
        self.assertEqual(kwargs["file_id"], self.file_id)

    async def test_the_window_is_built_from_the_two_required_dates(self):
        with patch.object(
            financial_ingest,
            "ingest_case_file",
            return_value=ingestion_of(IngestOutcome.stored),
        ) as call:
            await self.call(window_start=D(2019, 6, 1), window_end=D(2024, 5, 31))

        self.assertEqual(
            call.call_args.kwargs["window"],
            CenturyWindow(D(2019, 6, 1), D(2024, 5, 31)),
        )

    async def test_the_path_resolver_is_the_one_evidence_uploads_use(self):
        from routers.evidence import _resolve_stored_path

        with patch.object(
            financial_ingest,
            "ingest_case_file",
            return_value=ingestion_of(IngestOutcome.stored),
        ) as call:
            await self.call()

        self.assertIs(call.call_args.kwargs["resolve_path"], _resolve_stored_path)

    async def test_the_signed_in_user_is_the_run_actor(self):
        """A run records who started it, and nobody else can be asked later."""
        with patch.object(
            financial_ingest,
            "ingest_case_file",
            return_value=ingestion_of(IngestOutcome.stored),
        ) as call:
            await self.call()

        self.assertIs(call.call_args.kwargs["actor"], self.user)

    async def test_a_window_wider_than_a_century_is_a_400(self):
        with self.assertRaises(HTTPException) as ctx:
            await self.call(window_start=D(1900, 1, 1), window_end=D(2024, 12, 31))
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_a_backwards_window_is_a_400(self):
        with self.assertRaises(HTTPException) as ctx:
            await self.call(window_start=D(2024, 1, 1), window_end=D(2020, 1, 1))
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_a_file_outside_the_case_is_a_404(self):
        with patch.object(
            financial_ingest,
            "ingest_case_file",
            return_value=ingestion_of(
                IngestOutcome.not_found, reason="no such file in this case"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await self.call()

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "no such file in this case")

    async def test_a_failed_write_is_a_500(self):
        """Not a fact about the evidence, so not something to put on screen."""
        with patch.object(
            financial_ingest,
            "ingest_case_file",
            return_value=ingestion_of(
                IngestOutcome.write_failed, reason="value too long for column"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await self.call()

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "value too long for column")

    async def test_every_other_refusal_is_a_200_describing_it(self):
        """The assertion that fails against "anything but stored raises"."""
        for outcome in (
            IngestOutcome.already_ingested,
            IngestOutcome.unrecognised,
            IngestOutcome.ambiguous,
            IngestOutcome.out_of_window,
            IngestOutcome.unreadable,
            IngestOutcome.undescribable,
            IngestOutcome.unattributable,
            IngestOutcome.contradictory_period,
            IngestOutcome.refused,
        ):
            with self.subTest(outcome=outcome.value):
                with patch.object(
                    financial_ingest,
                    "ingest_case_file",
                    return_value=ingestion_of(outcome, reason="because"),
                ):
                    result = await self.call()
                self.assertEqual(result["outcome"], outcome.value)
                self.assertFalse(result["stored"])
                self.assertEqual(result["reason"], "because")

    async def test_every_outcome_is_accounted_for_by_these_tests(self):
        """A new outcome has to be given a status here rather than defaulting.

        The three groups above are the whole enum.  Adding a member without
        deciding whether it is a description, a 404 or a 500 would silently
        make it a 200, which is the wrong answer for anything that is a fault.
        """
        described = {
            IngestOutcome.already_ingested,
            IngestOutcome.unrecognised,
            IngestOutcome.ambiguous,
            IngestOutcome.out_of_window,
            IngestOutcome.unreadable,
            IngestOutcome.undescribable,
            IngestOutcome.unattributable,
            IngestOutcome.contradictory_period,
            IngestOutcome.refused,
        }
        self.assertEqual(
            set(IngestOutcome),
            described
            | {
                IngestOutcome.stored,
                IngestOutcome.not_found,
                IngestOutcome.write_failed,
            },
        )

    async def test_the_endpoint_offers_no_way_to_re_ingest(self):
        """``already_ingested`` is an answer, not a prompt with an override.

        A parameter that let a caller past it would store a second reading of
        one file in one case, and nothing reachable today can say which of the
        two governs.  Asserted on the signature rather than on a call, because
        the failure being guarded against is the parameter existing at all.
        """
        parameters = signature(financial_ingest.ingest_financial_file).parameters
        self.assertNotIn("reingest", parameters)
        self.assertNotIn("force", parameters)

    async def test_the_three_recorded_extras_are_passed_through_untouched(self):
        with patch.object(
            financial_ingest,
            "ingest_case_file",
            return_value=ingestion_of(IngestOutcome.stored),
        ) as call:
            await self.call(
                default_currency="GBP",
                document_type="bank statement",
                institution_name="Barclays",
            )
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["default_currency"], "GBP")
        self.assertEqual(kwargs["document_type"], "bank statement")
        self.assertEqual(kwargs["institution_name"], "Barclays")

    async def test_an_unexpected_service_failure_is_a_500_and_rolls_back(self):
        """The service returns for everything it anticipates.

        So an exception got past it with the session mid-transaction, and the
        connection goes back to the pool that way unless it is rolled back
        here.
        """
        db = FakeSession()
        with patch.object(
            financial_ingest,
            "ingest_case_file",
            side_effect=RuntimeError("database gone"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await self.call(db=db)

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(db.rollbacks, 1)


class FakeSession:
    """Enough of a session for the router, which only ever rolls one back."""

    def __init__(self) -> None:
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1


class RouterShapeTests(unittest.TestCase):
    """Where the route is mounted and what it is gated on."""

    def test_the_route_is_registered_on_the_app(self):
        from main import app

        paths = {
            (tuple(sorted(r.methods)), r.path)
            for r in app.routes
            if getattr(r, "methods", None)
        }
        self.assertIn((("POST",), "/api/financial/precheck"), paths)

    def test_the_ingest_route_is_registered_on_the_app(self):
        from main import app

        paths = {
            (tuple(sorted(r.methods)), r.path)
            for r in app.routes
            if getattr(r, "methods", None)
        }
        self.assertIn((("POST",), "/api/financial/ingest"), paths)

    def test_the_read_only_list_names_only_paths_this_router_serves(self):
        """A stale entry would quietly downgrade nothing and hide a live one."""
        served = {
            r.path for r in financial_ingest.router.routes if getattr(r, "path", None)
        }
        self.assertTrue(financial_ingest._READ_ONLY_PATHS <= served)

    def test_prechecking_is_gated_on_seeing_the_case(self):
        """It reads a file and reports it; it does not add to the case."""
        self.assertEqual(
            financial_ingest._ingest_case_permission(
                request_to("/api/financial/precheck"), {}
            ),
            ("case", "view"),
        )

    def test_ingesting_is_gated_on_being_able_to_add_evidence(self):
        """It writes to the case, so seeing the case is not enough."""
        self.assertEqual(
            financial_ingest._ingest_case_permission(
                request_to("/api/financial/ingest"), {}
            ),
            ("evidence", "upload"),
        )

    def test_an_unknown_path_on_this_router_gets_the_writer_bar(self):
        """The resolver fails closed.

        Both routes are POSTs and the method cannot tell them apart, so the
        read-only ones are named and everything else is a write.  A route added
        here without touching the resolver is then over-gated, which someone
        notices, rather than under-gated, which nobody does.
        """
        self.assertEqual(
            financial_ingest._ingest_case_permission(
                request_to("/api/financial/something-new"), {}
            ),
            ("evidence", "upload"),
        )

    def test_it_is_a_separate_router_from_the_read_only_ledger_one(self):
        """``financial_ledger`` declares that none of its routes write.

        The ingest route that follows this one does, so it cannot live there
        without making that module's own docstring false.
        """
        from routers import financial_ledger

        self.assertIsNot(financial_ingest.router, financial_ledger.router)
        self.assertEqual(
            financial_ingest.router.prefix, financial_ledger.router.prefix
        )


if __name__ == "__main__":
    unittest.main()
