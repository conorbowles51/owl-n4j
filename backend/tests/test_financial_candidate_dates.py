import unittest
from uuid import uuid4
from unittest.mock import patch
from services.financial.candidate_assessment import assess_candidate_dates
from services.financial.candidate_store import CandidateStoreError
from tests import test_financial_candidate_assessment as fixture


class CandidateDateTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CandidateAssessmentTests()
        self.f.setUp()
    def tearDown(self):
        self.f.tearDown()
    def assess(self, **updates):
        fixture = self.f.fixture
        return assess_candidate_dates(fixture.db, **{**dict(case_id=fixture.case, candidate_id=self.f.candidate_id), **updates})

    def test_date_role_source_and_no_write_are_preserved(self):
        self.f.save(raw="01/02/2026", meaning="value_date")
        result = self.assess()
        cell = next(c for c in result["date_cells"] if c["proposed_meaning"] == "value_date")
        self.assertEqual(cell["source"]["text"], "01/02/2026")
        self.assertEqual(cell["assessment"]["status"], "ambiguous_order")
        self.assertIn("locator", cell["source"])
        self.assertFalse(result["applied"])
        self.assertFalse(self.f.fixture.db.new or self.f.fixture.db.dirty)
        self.assertEqual(result, self.assess())

    def test_unknown_column_not_interpreted_and_missing_year_retained(self):
        self.f.save(raw="01/02/2026", meaning="unknown")
        result = self.assess()
        self.assertIn(1, result["unclassified_columns"])
        self.assertTrue(all(c["column_index"] != 1 for c in result["date_cells"]))
        self.assertEqual(result["date_cells"][0]["assessment"]["status"], "missing_year")

    def test_transaction_date_role_survives_grid_binding_and_assessment(self):
        self.f.save(raw="2026-02-01", meaning="transaction_date")
        cell = next(c for c in self.assess()["date_cells"] if c["column_index"] == 1)
        self.assertEqual(cell["proposed_meaning"], "transaction_date")
        self.assertEqual(cell["assessment"]["proposals"][0]["iso_date"], "2026-02-01")

    def test_transaction_date_role_survives_canonical_text_binding(self):
        from services.financial.pdf_candidates import pdf_mapping_source_revision
        from uuid import UUID
        f = self.f.fixture
        text = "01/02"
        position = f.text.content.index(text)
        saved = f.save(proposal=dict(case_id=str(f.case), evidence_file_id=str(f.file),
            source_revision=pdf_mapping_source_revision(f.db, case_id=f.case, evidence_file_id=f.file),
            table_id=str(uuid4()), start_char=position, end_char=position+len(text),
            columns=[dict(column_index=0, meaning="transaction_date")], rows=[dict(row_index=0,
                cells=[dict(column_index=0, source=dict(start_char=position, end_char=position+len(text), text=text))])]))
        self.f.candidate_id = UUID(saved["candidates"][0]["id"])
        cell = self.assess()["date_cells"][0]
        self.assertEqual(cell["proposed_meaning"], "transaction_date")
        self.assertEqual(cell["source"]["start_char"], position)
        self.assertEqual(cell["assessment"]["status"], "missing_year")

    def test_named_month_keeps_original_source_and_requires_review(self):
        self.f.save(raw="7 September 2026", meaning="transaction_date")
        cell = next(c for c in self.assess()["date_cells"] if c["column_index"] == 1)
        self.assertEqual(cell["source"]["text"], "7 September 2026")
        self.assertEqual(cell["assessment"]["proposals"][0]["iso_date"], "2026-09-07")
        self.assertTrue(cell["assessment"]["requires_source_review"])
        self.assertFalse(self.f.fixture.db.new or self.f.fixture.db.dirty)

    def test_wrong_case_and_changed_source_refused(self):
        self.f.save(meaning="booking_date")
        with self.assertRaises(CandidateStoreError) as error:
            self.assess(case_id=uuid4())
        self.assertEqual(error.exception.status_code, 404)
        self.f.fixture.geometry.payload=[]
        self.f.fixture.db.commit()
        with self.assertRaises(CandidateStoreError): self.assess()

    def test_generic_date_is_assessed_without_assigning_a_transaction_role(self):
        self.f.save(raw="01/02/2026", meaning="date")
        result=self.assess()
        cell=next(c for c in result['date_cells'] if c['column_index']==1)
        self.assertEqual(cell['proposed_meaning'],'date')
        self.assertEqual(cell['assessment']['status'],'ambiguous_order')
        self.assertEqual({p['iso_date'] for p in cell['assessment']['proposals']},{'2026-01-02','2026-02-01'})
        self.assertFalse(result['applied'])
        self.assertNotIn('reading',result)
        self.assertFalse(self.f.fixture.db.new or self.f.fixture.db.dirty)


class CandidateDateRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_scope_and_errors(self):
        from routers import financial_ledger as router
        from fastapi import HTTPException
        case, candidate = uuid4(), uuid4()
        with patch.object(router, "assess_candidate_dates", return_value={"applied": False}) as call:
            self.assertFalse((await router.assess_saved_candidate_dates(candidate, case, "db"))["applied"])
            call.assert_called_once_with("db", case_id=case, candidate_id=candidate)
        for error, status in ((CandidateStoreError("Reload",409),409),(RuntimeError("private detail"),500)):
            with patch.object(router, "assess_candidate_dates", side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    await router.assess_saved_candidate_dates(candidate, case, "db")
                self.assertEqual(caught.exception.status_code,status)
                self.assertNotIn("private",caught.exception.detail)
