import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import update
from services.financial.ledger_review_history import capture_pdf_review_history
from services.financial.ledger_summary import LedgerSummaryError
from postgres.models.financial_candidates import FinancialCandidateReview, FinancialExtractionCandidate, FinancialCandidateMapping
from tests import test_financial_candidate_reviews as fixtures

class LedgerReviewHistoryTests(unittest.TestCase):
    def setUp(self): self.f=fixtures.CandidateReviewTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def capture(self, **kw):
        f=self.f.fixture
        return capture_pdf_review_history(f.db,**{**dict(case_id=f.case,evidence_file_ids={f.file}),**kw})
    def test_originals_decisions_exact_money_and_scope_preserved(self):
        self.f.review('resolved',reading=self.f.reading(amount_minor='9007199254740993'))
        result=self.capture()
        self.assertEqual(result['reviews'][0]['reading']['amount_minor'],'9007199254740993')
        self.assertEqual(result['review_states'][0]['reading']['amount_minor'],'9007199254740993')
        self.assertTrue(result['candidates'][0]['snapshot'])
        self.assertTrue(result['reviews'][0]['reason'])
        self.assertEqual(self.capture(),result)
        self.assertEqual(self.capture(case_id=uuid4())['reviews'],[])
        self.assertEqual(self.capture(evidence_file_ids=set())['candidates'],[])
        self.assertFalse(self.f.fixture.db.new or self.f.fixture.db.dirty)
    def test_truncation_and_broken_review_chain_refused(self):
        self.f.review()
        with patch('services.financial.ledger_review_history.MAX_REVIEW_EXPORT_RECORDS',1):
            with self.assertRaises(LedgerSummaryError):self.capture()
        db=self.f.fixture.db
        db.execute(update(FinancialCandidateReview).values(previous_revision='0'*64));db.commit()
        with self.assertRaisesRegex(LedgerSummaryError,'chain'):self.capture()
    def test_original_digest_mismatch_refused(self):
        db=self.f.fixture.db
        db.execute(update(FinancialExtractionCandidate).values(snapshot_sha256='0'*64));db.commit()
        with self.assertRaisesRegex(LedgerSummaryError,'digest'):self.capture()

    def test_missing_candidate_population_is_refused(self):
        db=self.f.fixture.db
        db.execute(update(FinancialCandidateMapping).values(candidate_count=3));db.commit()
        with self.assertRaisesRegex(LedgerSummaryError,'coverage'):self.capture()
