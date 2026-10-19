"""Durable source/candidate links survive retries and refuse replacement."""
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from postgres.base import Base
from postgres.models.enums import ExtractionLayer
from postgres.models.financial_candidates import (
    FinancialCandidateMapping, FinancialExtractionCandidate, FinancialCandidateReview,
    FinancialCandidateFinalization, FinancialCandidateTransaction,
)
from services.financial.proof_class import SourceShape
from tests.test_financial_transactions_writer import TransactionPersistenceTestCase, TABLES as LEDGER_TABLES

CANDIDATE_TABLES = [model.__table__ for model in (
    FinancialCandidateMapping, FinancialExtractionCandidate, FinancialCandidateReview,
    FinancialCandidateFinalization, FinancialCandidateTransaction,
)]

class FinalizationFixture(TransactionPersistenceTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.db.connection(), tables=CANDIDATE_TABLES)
        self.user.email = f"finalization-{uuid4()}@example.test"
        self.document = self.admit(sha256_at_ingestion="c" * 64,
            extraction_layer=ExtractionLayer.investigator_review,
            shape=SourceShape.selected_document_rows)
        (self.transaction,) = self.write([self.draft()])
        self.mapping = FinancialCandidateMapping(case_id=self.case.id,
            evidence_file_id=self.document.evidence_file_id, mapping_revision="d" * 64,
            snapshot_sha256="e" * 64, snapshot={}, actor={}, candidate_count=1)
        self.db.add(self.mapping)
        self.db.flush()
        self.candidate = FinancialExtractionCandidate(mapping_id=self.mapping.id,
            candidate_key=str(uuid4()).replace("-", "") * 2, row_index=0, snapshot_sha256="a" * 64, snapshot={})
        self.db.add(self.candidate)
        self.db.flush()
        self.review = FinancialCandidateReview(candidate_id=self.candidate.id,
            sequence=1, status="resolved", reason="Synthetic review", reading={},
            actor={}, original_sha256="a" * 64, previous_revision="b" * 64)
        self.db.add(self.review)
        self.db.commit()

    def receipt_values(self, **updates):
        values = dict(id=uuid4(), case_id=self.case.id,
            evidence_file_id=self.document.evidence_file_id,
            source_document_id=self.document.id, ingestion_run_id=self.run.run_id,
            source_sha256="c" * 64, snapshot_sha256="a" * 64, snapshot={}, actor={},
            reason="Synthetic finalization", transaction_count=1)
        return {**values, **updates}

    def link_values(self, finalization_id, **updates):
        values = dict(id=uuid4(), finalization_id=finalization_id,
            candidate_id=self.candidate.id, review_id=self.review.id,
            transaction_id=self.transaction.id, source_claim_sha256="b" * 64,
            review_revision="c" * 64, original_sha256="a" * 64)
        return {**values, **updates}

    def finalize(self):
        receipt = FinancialCandidateFinalization(**self.receipt_values())
        self.db.add(receipt)
        self.db.flush()
        link = FinancialCandidateTransaction(**self.link_values(receipt.id))
        self.db.add(link)
        self.db.commit()
        return receipt, link

class FinalizationStorageTests(FinalizationFixture):
    def test_review_service_refuses_sealed_file_before_rebinding(self):
        from services.financial.candidate_reviews import review_candidate
        from services.financial.candidate_store import CandidateStoreError
        from services.financial.decisions import Actor
        self.finalize()
        with self.assertRaisesRegex(CandidateStoreError, "finalized"):
            review_candidate(self.db, case_id=self.case.id, candidate_id=self.candidate.id,
                request=dict(expected_revision="a" * 64, status="pending", reason="Reopen"),
                actor=Actor(name="Synthetic investigator", email="test@example.test"))

    def test_same_file_cannot_be_finalized_again(self):
        self.finalize()
        with self.assertRaises(IntegrityError):
            self.db.add(FinancialCandidateFinalization(**self.receipt_values()))
            self.db.commit()
        self.db.rollback()

    def test_same_candidate_or_transaction_cannot_be_linked_twice(self):
        receipt, _ = self.finalize()
        with self.assertRaises(IntegrityError):
            self.db.add(FinancialCandidateTransaction(**self.link_values(receipt.id)))
            self.db.commit()
        self.db.rollback()

    def test_receipt_and_link_cannot_be_rewritten(self):
        receipt, link = self.finalize()
        for obj, field, replacement in ((receipt, "reason", "replace audit"),
                                        (link, "review_revision", "d" * 64)):
            with self.assertRaises(ValueError):
                setattr(obj, field, replacement)
                self.db.commit()
            self.db.rollback()

    def test_link_keeps_original_transaction_when_it_is_quarantined(self):
        _, link = self.finalize()
        self.transaction.ledger_status = "quarantined"
        self.transaction.quarantine_reason = "adjudicated"
        self.db.commit()
        self.db.refresh(link)
        self.assertEqual(link.transaction_id, self.transaction.id)
