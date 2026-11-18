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


class PoliceAndLabForms(unittest.TestCase):
    """17 Nov, CM1 Thomas Keyes: the rules read a date from 18 of its 440 files; 407 are photos, videos or hold no
    date, and the lab and fire forms wrote their dates in ways the rules skipped."""

    def test_date_of_report_is_the_written_date(self):
        head = "Montgomery County Police Department Crime Laboratory Firearms Examination Unit " * 4
        r = read_dates(head + "FEU Examination Report (2127) Revision: 3 (11/22/2025) CR#: 250057502 "
                       "Date of Report: 3/16/2026")
        self.assertEqual([(x["kind"], x["date_from"], x["rule"]) for x in r],
                         [("written", date(2026, 3, 16), "cue-written+2")])

    def test_the_second_pass_never_changes_a_first_pass_reading(self):
        # measured 17 Nov over 35,984 live texts: letting the new cues compete changed 171 readings to other dates
        r = kinds("Invoice date: 01/15/2024 ... Date of Report: 3/16/2026")
        self.assertEqual((r["written"]["date_from"], r["written"]["rule"]), (date(2024, 1, 15), "cue-written"))

    def test_a_cue_with_an_equals_sign_reads_its_date(self):
        self.assertEqual(kinds("TO: Det. Elias Samghani, ID# 2211 DATE: = 2/15/2026")["written"]["date_from"],
                         date(2026, 2, 15))

    def test_a_two_digit_year_is_read_after_a_cue_and_never_alone(self):
        self.assertEqual(kinds("Examiner: Stephanie Luehr Date: 3/14/26 Item 1")["written"]["date_from"],
                         date(2026, 3, 14))
        self.assertEqual(kinds("Lot 3/14/26 shelf 12"), {})

    def test_a_declaration_is_signed_on_the_date_after_its_true_and_correct_clause(self):
        r = kinds("I declare under penalty of perjury that the foregoing is true and correct. March 9, 2026 "
                  "for dates of service after 2/21/2024")
        self.assertEqual(r["signed"]["date_from"], date(2026, 3, 9))

    def test_dates_of_birth_and_offence_dates_stay_unread(self):
        self.assertEqual(kinds("Thomas Lee Keyes, having the date of birth of 10/31/1964"), {})

    def test_an_incident_report_is_dated_the_day_it_was_reported(self):
        # 18 Nov, demo case b75f3f2c: the five police reports had no document date (lx-overlapviews-b)
        r = kinds("Incident report CCPD-24-1100. Offense: theft from a commercial building, over $1,500. Reported "
                  "Saturday 16 March 2024 at 06:10 by the day manager.")
        self.assertEqual((r["written"]["date_from"], r["written"]["rule"]), (date(2024, 3, 16), "cue-written+2"))
        self.assertEqual(kinds("Reported on 4 May 2024")["written"]["date_from"], date(2024, 5, 4))


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


class Used(Store):
    """Where the dates are used: the Timeline events and Corroborate's dated documents."""

    def test_timeline_event_says_read_by_loupe_with_words_until_confirmed_and_the_type_lets_a_filter_drop_it(self):
        S.store_for_file(self.db, self.file)
        (e,) = S.document_date_events(self.db, self.case)
        self.assertEqual((e["date"], e["type"]), ("2026-08-05", "Document date, not confirmed"))
        self.assertIn(S.READ_LABEL, e["summary"])
        self.assertIn("Invoice date", e["summary"])
        rid = S.effective(self.db, self.case)[0]["id"]
        self.assertEqual(S.document_date_events(self.db, self.case, confirmed_only=True), [])
        S.confirm(self.db, self.case, rid, None, "Neil Byrne")
        (e,) = S.document_date_events(self.db, self.case, confirmed_only=True)
        self.assertEqual(e["type"], "Document date")
        self.assertIn("Confirmed by Neil Byrne", e["summary"])

    def test_timeline_uses_only_the_corrected_date_and_shows_the_original(self):
        S.store_for_file(self.db, self.file)
        rid = S.effective(self.db, self.case)[0]["id"]
        S.correct(self.db, self.case, rid, date(2026, 8, 7), date(2026, 8, 7), None, "Neil Byrne")
        (e,) = S.document_date_events(self.db, self.case)
        self.assertEqual(e["date"], "2026-08-07")
        self.assertEqual(e["read_date"]["original"]["date_from"], "2026-08-05")

    def test_corroborate_gets_a_day_only_record_for_a_document_naming_the_person(self):
        from datetime import datetime, timezone
        from services.corroborate.store import CaseStore as Store
        S.store_for_file(self.db, self.file)
        self.db.execute(__import__("sqlalchemy").text("UPDATE evidence_document_texts SET content = :t"),
                        {"t": "Invoice date: 5 August 2026 billed to Ann Arden total 10"})
        S.store_for_file(self.db, self.file)
        stub = Store.__new__(Store)
        stub.db, stub.case, stub.c = self.db, str(self.case), {"c": str(self.case)}
        # SQLite keeps a uuid without hyphens; PostgreSQL reads either form
        stub.q = lambda sql, **p: self.db.execute(__import__("sqlalchemy").text(sql), {**p, "f": p["f"].replace("-", "")})
        stub.documents_naming = lambda people, need_time=True: [str(self.file)]
        people = [{"key": "ann", "names": ["Ann Arden"]}]
        lo, hi = datetime(2026, 8, 5, 22, tzinfo=timezone.utc), datetime(2026, 8, 6, 2, tzinfo=timezone.utc)
        (rec,) = Store.dated_documents(stub, people, [(lo, hi)])
        self.assertEqual((rec["kind"], rec["day_only"], rec["parties"]), ("doc_row", True, ["ann"]))
        self.assertIn("not confirmed", rec["body"])
        far = (datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 2, tzinfo=timezone.utc))
        self.assertEqual(Store.dated_documents(stub, people, [far]), [])


class Reread(Store):
    """scripts/document_dates_backfill.py --reread: a file read before gains only what the rules now read."""

    def _run(self, *args):
        from unittest.mock import patch
        from scripts import document_dates_backfill
        maker = sessionmaker(bind=self.engine, future=True)
        with patch("postgres.session._get_session_local", return_value=maker):
            document_dates_backfill.main(["--reread", *args])
        self.db.expire_all()
        return sorted((r.kind, r.date_from, r.rule) for r in self.db.query(DocumentDateReading))

    def test_a_reread_adds_the_second_pass_reading_once_and_keeps_the_first(self):
        S.store_for_file(self.db, self.file)
        self.db.commit()
        row = self.db.get(EvidenceDocumentText, self.file)
        row.content = "Invoice date: 5 August 2026 total 10. Sworn under penalty: the foregoing is true and correct. March 9, 2026"
        self.db.commit()
        self.assertEqual(len(self._run()), 1)  # a dry run writes nothing
        first = self._run("--apply")
        self.assertEqual(first, [("signed", date(2026, 3, 9), "docdates-rules-1:cue-signed+2"),
                                 ("written", date(2026, 8, 5), "docdates-rules-1:cue-written")])
        self.assertEqual(self._run("--apply"), first)
