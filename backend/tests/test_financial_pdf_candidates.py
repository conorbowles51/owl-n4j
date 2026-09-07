"""Binding is about exact occurrence and revision, never plausible numbers."""
import hashlib
import json
import unittest
from copy import deepcopy
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder
from services.financial.pdf_candidates import (
    PdfMappingError, PdfMappingProposal, bind_pdf_mapping, pdf_mapping_source_revision,
)


class PdfCandidateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[EvidenceFolder.__table__,
            EvidenceFile.__table__, EvidenceDocumentText.__table__])
        self.db = Session(self.engine)
        self.case, self.file = uuid4(), uuid4()
        self.content = "😀 Account XX12 GBP\nDate Amount\n01/02 1234\n03/02 1234"
        self.location = dict(kind="page", page_number=1, start_char=0,
                             end_char=len(self.content), text_origin="digital_text_layer")
        self.source = EvidenceDocumentText(evidence_file_id=self.file, content=self.content,
            content_sha256=hashlib.sha256(self.content.encode()).hexdigest(),
            character_count=len(self.content), source_locations=[self.location])
        self.evidence = EvidenceFile(id=self.file, case_id=self.case,
            original_filename="synthetic.pdf", stored_path="unused.pdf", sha256="a" * 64,
            size=0, status="processed")
        self.db.add_all([self.evidence, self.source])
        self.db.commit()
        self.mapping = dict(case_id=str(self.case), evidence_file_id=str(self.file),
            source_revision=self.revision(), table_id=str(uuid4()),
            start_char=self.content.index("Date"), end_char=len(self.content),
            columns=[dict(column_index=0, meaning="booking_date", header=self.span("Date")),
                     dict(column_index=1, meaning="amount", header=self.span("Amount"))],
            rows=[dict(row_index=i, cells=[dict(column_index=0, source=self.span(date)),
                dict(column_index=1, source=self.span("1234", last=i == 1))])
                for i, date in enumerate(("01/02", "03/02"))],
            context=dict(account=self.span("XX12"), currency=self.span("GBP")))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def span(self, text, last=False):
        start = self.content.rindex(text) if last else self.content.index(text)
        return dict(start_char=start, end_char=start + len(text), text=text)

    def revision(self):
        return pdf_mapping_source_revision(self.db, case_id=self.case, evidence_file_id=self.file)

    def bind(self, mapping=None, case=None):
        return bind_pdf_mapping(self.db, case_id=case or self.case,
                                proposal=self.mapping if mapping is None else mapping)

    def test_exact_occurrences_survive_without_becoming_ledger_values(self):
        result = self.bind()
        first, second = result.candidates
        self.assertNotEqual(first.candidate_key, second.candidate_key)
        self.assertEqual(first.cells[1].source.text, second.cells[1].source.text)
        self.assertNotEqual(first.cells[1].source.start_char, second.cells[1].source.start_char)
        self.assertEqual(first.cells[1].origin.value, "digital_text_layer")
        self.assertEqual(first.cells[1].page_number, 1)
        self.assertEqual(first.status, "pending")
        self.assertNotIn("amount_minor", result.model_dump_json())
        self.assertFalse(result.applied)
        self.assertFalse(result.file_bytes_verified)
        self.assertFalse(self.db.dirty or self.db.new or self.db.deleted)

    def test_round_trip_and_retry_are_stable(self):
        first = self.bind()
        self.assertEqual(first, self.bind(json.loads(first.proposal.model_dump_json())))

    def test_raw_zero_sign_currency_and_unreadable_values_are_not_normalized(self):
        for raw in ("0.00", "-123", "£123", "12?4", " 123", "1,23"):
            with self.subTest(raw=raw):
                self.source.content = self.content.replace("1234", raw)
                self.source.content_sha256 = hashlib.sha256(self.source.content.encode()).hexdigest()
                self.db.commit()
                mapping = deepcopy(self.mapping)
                mapping["source_revision"] = self.revision()
                for row in mapping["rows"]:
                    row["cells"][1]["source"]["text"] = raw
                result = self.bind(mapping)
                self.assertEqual(result.candidates[0].cells[1].source.text, raw)
                self.assertEqual(result.candidates[0].status, "pending")

    def test_interleaved_rows_are_not_accepted_as_source_order(self):
        first, second = self.mapping["rows"]
        first["cells"][1]["source"], second["cells"][1]["source"] = (
            second["cells"][1]["source"], first["cells"][1]["source"])
        with self.assertRaises(ValidationError):
            self.bind()

    def test_revalidated_model_copy_cannot_bypass_checks(self):
        model = PdfMappingProposal.model_validate(self.mapping)
        invalid = model.model_copy(update={"end_char": 0})
        with self.assertRaises(ValidationError):
            self.bind(invalid)

    def test_mapping_revision_changes_with_semantics_and_context(self):
        first = self.bind()
        for change in ("meaning", "context"):
            mapping = deepcopy(self.mapping)
            if change == "meaning":
                mapping["columns"][1]["meaning"] = "balance"
            else:
                mapping["context"] = {}
            new = self.bind(mapping)
            self.assertNotEqual(first.mapping_revision, new.mapping_revision)
            self.assertNotEqual(first.candidates[0].candidate_key, new.candidates[0].candidate_key)

    def test_missing_fields_and_ambiguous_columns_stay_pending(self):
        self.mapping["context"] = {}
        for column in self.mapping["columns"]:
            column["meaning"] = "unknown"
        result = self.bind()
        self.assertIsNone(result.proposal.context.account)
        self.assertIsNone(result.proposal.context.direction_convention)
        self.assertEqual(result.candidates[0].cells[0].source.text, "01/02")
        self.assertTrue(all(c.status == "pending" for c in result.candidates))

    def test_cross_case_refused_even_if_payload_is_relabelled(self):
        other = uuid4()
        for mapping in (self.mapping, {**self.mapping, "case_id": str(other)}):
            with self.assertRaises(PdfMappingError) as error:
                self.bind(mapping, case=other)
            self.assertEqual(error.exception.status_code, 404)

    def test_recorded_file_digest_drift_refused(self):
        self.evidence.sha256 = "b" * 64
        self.db.commit()
        with self.assertRaises(PdfMappingError) as error:
            self.bind()
        self.assertEqual(error.exception.status_code, 409)

    def test_missing_recorded_file_digest_refused(self):
        self.evidence.sha256 = ""
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_text_drift_and_corrupt_stored_digest_refused(self):
        self.source.content += " changed"
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()
        self.source.content_sha256 = hashlib.sha256(self.source.content.encode()).hexdigest()
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_provenance_drift_invalidates_unchanged_text(self):
        self.source.source_locations = [{**self.location, "text_origin": "recognised_glyphs"}]
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()
        self.mapping["source_revision"] = self.revision()
        self.assertEqual(self.bind().candidates[0].cells[1].origin.value, "recognised_glyphs")

    def test_extraction_job_change_invalidates_mapping(self):
        self.source.engine_job_id = uuid4()
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_unknown_or_overlapping_pages_do_not_acquire_digital_provenance(self):
        for locations in ([], [None], [self.location, self.location],
                          [{**self.location, "page_number": True}],
                          [{**self.location, "text_origin": "invalid"}]):
            with self.subTest(locations=locations):
                self.source.source_locations = locations
                self.db.commit()
                self.mapping["source_revision"] = self.revision()
                self.assertEqual(self.bind().candidates[0].cells[1].origin.value, "unknown")

    def test_cell_header_and_context_text_must_match(self):
        for path in ("cell", "header", "context"):
            mapping = deepcopy(self.mapping)
            span = (mapping["rows"][0]["cells"][1]["source"] if path == "cell" else
                    mapping["columns"][1]["header"] if path == "header" else mapping["context"]["account"])
            span["text"] = "X" * len(span["text"])
            with self.subTest(path=path), self.assertRaises(PdfMappingError):
                self.bind(mapping)

    def test_unicode_offsets_are_not_utf16_offsets(self):
        span = self.mapping["rows"][0]["cells"][1]["source"]
        span["start_char"] += 1
        span["end_char"] += 1
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_duplicate_rows_columns_cells_and_overlaps_refused(self):
        for defect in ("row", "column", "cell", "overlap", "undeclared", "order", "region"):
            mapping = deepcopy(self.mapping)
            if defect == "row":
                mapping["rows"][1]["row_index"] = 0
            elif defect == "column":
                mapping["columns"].append(mapping["columns"][0])
            elif defect == "cell":
                mapping["rows"][0]["cells"].append(mapping["rows"][0]["cells"][0])
            elif defect == "overlap":
                mapping["rows"][1]["cells"][1]["source"] = mapping["rows"][0]["cells"][1]["source"]
            elif defect == "undeclared":
                mapping["rows"][0]["cells"][1]["column_index"] = 5
            elif defect == "order":
                mapping["rows"].reverse()
            else:
                mapping["start_char"] = len(self.content) - 4
            with self.subTest(defect=defect), self.assertRaises(ValidationError):
                self.bind(mapping)

    def test_strict_offsets_and_forbidden_admission_fields(self):
        for value in (True, 1.0, "1", -1):
            mapping = deepcopy(self.mapping)
            mapping["rows"][0]["cells"][0]["source"]["start_char"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.bind(mapping)
        for key, value in (("proof_class", "p0"), ("status", "resolved"), ("amount_minor", 0)):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.bind({**self.mapping, key: value})
        self.mapping["rows"][0]["cells"][1]["origin"] = "digital_text_layer"
        with self.assertRaises(ValidationError):
            self.bind()

    def test_immutable_original_snapshot(self):
        result = self.bind()
        with self.assertRaises(ValidationError):
            result.candidates[0].cells[1].source.text = "9999"
        self.mapping["rows"][0]["cells"][1]["source"]["text"] = "9999"
        self.assertEqual(result.candidates[0].cells[1].source.text, "1234")

    def test_nonempty_and_bounded_contract(self):
        for updates in ({"rows": []}, {"columns": []}, {"rows": self.mapping["rows"] * 501}):
            with self.assertRaises(ValidationError):
                PdfMappingProposal.model_validate({**self.mapping, **updates})

    def test_package_surface(self):
        import services.financial as package
        for name in ("PdfMappingProposal", "PdfPendingCandidate", "bind_pdf_mapping", "pdf_mapping_source_revision"):
            self.assertIn(name, package.__all__)
            self.assertTrue(hasattr(package, name))
