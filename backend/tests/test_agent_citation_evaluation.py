"""Citation evaluation: every citation the agent's tools hand the model, and every citation an answer can carry, opens
the object it names. Scored as citations right / total.

The known objects are written by hand from the synthetic case below (which payment, which file, which page, or
"not in this case" / "choose a file"), not computed by the code under test. Each question takes its citations from
the layer the model copies them from (the ledger tool's ``cite`` and ``statement_cite``, the payments search group,
a document passage's ``cite``) or, for answers the model may write in older or wrong forms, from a fixed answer text;
each citation is then resolved the way the answer check and the renderer resolve it. Set LOUPE_CITATION_EVAL_OUT to
a file path to write one JSON line per question.
"""
import json
import os
import uuid

from postgres.models.evidence import EvidenceFile
from services import case_citations as C
from services.search.payments import search_payments
from tests.test_agent_financial_ledger_tools import LedgerToolFixture


class CitationEvaluation(LedgerToolFixture):
    def _file(self, name, case=None):
        self._file_index += 1
        file = EvidenceFile(id=uuid.uuid4(), case_id=(case or self.case).id, original_filename=name,
                            stored_path=f"/evidence/{uuid.uuid4()}", sha256=f"{self._file_index:064d}")
        self.db.add(file)
        self.db.commit()
        return file

    def _case(self):
        """Two statements on two accounts; rows at known pages (one row with no page); five evidence files, two of
        them sharing a name; a statement and a payment in another case."""
        self.bank_doc, _, bank = self.source(rows=3, amount=10000)
        self.card_doc, _, card = self.source(account=self.card, currency="USD", rows=2, amount=50000)
        pages = {bank[0].id: 2, bank[1].id: 2, bank[2].id: None, card[0].id: 5, card[1].id: 6}
        for row, text in zip(bank + card, ("Wire to ACME Ltd", "Rent March", "ACME refund", "Hotel Lisbon", "Fuel")):
            row.description = text
            page = pages[row.id]
            row.provenance = {**(row.provenance or {}), "locator": {"kind": "page_only", "page": page} if page
                              else {"kind": "none"}}
        self.db.commit()
        self.rows = {row.description: row for row in bank + card}
        self.pages = pages
        self.doc_of = {row.id: (self.bank_doc if row in bank else self.card_doc).evidence_file_id for row in bank + card}
        self.memo = self._file("Board memo.pdf")
        self.shared = [self._file("Scan.pdf"), self._file("Scan.pdf")]
        self.foreign_doc, _, foreign = self.source(rows=1)
        self.foreign_row = foreign[0]
        # move the third statement and its row to the other case
        self.foreign_row.case_id = self.other_case.id
        for obj in (self.foreign_doc,):
            obj.case_id = self.other_case.id
        self.db.get(EvidenceFile, self.foreign_doc.evidence_file_id).case_id = self.other_case.id
        self.db.commit()

    def _score(self, question, hrefs, expected):
        """``expected[href]`` is the known object: ("txn", id, page) / ("doc", file id, page or None) /
        ("ambiguous", {file ids}) / ("not_in_case",)."""
        resolved = {r.href: r for r in C.resolve_citations(self.db, self.case.id,
                                                           [C.parse_citation(h) for h in hrefs])}
        right, misses = 0, []
        for href in hrefs:
            r, want = resolved.get(href), expected[href]
            if want[0] == "txn":
                ok = (r and r.status == "ok" and r.transaction_id == str(want[1]) and r.page == want[2]
                      and r.evidence_file_id == str(self.doc_of[want[1]]))
            elif want[0] == "doc":
                ok = r and r.status == "ok" and r.evidence_file_id == str(want[1]) and r.page == want[2]
            elif want[0] == "ambiguous":
                ok = r and r.status == "ambiguous" and {c["evidence_file_id"] for c in r.candidates} == {
                    str(i) for i in want[1]}
            else:
                ok = r and r.status == "not_in_case"
            right += bool(ok)
            if not ok:
                misses.append(href)
        self.table.append({"question": question, "citations": len(hrefs), "right": right, "misses": misses})

    def test_every_citation_opens_the_object_it_names(self):
        self._case()
        self.table = []
        T = self.rows
        txn = lambda row: ("txn", row.id, self.pages[row.id])

        items = self.read()["items"]
        self._score("Which payments are in the ledger? (ledger rows, cite)",
                    [i["cite"] for i in items], {i["cite"]: txn(self.db.get(type(T["Fuel"]), uuid.UUID(i["transaction_id"])))
                                                 for i in items})
        statement = {}
        for i in items:
            row_id = uuid.UUID(i["transaction_id"])
            statement[i["statement_cite"]] = ("doc", self.doc_of[row_id], self.pages[row_id])
        self._score("On which statement page is each payment? (ledger rows, statement_cite)",
                    list(statement), statement)
        card = self.read(account_ids=[str(self.card.id)])["items"]
        self._score("Which payments are on the card? (account filter)", [i["cite"] for i in card],
                    {i["cite"]: txn(T[i["description"]]) for i in card})
        with self.engine.connect() as conn:
            _, hits, _ = search_payments(conn, self.case.id, "acme")
            _, by_amount, _ = search_payments(conn, self.case.id, "500.01")
        self._score("Find the ACME payments (payments search)", [h["cite"] for h in hits],
                    {h["cite"]: txn(T[h["title"]]) for h in hits})
        self._score("Find the payment of 500.01 (payments search by amount)", [h["cite"] for h in by_amount],
                    {h["cite"]: txn(T[h["title"]]) for h in by_amount})
        passages = [{"filename": "Board memo.pdf", "evidence_file_id": str(self.memo.id), "page_start": 4},
                    {"filename": "Board memo.pdf", "evidence_file_id": str(self.memo.id)}]
        self._score("What does the board memo say? (document passages, cite)",
                    [C.chunk_cite(p) for p in passages],
                    {C.chunk_cite(passages[0]): ("doc", self.memo.id, 4), C.chunk_cite(passages[1]): ("doc", self.memo.id, None)})
        # answers in older forms, and wrong ones, as a model may write them
        legacy = f"/cases/{self.case.id}/financial?view=transactions&payment={T['Rent March'].id}"
        older = {f"doc://Board%20memo.pdf/3": ("doc", self.memo.id, 3), "doc://Scan.pdf/2": ("ambiguous", [f.id for f in self.shared]),
                 legacy: txn(T["Rent March"]), "evidence://Board memo.pdf": ("doc", self.memo.id, None)}
        self._score("Answer with filename citations and an old payment link", list(older), older)
        wrong = {f"txn://{self.foreign_row.id}": ("not_in_case",), f"doc://{self.foreign_doc.evidence_file_id}/1": ("not_in_case",),
                 f"txn://{uuid.uuid4()}": ("not_in_case",), "doc://Invented.pdf/9": ("not_in_case",),
                 f"/cases/{self.other_case.id}/financial?view=transactions&payment={self.foreign_row.id}": ("not_in_case",)}
        self._score("Answer citing another case's statement and invented objects", list(wrong), wrong)
        # the stored answer: names pinned to file ids, the check counts what it marks
        answer, check = __import__("services.agent.storage", fromlist=["x"]).checked_answer(
            self.db, case_id=self.case.id, answer=" ".join(f"[c]({h})" for h in [*older, *wrong]))
        self.assertIn(f"(doc://{self.memo.id}/3)", answer)
        # "[c](evidence://Board memo.pdf)" holds a space, so in answer text it is not a link (both parsers agree)
        self.assertEqual((check["total"], check["not_in_case"], check["ambiguous"]), (8, 5, 1))

        total = sum(q["citations"] for q in self.table)
        right = sum(q["right"] for q in self.table)
        out = os.environ.get("LOUPE_CITATION_EVAL_OUT")
        if out:
            with open(out, "w") as handle:
                for line in self.table:
                    handle.write(json.dumps(line) + "\n")
                handle.write(json.dumps({"total": total, "right": right}) + "\n")
        self.assertEqual(len(self.table), 8)
        self.assertGreaterEqual(total, 25)
        self.assertEqual([q for q in self.table if q["misses"]], [])
        self.assertEqual(right, total)
