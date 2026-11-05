"""A document's text by page, its reader, and a passage kept as a citation (lx-textbench items A, C, D)."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder
from services import evidence_page_text as P


def page(number, start, end, **extra):
    return dict(kind="page", label=f"Page {number}", page_number=number, start_char=start, end_char=end, **extra)


NATIVE = dict(extraction_method="native", text_origin="digital_text_layer")
OCR = dict(extraction_method="tesseract_ocr", text_origin="recognised_glyphs", ocr_status="success", ocr_confidence=71.5,
           ocr_low_confidence=True)


class Base_(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__,
                                                      EvidenceDocumentText.__table__])
        self.db = sessionmaker(bind=self.engine, future=True)()
        self.case_id = uuid4()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def file(self, name="s.pdf", content=None, locations=(), status="processed", case_id=None, version="b" * 64, **fields):
        record = EvidenceFile(id=uuid4(), case_id=case_id or self.case_id, original_filename=name,
                              stored_path=f"/tmp/{name}", size=1, sha256="a" * 64, status=status, **fields)
        self.db.add(record)
        if content is not None:
            self.db.add(EvidenceDocumentText(evidence_file_id=record.id, content=content, content_sha256=version,
                                             character_count=len(content), source_locations=list(locations)))
        self.db.commit()
        return record

    def pages(self, record, offset=0, limit=5, path=None):
        return P.document_pages(self.db, record, path=path, page_offset=offset, page_limit=limit)


class Pages(Base_):
    TEXT = "Page one words\n\nSecond page\n\nThird page"

    def locations(self):
        return [page(1, 0, 14, **NATIVE), page(2, 16, 27, **OCR),
                page(3, 29, 29, extraction_method="tesseract_ocr", ocr_status="no_text"), page(4, 29, 39, **NATIVE)]

    def test_a_window_holds_its_pages_with_the_whole_documents_count(self):
        out = self.pages(self.file(content=self.TEXT, locations=self.locations()), offset=1, limit=1)
        self.assertEqual(out["page_count"], 4)
        self.assertTrue(out["has_more"])
        self.assertEqual([p["page_number"] for p in out["pages"]], [2])
        self.assertEqual(out["pages"][0]["text"], "Second page")
        self.assertEqual(out["text_version"], "b" * 64)

    def test_each_page_names_its_reader_and_confidence(self):
        pages = self.pages(self.file(content=self.TEXT, locations=self.locations()))["pages"]
        self.assertEqual(pages[0]["reader"]["kind"], "text_layer")
        self.assertFalse(pages[0]["reader"]["machine_read"])
        self.assertEqual(pages[1]["reader"]["kind"], "ocr")
        self.assertTrue(pages[1]["reader"]["machine_read"])
        self.assertEqual(pages[1]["reader"]["confidence"], 71.5)
        self.assertTrue(pages[1]["reader"]["low_confidence"])

    def test_a_page_with_no_text_says_why_never_blank(self):
        pages = self.pages(self.file(content=self.TEXT, locations=self.locations()))["pages"]
        self.assertIn("found no text", pages[2]["text_missing"])
        self.assertIsNone(pages[0]["text_missing"])

    def test_an_ocr_timeout_says_so(self):
        record = self.file(content="", locations=[page(1, 0, 0, ocr_status="timeout", text_origin="unread")])
        self.assertIn("ran out of time", self.pages(record)["pages"][0]["text_missing"])

    def test_a_failed_page_image_reading_is_said_on_the_page(self):
        message = "The page images could not be read just now; the statement stays held."
        record = self.file(content="", locations=[page(1, 0, 0, extraction_method="native")], metadata_={
            "financial_vision_reading": {"": dict(status="failed", at="2026-10-28T10:00:00+00:00", message=message)}})
        out = self.pages(record)
        self.assertIn(message, out["pages"][0]["text_missing"])
        self.assertIn("2026-10-28", out["page_image_failure"])

    def test_an_unknown_pdf_origin_is_not_called_the_files_own_text(self):
        reader = P.reader_of(dict(kind="page", extraction_method="native"))
        self.assertTrue(reader["machine_read"])
        self.assertIn("not recorded", reader["words"])

    def test_text_files_are_their_own_text_and_a_speakers_turn_stays_a_model_reading(self):
        for kind in ("text", "html", "markdown", "eml", "body", "sheet"):
            self.assertFalse(P.reader_of(dict(kind=kind))["machine_read"], kind)
        self.assertEqual(P.reader_of(dict(kind="audio_turn"))["kind"], "model")
        record = self.file(name="a.eml", content="Hello", locations=[dict(kind="eml", label="Document text", start_char=0, end_char=5)])
        self.assertEqual(self.pages(record)["pages"][0]["reader"]["kind"], "file_text")

    def test_a_model_reading_stays_labelled(self):
        vision = P.reader_of(dict(kind="image", reader_provider="openai_vision", reader_model="gpt-4o"))
        self.assertEqual(vision["kind"], "model")
        self.assertIn("gpt-4o", vision["words"])
        self.assertIn("not confirmed", vision["words"])
        speech = P.reader_of(dict(kind="audio"))
        self.assertEqual(speech["kind"], "model")
        self.assertIn("not recorded", speech["words"])
        self.assertTrue(P.reader_of(dict(kind="image"))["machine_read"])


class Absent(Base_):
    def test_each_status_gives_its_reason(self):
        self.assertIn("not been processed", self.pages(self.file(status="unprocessed"))["text_absent"])
        hidden = self.pages(self.file(status="failed", last_error="Client error '400 Bad Request' for url 'http://localhost'"))
        self.assertIn("failed", hidden["text_absent"])
        self.assertNotIn("localhost", hidden["text_absent"])
        self.assertIn("Unsupported file type", self.pages(self.file(status="failed", last_error="Unsupported file type: .dotx"))["text_absent"])
        self.assertIn("no text is stored", self.pages(self.file())["text_absent"])

    def test_a_pdf_without_text_still_counts_its_pages_from_the_file(self):
        import fitz
        with TemporaryDirectory() as folder:
            path = Path(folder) / "scan.pdf"
            document = fitz.open()
            for _ in range(3):
                document.new_page()
            document.save(path)
            out = self.pages(self.file(name="scan.pdf"), limit=2, path=path)
        self.assertEqual(out["page_count"], 3)
        self.assertEqual(out["image_pages"], 3)
        self.assertEqual(len(out["pages"]), 2)
        self.assertTrue(all(p["text_missing"] for p in out["pages"]))


class Sections(Base_):
    def test_a_long_transcript_pages_in_parts_and_loses_nothing(self):
        content = "x" * (P.PART_CHARACTERS * 2 + 7)
        record = self.file(name="a.mp3", content=content,
                           locations=[dict(kind="audio", label="Transcript", start_char=0, end_char=len(content)),
                                      dict(kind="audio_turn", label="Speaker", start_char=0, end_char=10)])
        out = self.pages(record)
        self.assertEqual(out["page_count"], 3)
        self.assertEqual(sum(len(p["text"]) for p in out["pages"]), len(content))
        self.assertEqual(out["pages"][0]["label"], "Transcript, part 1 of 3")
        self.assertEqual(out["pages"][0]["reader"]["kind"], "model")

    def test_a_pdf_with_no_page_ranges_is_not_stepped_with_its_images(self):
        import fitz
        with TemporaryDirectory() as folder:
            path = Path(folder) / "old.pdf"
            document = fitz.open()
            document.new_page()
            document.new_page()
            document.save(path)
            out = self.pages(self.file(name="old.pdf", content="undivided"), path=path)
        self.assertFalse(out["pages_in_step"])
        self.assertEqual(out["image_pages"], 2)
        self.assertEqual(out["pages"][0]["text"], "undivided")

    def test_a_character_gives_its_page(self):
        record = self.file(name="a.csv", content="y" * (P.PART_CHARACTERS + 5),
                           locations=[dict(kind="table", label="Table 1", start_char=0, end_char=P.PART_CHARACTERS + 5)])
        self.assertEqual(P.page_at(self.db, record, 3), 1)
        self.assertEqual(P.page_at(self.db, record, P.PART_CHARACTERS + 1), 2)
        self.assertIsNone(P.page_at(self.db, record, P.PART_CHARACTERS + 50))

    def test_a_missing_page_range_says_so(self):
        record = self.file(content="one", locations=[page(1, 0, 3, **NATIVE), page(3, 3, 3, **NATIVE)])
        out = self.pages(record)
        self.assertEqual(out["page_count"], 3)
        self.assertEqual(out["pages"][1]["text_missing"], "No text is stored for this page.")


class Passage(Base_):
    TEXT = "Paid to ACME Ltd\n\nWire to Globex"

    def doc(self, **kw):
        return self.file(content=self.TEXT, locations=[page(1, 0, 16, **NATIVE), page(2, 18, 32, **OCR)], **kw)

    def test_the_anchor_is_written_from_the_stored_text_with_its_reader(self):
        record = self.doc()
        label, anchor = P.passage_anchor(self.db, self.case_id, P.passage_id(record.id, "b" * 64, 18, 22))
        self.assertEqual(anchor["quote"], "Wire")
        self.assertEqual(anchor["page_number"], 2)
        self.assertEqual(anchor["page"], 2)
        self.assertEqual(anchor["evidence_file_id"], str(record.id))
        self.assertEqual((anchor["start_char"], anchor["end_char"]), (18, 22))
        self.assertEqual(anchor["text_version"], "b" * 64)
        self.assertEqual(anchor["reader"]["kind"], "ocr")
        self.assertIn("OCR", label)
        self.assertIn("“Wire”", label)

    def test_a_text_layer_quote_needs_no_reader_label(self):
        label, _ = P.passage_anchor(self.db, self.case_id, P.passage_id(self.doc().id, "b" * 64, 0, 4))
        self.assertNotIn("OCR", label)

    def test_offsets_count_characters_past_an_emoji(self):
        text = "😀 Paid £500"
        record = self.file(content=text, locations=[page(1, 0, len(text), **NATIVE)])
        _, anchor = P.passage_anchor(self.db, self.case_id, P.passage_id(record.id, "b" * 64, 2, 6))
        self.assertEqual(anchor["quote"], "Paid")
        self.assertEqual(self.pages(record)["pages"][0]["text"], text)

    def test_refusals(self):
        record = self.doc()
        with self.assertRaisesRegex(P.PassageError, "read again"):
            P.passage_anchor(self.db, self.case_id, P.passage_id(record.id, "c" * 64, 0, 4))
        with self.assertRaisesRegex(P.PassageError, "not found in this case"):
            P.passage_anchor(self.db, uuid4(), P.passage_id(record.id, "b" * 64, 0, 4))
        with self.assertRaisesRegex(P.PassageError, "one page"):
            P.passage_anchor(self.db, self.case_id, P.passage_id(record.id, "b" * 64, 10, 22))
        with self.assertRaisesRegex(P.PassageError, "at most"):
            P.passage_anchor(self.db, self.case_id, P.passage_id(record.id, "b" * 64, 0, P.QUOTE_MAX_CHARACTERS + 1))
        with self.assertRaises(P.PassageError):
            P.parse_passage("not a passage")

    def anchored(self, quote_start=18, quote_end=22):
        record = self.doc()
        _, anchor = P.passage_anchor(self.db, self.case_id, P.passage_id(record.id, "b" * 64, quote_start, quote_end))
        return record, anchor

    def reread(self, record, content, locations=()):
        text = self.db.get(EvidenceDocumentText, record.id)
        text.content, text.content_sha256, text.character_count = content, "c" * 64, len(content)
        text.source_locations = list(locations)
        self.db.commit()

    def test_an_unchanged_document_opens_at_the_passage(self):
        record, anchor = self.anchored()
        out = P.locate_passage(self.db, record, anchor)
        self.assertEqual(out["state"], "unchanged")
        self.assertEqual((out["start_char"], out["page_number"]), (18, 2))
        self.assertIsNone(out["words"])

    def test_a_reread_document_says_so_and_finds_the_words(self):
        record, anchor = self.anchored()
        self.reread(record, "cover\n\nWire to Globex", [page(1, 0, 5, **NATIVE), page(2, 7, 21, **NATIVE)])
        out = P.locate_passage(self.db, record, anchor)
        self.assertEqual(out["state"], "moved")
        self.assertEqual((out["start_char"], out["end_char"], out["page_number"]), (7, 11, 2))
        self.assertIn("read again", out["words"])

    def test_a_reread_document_without_the_words_opens_at_the_page_it_came_from(self):
        record, anchor = self.anchored()
        self.reread(record, "nothing like it")
        out = P.locate_passage(self.db, record, anchor)
        self.assertEqual(out["state"], "not_found")
        self.assertEqual(out["taken_page"], 2)
        self.assertEqual(out["quote"], "Wire")
        self.assertIn("not in the new reading", out["words"])


class Positions(unittest.TestCase):
    def test_a_text_layer_page_gives_fractions_and_a_rotated_page_stays_in_frame(self):
        import fitz
        with TemporaryDirectory() as folder:
            path = Path(folder) / "p.pdf"
            document = fitz.open()
            first = document.new_page(width=600, height=800)
            first.insert_text((60, 80), "Findme here")
            second = document.new_page(width=600, height=800)
            second.insert_text((60, 80), "Findme here")
            second.set_rotation(90)
            document.new_page()
            document.save(path)
            upright = P.page_positions(path, 1, "Findme")
            turned = P.page_positions(path, 2, "Findme")
            blank = P.page_positions(path, 3, "Findme")
            beyond = P.page_positions(path, 9, "Findme")
        self.assertTrue(upright["available"])
        self.assertAlmostEqual(upright["rects"][0]["x"], 0.1, places=2)
        self.assertLess(upright["rects"][0]["y"], 0.1)
        self.assertTrue(0 <= turned["rects"][0]["x"] <= 1 and 0 <= turned["rects"][0]["y"] <= 1)
        self.assertGreater(turned["rects"][0]["x"], 0.5)  # 90 degrees clockwise: the top left text is at the right
        self.assertEqual(blank, {"available": False, "rects": []})
        self.assertEqual(beyond, {"available": False, "rects": []})


if __name__ == "__main__":
    unittest.main()
