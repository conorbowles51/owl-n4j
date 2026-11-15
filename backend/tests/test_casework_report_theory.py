"""The casework report carries a theory's for and against, its reasons, its model readings, its counter-arguments, its
production numbers and its timeline (lx-theorycase C). SQLite on the ledger fixture, so payments are real rows."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest import mock

from postgres.base import Base
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.evidence import EvidenceFile
from postgres.models.workspace_ai import WorkspaceAIOutput
from services import case_selections, casework_report as cr, casework_report_facts as facts, theory_additions as T
from services.workspace_entry_service import add_entry_links, create_entry, get_entry
from tests.test_financial_duplicates import DuplicateTestCase
from tests.test_theory_additions import EXTRA, stub

PRODUCTION = [Base.metadata.tables[name] for name in (
    "production_sets", "production_assignments", "received_numbers", "production_stamped_copies")]


class CaseworkReportTheoryTests(DuplicateTestCase):
    def add(self, **kw):
        return T.add(self.db, case_id=self.case.id, entry_id=self.theory["id"], user=self.user, **kw)

    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=EXTRA + [CaseMandateVersion.__table__, CaseContext.__table__,
                                                          WorkspaceAIOutput.__table__] + PRODUCTION)
        patcher = mock.patch.object(case_selections, "graph_event_dates", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)
        document = self.make_document()
        period = self.make_period(document)
        self.rows = [self.add_row(period, document, amount=amount) for amount in (120_00, 75_50, 9_99)]
        self.theory = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="theory",
                                   title="Acme pays Ann", body="Acme routes money to Ann through small payments")
        self.pay = self.rows[0]
        # A payment against the theory, with the person's reason, and the model's reading of it.
        self.payment_add = self.add(surface="financial", relationship="contradicts", why="the money goes the other way",
                                    items=[{"target_type": "financial_transaction", "target_id": str(self.pay.id)}])
        T.infer_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"],
                          link_id=self.payment_add["added_link_ids"][0], user=self.user,
                          generator=stub("The payment leaves Ann's account [m1].", ["m1"], model="reader-model-2"))
        # A produced statement page cited for the theory: its file name states its production range.
        self.produced = EvidenceFile(id=uuid.uuid4(), case_id=self.case.id, original_filename="USA-000046.pdf",
                                     stored_path="/nowhere/USA-000046.pdf", sha256="ab" * 32, size=10)
        self.db.add(self.produced)
        self.db.commit()
        self.add(surface="evidence", relationship="supports", why="the statement names Ann",
                 items=[{"target_type": "evidence", "target_id": str(self.produced.id), "source_anchor": {"page": 1}}])
        # An accepted counter-argument: its payment link, as the proposal path saves it (no label), and its text.
        self.counter = WorkspaceAIOutput(
            id=uuid.uuid4(), case_id=self.case.id, target_type="theory", target_id=uuid.UUID(self.theory["id"]),
            output_type="counter_argument", version=1, job_status="completed", review_status="accepted",
            content={"title": "Ann repaid Acme", "body": "The March payment runs from Ann to Acme.", "strength": "strong",
                     "theory_id": self.theory["id"]},
            model_metadata={"model": "sweep-model-3"}, reviewed_by_user_id=self.user.id,
            reviewed_at=datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc))
        self.db.add(self.counter)
        self.db.commit()
        entry = get_entry(self.db, case_id=self.case.id, entry_id=uuid.UUID(self.theory["id"]))
        add_entry_links(self.db, case_id=self.case.id, entry_id=uuid.UUID(self.theory["id"]), current_user=self.user,
                        expected_version=entry["version"], ignore_existing=True, rationale="Counter-argument accepted",
                        links=[{"target_type": "financial_transaction", "target_id": str(self.rows[1].id),
                                "relationship": "contradicts",
                                "metadata": {"counter_argument": str(self.counter.id), "title": "Ann repaid Acme",
                                             "actor_origin": {"origin": {"model": "sweep-model-3"}}}}])
        # A financial finding saved from the ledger: a note with the ledger's tag.
        self.ledger_finding = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note",
                                           title="Cash out in March", body="Three withdrawals under 100",
                                           tags=["financial", "financial-entry-finding", "financial-conclusion"])

    def report_html(self, sections=("findings", "theories")):
        notes = [get_entry(self.db, case_id=self.case.id, entry_id=uuid.UUID(self.ledger_finding["id"]))]
        entries = {"findings": [], "theories": [get_entry(self.db, case_id=self.case.id,
                                                          entry_id=uuid.UUID(self.theory["id"]))]}
        if "notes" in sections:
            entries["notes"] = notes
        cr.fold_financial_findings(entries, notes)
        cr.fill_missing_link_labels(entries, lambda t, ids: facts.link_names(self.db, self.case.id, t, ids))
        facts.gather(self.db, self.case.id, entries)
        return cr.render_casework_report_html(entries, sections=list(sections), case_name="Matter A",
                                              generated_by="Investigator")

    def test_each_addition_prints_its_relationship_reason_who_and_when_and_the_model_reading_as_one(self):
        html = self.report_html()
        self.assertIn("<strong>Contradicts</strong> · Payment:", html)
        self.assertIn("Why: the money goes the other way", html)
        self.assertIn(f"Added by Investigator on {datetime.now(timezone.utc).date().isoformat()}", html)
        self.assertIn("What it shows (Model reading · reader-model-2 · not confirmed):", html)
        self.assertIn("The payment leaves Ann&#x27;s account [m1].", html)
        self.assertIn('class="narrative model"', html)

    def test_counter_argument_links_are_named_and_its_text_is_printed_as_the_models(self):
        html = self.report_html()
        self.assertNotIn("name not found", html)
        self.assertNotIn("financial_transaction", html)
        self.assertIn("From the counter-argument “Ann repaid Acme”, proposed by sweep-model-3", html)
        self.assertIn("Counter-arguments accepted (1)", html)
        self.assertIn("Model reading (sweep-model-3):</span> The March payment runs from Ann to Acme.", html)
        self.assertIn("Accepted by Investigator on 2026-11-14", html)

    def test_a_cited_page_prints_its_production_numbers_saying_what_kind_they_are(self):
        html = self.report_html()
        self.assertIn("Evidence file: USA-000046.pdf, page 1 · <span class=\"bates\">Production numbers: USA-000046", html)
        self.assertIn("suggested from the file name, not confirmed", html)

    def test_the_theory_prints_its_timeline_of_dated_items_in_date_order(self):
        html = self.report_html()
        self.assertIn("Timeline (", html)
        start = html.index("Timeline (")
        self.assertIn("Payment:", html[start:])

    def test_a_financial_finding_saved_from_the_ledger_is_under_findings_by_default_and_not_twice(self):
        html = self.report_html(sections=("findings", "theories", "notes"))
        self.assertIn("Findings (1)", html)
        self.assertIn("Financial finding, saved from the ledger", html)
        self.assertEqual(html.count("Cash out in March"), 1)
        self.assertLess(html.index("Cash out in March"), html.index("Theories ("))

    def test_a_timeline_item_with_no_name_prints_as_having_none_never_its_id(self):
        key = str(uuid.uuid4())
        entry = {"id": "t1", "entry_type": "theory", "title": "T", "body": "", "links": [],
                 "_report": {"timeline": [{"type": "graph_entity", "id": key, "label": key, "date": "2021-07-10"}],
                             "timeline_total": 1}}
        html = cr.render_casework_report_html({"theories": [entry]}, sections=["theories"], case_name="Matter A",
                                              generated_by="Investigator")
        self.assertNotIn(key, html)
        self.assertIn("2021-07-10 · Graph item: no name on record", html)
