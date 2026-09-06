import hashlib
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder
from services.financial.amount_assessment import AmountAssessmentError, assess_source_amount
from routers import financial_ledger


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__, EvidenceDocumentText.__table__])
        self.db = Session(self.engine)
        self.case, self.file = uuid4(), uuid4()
        self.content = "😀 Amount 1234 end"
        self.digest = hashlib.sha256(self.content.encode()).hexdigest()
        self.location = {"kind": "page", "page_number": 1, "start_char": 0,
                         "end_char": len(self.content), "text_origin": "recognised_glyphs"}
        self.source = EvidenceDocumentText(evidence_file_id=self.file, content=self.content,
            content_sha256=self.digest, character_count=len(self.content), source_locations=[self.location])
        self.db.add(EvidenceFile(id=self.file, case_id=self.case, original_filename="synthetic.pdf",
            stored_path="/tmp/loupe-neilbyrne-synthetic.pdf", sha256="a" * 64, size=0, status="processed"))
        self.db.add(self.source)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def assess(self, **overrides):
        params = dict(case_id=self.case, evidence_file_id=self.file, start_char=9, end_char=13,
                      expected_text="1234", content_sha256=self.digest, currency="USD")
        params.update(overrides)
        return assess_source_amount(self.db, **params)

    def test_recognised_text_proposes_exact_strings_without_a_settled_amount(self):
        answer = self.assess()
        self.assertEqual(answer["assessment"]["origin"], "recognised_glyphs")
        self.assertNotIn("minor_units", answer["assessment"])
        self.assertEqual({p["minor_units"] for p in answer["assessment"]["proposals"]}, {"1234", "123400"})
        self.assertFalse(answer["applied"])
        self.assertEqual(answer["offset_unit"], "unicode_code_points")
        self.assertEqual(answer["currency_source"], "caller_supplied")
        self.assertEqual(self.source.content, self.content)
        self.assertFalse(self.db.dirty)

    def test_measured_digital_text_is_parsed_without_ocr_suspicion(self):
        self.source.source_locations = [{**self.location, "text_origin": "digital_text_layer"}]
        self.db.commit()
        self.assertEqual(self.assess()["assessment"]["minor_units"], "123400")

    def test_missing_unknown_and_overlapping_provenance_stay_unknown(self):
        for locations in ([], [{}], [{**self.location, "text_origin": "new_origin"}],
                          [self.location, self.location], [None],
                          [{**self.location, "end_char": 11}]):
            with self.subTest(locations=locations):
                self.source.source_locations = locations
                self.db.commit()
                result = self.assess()["assessment"]
                self.assertEqual(result["origin"], "unknown")
                self.assertNotIn("minor_units", result)

    def test_wrong_case_does_not_disclose_source(self):
        with self.assertRaises(AmountAssessmentError) as ctx:
            self.assess(case_id=uuid4())
        self.assertEqual(ctx.exception.status_code, 404)

    def test_stale_digest_and_mismatched_offsets_are_refused(self):
        for overrides in ({"content_sha256": "b" * 64}, {"expected_text": "1235"},
                          {"start_char": 10, "end_char": 14}, {"end_char": 90}):
            with self.subTest(overrides=overrides), self.assertRaises(AmountAssessmentError) as ctx:
                self.assess(**overrides)
            self.assertEqual(ctx.exception.status_code, 409)

    def test_corrupt_stored_digest_is_refused(self):
        self.source.content_sha256 = "b" * 64
        self.db.commit()
        with self.assertRaises(AmountAssessmentError) as ctx:
            self.assess(content_sha256="b" * 64)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_invalid_ranges_and_currency_are_actionable(self):
        for overrides in ({"start_char": True}, {"start_char": -1}, {"end_char": 200},
                          {"end_char": 9}, {"currency": "XYZ"}):
            with self.subTest(overrides=overrides), self.assertRaises(AmountAssessmentError) as ctx:
                self.assess(**overrides)
            self.assertEqual(ctx.exception.status_code, 422)


class AssessmentRouterTests(unittest.IsolatedAsyncioTestCase):
    def body(self, **extra):
        return financial_ledger.AmountAssessmentRequest(start_char=0, end_char=4,
            expected_text="1234", content_sha256="a" * 64, currency="USD", **extra)

    def test_caller_cannot_supply_origin_or_admission(self):
        for extra in ({"origin": "digital_text_layer"}, {"applied": True}):
            with self.assertRaises(ValidationError):
                self.body(**extra)
        self.assertEqual(financial_ledger._ledger_case_permission(None, {}), ("case", "view"))

    async def test_case_and_validated_selection_are_forwarded(self):
        case, file = uuid4(), uuid4()
        body = self.body()
        with patch.object(financial_ledger, "assess_source_amount", return_value={"applied": False}) as call:
            result = await financial_ledger.assess_evidence_amount(file, body, case, "session")
        call.assert_called_once_with("session", case_id=case, evidence_file_id=file, **body.model_dump())
        self.assertFalse(result["applied"])

    async def test_refusal_status_is_preserved(self):
        with patch.object(financial_ledger, "assess_source_amount", side_effect=AmountAssessmentError("Reload", 409)):
            with self.assertRaises(HTTPException) as ctx:
                await financial_ledger.assess_evidence_amount(uuid4(), self.body(), uuid4(), "session")
        self.assertEqual(ctx.exception.status_code, 409)
