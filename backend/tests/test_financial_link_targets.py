"""Money as link targets: a pin holds a message, the payment and its statement page; a model draft shows its origin."""
import uuid
from unittest.mock import patch

from postgres.base import Base
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import (
    WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink, WorkspaceEntryRevision, WorkspaceLegacyMapping,
)
from postgres import link_types
from services.workspace_entry_service import (
    WorkspaceEntryValidationError, create_entry, list_financial_payment_links, search_attachment_options,
)
from tests.test_agent_financial_ledger_tools import LedgerToolFixture


class FinancialLinkTargetTests(LedgerToolFixture):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in (
            CaseProfile, CaseDeadline, CaseTask, WorkspaceEntry, WorkspaceEntryRevision, WorkspaceEntryLink,
            WorkspaceEntryEvent, WorkspaceLegacyMapping)])

    def test_the_registry_offers_money_to_workspace_and_dossiers(self):
        for kind in ("financial_account", "financial_party", "financial_transaction"):
            self.assertIn(kind, link_types.WORKSPACE_TYPES)
            self.assertIn(kind, link_types.DOSSIER_TYPES)

    def test_a_pin_holds_message_payment_and_statement_page_as_one_bundle(self):
        document, _, rows = self.source(rows=1, amount=123456)
        rows[0].description = "Wire to ACME"
        self.db.commit()
        record = str(uuid.uuid4())
        phone = link_types.PhoneTarget(label="C3 WhatsApp message", mapping_versions={"m": 1})
        link_types.register_phone_resolver("phone_record", lambda db, case_id, target_id: phone)
        try:
            entry = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="finding",
                                 title="Paid the day after the message", body="Bundle", links=[
                {"target_type": "phone_record", "target_id": record, "relationship": "supports"},
                {"target_type": "financial_transaction", "target_id": str(rows[0].id).upper(), "relationship": "supports"},
                {"target_type": "evidence", "target_id": str(document.evidence_file_id), "relationship": "supports",
                 "source_anchor": {"page": 3, "cite": f"doc://{document.evidence_file_id}/3"}},
            ])
        finally:
            link_types.unregister_phone_resolver("phone_record")
        links = {link["target_type"]: link for link in entry["links"]}
        self.assertEqual(set(links), {"phone_record", "financial_transaction", "evidence"})
        payment = links["financial_transaction"]
        self.assertEqual(payment["target_id"], str(rows[0].id))
        self.assertEqual(payment["source_anchor"]["cite"], f"txn://{rows[0].id}")
        self.assertIn("1234.56", payment["target_label"])
        self.assertIn("Wire to ACME", payment["target_label"])
        self.assertEqual(links["evidence"]["source_anchor"]["page"], 3)
        # the payment's details list the finding that holds it
        index = list_financial_payment_links(self.db, case_id=self.case.id)
        self.assertEqual(index["entries"][0]["payment_ids"], [str(rows[0].id)])

    def test_a_payment_or_account_of_another_case_is_refused(self):
        _, _, rows = self.source(rows=1)
        for kind, target in (("financial_transaction", rows[0].id), ("financial_account", self.account.id)):
            with self.assertRaises(WorkspaceEntryValidationError) as raised:
                create_entry(self.db, case_id=self.other_case.id, current_user=self.user, entry_type="note", body="x",
                             links=[{"target_type": kind, "target_id": str(target)}])
            self.assertIn("is not in this case", str(raised.exception))

    def test_attachment_search_finds_payments_and_accounts(self):
        _, _, rows = self.source(rows=1)
        rows[0].description = "Wire to ACME"
        self.db.commit()
        found = search_attachment_options(self.db, case_id=self.case.id, target_type="financial_transaction",
                                          query_text="acme")
        self.assertEqual([f["target_id"] for f in found], [str(rows[0].id)])
        self.assertEqual(found[0]["metadata"]["cite"], f"txn://{rows[0].id}")
        accounts = search_attachment_options(self.db, case_id=self.case.id, target_type="financial_account",
                                             query_text="Synthetic company")
        self.assertEqual([a["target_id"] for a in accounts], [str(self.account.id)])

    def test_a_model_drafted_entry_shows_it_was_drafted_and_who_accepted_it(self):
        origin = {"kind": "model", "model": "DeepSeek V4 Pro", "model_id": "deepseek-v4-pro",
                  "for": {"name": "Investigator", "user_id": str(self.user.id)}}
        accepted = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note",
                                body="Drafted text", actor_origin=origin)
        self.assertEqual(accepted["origin_label"], "Drafted by DeepSeek V4 Pro, accepted by Investigator")
        self.assertEqual(accepted["actor_origin"]["model_id"], "deepseek-v4-pro")
        pending = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note",
                               body="Drafted text", actor_origin=origin, review_state="pending")
        self.assertEqual(pending["origin_label"], "Drafted by DeepSeek V4 Pro, not yet accepted by a person")
        own = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note", body="Mine")
        self.assertIsNone(own["origin_label"])
        with self.assertRaises(WorkspaceEntryValidationError):
            create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note", body="x",
                         actor_origin={"kind": "person", "model": "x"})
