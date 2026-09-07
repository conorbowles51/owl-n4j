"""Pending originals are atomic, retry-safe and separate from financial totals."""
import unittest
from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy import event, func, select, update

from postgres.base import Base
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialExtractionCandidate, FinancialCandidateReview
from services.financial.candidate_store import CandidateStoreError, read_candidate_mapping, store_pdf_candidates
from services.financial.decisions import Actor
from services.financial.pdf_candidates import pdf_mapping_source_revision
from tests import test_financial_pdf_geometry_candidates as grid_fixture


class CandidateStoreTests(unittest.TestCase):
    revision = grid_fixture.GridBindingTests.revision

    def setUp(self):
        grid_fixture.GridBindingTests.setUp(self)
        Base.metadata.create_all(self.engine, tables=[FinancialCandidateMapping.__table__, FinancialExtractionCandidate.__table__, FinancialCandidateReview.__table__])
        self.mapping["schema_version"] = "pdf-grid-mapping-v1"
        self.actor = Actor(name="Synthetic investigator", email="synthetic@example.test")

    def tearDown(self):
        grid_fixture.GridBindingTests.tearDown(self)

    def save(self, **updates):
        params = dict(case_id=self.case, proposal=self.mapping, actor=self.actor)
        params.update(updates)
        return store_pdf_candidates(self.db, **params)

    def counts(self):
        return tuple(self.db.scalar(select(func.count()).select_from(model))
                     for model in (FinancialCandidateMapping, FinancialExtractionCandidate))

    def read(self, result, case=None):
        return read_candidate_mapping(self.db, case_id=case or self.case, mapping_id=UUID(result["id"]))

    def test_save_survives_new_session_and_does_not_create_amount_fields(self):
        saved = self.save()
        self.assertTrue(saved["created"])
        self.assertEqual(self.counts(), (1, 2))
        self.db.close()
        from sqlalchemy.orm import Session
        self.db = Session(self.engine)
        loaded = self.read(saved)
        self.assertEqual(loaded["candidates"], saved["candidates"])
        self.assertEqual(loaded["actor"]["name"], self.actor.name)
        self.assertEqual({r["status"] for r in loaded["candidates"]}, {"pending"})
        self.assertNotIn("amount_minor", FinancialExtractionCandidate.__table__.columns)
        self.assertFalse(loaded["applied"])

    def test_retry_preserves_ids_original_actor_and_counts(self):
        first = self.save()
        second = self.save(actor=Actor("Another investigator", "another@example.test"))
        self.assertFalse(second["created"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["candidates"], second["candidates"])
        self.assertEqual(first["actor"], second["actor"])
        self.assertEqual(self.counts(), (1, 2))

    def test_stale_retry_refused_without_overwriting_originals(self):
        saved = self.save()
        self.text.source_locations = []
        self.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.save()
        self.assertEqual(self.read(saved)["candidates"], saved["candidates"])
        self.assertEqual(self.counts(), (1, 2))

    def test_new_mapping_revision_keeps_old_originals(self):
        saved = self.save()
        self.mapping["columns"][1]["meaning"] = "balance"
        revised = self.save()
        self.assertNotEqual(saved["id"], revised["id"])
        self.assertEqual(self.counts(), (2, 4))
        self.assertEqual(self.read(saved)["candidates"][0]["original"]["cells"][1]["proposed_meaning"], "amount")

    def test_canonical_text_candidates_can_also_be_saved(self):
        position = self.text.content.index("1234")
        proposal = dict(case_id=str(self.case), evidence_file_id=str(self.file),
            source_revision=pdf_mapping_source_revision(self.db, case_id=self.case, evidence_file_id=self.file),
            table_id=str(uuid4()), start_char=position, end_char=position + 4,
            columns=[dict(column_index=0, meaning="unknown")], rows=[dict(row_index=0,
                cells=[dict(column_index=0, source=dict(start_char=position, end_char=position+4, text="1234"))])])
        saved = self.save(proposal=proposal)
        self.assertEqual(saved["candidates"][0]["original"]["cells"][0]["source"]["text"], "1234")
        self.assertEqual(self.counts(), (1, 1))

    def test_cross_case_save_read_and_relabelled_proposal_are_refused(self):
        saved = self.save()
        other = uuid4()
        for proposal in (self.mapping, {**self.mapping, "case_id": str(other)}):
            with self.assertRaises(CandidateStoreError) as error:
                self.save(case_id=other, proposal=proposal)
            self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(CandidateStoreError) as error:
            self.read(saved, other)
        self.assertEqual(error.exception.status_code, 404)

    def test_partial_insert_rolls_back_the_whole_mapping(self):
        def fail_second(mapper, connection, candidate):
            if candidate.row_index == 1:
                raise RuntimeError("Synthetic mid-save failure")
        event.listen(FinancialExtractionCandidate, "before_insert", fail_second)
        try:
            with self.assertRaises(RuntimeError):
                self.save()
        finally:
            event.remove(FinancialExtractionCandidate, "before_insert", fail_second)
        self.assertEqual(self.counts(), (0, 0))
        self.assertTrue(self.save()["created"])

    def test_original_updates_are_refused_by_orm(self):
        saved = self.save()
        for model in (FinancialCandidateMapping, FinancialExtractionCandidate):
            row = self.db.scalar(select(model))
            row.snapshot = {"changed": True}
            with self.assertRaises(ValueError):
                self.db.commit()
            self.db.rollback()
        self.assertEqual(self.read(saved)["candidates"], saved["candidates"])

    def test_returned_payload_does_not_mutate_stored_original(self):
        saved = self.save()
        expected = deepcopy(saved["candidates"])
        saved["candidates"][0]["original"]["cells"][0]["text"] = "changed"
        self.db.commit()
        self.assertEqual(self.read(saved)["candidates"], expected)

    def test_incomplete_candidate_population_is_refused(self):
        saved = self.save()
        self.db.delete(self.db.scalar(select(FinancialExtractionCandidate)))
        self.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.read(saved)
        with self.assertRaises(CandidateStoreError):
            self.save()

    def test_corrupted_snapshot_is_detected_on_sqlite_without_pg_trigger(self):
        saved = self.save()
        self.db.execute(update(FinancialExtractionCandidate).values(snapshot={"changed": True}))
        self.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.read(saved)

    def test_dirty_session_is_refused_without_losing_unrelated_changes(self):
        self.evidence.original_filename = "unsaved name.pdf"
        with self.assertRaises(CandidateStoreError):
            self.save()
        self.assertIn(self.evidence, self.db.dirty)
        self.db.rollback()
        self.assertEqual(self.counts(), (0, 0))

    def test_actor_required(self):
        with self.assertRaises(CandidateStoreError):
            self.save(actor=None)
        self.assertEqual(self.counts(), (0, 0))

    def test_missing_source_row_is_refused_before_binding(self):
        self.db.delete(self.text)
        self.db.commit()
        with self.assertRaises(CandidateStoreError) as error:
            self.save()
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.counts(), (0, 0))

    def test_missing_geometry_row_is_refused_before_binding(self):
        self.db.delete(self.geometry)
        self.db.commit()
        with self.assertRaises(CandidateStoreError) as error:
            self.save()
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.counts(), (0, 0))

    def test_caller_built_bound_mapping_cannot_be_used_as_original(self):
        from services.financial.pdf_geometry_candidates import bind_pdf_grid_mapping
        bound = bind_pdf_grid_mapping(self.db, case_id=self.case, proposal=self.mapping)
        with self.assertRaises(CandidateStoreError):
            self.save(proposal=bound)
