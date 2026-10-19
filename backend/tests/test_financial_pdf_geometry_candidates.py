import hashlib
import unittest
from copy import deepcopy
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder, EvidenceTableGeometry
from services.financial.pdf_candidates import PdfMappingError
from services.financial.pdf_geometry_candidates import bind_pdf_grid_mapping, pdf_grid_source_revision


def rectangle(y, x=20, width=40, height=10):
    return dict(kind="page_rectangle", page=1, rect=[v * 1000 for v in (x, y, x + width, y + height)],
                page_size=[600000, 800000], units="millipoints", space="pdf_displayed")


class GridBindingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__,
            EvidenceDocumentText.__table__, EvidenceTableGeometry.__table__])
        self.db = Session(self.engine)
        self.case, self.file, self.job = uuid4(), uuid4(), uuid4()
        # Deliberately not a row-major rendition of the table.
        content = "😀 GBP\n01/02 03/02\n1234 1234"
        self.location = dict(kind="page", page_number=1, start_char=0,
                             end_char=len(content), text_origin="digital_text_layer")
        self.text = EvidenceDocumentText(evidence_file_id=self.file, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            engine_job_id=self.job, source_locations=[self.location])
        self.evidence = EvidenceFile(id=self.file, case_id=self.case, sha256="a" * 64,
            original_filename="synthetic.pdf", stored_path="unused.pdf", size=0, status="processed")
        self.payload = [dict(table_source="drawn_geometry", geometry_source="cell_rectangles",
            table=dict(page=1, table=rectangle(0, x=0, width=200, height=200), unlocated_values=0,
                values=[dict(row=r, column=c, text=value, locator=rectangle(20 + r * 20, x=20+c*50))
                        for r in range(2) for c, value in enumerate(("01/02" if r == 0 else "03/02", "1234"))]))]
        self.geometry = EvidenceTableGeometry(evidence_file_id=self.file, page_number=1,
            engine_job_id=self.job, payload=deepcopy(self.payload))
        self.db.add_all([self.evidence, self.text, self.geometry])
        self.db.commit()
        self.mapping = dict(case_id=str(self.case), evidence_file_id=str(self.file),
            source_revision=self.revision(), page_number=1, table_index=0,
            columns=[dict(column_index=0, meaning="booking_date"), dict(column_index=1, meaning="amount")],
            rows=[dict(row_index=r, cells=[dict(column_index=c, expected_text=value)
                for c, value in enumerate(("01/02" if r == 0 else "03/02", "1234"))]) for r in range(2)])

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def revision(self):
        return pdf_grid_source_revision(self.db, case_id=self.case, evidence_file_id=self.file, page_number=1)

    def bind(self, mapping=None, case=None):
        return bind_pdf_grid_mapping(self.db, case_id=case or self.case,
                                     proposal=self.mapping if mapping is None else mapping)

    def update_geometry(self, payload):
        self.geometry.payload = payload
        self.db.commit()
        self.mapping["source_revision"] = self.revision()

    def test_same_amounts_retain_distinct_grid_positions_and_rectangles(self):
        result = self.bind()
        first, second = result.candidates
        self.assertNotEqual(first.candidate_key, second.candidate_key)
        self.assertEqual(first.cells[1].text, second.cells[1].text)
        self.assertNotEqual(first.cells[1].locator.rectangle.y0, second.cells[1].locator.rectangle.y0)
        self.assertEqual(first.cells[1].locator.to_json(), self.payload[0]["table"]["values"][1]["locator"])
        self.assertEqual(first.cells[1].origin.value, "digital_text_layer")
        self.assertEqual(first.status, "pending")
        self.assertNotIn("amount_minor", result.model_dump_json())
        self.assertNotIn("start_char", result.model_dump_json())
        self.assertFalse(result.applied or result.file_bytes_verified)
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)

    def test_roundtrip_and_retry_stable(self):
        result = self.bind()
        self.assertEqual(result, self.bind(result.proposal.model_dump(mode="json")))

    def test_mapping_semantics_change_revision(self):
        first = self.bind()
        self.mapping["columns"][1]["meaning"] = "balance"
        second = self.bind()
        self.assertNotEqual(first.mapping_revision, second.mapping_revision)
        self.assertNotEqual(first.candidates[0].candidate_key, second.candidates[0].candidate_key)

    def test_cross_case_and_relabelled_payload_refused(self):
        other = uuid4()
        for mapping in (self.mapping, {**self.mapping, "case_id": str(other)}):
            with self.assertRaises(PdfMappingError) as error:
                self.bind(mapping, case=other)
            self.assertEqual(error.exception.status_code, 404)

    def test_geometry_change_invalidates_unchanged_text(self):
        changed = deepcopy(self.payload)
        changed[0]["table"]["values"][1]["locator"]["rect"][0] += 1
        self.geometry.payload = changed
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_missing_or_different_extraction_job_refused(self):
        for job in (None, uuid4()):
            self.geometry.engine_job_id = job
            self.db.commit()
            with self.assertRaises(PdfMappingError):
                self.bind()

    def test_missing_text_job_refused_even_when_both_missing(self):
        self.geometry.engine_job_id = None
        self.text.engine_job_id = None
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_file_and_text_changes_refused(self):
        self.evidence.sha256 = "b" * 64
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()
        self.mapping["source_revision"] = self.revision()
        self.text.content += " changed"
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_wrong_cell_text_is_not_searched_elsewhere(self):
        self.mapping["rows"][0]["cells"][0]["expected_text"] = "03/02"
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_missing_table_or_row_refused(self):
        with self.assertRaises(PdfMappingError):
            self.bind({**self.mapping, "table_index": 1})
        self.mapping["rows"][1]["row_index"] = 9
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_malformed_and_duplicate_stored_coordinates_refused(self):
        for defect in (True, -1, "1", 1.0):
            payload = deepcopy(self.payload)
            payload[0]["table"]["values"][0]["row"] = defect
            self.update_geometry(payload)
            with self.assertRaises(PdfMappingError):
                self.bind()
        payload = deepcopy(self.payload)
        payload[0]["table"]["values"].append(payload[0]["table"]["values"][0])
        self.update_geometry(payload)
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_wrong_page_and_invalid_rectangles_refused(self):
        for update in ({"page": 2}, {"page": True}, {"rect": [-1, 20, 30, 40]},
                       {"page_size": [601, 800]}, {"units": "points"},
                       {"rect": [250000, 20000, 300000, 40000]}):
            payload = deepcopy(self.payload)
            payload[0]["table"]["values"][0]["locator"].update(update)
            self.update_geometry(payload)
            with self.subTest(update=update), self.assertRaises(PdfMappingError):
                self.bind()

    def test_unlocated_cell_remains_unlocated(self):
        payload = deepcopy(self.payload)
        payload[0]["table"]["values"][0]["locator"] = dict(kind="unlocated", page=1)
        payload[0]["table"]["unlocated_values"] = 1
        self.update_geometry(payload)
        self.assertIsNone(self.bind().candidates[0].cells[0].locator.rectangle)

    def test_overlapping_stored_cells_are_refused(self):
        payload = deepcopy(self.payload)
        payload[0]["table"]["values"][1]["locator"] = rectangle(20, x=30)
        self.update_geometry(payload)
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_geometry_source_cannot_contradict_cell_rectangles(self):
        payload = deepcopy(self.payload)
        payload[0]["geometry_source"] = "table_rectangle_only"
        self.update_geometry(payload)
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_geometry_without_cell_rectangles_does_not_invent_them(self):
        payload = deepcopy(self.payload)
        payload[0]["geometry_source"] = "table_rectangle_only"
        for cell in payload[0]["table"]["values"]:
            cell["locator"] = dict(kind="unlocated", page=1)
        payload[0]["table"]["unlocated_values"] = 4
        self.update_geometry(payload)
        result = self.bind()
        self.assertTrue(all(c.locator.rectangle is None for r in result.candidates for c in r.cells))

    def test_exact_stored_text_is_not_trimmed_or_parsed(self):
        payload = deepcopy(self.payload)
        payload[0]["table"]["values"][1]["text"] = " -0.00 "
        self.update_geometry(payload)
        self.mapping["rows"][0]["cells"][1]["expected_text"] = " -0.00 "
        self.assertEqual(self.bind().candidates[0].cells[1].text, " -0.00 ")

    def test_nonfinite_geometry_revision_is_actionable(self):
        payload = deepcopy(self.payload)
        payload[0]["table"]["values"][1]["locator"]["rect"][0] = float("nan")
        self.geometry.payload = payload
        self.db.commit()
        with self.assertRaises(PdfMappingError) as error:
            self.bind()
        self.assertEqual(error.exception.status_code, 409)

    def test_missing_malformed_overlapping_provenance_stays_unknown(self):
        for locations in ([], [None], [self.location, self.location],
                          [{**self.location, "end_char": True}],
                          [{**self.location, "text_origin": "future"}]):
            self.text.source_locations = locations
            self.db.commit()
            self.mapping["source_revision"] = self.revision()
            self.assertEqual(self.bind().candidates[0].cells[1].origin.value, "unknown")

    def test_recognised_origin_is_retained_and_drift_refused(self):
        self.text.source_locations = [{**self.location, "text_origin": "recognised_glyphs"}]
        self.db.commit()
        with self.assertRaises(PdfMappingError):
            self.bind()
        self.mapping["source_revision"] = self.revision()
        self.assertEqual(self.bind().candidates[0].cells[1].origin.value, "recognised_glyphs")

    def test_source_backed_context_and_unknown_columns(self):
        self.mapping["context"] = dict(currency=dict(start_char=2, end_char=5, text="GBP"))
        self.mapping["columns"][1]["meaning"] = "unknown"
        self.assertEqual(self.bind().candidates[0].status, "pending")
        self.mapping["context"]["currency"]["text"] = "USD"
        with self.assertRaises(PdfMappingError):
            self.bind()

    def test_caller_cannot_supply_origin_rectangle_or_admission(self):
        for key, value in (("origin", "digital_text_layer"), ("locator", rectangle(10)),
                           ("status", "resolved"), ("amount_minor", 0), ("proof_class", "p0")):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.bind({**self.mapping, key: value})

    def test_strict_unique_ordered_mapping(self):
        for page in (True, 1.0, "1", 0):
            with self.assertRaises(ValidationError):
                self.bind({**self.mapping, "page_number": page})
        self.mapping["rows"].reverse()
        with self.assertRaises(ValidationError):
            self.bind()

    def test_nested_originals_are_immutable(self):
        result = self.bind()
        with self.assertRaises((AttributeError, ValidationError)):
            result.candidates[0].cells[0].locator.rectangle.x0 = 99
        self.payload[0]["table"]["values"][0]["text"] = "changed"
        self.assertEqual(result.candidates[0].cells[0].text, "01/02")

    def test_generated_pdf_extraction_binds_the_actual_stored_cells(self):
        import fitz
        from services.financial.pdf_tables import read_tables
        with fitz.open() as document:
            page = document.new_page(width=600, height=800)
            for x in (50, 200, 350):
                page.draw_line((x, 50), (x, 130))
            for y in (50, 90, 130):
                page.draw_line((50, y), (350, y))
            for row, date in enumerate(("01/02", "03/02")):
                page.insert_text((60, 75 + row * 40), date)
                page.insert_text((210, 75 + row * 40), "1234")
            extracted = read_tables(page, 1)
            self.assertEqual(len(extracted), 1)
            self.evidence.sha256 = hashlib.sha256(document.tobytes()).hexdigest()
            self.text.content = page.get_text()
            self.text.content_sha256 = hashlib.sha256(self.text.content.encode()).hexdigest()
            self.text.character_count = len(self.text.content)
            self.text.source_locations = [{**self.location, "end_char": len(self.text.content)}]
            self.update_geometry([table.to_json() for table in extracted])
        result = self.bind()
        self.assertEqual(result.table_source.value, "drawn_geometry")
        first, second = result.candidates
        self.assertEqual(first.cells[1].locator.rectangle.y0, 50000)
        self.assertEqual(second.cells[1].locator.rectangle.y0, 90000)
        self.assertEqual(first.cells[1].text, "1234")
