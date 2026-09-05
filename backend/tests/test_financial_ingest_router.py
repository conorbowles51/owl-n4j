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
import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException

from routers import financial_ingest
from services.financial.native import CenturyWindow
from services.financial.native_precheck import FilePrecheck, PrecheckOutcome

D = datetime.date


def result_of(outcome, **kw) -> FilePrecheck:
    kw.setdefault("file_id", "file-1")
    return FilePrecheck(outcome=outcome, **kw)


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

    def test_prechecking_is_gated_on_seeing_the_case(self):
        """It reads a file and reports it; it does not add to the case."""
        self.assertEqual(
            financial_ingest._ingest_case_permission(None, {}), ("case", "view")
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
