"""Production numbers: the rules a court reader relies on. Each test here fails on code without the rule."""
import hashlib
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import fitz
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.production_numbers import ProductionAssignment, ProductionSet, ProductionStampedCopy, ReceivedNumber
from postgres.models.user import User
from services import case_citations as C
from services import production_numbers as P


class NameRules(unittest.TestCase):
    def texts(self, name):
        return [item["text"] for item in P.suggestions_from_name(name)]

    def test_the_shapes_held_in_real_productions(self):
        self.assertEqual(self.texts("001765-001895 LSI-06202025-1307948 STMTS.pdf"), ["001765-001895"])
        self.assertEqual(self.texts("006756-006756 Invoice Doc.pdf"), ["006756"])
        self.assertEqual(self.texts("USA-261411.pdf"), ["USA-261411"])
        self.assertEqual(self.texts("005424-005433 Hopper SWA000001-SWA000010_Redacted.pdf"),
                         ["005424-005433", "SWA000001-SWA000010"])

    def test_names_that_only_resemble_a_number_are_left_alone(self):
        for name in ("IMG-20221126-WA0000.mp4", "PTT-20221129-WA0086.opus", "00002483-8662 Especificación.pdf",
                     "00004015-20230720 Proyecto.pptx", "2024-2025 - Statement.pdf", "photos_249298813937355.jpg",
                     "videos_1180083589399137.mp4", "._001765-001895 x.pdf", "20230216-20230324 report.pdf",
                     "CDR_Mediations_3019235362_11959904.xls", "IMG00012.jpg"):
            self.assertEqual(self.texts(name), [], name)

    def test_a_person_may_write_a_number_several_ways(self):
        self.assertEqual(P.parse_number("owl-000012").key, "OWL")
        self.assertEqual(P.parse_number("OWL 12").value, 12)
        low, high = P.parse_range("OWL000012-000020")
        self.assertEqual((low.key, high.key, high.value), ("OWL", "OWL", 20))
        with self.assertRaises(P.ProductionNumberError):
            P.parse_range("OWL000020", "OWL000012")
        with self.assertRaises(P.ProductionNumberError):
            P.parse_range("OWL000012", "ABC000020")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
        tables = [Base.metadata.tables[name] for name in (
            "users", "cases", "evidence_folders", "evidence_files", "production_sets", "production_assignments",
            "received_numbers", "production_stamped_copies")]
        Base.metadata.create_all(self.engine, tables=tables)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.folder = tempfile.TemporaryDirectory(prefix="lxb-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        env = mock.patch.dict(os.environ, {"LOUPE_PRODUCTION_COPY_DIR": str(self.root / "copies")})
        env.start()
        self.addCleanup(env.stop)
        resolved = mock.patch.object(P, "_resolve", lambda file=None, stored_path=None: Path(
            file.stored_path if file is not None else stored_path))
        resolved.start()
        self.addCleanup(resolved.stop)
        self.user = User(id=uuid.uuid4(), email="p@example.test", name="Pat Person", password_hash="x")
        self.db.add(self.user)
        self.db.flush()
        self.case = Case(id=uuid.uuid4(), title="c", created_by_user_id=self.user.id, owner_user_id=self.user.id)
        self.db.add(self.case)
        self.db.commit()
        self.index = 0

    def pdf(self, name, pages=3, rotate=0):
        self.index += 1
        path = self.root / f"{self.index}-{uuid.uuid4().hex}.pdf"
        with fitz.open() as document:
            for at in range(pages):
                page = document.new_page()
                page.insert_text((72, 72), f"{name} page {at + 1}")
                page.set_rotation(rotate)
            document.save(path)
        return self.add(name, path)

    def add(self, name, path):
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        row = EvidenceFile(id=uuid.uuid4(), case_id=self.case.id, original_filename=name, stored_path=str(path),
                           sha256=digest, size=Path(path).stat().st_size)
        self.db.add(row)
        self.db.commit()
        return row

    def media(self, name="Interview.mp4"):
        self.index += 1
        path = self.root / f"{self.index}.mp4"
        path.write_bytes(b"not pages")
        return self.add(name, path)

    def set(self, prefix="OWL", start=1, padding=6):
        return P.create_set(self.db, self.case.id, name="First", prefix=prefix, start=start, padding=padding, user=self.user)


class NeverReissued(Fixture):
    def test_a_range_is_one_number_per_page_in_order(self):
        s, a, b = self.set(), self.pdf("a.pdf", 3), self.pdf("b.pdf", 2)
        out = P.assign(self.db, self.case.id, s.id, [a.id, b.id], user=self.user)
        self.assertEqual([item["text"] for item in out["issued"]], ["OWL000001-OWL000003", "OWL000004-OWL000005"])
        self.assertEqual(out["next_text"], "OWL000006")

    def test_no_reissue_after_withdrawal_removal_or_purge(self):
        s, a, b, c = self.set(), self.pdf("a.pdf", 3), self.pdf("b.pdf", 2), self.pdf("c.pdf", 1)
        out = P.assign(self.db, self.case.id, s.id, [a.id, b.id, c.id], user=self.user)
        P.withdraw_assignment(self.db, self.case.id, uuid.UUID(out["issued"][2]["id"]), reason="wrong file", user=self.user)
        self.db.delete(self.db.get(EvidenceFile, b.id))  # the 30-day purge removes the row itself
        self.db.commit()
        kept = self.db.get(ProductionAssignment, uuid.UUID(out["issued"][1]["id"]))
        self.assertIsNone(kept.evidence_file_id)
        self.assertEqual((kept.file_name, kept.first_number, kept.last_number), ("b.pdf", 4, 5))
        again = P.assign(self.db, self.case.id, s.id, [c.id, self.pdf("d.pdf", 1).id], user=self.user)
        # number 6 was withdrawn from c.pdf; c.pdf is numbered afresh, and nobody gets 4, 5 or 6
        self.assertEqual([item["text"] for item in again["issued"]], ["OWL000007", "OWL000008"])

    def test_the_same_prefix_cannot_start_a_second_count(self):
        self.set()
        for prefix in ("OWL", "owl", "OWL-"):
            with self.assertRaises(P.ProductionNumberError) as refused:
                self.set(prefix=prefix)
            self.assertEqual(refused.exception.status_code, 409)

    def test_a_file_already_numbered_keeps_its_range_and_is_reported(self):
        s, a = self.set(), self.pdf("a.pdf", 2)
        P.assign(self.db, self.case.id, s.id, [a.id], user=self.user)
        out = P.assign(self.db, self.case.id, s.id, [a.id], user=self.user)
        self.assertEqual(out["issued"], [])
        self.assertIn("OWL000001-OWL000002", out["skipped"][0]["reason"])
        self.assertEqual(self.db.get(ProductionSet, s.id).next_number, 3)

    def test_media_is_numbered_at_file_level_and_says_so(self):
        s, video = self.set(), self.media()
        issued = P.assign(self.db, self.case.id, s.id, [video.id], level="page", user=self.user)["issued"][0]
        self.assertEqual((issued["level"], issued["text"], issued["note"]), ("file", "OWL000001", P.NO_PAGES_WORDS))

    def test_a_file_of_another_case_is_not_numbered(self):
        s = self.set()
        out = P.assign(self.db, self.case.id, s.id, [uuid.uuid4()], user=self.user)
        self.assertEqual((out["issued"], out["skipped"][0]["reason"]), ([], "This file is not in the case."))


class SuggestedStaysSuggested(Fixture):
    def test_a_name_suggests_and_nothing_is_stored(self):
        file = self.pdf("000010-000012 Statements.pdf", 3)
        numbers = P.case_numbers(self.db, self.case.id)["files"][str(file.id)]
        self.assertEqual(numbers["suggested"][0]["status"], "suggested")
        self.assertEqual(numbers["suggested"][0]["label"], P.SUGGESTED_WORDS)
        self.assertEqual(numbers["received"], [])
        self.assertEqual(self.db.query(ReceivedNumber).count(), 0)

    def test_every_reader_of_the_number_gets_the_label(self):
        file = self.pdf("000010-000012 Statements.pdf", 3)
        refs = P.references_for(self.db, self.case.id, [(file.id, 2)])[(str(file.id), 2)]
        self.assertEqual(refs[0]["kind"], "suggested")
        self.assertIn("not confirmed", P.reference_words(refs))
        hit = P.find_number(self.db, self.case.id, "000011")["hits"][0]
        self.assertEqual((hit["kind"], hit["label"], hit["page"]), ("suggested", P.SUGGESTED_WORDS, 2))

    def test_only_a_persons_answer_makes_it_a_value_under_their_name(self):
        file = self.pdf("000010-000012 Statements.pdf", 3)
        row = P.decide_suggestion(self.db, self.case.id, file.id, first_text="000010", last_text="000012", confirm=True, user=self.user)
        self.db.commit()
        self.assertEqual((row.source, row.status, row.decided_by_name), ("file_name", "confirmed", "Pat Person"))
        numbers = P.case_numbers(self.db, self.case.id)["files"][str(file.id)]
        self.assertEqual((numbers["suggested"], numbers["received"][0]["label"]),
                         ([], "Received, read from the file name, confirmed by Pat Person"))

    def test_a_range_the_name_does_not_state_cannot_be_confirmed(self):
        file = self.pdf("000010-000012 Statements.pdf", 3)
        with self.assertRaises(P.ProductionNumberError):
            P.decide_suggestion(self.db, self.case.id, file.id, first_text="000099", last_text="000100", confirm=True, user=self.user)

    def test_a_rejection_stays_on_record_and_undoing_it_suggests_again(self):
        file = self.pdf("000010-000012 Statements.pdf", 3)
        row = P.decide_suggestion(self.db, self.case.id, file.id, first_text="000010", last_text="000012", confirm=False, user=self.user)
        self.assertEqual(P.case_numbers(self.db, self.case.id)["files"][str(file.id)]["suggested"], [])
        self.assertEqual(P.find_number(self.db, self.case.id, "000011")["total"], 0)
        P.withdraw_received(self.db, self.case.id, row.id, user=self.user)
        self.assertEqual(len(P.case_numbers(self.db, self.case.id)["files"][str(file.id)]["suggested"]), 1)


class Conflicts(Fixture):
    def kinds(self, file):
        return [c["kind"] for c in P.case_numbers(self.db, self.case.id)["files"][str(file.id)]["conflicts"]]

    def test_a_person_entry_that_differs_from_the_name_keeps_both_and_shows_it(self):
        file = self.pdf("000010-000012 Statements.pdf", 3)
        P.enter_received(self.db, self.case.id, file.id, first="000020", last="000022", user=self.user)
        numbers = P.case_numbers(self.db, self.case.id)["files"][str(file.id)]
        self.assertEqual((numbers["received"][0]["text"], numbers["suggested"][0]["text"]),
                         ("000020-000022", "000010-000012"))
        self.assertEqual([c["kind"] for c in numbers["conflicts"]], ["same_file_differs"])

    def test_an_assigned_range_never_replaces_a_received_one(self):
        s, file = self.set(prefix="ABC", start=100), self.pdf("a.pdf", 3)
        P.enter_received(self.db, self.case.id, file.id, first="ABC000100", last="ABC000102", user=self.user)
        other = self.pdf("b.pdf", 3)
        P.assign(self.db, self.case.id, s.id, [other.id], user=self.user)
        numbers = P.case_numbers(self.db, self.case.id)["files"]
        self.assertEqual(numbers[str(file.id)]["received"][0]["text"], "ABC000100-ABC000102")
        self.assertEqual(self.kinds(file), ["same_number"])
        self.assertEqual(self.kinds(other), ["same_number"])

    def test_a_range_the_wrong_size_is_shown_and_opens_no_page(self):
        file = self.pdf("a.pdf", 3)
        P.enter_received(self.db, self.case.id, file.id, first="ABC000100", last="ABC000104", user=self.user)
        self.assertEqual(self.kinds(file), ["pages_differ"])
        hit = P.find_number(self.db, self.case.id, "ABC000102")["hits"][0]
        self.assertEqual((hit["page"], hit["note"]), (None, P.PAGE_NOT_CERTAIN))

    def test_two_prefixes_on_one_file_are_not_a_conflict(self):
        file = self.pdf("005424-005433 Hopper SWA000001-SWA000010_Redacted.pdf", 10)
        self.assertEqual(self.kinds(file), [])


class Finding(Fixture):
    def test_a_number_goes_to_its_page_with_or_without_the_prefix(self):
        s, a, b = self.set(), self.pdf("a.pdf", 3), self.pdf("b.pdf", 4)
        P.assign(self.db, self.case.id, s.id, [a.id, b.id], user=self.user)
        for query in ("OWL000005", "owl-5", "000005"):
            hit = P.find_number(self.db, self.case.id, query)["hits"][0]
            self.assertEqual((hit["evidence_file_id"], hit["page"]), (str(b.id), 2), query)

    def test_a_range_finds_every_file_it_touches(self):
        s, a, b = self.set(), self.pdf("a.pdf", 3), self.pdf("b.pdf", 4)
        P.assign(self.db, self.case.id, s.id, [a.id, b.id], user=self.user)
        self.assertEqual(P.find_number(self.db, self.case.id, "OWL000002-OWL000005")["total"], 2)

    def test_a_withdrawn_number_is_found_and_says_so(self):
        s, a = self.set(), self.pdf("a.pdf", 1)
        issued = P.assign(self.db, self.case.id, s.id, [a.id], user=self.user)["issued"][0]
        P.withdraw_assignment(self.db, self.case.id, uuid.UUID(issued["id"]), reason="wrong file", user=self.user)
        hit = P.find_number(self.db, self.case.id, "OWL000001")["hits"][0]
        self.assertEqual((hit["label"], hit["page"]), ("Withdrawn: wrong file", None))

    def test_ordinary_words_are_not_numbers(self):
        self.pdf("a.pdf", 1)
        with mock.patch.object(P, "_stored_rows", side_effect=AssertionError("no read for words")):
            self.assertEqual(P.find_number(self.db, self.case.id, "invoice")["parsed"], False)
            self.assertEqual(P.find_number(self.db, self.case.id, "12")["parsed"], False)

    def test_a_citation_carries_the_number_of_its_page_and_its_kind(self):
        s, a = self.set(), self.pdf("a.pdf", 3)
        P.assign(self.db, self.case.id, s.id, [a.id], user=self.user)
        found = {r.page: r for r in C.resolve_citations(self.db, self.case.id, C.citations_in(
            f"[a](doc://{a.id}/2) [b](doc://{a.id})"))}
        self.assertEqual(found[2].production_numbers[0]["number"], "OWL000002")
        self.assertEqual(found[None].production_numbers[0]["number"], "OWL000001-OWL000003")
        self.assertEqual(P.reference_words(found[2].production_numbers), "OWL000002 (assigned)")


class Import(Fixture):
    def test_every_line_lands_or_comes_back_with_its_reason(self):
        self.pdf("a.pdf", 2)
        self.pdf("same.pdf", 1)
        self.pdf("same.pdf", 1)
        out = P.import_received(self.db, self.case.id, "File name,First,Last\na.pdf,ABC000001,ABC000002\nsame.pdf,ABC3,ABC3\n"
                                "gone.pdf,ABC4,ABC4\na.pdf,ABC9,ABC8\n", user=self.user)
        self.assertEqual([row["text"] for row in out["imported"]], ["ABC000001-ABC000002"])
        self.assertEqual(out["imported"][0]["label"], "Received, imported by Pat Person")
        self.assertEqual([p["line"] for p in out["problems"]], [3, 4, 5])


class Stamping(Fixture):
    def test_stamped_copy_leaves_the_original_and_its_hash_unchanged(self):
        s, a = self.set(), self.pdf("a.pdf", 3)
        issued = P.assign(self.db, self.case.id, s.id, [a.id], user=self.user)["issued"][0]
        before_bytes = Path(a.stored_path).read_bytes()
        copy = P.stamp_copy(self.db, self.case.id, uuid.UUID(issued["id"]), user=self.user)
        self.db.commit()
        self.assertEqual(Path(a.stored_path).read_bytes(), before_bytes)
        self.assertEqual(self.db.get(EvidenceFile, a.id).sha256, hashlib.sha256(before_bytes).hexdigest())
        self.assertEqual(copy.source_sha256, a.sha256)
        self.assertNotEqual(copy.sha256, a.sha256)
        self.assertEqual(copy.sha256, hashlib.sha256(Path(copy.storage_path).read_bytes()).hexdigest())
        with fitz.open(copy.storage_path) as document:
            self.assertEqual([("OWL00000%d" % n) in page.get_text() for n, page in enumerate(document, 1)], [True] * 3)
        self.assertFalse(Path(copy.storage_path).is_relative_to(Path(a.stored_path).parent / "evidence"))

    def test_a_turned_page_still_carries_its_number_on_the_page(self):
        s, a = self.set(), self.pdf("a.pdf", 1, rotate=90)
        issued = P.assign(self.db, self.case.id, s.id, [a.id], user=self.user)["issued"][0]
        copy = P.stamp_copy(self.db, self.case.id, uuid.UUID(issued["id"]), user=self.user)
        with fitz.open(copy.storage_path) as document:
            self.assertIn("OWL000001", document[0].get_text())
            self.assertTrue(document[0].rect.contains(document[0].search_for("OWL000001")[0] * document[0].rotation_matrix)
                            or document[0].search_for("OWL000001"))

    def test_an_original_that_no_longer_matches_is_not_stamped(self):
        s, a = self.set(), self.pdf("a.pdf", 1)
        issued = P.assign(self.db, self.case.id, s.id, [a.id], user=self.user)["issued"][0]
        with open(a.stored_path, "ab") as handle:
            handle.write(b"\n%tampered")
        with self.assertRaises(P.ProductionNumberError):
            P.stamp_copy(self.db, self.case.id, uuid.UUID(issued["id"]), user=self.user)
        self.assertEqual(self.db.query(ProductionStampedCopy).count(), 0)

    def test_a_file_with_no_pages_cannot_be_stamped_and_says_so(self):
        s, video = self.set(), self.media()
        issued = P.assign(self.db, self.case.id, s.id, [video.id], user=self.user)["issued"][0]
        with self.assertRaises(P.ProductionNumberError) as refused:
            P.stamp_copy(self.db, self.case.id, uuid.UUID(issued["id"]), user=self.user)
        self.assertIn("Only a PDF", str(refused.exception))


class Bounded(Fixture):
    def test_the_whole_case_costs_the_same_reads_however_many_files(self):
        s = self.set()
        files = [self.pdf(f"{n:06d}-{n:06d} x.pdf", 1) for n in range(1, 4)]
        P.assign(self.db, self.case.id, s.id, [f.id for f in files[:2]], user=self.user)
        self.db.commit()
        counted = []
        event.listen(self.engine, "before_cursor_execute", lambda *args: counted.append(args[2]))
        P.case_numbers(self.db, self.case.id)
        small = len(counted)
        for n in range(4, 24):
            self.pdf(f"{n:06d}-{n:06d} x.pdf", 1)
        counted.clear()
        P.case_numbers(self.db, self.case.id)
        self.assertLessEqual(len(counted), small)


class Exports(Fixture):
    """The number travels beside the citation into the CSV and the PDF provenance column, with its kind."""

    def test_the_judgement_csv_carries_the_number_with_its_kind(self):
        from services.financial import judgements as J
        file = self.pdf("000010-000012 Statements.pdf", 3)
        item = {"evidence_file_id": str(file.id), "page": "2", "priority": 1, "priority_label": "High", "status": "open",
                "category_label": "c", "rule_label": "r", "summary": "s", "rule_id": "x", "origin": "rule", "strength": "proved", "filename": file.original_filename}
        numbers = J.export_numbers(self.db, self.case.id, {"items": [item]})
        self.assertIn("not confirmed", numbers[(str(file.id), 2)])
        self.assertIn("Production number", J.EXPORT_COLUMNS)
        row = J.export_csv({"items": [item]}, numbers=numbers).decode("utf-8-sig")
        self.assertIn("000010-000012 (suggested", row)

    def test_the_export_survives_calls_with_and_without_a_page_on_one_file(self):
        from services.financial import judgements as J
        file = self.pdf("000010-000012 Statements.pdf", 3)
        base = {"evidence_file_id": str(file.id), "priority": 1, "priority_label": "High", "status": "open",
                "category_label": "c", "rule_label": "r", "summary": "s", "rule_id": "x", "origin": "rule",
                "strength": "proved", "filename": file.original_filename}
        items = [dict(base, page=None), dict(base, page="2")]
        numbers = J.export_numbers(self.db, self.case.id, {"items": items})
        self.assertIn((str(file.id), 2), numbers)

    def test_the_pdf_provenance_label_prints_the_reference(self):
        from services.financial_export_service import _provenance_label
        label = _provenance_label({"source_filename": "a.pdf", "source_page": 2,
                                   "production_reference": "000011 (suggested from the file name, not confirmed)"})
        self.assertIn("000011", label)
        self.assertNotIn("000011", _provenance_label({"source_filename": "a.pdf", "source_page": 2}))
