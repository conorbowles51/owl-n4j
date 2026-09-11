from unittest.mock import patch
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction, AdjudicationEvent
from services.financial.corrections import correct_transaction
from services.financial.correction_preview import CorrectionPreviewError
from services.financial.duplicate_decisions import duplicate_revision
from services.financial.reconcile import total_transactions
from tests.test_financial_duplicates import DuplicateTestCase, printed


class CorrectionTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        self.document = self.make_copy(opening=printed(0), closing=printed(42000))
        self.document.metadata_ = {"source_shape": "statement_document"}
        self.db.commit()
        self.row = self.db.scalar(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.document.id,
            FinancialTransaction.amount_minor == 40000))

    def correct(self, row=None, **overrides):
        row = row or self.row
        args = dict(case_id=self.case.id, transaction_id=row.id, amount_minor=41000,
                    direction="credit", expected_revision=duplicate_revision(self.db, self.document),
                    actor=self.actor, reason="Checked the source amount")
        args.update(overrides)
        return correct_transaction(self.db, **args)

    def test_replacement_audit_and_reconciliation_commit_together(self):
        ref = self.row.ref_id
        result = self.correct()
        self.db.refresh(self.row)
        self.assertEqual(self.row.amount_minor, 40000)
        self.assertEqual(self.row.ref_id, ref)
        self.assertEqual(self.row.ledger_status, "superseded")
        new = self.db.get(FinancialTransaction, self.row.superseded_by_id)
        self.assertEqual(new.amount_minor, 41000)
        self.assertNotEqual(new.ref_id, ref)
        totals = total_transactions(self.db, period_id=new.statement_period_id, currency="GBP")
        self.assertEqual(totals.credits.minor_units, 43000)
        self.assertEqual(totals.counted, 2)
        self.assertEqual(result["proof_class"], "p3")
        events = list(self.db.scalars(select(AdjudicationEvent).where(AdjudicationEvent.decision == "correct_transaction")))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor_user_id, self.user.id)
        self.assertEqual(events[0].before["row"]["amount_minor"], "40000")

    def test_date_description_and_balance_correction_preserves_original_and_source(self):
        from datetime import date
        original_date = self.row.transaction_date
        original_balance = self.row.running_balance_minor
        original_source = self.row.provenance.get("locator")
        result = self.correct(amount_minor=self.row.amount_minor, direction=self.row.direction,
            fields={'transaction_date': '2023-02-07', 'description': 'Corrected source description',
                    'running_balance_minor': '12345', 'bank_reference': 'PRINTED-REF'})
        self.db.refresh(self.row)
        replacement = self.db.get(FinancialTransaction, self.row.superseded_by_id)
        self.assertEqual(self.row.transaction_date, original_date)
        self.assertEqual(self.row.running_balance_minor, original_balance)
        self.assertEqual(replacement.transaction_date, date(2023, 2, 7))
        self.assertEqual(replacement.description, 'Corrected source description')
        self.assertEqual(replacement.running_balance_minor, 12345)
        self.assertEqual(replacement.bank_reference, 'PRINTED-REF')
        if self.row.ordering_date_source == 'transaction':
            self.assertEqual(replacement.ordering_date, date(2023, 2, 7))
        self.assertEqual(replacement.provenance.get("locator"), original_source)
        self.assertFalse(result['native_controls_rechecked'])

    def test_invalid_field_corrections_leave_the_original_current(self):
        for fields in ({'transaction_date': '2023-02-30'}, {'running_balance_minor': '9223372036854775808'},
                       {'account_id': 'another-account'}, {'transaction_date': None, 'posted_date': None,
                        'value_date': None, 'effective_date': None}):
            with self.subTest(fields=fields), self.assertRaises(CorrectionPreviewError):
                self.correct(fields=fields)
        self.db.refresh(self.row)
        self.assertEqual(self.row.ledger_status, 'admitted')

    def test_can_correct_back_without_overwriting_history(self):
        self.correct()
        new = self.db.get(FinancialTransaction, self.row.superseded_by_id)
        self.correct(new, amount_minor=40000)
        restored = self.db.get(FinancialTransaction, new.superseded_by_id)
        self.assertEqual(restored.amount_minor, 40000)
        self.assertEqual(self.document.proof_class, "p2")
        self.assertNotEqual(restored.id, self.row.id)

    def test_quarantine_is_preserved_on_replacement(self):
        self.row.ledger_status, self.row.quarantine_reason = "quarantined", "adjudicated"
        self.db.commit()
        self.correct()
        new = self.db.get(FinancialTransaction, self.row.superseded_by_id)
        self.assertEqual((new.ledger_status, new.quarantine_reason), ("quarantined", "adjudicated"))
        self.assertIsNone(self.row.quarantine_reason)

    def test_stale_revision_refuses_without_audit(self):
        with self.assertRaises(CorrectionPreviewError):
            self.correct(expected_revision="0" * 64)
        self.assertEqual(list(self.db.scalars(select(AdjudicationEvent))), [])

    def test_recorded_correction_cannot_be_submitted_twice(self):
        revision = duplicate_revision(self.db, self.document)
        self.correct(expected_revision=revision)
        with self.assertRaises(CorrectionPreviewError):
            self.correct(expected_revision=revision)
        events = list(self.db.scalars(select(AdjudicationEvent).where(AdjudicationEvent.decision == "correct_transaction")))
        self.assertEqual(len(events), 1)

    def test_wrong_case_cannot_write(self):
        with self.assertRaises(CorrectionPreviewError) as caught:
            self.correct(case_id=self.other_case.id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_reclassification_failure_rolls_back_everything(self):
        with patch("services.financial.corrections.reclassify_after_reconciliation", side_effect=RuntimeError("grading failed")):
            with self.assertRaises(RuntimeError):
                self.correct()
        self.db.refresh(self.row)
        self.assertEqual(self.row.ledger_status, "admitted")
        self.assertIsNone(self.row.superseded_by_id)
        self.assertEqual(list(self.db.scalars(select(AdjudicationEvent))), [])

    def test_endpoint_derives_actor_and_requires_case_edit(self):
        import asyncio
        from routers import financial_adjudication as router
        route = next(r for r in router.router.routes if r.path.endswith("/correction"))
        dependencies = {d.call for d in route.dependant.dependencies}
        self.assertIn(router.get_current_db_user, dependencies)
        self.assertIn(router._require_adjudication_case_access, dependencies)
        body = router.AmountCorrectionRequest(amount_minor="41000", direction="credit", reason="Reviewed", expected_revision="a" * 64)
        with patch.object(router, "correct_transaction", return_value={"applied": True}) as call:
            result = asyncio.run(router.record_amount_correction(self.row.id, body, self.case.id, self.user, self.db))
        self.assertTrue(result["applied"])
        self.assertEqual(call.call_args.kwargs["actor"].user_id, self.user.id)
        self.assertEqual(call.call_args.kwargs["amount_minor"], 41000)

    def test_commit_failure_rolls_back_replacement_and_original(self):
        with patch.object(self.db, "commit", side_effect=RuntimeError("commit failure")):
            with self.assertRaises(RuntimeError):
                self.correct()
        self.db.refresh(self.row)
        self.assertEqual(self.row.ledger_status, "admitted")
        self.assertIsNone(self.row.superseded_by_id)
        self.assertEqual(list(self.db.scalars(select(AdjudicationEvent))), [])

    def test_native_controls_are_not_claimed_to_have_been_rechecked(self):
        self.document.metadata_ = {"source_shape": "native_with_control_totals"}
        self.db.commit()
        self.correct()
        new = self.db.get(FinancialTransaction, self.row.superseded_by_id)
        result = self.correct(new, amount_minor=40000)
        self.assertEqual(result["proof_class"], "p3")
        self.assertTrue(self.document.metadata_["admissibility_reservations"])

    def test_printed_running_balances_require_revalidation(self):
        self.row.running_balance_minor = 40000
        self.db.commit()
        self.correct()
        new = self.db.get(FinancialTransaction, self.row.superseded_by_id)
        self.correct(new, amount_minor=40000)
        self.assertEqual(self.document.proof_class, "p3")
        self.assertIn("running-balance", self.document.metadata_["admissibility_reservations"][0])

    def test_recorded_correction_retains_running_balance_diagnostics_without_promotion(self):
        self.row.running_balance_minor = 40000
        self.db.commit()
        result = self.correct()
        event = self.db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.decision == "correct_transaction"))
        comparison = event.after["running_balance_comparison"]
        self.assertTrue(comparison["available"])
        self.assertEqual(comparison["interpretations"][0]["proposed"]["mismatch_count"], 1)
        self.assertEqual(result["proof_class"], "p3")
        self.assertIn("requires revalidation", self.document.metadata_["admissibility_reservations"][0])

    def test_unknown_shape_is_an_explicit_refusal(self):
        self.document.metadata_ = {}
        self.db.commit()
        with self.assertRaises(CorrectionPreviewError) as caught:
            self.correct()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIsNone(self.row.superseded_by_id)

    def test_return_to_real_content_hash_allocates_another_occurrence(self):
        from dataclasses import fields
        from services.financial.references import RowReading, content_hash, ref_id
        from postgres.models.enums import TransactionDirection
        values = {field.name: getattr(self.row, field.name) for field in fields(RowReading)}
        values["direction"] = TransactionDirection(self.row.direction)
        digest = content_hash(RowReading(**values))
        self.row.content_hash = digest
        self.row.ref_id = ref_id(self.document.sha256_at_ingestion, digest)
        self.db.commit()
        self.correct()
        new = self.db.get(FinancialTransaction, self.row.superseded_by_id)
        self.correct(new, amount_minor=40000)
        last = self.db.get(FinancialTransaction, new.superseded_by_id)
        self.assertNotEqual(last.content_hash, digest)
        self.assertEqual(last.provenance["correction"]["occurrence"], 1)

    def test_preview_predicts_recorded_class_and_reservations_without_writes(self):
        from services.financial.correction_preview import preview_amount_correction
        self.row.running_balance_minor = 40000
        self.db.commit()
        preview = preview_amount_correction(self.db, case_id=self.case.id, transaction_id=self.row.id,
                                             amount_minor=41000, direction="credit")
        verification = preview["verification"]
        self.assertTrue(verification["can_record"])
        self.assertEqual(verification["proposed_proof_class"], "p3")
        self.assertFalse(verification["included_in_default_totals"])
        self.assertNotIn("admissibility_reservations", self.document.metadata_)
        result = self.correct(expected_revision=preview["document_revision"])
        self.assertEqual(result["proof_class"], verification["proposed_proof_class"])
        self.assertEqual(self.document.metadata_["admissibility_reservations"], verification["reservations"])

    def test_source_metadata_changes_invalidate_review(self):
        revision = duplicate_revision(self.db, self.document)
        self.document.metadata_ = {**self.document.metadata_, "admissibility_reservations": ["Manual hold"]}
        self.db.commit()
        with self.assertRaises(CorrectionPreviewError) as caught:
            self.correct(expected_revision=revision)
        self.assertEqual(caught.exception.status_code, 409)

    def test_preview_reports_unknown_source_as_not_recordable(self):
        from services.financial.correction_preview import preview_amount_correction
        self.document.metadata_ = {}
        self.db.commit()
        preview = preview_amount_correction(self.db, case_id=self.case.id, transaction_id=self.row.id,
                                             amount_minor=41000, direction="credit")
        self.assertFalse(preview["verification"]["can_record"])
        self.assertIsNone(preview["verification"]["proposed_proof_class"])

    def test_verification_disagreement_rolls_back_recording(self):
        with patch("services.financial.corrections.reclassify_after_reconciliation"):
            with self.assertRaises(CorrectionPreviewError):
                self.correct()
        self.db.refresh(self.row)
        self.assertIsNone(self.row.superseded_by_id)
        self.assertEqual(list(self.db.scalars(select(AdjudicationEvent))), [])
