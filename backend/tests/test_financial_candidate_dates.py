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

    def test_wrong_case_and_changed_source_refused(self):
        self.f.save(meaning="booking_date")
        with self.assertRaises(CandidateStoreError) as error:
            self.assess(case_id=uuid4())
        self.assertEqual(error.exception.status_code, 404)
        self.f.fixture.geometry.payload=[]
        self.f.fixture.db.commit()
        with self.assertRaises(CandidateStoreError): self.assess()


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
