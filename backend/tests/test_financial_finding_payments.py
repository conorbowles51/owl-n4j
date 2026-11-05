"""Adding payments to a saved finding: the new ones are cited, what it already cites stays as saved."""
from copy import deepcopy
from uuid import UUID

from sqlalchemy import select

from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_transaction_number import FinancialTransactionNumber
from postgres.models.workspace_entry import (
    WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink, WorkspaceEntryRevision,
)
from services.workspace_entry_service import (
    WorkspaceEntryConflict, WorkspaceEntryValidationError, add_financial_payments, create_entry, get_entry,
)
from tests.test_financial_duplicates import DuplicateTestCase

SCHEMA = "loupe.financial.payment_selection/1"


class FindingPaymentTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[
            FinancialTransactionNumber.__table__, WorkspaceEntry.__table__, WorkspaceEntryRevision.__table__,
            WorkspaceEntryLink.__table__, WorkspaceEntryEvent.__table__])
        self.document = self.make_copy()
        self.file_id = str(self.document.evidence_file_id)
        self.rows = list(self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.document.id).order_by(FinancialTransaction.row_index)))
        self.assertGreaterEqual(len(self.rows), 2)

    def snapshot(self, row):
        return {"key": str(row.id), "case_id": str(self.case.id), "amount_minor": "111", "description": "As cited"}

    def finding(self, cited=(), tags=("financial", "financial-workspace"), metadata=None):
        links = []
        if cited:
            links = [{"target_type": "evidence", "target_id": self.file_id, "target_label": "statement.pdf",
                      "relationship": "context",
                      "source_anchor": {"financial_transaction_ids": [str(r.id) for r in cited],
                                        "financial_ref_ids": [r.ref_id for r in cited]},
                      "metadata": metadata or {"schema": SCHEMA, "transactions": [self.snapshot(r) for r in cited]}}]
        return create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note",
                            title="Observation", body="What the records show", tags=list(tags), links=links)

    def add(self, entry, ids, version=None):
        return add_financial_payments(self.db, case_id=self.case.id, entry_id=UUID(entry["id"]),
                                      current_user=self.user, expected_version=version or entry["version"],
                                      transaction_ids=[str(i) for i in ids])

    def test_a_finding_with_no_payments_gains_a_cited_link(self):
        entry = self.finding()
        result = self.add(entry, [self.rows[0].id])
        self.assertEqual((result["added"], result["already_cited"]), (1, 0))
        link = result["entry"]["links"][0]
        self.assertEqual((link["target_type"], link["target_id"]), ("evidence", self.file_id))
        self.assertEqual(link["source_anchor"]["financial_transaction_ids"], [str(self.rows[0].id)])
        self.assertEqual(link["source_anchor"]["financial_ref_ids"], [self.rows[0].ref_id])
        self.assertEqual(link["metadata"]["schema"], SCHEMA)
        self.assertEqual(link["metadata"]["transactions"][0]["key"], str(self.rows[0].id))
        self.assertEqual(result["entry"]["version"], entry["version"] + 1)

    def test_payments_from_a_file_already_linked_are_appended_and_saved_citations_do_not_change(self):
        """The link is unique per file, so a link-add skips this payment as 'already linked'; it must be cited."""
        entry = self.finding(cited=[self.rows[0]])
        before = deepcopy(entry["links"][0])
        self.rows[0].description = "Corrected since it was cited"
        self.db.commit()
        result = self.add(entry, [self.rows[1].id])
        self.assertEqual(result["added"], 1)
        self.assertEqual(len(result["entry"]["links"]), 1)
        link = result["entry"]["links"][0]
        self.assertEqual(link["id"], before["id"])
        self.assertEqual(link["source_anchor"]["financial_transaction_ids"],
                         [*before["source_anchor"]["financial_transaction_ids"], str(self.rows[1].id)])
        self.assertEqual(link["source_anchor"]["financial_ref_ids"],
                         [*before["source_anchor"]["financial_ref_ids"], self.rows[1].ref_id])
        self.assertEqual(link["metadata"]["transactions"][0], before["metadata"]["transactions"][0])
        self.assertEqual(link["metadata"]["transactions"][1]["key"], str(self.rows[1].id))

    def test_a_payment_already_cited_is_counted_not_captured_again(self):
        entry = self.finding(cited=[self.rows[0]])
        result = self.add(entry, [self.rows[0].id])
        self.assertEqual((result["added"], result["already_cited"]), (0, 1))
        self.assertEqual(result["entry"]["version"], entry["version"])
        self.assertEqual(result["entry"]["links"], entry["links"])

    def test_one_event_records_who_what_and_when_and_a_revision_follows(self):
        entry = self.finding(cited=[self.rows[0]])
        self.add(entry, [self.rows[0].id, self.rows[1].id])
        events = list(self.db.scalars(select(WorkspaceEntryEvent).where(
            WorkspaceEntryEvent.entry_id == UUID(entry["id"]), WorkspaceEntryEvent.event_type == "link_added")))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor_user_id, self.user.id)
        self.assertEqual(events[0].rationale, "Added selected payments to this finding")
        self.assertEqual(events[0].after_state["added"], 1)
        self.assertEqual(events[0].after_state["skipped"], 1)
        self.assertEqual(events[0].after_state["transaction_ids"], [str(self.rows[1].id)])
        self.assertEqual(events[0].after_state["ref_ids"], [self.rows[1].ref_id])
        self.assertIsNotNone(events[0].created_at)
        revisions = list(self.db.scalars(select(WorkspaceEntryRevision).where(
            WorkspaceEntryRevision.entry_id == UUID(entry["id"]))))
        self.assertEqual(max(r.revision_number for r in revisions), entry["version"] + 1)

    def test_a_stale_version_is_refused_and_nothing_is_added(self):
        entry = self.finding(cited=[self.rows[0]])
        with self.assertRaises(WorkspaceEntryConflict):
            self.add(entry, [self.rows[1].id], version=entry["version"] + 5)
        self.assertEqual(get_entry(self.db, case_id=self.case.id, entry_id=UUID(entry["id"]))["links"], entry["links"])

    def test_a_payment_no_longer_current_refuses_the_whole_request(self):
        entry = self.finding()
        self.rows[1].ledger_status = "superseded"
        self.db.commit()
        with self.assertRaises(WorkspaceEntryConflict):
            self.add(entry, [self.rows[0].id, self.rows[1].id])
        self.db.rollback()
        self.assertEqual(get_entry(self.db, case_id=self.case.id, entry_id=UUID(entry["id"]))["links"], [])

    def test_a_payment_of_another_case_is_refused(self):
        entry = self.finding()
        self.rows[0].case_id = self.other_case.id
        self.db.commit()
        with self.assertRaises(WorkspaceEntryValidationError):
            self.add(entry, [self.rows[0].id])

    def test_a_malformed_reference_and_an_empty_request_are_refused(self):
        entry = self.finding()
        for ids in (["not-a-payment"], []):
            with self.assertRaises(WorkspaceEntryValidationError):
                self.add(entry, ids)

    def test_a_saved_report_and_a_non_financial_entry_do_not_take_payments(self):
        for tags in (("financial", "financial-report"), ("other",)):
            with self.assertRaises(WorkspaceEntryValidationError):
                self.add(self.finding(tags=tags), [self.rows[0].id])

    def test_a_selection_carrying_an_analysis_keeps_what_the_analysis_read(self):
        entry = self.finding(cited=[self.rows[0]], metadata={"schema": SCHEMA, "analysis": {"summary": "One payment"},
                                                             "transactions": [self.snapshot(self.rows[0])]})
        before = deepcopy(entry["links"][0])
        result = self.add(entry, [self.rows[1].id])
        kept = next(l for l in result["entry"]["links"] if l["id"] == before["id"])
        self.assertEqual(kept["source_anchor"], before["source_anchor"])
        self.assertEqual(kept["metadata"], before["metadata"])
        added = next(l for l in result["entry"]["links"] if l["id"] != before["id"])
        self.assertEqual((added["target_type"], added["target_id"]), ("financial_transaction", str(self.rows[1].id)))

    def test_a_saved_analysis_on_the_same_file_keeps_its_own_anchor(self):
        entry = self.finding(cited=[self.rows[0]], metadata={"schema": "loupe.financial.saved_trace/1", "envelope": {}})
        before = deepcopy(entry["links"][0])
        result = self.add(entry, [self.rows[1].id])
        kept = next(l for l in result["entry"]["links"] if l["id"] == before["id"])
        self.assertEqual(kept["source_anchor"], before["source_anchor"])
        self.assertEqual(kept["metadata"], before["metadata"])
        added = next(l for l in result["entry"]["links"] if l["id"] != before["id"])
        self.assertEqual((added["target_type"], added["target_id"]), ("financial_transaction", str(self.rows[1].id)))
        self.assertEqual(added["source_anchor"]["financial_transaction_ids"], [str(self.rows[1].id)])
        self.assertEqual(added["source_anchor"]["cite"], f"txn://{self.rows[1].id}")
        self.assertEqual(added["metadata"]["transactions"][0]["key"], str(self.rows[1].id))
