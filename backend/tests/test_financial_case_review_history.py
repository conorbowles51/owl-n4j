import unittest
from unittest.mock import patch
from uuid import uuid4
from postgres.base import Base
from postgres.models.financial import AdjudicationEvent
from services.financial.case_financial_history import capture_case_financial_history
from services.financial.ledger_summary import LedgerSummaryError
from tests import test_financial_candidate_reviews as fixture


class CaseReviewHistoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CandidateReviewTests()
        self.f.setUp()
        Base.metadata.create_all(self.f.fixture.engine, tables=[AdjudicationEvent.__table__])

    def tearDown(self):
        self.f.tearDown()

    def capture(self, **kwargs):
        return capture_case_financial_history(self.f.fixture.db, case_id=kwargs.get('case_id', self.f.fixture.case))

    def test_pending_and_rejected_readings_are_retained_without_ledger_admission(self):
        before = self.capture()
        self.assertEqual(len(before['pdf_review_history']['candidates']), 2)
        self.assertEqual(before['pdf_review_history']['review_states'][0]['status'], 'pending')
        self.f.review('rejected')
        after = self.capture()
        self.assertEqual(len(after['pdf_review_history']['reviews']), 1)
        self.assertEqual(next(row for row in after['pdf_review_history']['review_states'] if row['candidate_id'] == str(self.f.candidate_id))['status'], 'rejected')
        self.assertEqual(after['pdf_review_history']['finalizations'], [])
        self.assertFalse(self.f.fixture.db.new or self.f.fixture.db.dirty)

    def test_other_case_is_empty_and_limits_refuse_partial_history(self):
        other = self.capture(case_id=uuid4())
        self.assertEqual(other['decisions'], [])
        self.assertEqual(other['pdf_review_history']['candidates'], [])
        with patch('services.financial.case_financial_history.MAX_CASE_HISTORY_RECORDS', 0):
            with self.assertRaises(LedgerSummaryError): self.capture()

    def test_decisions_outside_ledger_rows_are_captured_and_sequence_gaps_refused(self):
        from postgres.models.enums import AdjudicationSubject, AdjudicationDecision
        f = self.f.fixture
        subject = uuid4()
        def event(sequence):
            return AdjudicationEvent(case_id=f.case, subject_type=AdjudicationSubject.evidence_file.value,
                subject_id=subject, subject_sequence=sequence, decision=AdjudicationDecision.admit_financial_document.value,
                reason='Synthetic outside-ledger decision', actor_name='Tester', actor_email='fixture@example.test')
        f.db.add(event(2));f.db.commit()
        with self.assertRaisesRegex(LedgerSummaryError, 'sequence gap'): self.capture()
        f.db.add(event(1));f.db.commit()
        result = self.capture()
        self.assertEqual([d['subject_sequence'] for d in result['decisions']], [1, 2])
        self.assertEqual(result['decisions'][0]['reason'], 'Synthetic outside-ledger decision')
