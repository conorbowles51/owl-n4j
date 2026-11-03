"""Citations checked against the case: doc:// by file id with its page, txn:// rows, rec:// records, old links."""
import unittest
import uuid

from postgres.models.evidence import EvidenceFile
from services import case_citations as C
from tests.test_agent_financial_ledger_tools import LedgerToolFixture


class ParseTests(unittest.TestCase):
    def test_schemes_pages_and_old_forms(self):
        fid, tid, rid = (str(uuid.uuid4()) for _ in range(3))
        self.assertEqual(C.parse_citation(f"doc://{fid}/4").page, 4)
        self.assertIsNone(C.parse_citation(f"doc://{fid}").page)
        self.assertFalse(C.parse_citation(f"doc://{fid}").by_name)
        named = C.parse_citation("doc://March%20statement.pdf/12")
        self.assertEqual((named.target, named.page, named.by_name), ("March statement.pdf", 12, True))
        # no page given is not page 1
        self.assertIsNone(C.parse_citation("doc://March%20statement.pdf").page)
        self.assertEqual(C.parse_citation(f"txn://{tid}").target, tid)
        record = C.parse_citation(f"rec://{rid}#body")
        self.assertEqual((record.scheme, record.field), ("rec", "body"))
        case = str(uuid.uuid4())
        old = C.parse_citation(f"/cases/{case}/financial?view=transactions&payment={tid}")
        self.assertEqual((old.scheme, old.target, old.legacy, old.linked_case_id), ("txn", tid, True, case))
        self.assertIsNone(C.parse_citation("https://example.com/page"))
        self.assertIsNone(C.parse_citation("txn://not-an-id"))

    def test_citations_in_markdown_once_each(self):
        tid = str(uuid.uuid4())
        text = f"[a](txn://{tid}) and [b](txn://{tid}) and [c](doc://x.pdf/2) [web](https://example.com)"
        self.assertEqual([c.href for c in C.citations_in(text)], [f"txn://{tid}", "doc://x.pdf/2"])


class CaseCheckTests(LedgerToolFixture):
    def _file(self, name, case=None, **extra):
        self._file_index += 1
        file = EvidenceFile(id=uuid.uuid4(), case_id=(case or self.case).id, original_filename=name,
                            stored_path=f"/evidence/{uuid.uuid4()}", sha256=f"{self._file_index:064d}", **extra)
        self.db.add(file)
        self.db.commit()
        return file

    def test_doc_by_id_in_case_and_not_in_case(self):
        own = self._file("own.pdf")
        foreign = self._file("foreign.pdf", case=self.other_case)
        result = {r.href: r for r in C.resolve_citations(self.db, self.case.id, C.citations_in(
            f"[a](doc://{own.id}/3) [b](doc://{foreign.id}/1) [c](doc://{own.id})"))}
        self.assertEqual(result[f"doc://{own.id}/3"].status, "ok")
        self.assertEqual(result[f"doc://{own.id}/3"].page, 3)
        # a file of another case is "not in this case", in the same words as one that does not exist
        self.assertEqual(result[f"doc://{foreign.id}/1"].reason, C.NOT_IN_CASE)
        nopage = result[f"doc://{own.id}"]
        self.assertEqual((nopage.status, nopage.page, nopage.page_given), ("ok", None, False))

    def test_shared_filename_is_a_choice_never_a_guess(self):
        first = self._file("Statement.pdf")
        second = self._file("Statement.pdf")
        self._file("Statement.pdf", case=self.other_case)
        unique = self._file("Unique.pdf")
        [shared, single, missing] = C.resolve_citations(self.db, self.case.id, C.citations_in(
            "[a](doc://Statement.pdf/2) [b](doc://Unique.pdf/5) [c](doc://Nowhere.pdf/1)"))
        self.assertEqual(shared.status, "ambiguous")
        self.assertEqual({c["evidence_file_id"] for c in shared.candidates}, {str(first.id), str(second.id)})
        self.assertIsNone(shared.evidence_file_id)
        self.assertEqual((single.status, single.evidence_file_id, single.page), ("ok", str(unique.id), 5))
        self.assertEqual(missing.status, "not_in_case")

    def test_internal_copy_does_not_make_a_name_ambiguous(self):
        original = self._file("Copied.pdf")
        self._file_index += 1
        copy = EvidenceFile(id=uuid.uuid4(), case_id=self.case.id, original_filename="Copied.pdf",
                            stored_path="/evidence/copy", sha256=original.sha256,
                            metadata_={"statement_root_evidence_id": str(original.id)})
        self.db.add(copy)
        self.db.commit()
        [r] = C.resolve_citations(self.db, self.case.id, C.citations_in("[a](doc://Copied.pdf/1)"))
        self.assertEqual((r.status, r.evidence_file_id), ("ok", str(original.id)))

    def test_txn_in_case_carries_its_statement_page_and_old_links_resolve(self):
        document, _, rows = self.source(rows=1)
        row = rows[0]
        row.provenance = {**(row.provenance or {}), "locator": {"kind": "page_only", "page": 7}}
        self.db.commit()
        _, _, foreign = self.source(rows=0)
        old = f"/cases/{self.case.id}/financial?view=transactions&payment={row.id}"
        wrong_case = f"/cases/{self.other_case.id}/financial?view=transactions&payment={row.id}"
        text = f"[a](txn://{row.id}) [b]({old}) [c](txn://{uuid.uuid4()}) [d]({wrong_case})"
        result = {r.href: r for r in C.resolve_citations(self.db, self.case.id, C.citations_in(text))}
        self.assertEqual(result[f"txn://{row.id}"].status, "ok")
        self.assertEqual(result[f"txn://{row.id}"].page, 7)
        self.assertEqual(result[f"txn://{row.id}"].evidence_file_id, str(document.evidence_file_id))
        self.assertEqual(result[old].status, "ok")
        self.assertEqual(result[wrong_case].status, "not_in_case")
        check = C.check_text(self.db, self.case.id, text)
        self.assertEqual((check["total"], check["ok"], check["not_in_case"]), (4, 2, 2))

    def test_txn_of_another_case_is_not_in_this_case(self):
        _, _, rows = self.source(rows=1)
        [r] = C.resolve_citations(self.db, self.other_case.id, C.citations_in(f"[a](txn://{rows[0].id})"))
        self.assertEqual((r.status, r.reason), ("not_in_case", C.NOT_IN_CASE))

    def test_rec_without_phone_records_is_not_in_case(self):
        [r] = C.resolve_citations(self.db, self.case.id, C.citations_in(f"[a](rec://{uuid.uuid4()})"))
        self.assertEqual(r.status, "not_in_case")

    def test_canonicalize_pins_unique_names_and_old_payment_links_only(self):
        unique = self._file("Unique.pdf")
        self._file("Twice.pdf")
        self._file("Twice.pdf")
        _, _, rows = self.source(rows=1)
        old = f"/cases/{self.case.id}/financial?view=transactions&payment={rows[0].id}"
        text = (f"[u](doc://Unique.pdf/4) [n](doc://Unique.pdf) [t](doc://Twice.pdf/2) [m](doc://Missing.pdf/1) "
                f"[p]({old})")
        out = C.canonicalize(self.db, self.case.id, text)
        self.assertIn(f"[u](doc://{unique.id}/4)", out)
        self.assertIn(f"[n](doc://{unique.id})", out)  # no page stays no page
        self.assertIn("[t](doc://Twice.pdf/2)", out)
        self.assertIn("[m](doc://Missing.pdf/1)", out)
        self.assertIn(f"[p](txn://{rows[0].id})", out)

    def test_agent_answer_is_stored_pinned_and_checked(self):
        from services.agent.storage import checked_answer
        unique = self._file("Unique.pdf")
        _, _, rows = self.source(rows=1)
        missing = uuid.uuid4()
        answer, check = checked_answer(self.db, case_id=self.case.id, answer=(
            f"Paid [12 Mar](txn://{rows[0].id}) per [Unique.pdf, p.2](doc://Unique.pdf/2); "
            f"also [a row](txn://{missing})."))
        self.assertIn(f"(doc://{unique.id}/2)", answer)
        self.assertEqual((check["total"], check["ok"], check["not_in_case"]), (3, 2, 1))
        self.assertEqual(check["problems"][0]["href"], f"txn://{missing}")
        self.assertEqual(check["problems"][0]["reason"], C.NOT_IN_CASE)


class ChatSourceListTests(unittest.TestCase):
    def test_a_passage_without_a_page_is_not_listed_as_page_one(self):
        from services.rag_service import RAGService
        rag = object.__new__(RAGService)
        fid = str(uuid.uuid4())
        text = rag._format_document_summary([
            {"metadata": {"filename": "No page.pdf"}, "distance": 0.1},
            {"metadata": {"filename": "Paged.pdf", "page_start": 4, "evidence_file_id": fid}, "distance": 0.2},
        ])
        self.assertIn("(doc://No%20page.pdf)", text)
        self.assertNotIn("No%20page.pdf/1", text)
        self.assertIn(f"(doc://{fid}/4)", text)


class LedgerRowCitationTests(LedgerToolFixture):
    def test_each_row_cites_itself_and_its_statement_page(self):
        document, _, rows = self.source(rows=2)
        rows[0].provenance = {**(rows[0].provenance or {}), "locator": {"kind": "page_only", "page": 3}}
        self.db.commit()
        items = {i["transaction_id"]: i for i in self.read()["items"]}
        paged, unpaged = items[str(rows[0].id)], items[str(rows[1].id)]
        self.assertEqual(paged["cite"], f"txn://{rows[0].id}")
        self.assertEqual(paged["statement_cite"], f"doc://{document.evidence_file_id}/3")
        self.assertEqual(unpaged["statement_page"], None)
        self.assertEqual(unpaged["statement_cite"], f"doc://{document.evidence_file_id}")
        self.assertNotIn("financial_href", paged)


if __name__ == "__main__":
    unittest.main()
