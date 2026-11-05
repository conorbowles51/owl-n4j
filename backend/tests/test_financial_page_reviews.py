"""A person's page review is saved with who, when and why, can be undone, and changes no reading or total."""
import json
from types import SimpleNamespace

from sqlalchemy import func, select

from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_page_review import FinancialPageReview
from services.financial.ledger_snapshot import (
    LedgerSnapshot, _capture_history, capture_ledger_snapshot, render_ledger_report,
)
from services.financial.page_reviews import (
    capture_page_reviews, read_page_reviews, save_page_review, undo_page_review,
)
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_duplicates import DuplicateTestCase


class PageReviewTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[
            table for table in Base.metadata.sorted_tables if table.name.startswith("financial_")])
        self.document = self.make_copy()
        self.file_id = self.document.evidence_file_id
        self.person = SimpleNamespace(user_id=self.user.id, name="Investigator", email="investigator@example.test")

    def save(self, page=3, disposition="supporting_correspondence", reason="Bank letter about fees", expected=None, actor=None):
        return save_page_review(self.db, case_id=self.case.id, evidence_file_id=self.file_id, page_number=page,
                                disposition=disposition, reason=reason, expected_review_id=expected,
                                actor=actor or self.person)

    def export(self):
        snapshot = capture_ledger_snapshot(self.db, case_id=self.case.id)
        return _capture_history(self.db, json.loads(snapshot.content), case_id=self.case.id)

    def undo(self, page, expected):
        return undo_page_review(self.db, case_id=self.case.id, evidence_file_id=self.file_id, page_number=page,
                                expected_review_id=expected, actor=self.person)

    def test_a_saved_review_records_what_why_who_when_and_the_exact_file(self):
        review = self.save()["reviews"][0]
        self.assertEqual(review["page_number"], 3)
        self.assertEqual(review["label"], "Supporting correspondence")
        self.assertEqual(review["reason"], "Bank letter about fees")
        self.assertEqual(review["saved_by"], "Investigator")
        self.assertTrue(review["saved_at"])
        self.assertTrue(review["same_file_bytes"])
        self.assertIsNone(review["origin"])

    def test_each_of_the_four_answers_saves_and_an_unknown_one_is_refused(self):
        expected = None
        for disposition in ("supporting_correspondence", "continuation", "blank", "other"):
            result = self.save(disposition=disposition, expected=expected)
            expected = result["reviews"][0]["id"]
        with self.assertRaises(PdfMappingError) as refused:
            self.save(disposition="no_transactions", expected=expected)
        self.assertEqual(refused.exception.status_code, 422)

    def test_a_reason_is_required(self):
        with self.assertRaises(PdfMappingError):
            self.save(reason="   ")

    def test_undo_returns_to_the_review_before_and_keeps_the_history(self):
        first = self.save()["reviews"][0]
        second = self.save(disposition="blank", reason="Nothing printed", expected=first["id"])["reviews"][0]
        result = self.undo(3, second["id"])
        self.assertEqual([r["id"] for r in result["reviews"]], [first["id"]])
        self.assertEqual(len(result["history"]), 2)
        undone = next(r for r in result["history"] if r["id"] == second["id"])
        self.assertEqual(undone["undone_by"], "Investigator")
        result = self.undo(3, first["id"])
        self.assertEqual(result["reviews"], [])
        self.assertEqual(len(result["history"]), 2)
        with self.assertRaises(PdfMappingError):
            self.undo(3, None)

    def test_a_save_over_someone_elses_newer_review_is_refused_and_names_them(self):
        self.save()
        other = SimpleNamespace(user_id=self.user.id, name="A Colleague", email="c@example.test")
        with self.assertRaises(PdfMappingError) as refused:
            self.save(reason="Mine", actor=other)
        self.assertEqual(refused.exception.status_code, 409)
        self.assertIn("Investigator", str(refused.exception))
        self.assertEqual(len(read_page_reviews(self.db, case_id=self.case.id, evidence_file_id=self.file_id)["history"]), 1)

    def test_a_model_doing_the_work_stays_labelled(self):
        model = SimpleNamespace(user_id=self.user.id, name="Investigator", email=None,
                                origin={"kind": "model", "model": "TestModel"})
        self.assertEqual(self.save(actor=model)["reviews"][0]["origin"]["model"], "TestModel")

    def test_another_case_cannot_read_or_save(self):
        for call in (lambda: read_page_reviews(self.db, case_id=self.other_case.id, evidence_file_id=self.file_id),
                     lambda: save_page_review(self.db, case_id=self.other_case.id, evidence_file_id=self.file_id,
                                              page_number=1, disposition="blank", reason="x", expected_review_id=None,
                                              actor=self.person)):
            with self.assertRaises(PdfMappingError) as refused:
                call()
            self.assertEqual(refused.exception.status_code, 404)

    def test_a_review_changes_no_payment_or_statement_reading(self):
        def state():
            self.db.expire_all()
            rows = self.db.execute(select(FinancialTransaction.id, FinancialTransaction.amount_minor,
                                          FinancialTransaction.ledger_status)).all()
            return sorted(map(str, rows)), self.db.get(type(self.document), self.document.id).status
        before = state()
        review = self.save()["reviews"][0]
        self.undo(3, review["id"])
        self.assertEqual(state(), before)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialPageReview)), 1)

    def test_an_export_lists_reviews_and_undone_ones_stay_marked(self):
        first = self.save()["reviews"][0]
        self.save(page=4, disposition="blank", reason="Nothing printed")
        self.undo(3, first["id"])
        captured = capture_page_reviews(self.db, case_id=self.case.id, evidence_file_ids=[self.file_id])
        self.assertEqual([(r["page_number"], bool(r["undone_at"])) for r in captured], [(3, True), (4, False)])
        document = self.export()
        self.assertEqual(len(document["page_reviews"]), 2)
        content = json.dumps(document)
        html = render_ledger_report(LedgerSnapshot(content=content, sha256="0" * 64, byte_count=len(content)))
        self.assertIn("Original pages reviewed by a person", html)
        self.assertIn("Bank letter about fees", html)

    def test_an_export_with_no_reviews_has_no_new_key(self):
        self.assertNotIn("page_reviews", self.export())
