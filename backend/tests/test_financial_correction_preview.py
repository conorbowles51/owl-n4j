"""Correction review never mutates evidence or silently releases held rows."""
import uuid
from unittest.mock import patch

from sqlalchemy import select
from pydantic import ValidationError

from postgres.models.financial import AdjudicationEvent, FinancialTransaction, FinancialStatementPeriod
from services.financial.correction_preview import CorrectionPreviewError, preview_amount_correction
from tests.test_financial_duplicates import DuplicateTestCase, printed


class CorrectionPreviewTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        self.document = self.make_copy(opening=printed(0), closing=printed(42000))
        self.row = self.db.scalar(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.document.id,
            FinancialTransaction.amount_minor == 40000))

    def preview(self, **overrides):
        args = dict(case_id=self.case.id, transaction_id=self.row.id,
                    amount_minor=41000, direction="credit")
        args.update(overrides)
        return preview_amount_correction(self.db, **args)

    def test_current_and_proposed_identity_are_fresh_without_writes(self):
        period = self.db.get(FinancialStatementPeriod, self.row.statement_period_id)
        period.delta_minor = 9876
        self.db.commit()
        result = self.preview()
        self.assertEqual(result["statement_identity"]["current"]["delta_minor"], "0")
        self.assertEqual(result["statement_identity"]["proposed"]["delta_minor"], "1000")
        self.assertFalse(result["applied"])
        self.assertFalse(result["proof_class_changed"])
        self.assertFalse(result["native_controls_rechecked"])
        self.db.commit()  # Even a caller committing the preview changes nothing.
        self.db.refresh(self.row)
        self.db.refresh(period)
        self.assertEqual(self.row.amount_minor, 40000)
        self.assertEqual(period.delta_minor, 9876)
        self.assertEqual(list(self.db.scalars(select(AdjudicationEvent))), [])

    def test_direction_is_explicit_and_exact(self):
        result = self.preview(amount_minor=40000, direction="debit")
        self.assertEqual(result["statement_identity"]["proposed"]["delta_minor"], "-80000")
        self.assertEqual(result["original"]["amount_minor"], "40000")

    def test_quarantine_stays_excluded(self):
        self.row.ledger_status, self.row.quarantine_reason = "quarantined", "adjudicated"
        self.db.commit()
        result = self.preview()
        self.assertEqual(result["proposed"]["ledger_status"], "quarantined")
        self.assertEqual(result["statement_identity"]["current"], result["statement_identity"]["proposed"])

    def test_bigint_is_serialized_without_javascript_rounding(self):
        result = self.preview(amount_minor=9007199254740993)
        self.assertEqual(result["proposed"]["amount_minor"], "9007199254740993")

    def test_invalid_and_unchanged_inputs_are_refused(self):
        for value in (True, 1.1, "100", -1, 9223372036854775808, 40000):
            with self.subTest(value=value), self.assertRaises(CorrectionPreviewError):
                self.preview(amount_minor=value)
        with self.assertRaises(CorrectionPreviewError):
            self.preview(direction="unknown")

    def test_wrong_case_is_missing(self):
        for case_id in (self.other_case.id, uuid.uuid4()):
            with self.assertRaises(CorrectionPreviewError) as exc:
                self.preview(case_id=case_id)
            self.assertEqual(exc.exception.status_code, 404)

    def test_excluded_document_and_superseded_row_are_refused(self):
        self.document.status = "superseded"
        self.db.commit()
        with self.assertRaises(CorrectionPreviewError):
            self.preview()
        self.document.status = "admitted"
        self.row.ledger_status = "superseded"
        self.db.commit()
        with self.assertRaises(CorrectionPreviewError):
            self.preview()

    def test_unlinked_row_does_not_invent_period(self):
        self.row.statement_period_id = None
        self.db.commit()
        self.assertIsNone(self.preview()["statement_identity"])

    def test_revision_changes_when_reading_changes(self):
        first = self.preview()["document_revision"]
        self.row.content_hash = "f" * 64
        self.db.commit()
        self.assertNotEqual(first, self.preview()["document_revision"])

    def test_locator_is_preserved(self):
        self.row.provenance = {"locator": {"kind": "not_positional"}}
        self.db.commit()
        self.assertEqual(self.preview()["original"]["locator"], {"kind": "not_positional"})

    def test_cross_document_period_link_is_refused(self):
        other = self.make_copy()
        period = self.db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == other.id))
        self.row.statement_period_id = period.id
        self.db.commit()
        with self.assertRaises(CorrectionPreviewError) as exc:
            self.preview()
        self.assertEqual(exc.exception.status_code, 409)

    def test_running_balance_comparison_changes_with_proposal_without_writes(self):
        self.row.running_balance_minor = 40000
        self.db.commit()
        result = self.preview()
        self.assertTrue(result["running_balances"]["available"])
        forward = result["running_balances"]["interpretations"][0]
        self.assertEqual(forward["current"]["mismatch_count"], 0)
        self.assertEqual(forward["proposed"]["mismatch_count"], 1)
        self.assertFalse(self.db.dirty or self.db.new)

    def test_running_balance_change_invalidates_review_even_without_rehashed_content(self):
        first = self.preview()["document_revision"]
        self.row.running_balance_minor = 40000
        self.db.commit()
        self.assertNotEqual(first, self.preview()["document_revision"])

    def test_route_inherits_authentication_and_case_edit(self):
        from routers import financial_adjudication as router
        route = next(r for r in router.router.routes if r.path.endswith("/correction-preview"))
        dependencies = {d.call for d in route.dependant.dependencies}
        self.assertIn(router.get_current_db_user, dependencies)
        self.assertIn(router._require_adjudication_case_access, dependencies)
        self.assertEqual(router._adjudication_case_permission(None, {}), ("case", "edit"))

    def test_request_requires_integer_string(self):
        from routers.financial_adjudication import AmountCorrectionPreviewRequest
        for value in (100, 1.5, True, "1.5", "-1", "1e3", "01"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                AmountCorrectionPreviewRequest(amount_minor=value, direction="credit")

    def test_route_redacts_failure_and_releases_locks(self):
        import asyncio
        from fastapi import HTTPException
        from routers import financial_adjudication as router
        body = router.AmountCorrectionPreviewRequest(amount_minor="100", direction="credit")
        with patch.object(router, "preview_amount_correction", side_effect=RuntimeError("private SQL")), patch.object(self.db, "rollback") as rollback:
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(router.amount_correction_preview(self.row.id, body, self.case.id, self.db))
            self.assertEqual(exc.exception.status_code, 500)
            self.assertNotIn("private", exc.exception.detail)
            rollback.assert_called_once()
