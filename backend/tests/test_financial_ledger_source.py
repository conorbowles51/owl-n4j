from unittest.mock import patch
import unittest

from fastapi import HTTPException
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialTransaction
from services.financial.ledger_source import LedgerSourceError, ledger_source
from services.financial.transactions import LOCATOR_PROVENANCE_KEY
from tests.test_financial_duplicates import DuplicateTestCase
from routers import financial_ledger


class LedgerSourceTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        self.document = self.make_copy()
        self.row = self.db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == self.document.id))
        self.file = self.db.get(EvidenceFile, self.document.evidence_file_id)

    def read(self, **extra):
        return ledger_source(self.db, **{ "case_id": self.case.id, "transaction_id": self.row.id, **extra})

    def test_file_identity_is_resolved_without_exposing_disk_path_or_changing_rows(self):
        result = self.read()
        self.assertEqual(result["evidence_file_id"], str(self.file.id))
        self.assertEqual(result["source_document_id"], str(self.document.id))
        self.assertNotIn("stored_path", result)
        self.assertFalse(result["file_bytes_verified"])
        self.assertFalse(self.db.dirty)

    def test_wrong_case_and_cross_case_links_are_not_disclosed(self):
        with self.assertRaises(LedgerSourceError) as ctx:
            self.read(case_id=self.other_case.id)
        self.assertEqual(ctx.exception.status_code, 404)
        self.file.case_id = self.other_case.id
        self.db.commit()
        with self.assertRaises(LedgerSourceError) as ctx:
            self.read()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_digest_drift_refuses_navigation(self):
        self.file.sha256 = "b" * 64
        self.db.commit()
        with self.assertRaises(LedgerSourceError) as ctx:
            self.read()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_stored_page_is_retained_for_historical_rows(self):
        self.row.provenance = {LOCATOR_PROVENANCE_KEY: {"kind": "page_only", "page": 1}}
        self.row.ledger_status = "superseded"
        self.db.commit()
        result = self.read()
        self.assertEqual(result["locator"], {"kind": "page_only", "page": 1})
        self.assertEqual(result["locator_state"], "stored")
        self.assertEqual(result["ledger_status"], "superseded")

    def test_stored_rectangle_is_returned_in_its_original_coordinate_space(self):
        locator = {"kind": "page_rectangle", "page": 1, "rect": [1000, 2000, 5000, 6000],
                   "page_size": [612000, 792000], "units": "millipoints", "space": "pdf_displayed"}
        self.row.provenance = {LOCATOR_PROVENANCE_KEY: locator}
        self.db.commit()
        self.assertEqual(self.read()["locator"], locator)

    def test_equal_but_invalid_digests_are_not_reported_as_matching(self):
        self.file.sha256 = self.document.sha256_at_ingestion = "invalid"
        self.db.commit()
        with self.assertRaises(LedgerSourceError):
            self.read()

    def test_missing_malformed_and_out_of_range_locators_do_not_invent_positions(self):
        for raw, state in ((None, "missing"), ({"kind": "page_only", "page": True}, "invalid"),
                           ({"kind": "page_only", "page": 99}, "invalid"), ([], "invalid")):
            self.document.page_count = 2
            self.row.provenance = {} if raw is None else {LOCATOR_PROVENANCE_KEY: raw}
            self.db.commit()
            result = self.read()
            self.assertIsNone(result["locator"])
            self.assertEqual(result["locator_state"], state)


class LedgerSourceRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_case_scope_and_refusal_status_are_preserved(self):
        with patch.object(financial_ledger, "ledger_source", return_value={"locator": None}) as call:
            await financial_ledger.get_ledger_source("row", "case", "session")
        call.assert_called_once_with("session", case_id="case", transaction_id="row")
        with patch.object(financial_ledger, "ledger_source", side_effect=LedgerSourceError("Changed", 409)):
            with self.assertRaises(HTTPException) as ctx:
                await financial_ledger.get_ledger_source("row", "case", "session")
        self.assertEqual(ctx.exception.status_code, 409)
