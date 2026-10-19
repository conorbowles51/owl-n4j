import unittest
from copy import deepcopy
from uuid import UUID, uuid4
from unittest.mock import patch

from sqlalchemy import select, update

from postgres.models.financial_candidates import FinancialExtractionCandidate
from services.financial.candidate_assessment import assess_candidate_amounts
from services.financial.candidate_store import CandidateStoreError
from services.financial.pdf_candidates import _digest, pdf_mapping_source_revision
from tests import test_financial_candidate_store as store_fixture


class CandidateAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = store_fixture.CandidateStoreTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def save(self, raw="1234", origin="digital_text_layer", meaning="amount"):
        f = self.fixture
        payload = deepcopy(f.geometry.payload)
        payload[0]["table"]["values"][1]["text"] = raw
        f.geometry.payload = payload
        f.text.source_locations = [{**f.location, "text_origin": origin}]
        f.db.commit()
        f.mapping["rows"][0]["cells"][1]["expected_text"] = raw
        f.mapping["columns"][1]["meaning"] = meaning
        f.mapping["source_revision"] = f.revision()
        saved = f.save()
        self.candidate_id = UUID(saved["candidates"][0]["id"])
        return saved

    def assess(self, **updates):
        f = self.fixture
        params = dict(case_id=f.case, candidate_id=self.candidate_id, currency="GBP")
        params.update(updates)
        return assess_candidate_amounts(f.db, **params)

    def test_digital_reading_does_not_resolve_or_admit_candidate(self):
        self.save()
        result = self.assess()
        cell = result["amount_cells"][0]
        self.assertEqual(cell["assessment"]["minor_units"], "123400")
        self.assertEqual(cell["source"]["text"], "1234")
        self.assertEqual(cell["source"]["locator"]["rect"], [70000, 20000, 110000, 30000])
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["applied"])
        self.assertFalse(self.fixture.db.dirty or self.fixture.db.new)
        self.assertEqual(self.fixture.counts(), (1, 2))

    def test_recognised_amount_retains_all_alternatives_as_exact_strings(self):
        self.save(origin="recognised_glyphs")
        reading = self.assess()["amount_cells"][0]["assessment"]
        self.assertNotIn("minor_units", reading)
        self.assertEqual({p["minor_units"] for p in reading["proposals"]}, {"1234", "123400"})
        self.assertEqual(reading["origin"], "recognised_glyphs")

    def test_unknown_origin_is_not_promoted_to_digital(self):
        self.save(origin="unknown")
        reading = self.assess()["amount_cells"][0]["assessment"]
        self.assertEqual(reading["origin"], "unknown")
        self.assertNotIn("minor_units", reading)

    def test_large_amount_zero_and_sign_are_exact(self):
        for raw, expected in (("9007199254740993.01", "900719925474099301"), ("0.00", "0"), ("-12.34", "-1234")):
            with self.subTest(raw=raw):
                self.save(raw=raw)
                self.assertEqual(self.assess()["amount_cells"][0]["assessment"]["minor_units"], expected)

    def test_unreadable_value_is_kept_without_placeholder_zero(self):
        self.save(raw="not legible")
        cell = self.assess()["amount_cells"][0]
        self.assertEqual(cell["source"]["text"], "not legible")
        self.assertTrue(cell["error"] or cell["assessment"].get("suspicion") != "none")
        self.assertNotIn("minor_units", cell["assessment"] or {})

    def test_unknown_columns_are_not_automatically_treated_as_amounts(self):
        self.save(meaning="unknown")
        result = self.assess()
        self.assertEqual(result["amount_cells"], [])
        self.assertEqual(result["unclassified_columns"], [1])

    def test_balance_is_labelled_separately_from_transaction_amount(self):
        self.save(meaning="balance")
        self.assertEqual(self.assess()["amount_cells"][0]["proposed_meaning"], "balance")

    def test_currency_is_explicit_context_and_changes_assessment_revision(self):
        self.save()
        first, second = self.assess(), self.assess(currency="USD")
        self.assertEqual(first["currency_source"], "caller_supplied")
        self.assertNotEqual(first["assessment_revision"], second["assessment_revision"])
        self.assertEqual(first, self.assess())

    def test_unsupported_currency_is_refused(self):
        self.save()
        for currency in (None, "XYZ", True, 123):
            with self.assertRaises(CandidateStoreError) as error:
                self.assess(currency=currency)
            self.assertEqual(error.exception.status_code, 422)

    def test_cross_case_and_unknown_candidate_refused(self):
        self.save()
        for params in ({"case_id": uuid4()}, {"candidate_id": uuid4()}):
            with self.assertRaises(CandidateStoreError) as error:
                self.assess(**params)
            self.assertEqual(error.exception.status_code, 404)

    def test_source_or_provenance_drift_refuses_old_assessment(self):
        self.save()
        self.fixture.text.source_locations = []
        self.fixture.db.commit()
        with self.assertRaises(CandidateStoreError) as error:
            self.assess()
        self.assertEqual(error.exception.status_code, 409)

    def test_geometry_drift_refuses_old_assessment(self):
        self.save()
        f = self.fixture
        payload = deepcopy(f.geometry.payload)
        payload[0]["table"]["values"][1]["locator"]["rect"][0] += 1
        f.geometry.payload = payload
        f.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.assess()

    def test_rehashed_corrupt_original_is_refused_by_source_rebinding(self):
        self.save()
        f = self.fixture
        row = f.db.scalar(select(FinancialExtractionCandidate).where(FinancialExtractionCandidate.id == self.candidate_id))
        forged = deepcopy(row.snapshot)
        forged["cells"][1]["text"] = "9999"
        f.db.execute(update(FinancialExtractionCandidate).where(FinancialExtractionCandidate.id == row.id)
                     .values(snapshot=forged, snapshot_sha256=_digest(forged)))
        f.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.assess()

    def test_canonical_candidate_is_assessed_at_its_original_span(self):
        f = self.fixture
        position = f.text.content.index("1234")
        proposal = dict(case_id=str(f.case), evidence_file_id=str(f.file),
            source_revision=pdf_mapping_source_revision(f.db, case_id=f.case, evidence_file_id=f.file),
            table_id=str(uuid4()), start_char=position, end_char=position+4,
            columns=[dict(column_index=0, meaning="amount")], rows=[dict(row_index=0,
                cells=[dict(column_index=0, source=dict(start_char=position, end_char=position+4, text="1234"))])])
        saved = f.save(proposal=proposal)
        self.candidate_id = UUID(saved["candidates"][0]["id"])
        source = self.assess()["amount_cells"][0]["source"]
        self.assertEqual(source["start_char"], position)
        self.assertEqual(source["end_char"], position+4)
        self.assertNotIn("locator", source)


    def test_source_context_is_limited_to_saved_row_and_rechecks_revision(self):
        from services.financial.candidate_assessment import candidate_source_readings
        saved=self.save();f=self.fixture
        source={'source_revision':saved['original']['proposal']['source_revision'],
                'layout_context':{'version':1,'rows':[{'row_index':0},{'row_index':1}]}}
        with patch('services.financial.candidate_sources.read_candidate_source',return_value=source):
            result=candidate_source_readings(f.db,case_id=f.case,candidate_id=self.candidate_id)
            self.assertEqual(result['layout_context']['rows'],[{'row_index':0}])
            self.assertFalse(result['applied'])
        source['source_revision']='f'*64
        with patch('services.financial.candidate_sources.read_candidate_source',return_value=source):
            with self.assertRaises(CandidateStoreError) as caught:
                candidate_source_readings(f.db,case_id=f.case,candidate_id=self.candidate_id)
            self.assertEqual(caught.exception.status_code,409)


class CandidateAssessmentRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_case_and_currency_are_forwarded_under_read_permission(self):
        from routers import financial_ledger as router
        case, candidate = uuid4(), uuid4()
        with patch.object(router, "assess_candidate_amounts", return_value={"applied": False}) as call:
            result = await router.assess_saved_candidate(candidate, router.CandidateAmountAssessmentRequest(currency="GBP"), case, "db")
        call.assert_called_once_with("db", case_id=case, candidate_id=candidate, currency="GBP")
        self.assertFalse(result["applied"])
        self.assertEqual(router._ledger_case_permission(None, {}), ("case", "view"))

    async def test_mapping_route_scopes_read(self):
        from routers import financial_ledger as router
        case, mapping = uuid4(), uuid4()
        with patch.object(router, "read_candidate_mapping", return_value={}) as call:
            await router.get_candidate_mapping(mapping, case, "db")
        call.assert_called_once_with("db", case_id=case, mapping_id=mapping)

    async def test_stale_source_status_is_preserved(self):
        from fastapi import HTTPException
        from routers import financial_ledger as router
        with patch.object(router, "assess_candidate_amounts", side_effect=CandidateStoreError("Reload", 409)):
            with self.assertRaises(HTTPException) as error:
                await router.assess_saved_candidate(uuid4(), router.CandidateAmountAssessmentRequest(currency="GBP"), uuid4(), "db")
        self.assertEqual(error.exception.status_code, 409)

    async def test_unexpected_errors_do_not_disclose_database_details(self):
        from fastapi import HTTPException
        from routers import financial_ledger as router
        with patch.object(router, "read_candidate_mapping", side_effect=RuntimeError("private database detail")):
            with self.assertRaises(HTTPException) as error:
                await router.get_candidate_mapping(uuid4(), uuid4(), "db")
        self.assertEqual(error.exception.status_code, 500)
        self.assertNotIn("private", error.exception.detail)

    def test_body_cannot_supply_raw_text_origin_or_admission(self):
        from pydantic import ValidationError
        from routers import financial_ledger as router
        for extra in ({"origin": "digital_text_layer"}, {"raw": "0"}, {"applied": True}):
            with self.assertRaises(ValidationError):
                router.CandidateAmountAssessmentRequest(currency="GBP", **extra)
