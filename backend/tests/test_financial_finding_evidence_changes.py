"""A finding says when a cited payment changed since it was cited; its saved citation stays as saved."""
from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy import select

from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_transaction_number import FinancialTransactionNumber
from postgres.models.workspace_entry import (
    WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink, WorkspaceEntryRevision,
)
from services.financial.finding_evidence_changes import (
    MAX_ENTRIES, EvidenceChangeError, finding_evidence_changes,
)
from services.financial.ledger_source import ledger_source
from services.workspace_entry_service import create_entry, get_entry
from tests.test_financial_duplicates import DuplicateTestCase


class EvidenceChangeFixture(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[
            FinancialTransactionNumber.__table__, WorkspaceEntry.__table__, WorkspaceEntryRevision.__table__,
            WorkspaceEntryLink.__table__, WorkspaceEntryEvent.__table__])
        document = self.make_copy()
        self.rows = list(self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == document.id).order_by(FinancialTransaction.row_index)))
        self.file_id = str(document.evidence_file_id)

    def finding(self, rows, saved=True):
        sources = [ledger_source(self.db, case_id=self.case.id, transaction_id=row.id) for row in rows]
        metadata = {"schema": "loupe.financial.payment_selection/1"}
        if saved:
            metadata["transactions"] = [source["transaction"] for source in sources]
        return create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note", title="F",
                            body="Body", tags=["financial"], links=[{
                                "target_type": "evidence", "target_id": self.file_id, "relationship": "context",
                                "source_anchor": {"financial_transaction_ids": [str(r.id) for r in rows],
                                                  "financial_ref_ids": [r.ref_id for r in rows]},
                                "metadata": metadata}])

    def read(self, entry):
        return finding_evidence_changes(self.db, case_id=self.case.id, entry_ids=[entry["id"]])["entries"][entry["id"]]

    def replacement(self, row, **values):
        columns = {c.key: getattr(row, c.key) for c in FinancialTransaction.__mapper__.column_attrs}
        new = FinancialTransaction(**{**columns, "id": uuid4(), "ref_id": row.ref_id + "-c", "row_index": 900,
                                      "content_hash": uuid4().hex * 2, **values})
        self.db.add(new)
        self.db.flush()
        row.ledger_status, row.superseded_by_id = "superseded", new.id
        self.db.commit()
        return new


class EvidenceChangeTests(EvidenceChangeFixture):
    def test_an_unchanged_citation_reports_nothing(self):
        entry = self.finding(self.rows[:2])
        self.assertEqual(self.read(entry), {"cited": 2, "not_compared": 0, "changed": []})

    def test_a_correction_is_followed_to_the_current_row_and_says_what_changed(self):
        entry = self.finding(self.rows[:1])
        before = deepcopy(entry["links"])
        old = self.rows[0].amount_minor
        new = self.replacement(self.rows[0], amount_minor=old + 500)
        result = self.read(entry)
        self.assertEqual(len(result["changed"]), 1)
        change = result["changed"][0]
        self.assertEqual((change["state"], change["current_id"]), ("corrected", str(new.id)))
        self.assertEqual(change["ref_id"], self.rows[0].ref_id)
        self.assertEqual(change["changes"], [{"field": "amount_minor", "label": "Amount", "cited": str(old),
                                              "current": str(old + 500)}])
        self.assertEqual(get_entry(self.db, case_id=self.case.id, entry_id=UUID(entry["id"]))["links"], before)

    def test_a_chain_of_corrections_ends_at_the_last_row(self):
        entry = self.finding(self.rows[:1])
        first = self.replacement(self.rows[0], description="Second reading")
        last = self.replacement(first, description="Third reading", ref_id="last")
        change = self.read(entry)["changed"][0]
        self.assertEqual(change["current_id"], str(last.id))
        self.assertEqual(change["changes"][0]["current"], "Third reading")

    def test_a_payment_set_aside_or_removed_is_named(self):
        entry = self.finding(self.rows[:2])
        self.rows[0].ledger_status = "superseded"
        self.db.commit()
        changed = self.read(entry)["changed"]
        self.assertEqual([c["state"] for c in changed], ["set_aside"])
        link = self.db.scalar(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id == UUID(entry["id"])))
        gone = str(uuid4())
        link.source_anchor = {**link.source_anchor, "financial_transaction_ids": [gone]}
        self.db.commit()
        self.assertEqual([(c["state"], c["transaction_id"]) for c in self.read(entry)["changed"]], [("missing", gone)])

    def test_a_label_a_person_saved_counts_and_a_description_guess_does_not(self):
        entry = self.finding(self.rows[:1])
        self.assertEqual(self.read(entry)["changed"], [])
        self.rows[0].metadata_ = {**(self.rows[0].metadata_ or {}), "investigation_labels": {"category": "Rent"}}
        self.db.commit()
        change = self.read(entry)["changed"][0]
        self.assertEqual(change["state"], "changed")
        self.assertEqual([(c["field"], c["current"]) for c in change["changes"]], [("category", "Rent")])

    def test_a_model_reading_stays_labelled(self):
        entry = self.finding(self.rows[:1])
        self.rows[0].description = "MODEL LINE rest"
        self.rows[0].provenance = {**(self.rows[0].provenance or {}), "reader_descriptions": {
            "basis": "page_image_first_line", "first_line": {"before": "x", "after": "MODEL LINE"},
            "origin": {"model": "TestModel"}}}
        self.db.commit()
        change = self.read(entry)["changed"][0]["changes"][0]
        self.assertEqual(change["reading"], "Read by TestModel · not confirmed")

    def test_a_citation_with_no_saved_values_is_counted_not_called_clean(self):
        entry = self.finding(self.rows[:1], saved=False)
        self.assertEqual(self.read(entry), {"cited": 1, "not_compared": 1, "changed": []})

    def test_another_case_and_a_deleted_finding_show_nothing(self):
        entry = self.finding(self.rows[:1])
        other = finding_evidence_changes(self.db, case_id=self.other_case.id, entry_ids=[entry["id"]])
        self.assertEqual(other["entries"][entry["id"]], {"cited": 0, "not_compared": 0, "changed": []})

    def test_more_findings_than_a_request_takes_are_refused(self):
        with self.assertRaises(EvidenceChangeError):
            finding_evidence_changes(self.db, case_id=self.case.id, entry_ids=[str(uuid4()) for _ in range(MAX_ENTRIES + 1)])


class TheoryCitationChangeTests(EvidenceChangeFixture):
    """A theory's payment links and ledger groups say when a cited payment changed (lx-theorycase B)."""

    def setUp(self):
        super().setUp()
        from postgres.models.case_selection import CaseSelection
        from postgres.models.collection_membership import CollectionMembership
        from postgres.models.theory_narrative import TheoryNarrative
        Base.metadata.create_all(self.engine, tables=[CaseSelection.__table__, CollectionMembership.__table__,
                                                      TheoryNarrative.__table__])
        self.theory = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="theory",
                                   title="T", body="Acme pays Ann")

    def add(self, **kw):
        from services import theory_additions as T
        return T.add(self.db, case_id=self.case.id, entry_id=self.theory["id"], user=self.user, **kw)

    def test_a_single_payment_link_keeps_its_cited_values_and_shows_the_value_as_cited_beside_now(self):
        row = self.rows[0]
        result = self.add(surface="financial", relationship="contradicts",
                          items=[{"target_type": "financial_transaction", "target_id": str(row.id)}])
        link_id = result["added_link_ids"][0]
        self.assertEqual(self.read(self.theory), {"cited": 1, "not_compared": 0, "changed": []})
        old = row.amount_minor
        new = self.replacement(row, amount_minor=old + 250)
        change = self.read(self.theory)["changed"][0]
        self.assertEqual((change["state"], change["current_id"], change["link_id"]), ("corrected", str(new.id), link_id))
        self.assertEqual(change["changes"], [{"field": "amount_minor", "label": "Amount", "cited": str(old),
                                              "current": str(old + 250)}])

    def test_a_resave_cannot_rewrite_or_drop_the_cited_values(self):
        from services.workspace_entry_service import update_entry
        row = self.rows[0]
        self.add(surface="financial", items=[{"target_type": "financial_transaction", "target_id": str(row.id)}])
        entry = get_entry(self.db, case_id=self.case.id, entry_id=UUID(self.theory["id"]))
        links = [{**link, "metadata": {**link["metadata"], "cited": {"amount_minor": 1}}} for link in entry["links"]]
        update_entry(self.db, case_id=self.case.id, entry_id=UUID(self.theory["id"]), current_user=self.user,
                     expected_version=entry["version"], links=links)
        saved = get_entry(self.db, case_id=self.case.id, entry_id=UUID(self.theory["id"]))["links"][0]["metadata"]
        self.assertEqual(saved["cited"]["amount_minor"], row.amount_minor)

    def test_payments_in_a_ledger_group_are_compared_member_by_member(self):
        rows = self.rows[:2]
        result = self.add(surface="financial", group={
            "group_type": "financial_selection", "words": "two payments", "how": {},
            "members": [{"type": "financial_transaction", "id": str(r.id)} for r in rows]})
        self.assertEqual(self.read(self.theory), {"cited": 2, "not_compared": 0, "changed": []})
        self.replacement(rows[1], description="CORRECTED WORDS")
        changed = self.read(self.theory)["changed"]
        self.assertEqual(len(changed), 1)
        self.assertEqual((changed[0]["transaction_id"], changed[0]["link_id"]), (str(rows[1].id), result["added_link_ids"][0]))
        self.assertEqual([c["field"] for c in changed[0]["changes"]], ["description"])
        self.assertEqual(changed[0]["changes"][0]["current"], "CORRECTED WORDS")
