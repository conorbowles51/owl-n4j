"""Dates read from document text: the rules and the store (lx-docdates B, C)."""
from __future__ import annotations

import unittest
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.document_date import DocumentDateReading
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder
from services import document_date_store as S
from services.document_dates import read_dates


def kinds(text):
    return {r["kind"]: r for r in read_dates(text)}


class Rules(unittest.TestCase):
    def test_statement_period_and_cut_off_date(self):
        r = kinds("Periodo DEL 01/08/2026 AL 31/08/2026 Fecha de Corte 31/08/2026 No. de Cuenta 1")
        self.assertEqual((r["period"]["date_from"], r["period"]["date_to"]), (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(r["written"]["date_from"], date(2026, 8, 31))
        self.assertIn("Periodo DEL 01/08/2026", r["period"]["words"])

    def test_spanish_words_period(self):
        r = kinds("PERIODO: Del 1 Marzo 2024 al 31 marzo 2024 DIAS TRANSCURRIDOS")
        self.assertEqual(r["period"]["date_to"], date(2024, 3, 31))

    def test_letter_and_email_dates(self):
        self.assertEqual(kinds("(Metropolitan Grand Jury) June 3, 2026 The Grand Jury")["written"]["date_from"], date(2026, 6, 3))
        r = kinds("Duncan <d@x.com> Thu, Apr 9, 2026 at 8:08 AM To: Pat")
        self.assertEqual(r["written"]["date_from"], date(2026, 4, 9))

    def test_a_date_with_a_different_meaning_is_not_the_documents_date(self):
        self.assertEqual(kinds("Payment Due Date Jan. 17, 2021 For online"), {})
        self.assertEqual(kinds("Contract Number: 2040001138 Contract Date: May 06, 2002 Type"), {})
        self.assertEqual(kinds("The nature of the activity: On 02/19/2024, SA Gray obtained a"), {})

    def test_an_ambiguous_numeric_date_is_skipped_never_guessed(self):
        self.assertEqual(kinds("Date: 03/04/2026"), {})
        self.assertEqual(kinds("Date: 13/04/2026")["written"]["date_from"], date(2026, 4, 13))

    def test_video_frame_stamps_are_not_read(self):
        self.assertEqual(kinds("[01:30] 2025-12-24 14:52:33 AXON BODY 3"), {})

    def test_page_of_the_words(self):
        text = "Page one\n\nSecond Fecha de Corte 2025-01-31 here"
        locs = [{"page_number": 1, "start_char": 0, "end_char": 8}, {"page_number": 2, "start_char": 10, "end_char": len(text)}]
        self.assertEqual(read_dates(text, locs)[0]["page"], 2)


class Store(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__,
                                                      EvidenceDocumentText.__table__, DocumentDateReading.__table__])
        self.db = sessionmaker(bind=self.engine, future=True)()
        self.case = uuid4()
        self.file = uuid4()
        self.db.add(EvidenceFile(id=self.file, case_id=self.case, original_filename="a.pdf", stored_path="/tmp/a",
                                 size=1, sha256="a" * 64, status="processed"))
        text = "Invoice date: 5 August 2026 total 10"
        self.db.add(EvidenceDocumentText(evidence_file_id=self.file, content=text, content_sha256="b" * 64,
                                         character_count=len(text), source_locations=[]))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_reading_is_stored_as_loupes_with_its_words_and_repeats_add_nothing(self):
        self.assertEqual(S.store_for_file(self.db, self.file), 1)
        self.assertEqual(S.store_for_file(self.db, self.file), 0)
        (v,) = S.effective(self.db, self.case)
        self.assertEqual((v["source"], v["confirmed"], v["label"]), ("rule", False, S.READ_LABEL))
        self.assertIn("Invoice date", v["words"])
        self.assertEqual(S.effective(self.db, self.case, confirmed_only=True), [])

    def test_confirm_marks_it_with_the_person_and_drops_the_label(self):
        S.store_for_file(self.db, self.file)
        rid = S.effective(self.db, self.case)[0]["id"]
        out = S.confirm(self.db, self.case, rid, None, "Neil Byrne")
        self.assertTrue(out["confirmed"] and out["label"] is None and out["confirmed_by"] == "Neil Byrne")
        self.assertEqual(len(S.effective(self.db, self.case, confirmed_only=True)), 1)

    def test_correction_keeps_the_original_and_only_the_correction_is_used(self):
        S.store_for_file(self.db, self.file)
        rid = S.effective(self.db, self.case)[0]["id"]
        S.correct(self.db, self.case, rid, date(2026, 8, 6), date(2026, 8, 6), None, "Neil Byrne")
        (v,) = S.effective(self.db, self.case)
        self.assertEqual((v["source"], v["date_from"]), ("person", "2026-08-06"))
        self.assertEqual(v["original"]["date_from"], "2026-08-05")
        self.assertEqual(self.db.query(DocumentDateReading).count(), 2)
        self.assertEqual(S.store_for_file(self.db, self.file), 0)

    def test_backfill_uses_the_same_path_and_counts_per_case(self):
        dry = S.backfill(self.db)
        self.assertEqual(dry[str(self.case)], {"files": 1, "readings": 0})
        self.assertEqual(self.db.query(DocumentDateReading).count(), 0)
        self.assertEqual(S.backfill(self.db, apply=True)[str(self.case)]["readings"], 1)
        self.assertEqual(S.backfill(self.db, apply=True), {})

    def test_the_sync_stores_dates_when_a_job_completes(self):
        from services.evidence_job_sync import _sync_db_record_from_job
        rec = self.db.get(EvidenceFile, self.file)
        rec.status = "processing"
        _sync_db_record_from_job(rec, {"status": "completed"}, self.db, request_checked=True)
        self.assertEqual(self.db.query(DocumentDateReading).count(), 1)


if __name__ == "__main__":
    unittest.main()
