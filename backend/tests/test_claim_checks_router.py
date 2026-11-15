"""Unchecked claims per file of a case, for the evidence screen's notice (lx-citeproof D)."""
import uuid

from sqlalchemy import text

from postgres.models.evidence import EvidenceFile
from routers.claim_checks import unchecked_counts
from tests.test_agent_financial_ledger_tools import LedgerToolFixture


class UncheckedCountTests(LedgerToolFixture):
    def test_counts_per_file_smallest_first_and_only_this_case(self):
        self.assertEqual(unchecked_counts(self.db, self.case.id)["unchecked"], 0)  # no table: nothing to show
        self.db.execute(text("CREATE TABLE evidence_claims (id TEXT, case_id TEXT, evidence_file_id TEXT, status TEXT)"))
        big, small = (EvidenceFile(id=uuid.uuid4(), case_id=self.case.id, original_filename=name,
                                   stored_path=f"/e/{name}", sha256=str(i) * 64) for i, name in ((1, "big.pdf"),
                                                                                                    (2, "small.pdf")))
        self.db.add_all([big, small])
        rows = [(big.id, "unreviewed")] * 3 + [(small.id, "unreviewed"), (small.id, "verified")]
        for i, (file_id, status) in enumerate(rows):
            self.db.execute(text("INSERT INTO evidence_claims VALUES (:i, :c, :f, :s)"),
                            {"i": str(i), "c": str(self.case.id), "f": file_id.hex, "s": status})  # as SQLite stores a uuid
        self.db.execute(text("INSERT INTO evidence_claims VALUES ('x', :c, :f, 'unreviewed')"),
                        {"c": str(self.other_case.id), "f": big.id.hex})
        self.db.commit()
        found = unchecked_counts(self.db, self.case.id)
        self.assertEqual(found["unchecked"], 4)
        self.assertEqual([(f["filename"], f["unchecked"]) for f in found["files"]], [("small.pdf", 1), ("big.pdf", 3)])
        self.assertEqual(found["files"][0]["evidence_file_id"], str(small.id))
