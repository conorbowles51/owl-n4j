"""A whole reviewed PDF batch writes exactly once and keeps source originals."""
import hashlib
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction, FinancialIngestionRun
from postgres.models.financial_candidates import FinancialCandidateFinalization, FinancialCandidateTransaction
from services.financial.candidate_materialization import CandidateFinalizationRequest, finalize_candidates, preview_candidate_finalization
from services.financial.candidate_reviews import review_candidate, read_candidate_review
from services.financial.candidate_store import CandidateStoreError, store_pdf_candidates
from services.financial.decisions import Actor
from services.financial.pdf_geometry_candidates import pdf_grid_source_revision
from tests.test_financial_candidate_finalizations import CANDIDATE_TABLES
from tests.test_financial_pdf_geometry_candidates import rectangle
from tests.test_financial_transactions_writer import TransactionPersistenceTestCase


class MaterializationFixture(TransactionPersistenceTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.db.connection(), tables=CANDIDATE_TABLES +
            [EvidenceDocumentText.__table__, EvidenceTableGeometry.__table__])
        self.path = Path(self._directory) / "synthetic.pdf"
        self.path.write_bytes(b"%PDF-1.4\nsynthetic byte-verification fixture\n")
        self.file = self.evidence(hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.file.stored_path = str(self.path)
        self.file.size = self.path.stat().st_size
        content = "01/02 1234\n03/02 1234"
        job = uuid4()
        self.text = EvidenceDocumentText(evidence_file_id=self.file.id, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            engine_job_id=job, source_locations=[dict(kind="page", page_number=1,
                start_char=0, end_char=len(content), text_origin="digital_text_layer")])
        self.geometry = EvidenceTableGeometry(evidence_file_id=self.file.id, page_number=1, engine_job_id=job,
            payload=[dict(table_source="drawn_geometry", geometry_source="cell_rectangles",
                table=dict(page=1, table=rectangle(0, x=0, width=200, height=200), unlocated_values=0,
                    values=[dict(row=r, column=c, text=value, locator=rectangle(20+r*20, x=20+c*50))
                            for r, day in enumerate(("01/02", "03/02")) for c,value in enumerate((day,"1234"))]))])
        self.db.add_all([self.text, self.geometry])
        self.db.commit()
        self.actor = Actor(self.user.name, self.user.email, self.user.id)
        self.proposal = dict(schema_version="pdf-grid-mapping-v1", case_id=str(self.case.id),
            evidence_file_id=str(self.file.id), page_number=1, table_index=0,
            source_revision=pdf_grid_source_revision(self.db, case_id=self.case.id, evidence_file_id=self.file.id, page_number=1),
            columns=[dict(column_index=0, meaning="booking_date"),dict(column_index=1,meaning="amount")],
            rows=[dict(row_index=r,cells=[dict(column_index=c,expected_text=v) for c,v in enumerate((day,"1234"))])
                  for r,day in enumerate(("01/02","03/02"))])
        self.saved = store_pdf_candidates(self.db, case_id=self.case.id, proposal=self.proposal, actor=self.actor)
        self.candidates = [UUID(row["id"]) for row in self.saved["candidates"]]
        for candidate_id in self.candidates:
            self.decide(candidate_id, "resolved")

    def decide(self, candidate_id, status, **updates):
        state = read_candidate_review(self.db, case_id=self.case.id, candidate_id=candidate_id)
        reading = dict(account_id=str(self.acct.id), currency="GBP", amount_minor="1234", direction="debit",
            booking_date="2026-02-01", transaction_date="2026-01-31", value_date="2026-02-02", description="Synthetic")
        reading.update(updates)
        return review_candidate(self.db, case_id=self.case.id, candidate_id=candidate_id, actor=self.actor,
            request=dict(expected_revision=state["review_revision"], status=status, reason="Synthetic review",
                reading=reading if status=="resolved" else None))

    def preview(self, **updates):
        with self.SessionLocal() as session:
            return preview_candidate_finalization(session, **{**dict(case_id=self.case.id,
                evidence_file_id=self.file.id, resolve_path=Path), **updates})

    def request(self):
        return dict(expected_revision=self.preview()["revision"], documentary_financial_rows=True,
                    accept_incomplete_coverage=True, reason="Reviewed documentary rows; selected coverage only")

    def finalize(self, request=None, **updates):
        return finalize_candidates(**{**dict(session_factory=self.SessionLocal, case_id=self.case.id,
            evidence_file_id=self.file.id, request=request or self.request(), actor=self.actor, resolve_path=Path), **updates})

    def transactions(self):
        self.db.expire_all()
        return list(self.db.scalars(select(FinancialTransaction).join(FinancialSourceDocument,
            FinancialTransaction.source_document_id == FinancialSourceDocument.id)
            .where(FinancialSourceDocument.evidence_file_id == self.file.id).order_by(FinancialTransaction.row_index)))


class MaterializationTests(MaterializationFixture):
    def test_whole_batch_exact_dates_provenance_and_idempotent_retry(self):
        request = self.request()
        result = self.finalize(request)
        again = self.finalize(request)
        self.assertTrue(result["created"])
        self.assertEqual(again, {**result, "created": False})
        rows = self.transactions()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row.ref_id for row in rows}), 2)
        self.assertEqual([row.amount_minor for row in rows], [1234,1234])
        self.assertEqual({row.proof_class for row in rows}, {"p3"})
        self.assertEqual({row.extraction_layer for row in rows}, {4})
        self.assertEqual(str(rows[0].posted_date), "2026-02-01")
        self.assertEqual(str(rows[0].transaction_date), "2026-01-31")
        self.assertEqual(str(rows[0].value_date), "2026-02-02")
        self.assertEqual(rows[0].provenance["candidate_original"], self.saved["candidates"][0]["original"])
        self.assertFalse(result["included_in_default_totals"])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialCandidateTransaction)),2)
        self.assertTrue(self.preview()["applied"])

    def test_rejected_original_is_retained_but_never_written_as_money(self):
        self.decide(self.candidates[1], "rejected")
        self.assertEqual(self.preview()["rejected_count"], 1)
        self.assertEqual(self.finalize()["transaction_count"],1)
        state = read_candidate_review(self.db, case_id=self.case.id,candidate_id=self.candidates[1])
        self.assertEqual(state["status"], "rejected")
        self.assertEqual(len(state["history"]),2)

    def test_pending_or_all_rejected_batch_is_refused(self):
        self.decide(self.candidates[0], "pending")
        with self.assertRaisesRegex(CandidateStoreError, "every saved"):
            self.preview()
        for candidate in self.candidates:self.decide(candidate,"rejected")
        with self.assertRaisesRegex(CandidateStoreError,"At least one"):
            self.preview()
        self.assertEqual(self.transactions(),[])

    def test_stale_review_or_account_context_refuses_write(self):
        request=self.request()
        self.decide(self.candidates[0], "resolved", amount_minor="500")
        with self.assertRaisesRegex(CandidateStoreError,"Reload"):
            self.finalize(request)
        self.assertEqual(self.transactions(),[])

    def test_changed_actual_bytes_refuse_write(self):
        request=self.request()
        self.path.write_bytes(b"changed")
        with self.assertRaisesRegex(CandidateStoreError,"bytes do not match"):
            self.finalize(request)
        self.assertEqual(self.transactions(),[])

    def test_account_currency_change_is_refused(self):
        request=self.request()
        self.acct.currency="USD"; self.db.commit()
        with self.assertRaisesRegex(CandidateStoreError,"account currency"):
            self.finalize(request)
        self.assertEqual(self.transactions(),[])

    def test_another_document_scoped_account_cannot_be_used(self):
        request=self.request()
        self.acct.metadata_={"candidate_account_source_file_id":str(uuid4())};self.db.commit()
        with self.assertRaisesRegex(CandidateStoreError,"source PDF changed"):
            self.finalize(request)
        self.assertEqual(self.transactions(),[])

    def test_existing_ledger_reading_of_same_bytes_blocks_another_batch(self):
        request=self.request()
        self.admit(sha256_at_ingestion=self.file.sha256)
        self.db.commit()
        with self.assertRaisesRegex(CandidateStoreError,"identical source bytes"):
            self.finalize(request)
        self.assertEqual(self.transactions(),[])

    def test_changed_geometry_refuses_write(self):
        request=self.request()
        self.geometry.payload=[];self.db.commit()
        with self.assertRaises(CandidateStoreError):self.finalize(request)
        self.assertEqual(self.transactions(),[])

    def test_same_source_in_another_mapping_is_not_a_second_transaction(self):
        proposal=deepcopy(self.proposal);proposal["columns"][1]["meaning"]="credit"
        other=store_pdf_candidates(self.db,case_id=self.case.id,proposal=proposal,actor=self.actor)
        for row in other["candidates"]:self.decide(UUID(row["id"]),"resolved")
        with self.assertRaisesRegex(CandidateStoreError,"overlap"):
            self.preview()

    def test_wrong_case_is_refused_before_file_resolution(self):
        with patch("services.financial.candidate_materialization.verify_candidate_source_bytes") as call:
            with self.assertRaises(CandidateStoreError) as error:self.preview(case_id=self.other_case.id)
            self.assertEqual(error.exception.status_code,404);call.assert_not_called()

    def test_transaction_or_link_failure_rolls_back_entire_document(self):
        request=self.request()
        from services.financial import candidate_materialization as module
        original=module._receipt
        def fail_on_receipt(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError("Synthetic failure after all rows and links flushed")
        with patch.object(module,"_receipt",side_effect=fail_on_receipt):
            with self.assertRaises(RuntimeError):self.finalize(request)
        self.assertEqual(self.transactions(),[])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialCandidateFinalization)),0)
        self.assertTrue(self.finalize(request)["created"])

    def test_changed_request_after_finalization_is_refused(self):
        request=self.request();self.finalize(request)
        with self.assertRaisesRegex(CandidateStoreError,"different request"):
            self.finalize({**request,"reason":"A different decision"})

    def test_attestations_cannot_be_missing_false_or_coerced(self):
        request=self.request()
        for value in (False, 1, "true", None):
            with self.assertRaises(ValidationError):
                CandidateFinalizationRequest.model_validate({**request,"documentary_financial_rows":value})
        with self.assertRaises(ValidationError):
            CandidateFinalizationRequest.model_validate({**request,"proof_class":"p2"})
