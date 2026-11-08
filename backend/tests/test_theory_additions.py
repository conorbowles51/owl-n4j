"""Everything in a case can be added to a theory, singly or as a group, and each addition explains itself
(lx-theorybuild A, B, C, D, G, H, I). SQLite, on the ledger fixture, so ledger rows and their corrections are real.

The graph is not here: ``graph_keys_in_case`` answers from a fixed set per case, keyed on case and key together.
"""
from __future__ import annotations

import uuid
from unittest import mock

from postgres.base import Base
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.case_selection import CaseSelection
from postgres.models.collection_membership import CollectionMembership
from postgres.models.theory_narrative import TheoryNarrative
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
    WorkspaceLegacyMapping,
)
from services import case_selections, theory_additions as T
from services.workspace_entry_service import (
    WorkspaceEntryValidationError,
    add_entry_link,
    create_entry,
    get_entry,
    update_entry,
)
from tests.test_financial_duplicates import DuplicateTestCase

EXTRA = [CaseProfile.__table__, CaseDeadline.__table__, CaseTask.__table__, WorkspaceEntry.__table__,
         WorkspaceEntryRevision.__table__, WorkspaceEntryLink.__table__, WorkspaceEntryEvent.__table__,
         WorkspaceLegacyMapping.__table__, CaseSelection.__table__, CollectionMembership.__table__,
         TheoryNarrative.__table__]


def stub(narrative, citations, model="stub-model-1"):
    calls = []

    def run(prompt):
        calls.append(prompt)
        return {"narrative": narrative, "citations": citations}, {"provider": "test", "model_id": model}
    run.calls = calls
    return run


class TheoryAdditionTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=EXTRA)
        self.graph = {str(self.case.id): {"person:ann", "person:bob", "company:acme", "event:meeting-1"},
                      str(self.other_case.id): {"person:zed"}}
        patcher = mock.patch.object(case_selections, "graph_keys_in_case",
                                    side_effect=lambda case_id, keys: {k for k in keys if k in self.graph.get(case_id, set())})
        patcher.start()
        self.addCleanup(patcher.stop)
        document = self.make_document()
        period = self.make_period(document)
        self.evidence_id = document.evidence_file_id
        self.rows = [self.add_row(period, document, amount=amount) for amount in (120_00, 75_50, 9_99)]
        other_document = self.make_document(run=self.other_run, case=self.other_case)
        other_period = self.make_period(other_document, account=self.other_account, run=self.other_run)
        self.other_row = self.add_row(other_period, other_document, amount=5_00, account=self.other_account,
                                      run=self.other_run)
        self.theory = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="theory",
                                   title="Acme pays Ann", body="Acme routes money to Ann through small payments")

    # -- helpers -------------------------------------------------------------------------------------------------

    def add(self, **kw):
        return T.add(self.db, case_id=self.case.id, entry_id=self.theory["id"], user=self.user, **kw)

    def reading(self):
        return T.reading(self.db, case_id=self.case.id, entry_id=self.theory["id"])

    def loupe(self, link_id):
        return T.loupe(self.db, case_id=self.case.id, entry_id=self.theory["id"], link_id=link_id)

    def group(self, group_type, members, how, words, surface):
        return self.add(surface=surface, group={"group_type": group_type, "members": members, "how": how,
                                                "words": words})

    # -- A / B: every surface, singly and as a group ------------------------------------------------------------

    def test_graph_single_and_selection_keep_why_members_and_how(self):
        single = self.add(surface="graph", why="the hub of the payments",
                          items=[{"target_type": "graph_entity", "target_id": "person:ann", "target_label": "Ann"}])
        grp = self.group("graph_selection",
                         [{"type": "graph_entity", "id": "person:ann", "label": "Ann"},
                          {"type": "graph_entity", "id": "company:acme", "label": "Acme"},
                          {"type": "graph_entity", "id": "person:zed", "label": "Zed (other case)"}],
                         {"selection": "lasso", "filter": {"types": ["Person", "Company"]}},
                         "Ann, Acme and who they paid", "graph")
        self.assertEqual(grp["group"]["member_count"], 2)
        self.assertEqual(grp["group"]["left_out"], 1)  # the other case's entity is not kept, and it says so
        additions = {a["link_id"]: a for a in self.reading()["additions"]}
        one = additions[single["added_link_ids"][0]]
        self.assertEqual((one["kind"], one["surface"], one["why"], one["added_by"]),
                         ("single", "graph", "the hub of the payments", "Investigator"))
        two = additions[grp["added_link_ids"][0]]
        self.assertEqual((two["kind"], two["surface"], two["member_count"], two["left_out"]), ("group", "graph", 2, 1))
        self.assertEqual(two["how"], {"selection": "lasso", "filter": {"types": ["Person", "Company"]}})
        self.assertTrue(two["label"].startswith("2 items from the graph, chosen: Ann, Acme"))
        # re-opened through its Loupe: exactly its members and its why
        lens = self.loupe(grp["added_link_ids"][0])
        self.assertEqual([m["ref"] for m in lens["members"]], ["graph_entity:person:ann", "graph_entity:company:acme"])
        self.assertEqual(lens["addition"]["why"], "Ann, Acme and who they paid")

    def test_a_graph_entity_of_another_case_is_refused(self):
        with self.assertRaises(WorkspaceEntryValidationError):
            self.add(surface="graph", items=[{"target_type": "graph_entity", "target_id": "person:zed"}])

    def test_significant_item_and_whole_layer_snapshot(self):
        self.add(surface="significant", items=[{"target_type": "graph_entity", "target_id": "person:bob"}])
        snap = self.group("significant_set", [{"type": "graph_entity", "id": k} for k in ("person:ann", "person:bob")],
                          {"snapshot": True, "layer": "significant"}, "the whole Significant layer", "significant")
        self.assertIn("from the Significant layer", snap["group"]["label"])

    def test_timeline_range_holds_events_and_ledger_rows(self):
        grp = self.group("timeline_range",
                         [{"type": "graph_entity", "id": "event:meeting-1"},
                          {"type": "financial_transaction", "id": str(self.rows[0].id)},
                          {"type": "financial_transaction", "id": str(self.other_row.id)}],
                         {"range": {"start": "2026-01-01", "end": "2026-01-31"}}, "January 2026", "timeline")
        self.assertEqual((grp["group"]["member_count"], grp["group"]["left_out"]), (2, 1))
        lens = self.loupe(grp["added_link_ids"][0])
        self.assertEqual(lens["group"]["how"], {"range": {"start": "2026-01-01", "end": "2026-01-31"}})
        self.assertEqual(lens["members"][1]["date"], "2026-01-15")

    def test_evidence_file_and_folder_selection(self):
        self.add(surface="evidence", items=[{"target_type": "evidence", "target_id": str(self.evidence_id)}])
        grp = self.group("evidence_selection", [{"type": "evidence", "id": str(self.evidence_id)}],
                         {"folder": "Bank statements"}, "the bank statements folder", "evidence")
        self.assertEqual(grp["group"]["member_count"], 1)

    def test_financial_single_and_selection_scoped_to_the_case(self):
        self.add(surface="financial", items=[{"target_type": "financial_transaction", "target_id": str(self.rows[0].id)}])
        grp = self.group("financial_selection",
                         [{"type": "financial_transaction", "id": str(r.id)} for r in self.rows],
                         {"filter": {"amount_below": 10000}}, "payments under 100", "financial")
        self.assertEqual(grp["group"]["member_count"], 3)
        with self.assertRaises(T.AdditionError):
            self.group("financial_selection", [{"type": "financial_transaction", "id": str(self.other_row.id)}],
                       {}, "another case's row", "financial")

    def test_map_area(self):
        grp = self.group("map_selection", [{"type": "graph_entity", "id": "company:acme"}],
                         {"area": {"west": -1, "south": 51, "east": 0, "north": 52}}, "around the office", "map")
        self.assertIn("from the map", grp["group"]["label"])

    def test_a_group_of_another_case_cannot_be_linked(self):
        other = case_selections.freeze(self.db, case_id=self.other_case.id, group_type="graph_selection",
                                       members=[{"type": "graph_entity", "id": "person:zed"}], how={}, words="zed")
        with self.assertRaises(WorkspaceEntryValidationError):
            add_entry_link(self.db, case_id=self.case.id, entry_id=uuid.UUID(self.theory["id"]),
                           current_user=self.user, expected_version=self.theory["version"],
                           link={"target_type": "graph_selection", "target_id": other["id"]})

    def test_corrected_row_and_deleted_file_show_their_state_never_drop(self):
        grp = self.group("financial_selection", [{"type": "financial_transaction", "id": str(self.rows[1].id)}],
                         {}, "the 75.50 payment", "financial")
        self.rows[1].superseded_by_id = self.rows[2].id
        self.db.commit()
        lens = self.loupe(grp["added_link_ids"][0])
        self.assertEqual(lens["members"][0]["state"], "corrected")
        self.assertEqual(lens["members"][0]["corrected_by"], str(self.rows[2].id))
        files = self.group("evidence_selection", [{"type": "evidence", "id": str(self.evidence_id)}], {}, "f", "evidence")
        from postgres.models.evidence import EvidenceFile
        from datetime import datetime, timezone
        self.db.get(EvidenceFile, self.evidence_id).deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        lens = self.loupe(files["added_link_ids"][0])
        self.assertEqual(len(lens["members"]), 1)
        self.assertEqual(lens["members"][0]["state"], "deleted")
        self.assertIn("deleted, in Deleted items", lens["members"][0]["text"])

    def test_the_why_cannot_be_forged_and_survives_an_entry_save(self):
        added = self.add(surface="graph", why="person's own reason",
                         items=[{"target_type": "graph_entity", "target_id": "person:ann"}])
        entry = get_entry(self.db, case_id=self.case.id, entry_id=uuid.UUID(self.theory["id"]))
        links = [{"target_type": l["target_type"], "target_id": l["target_id"],
                  "metadata": {"addition": {"origin": "agent", "why": "forged"}}} for l in entry["links"]]
        links.append({"target_type": "graph_entity", "target_id": "person:bob",
                      "metadata": {"addition": {"origin": "agent", "model": "forged"}}})
        update_entry(self.db, case_id=self.case.id, entry_id=uuid.UUID(self.theory["id"]), current_user=self.user,
                     expected_version=entry["version"], links=links)
        additions = {a["target_id"]: a for a in self.reading()["additions"]}
        self.assertEqual(additions["person:ann"]["why"], "person's own reason")
        self.assertEqual(additions["person:ann"]["origin"], "person")
        self.assertEqual(additions["person:ann"]["link_id"], added["added_link_ids"][0])
        self.assertIsNone(additions["person:bob"]["model"])
        self.assertEqual(additions["person:bob"]["origin"], "person")

    def test_an_addition_made_by_an_agent_proposal_is_labelled_as_the_models(self):
        added = self.add(surface="graph", items=[{"target_type": "graph_entity", "target_id": "person:bob"}])
        T.mark_agent_addition(self.db, added["added_link_ids"], model="gpt-test", why="Bob received the third payment",
                              proposal_id=str(uuid.uuid4()), accepted_by=self.user)
        self.db.commit()
        row = self.reading()["additions"][0]
        self.assertEqual((row["origin"], row["model"], row["accepted_by"]), ("agent", "gpt-test", "Investigator"))

    # -- G / I: narratives ---------------------------------------------------------------------------------------

    def test_inferred_narrative_is_a_model_reading_with_citations_to_members_until_confirmed(self):
        grp = self.group("financial_selection", [{"type": "financial_transaction", "id": str(r.id)} for r in self.rows],
                         {"filter": {"account": "current"}}, "three January payments", "financial")
        link_id = grp["added_link_ids"][0]
        gen = stub("Three payments left the account on 15 January [m1][m2], the smallest 9.99 [m3] [m9].",
                   ["m1", "m2"])
        made = T.infer_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"], link_id=link_id,
                                 user=self.user, generator=gen)
        self.assertEqual(made["origin"], "agent")
        self.assertEqual(made["model"], "stub-model-1")
        self.assertIsNone(made["written_by"])  # never saved under the person's name
        self.assertEqual(made["asked_by"], "Investigator")
        self.assertEqual(made["words"], "Model reading · stub-model-1 · not confirmed")
        self.assertEqual([c["ref"] for c in made["citations"]],
                         [f"financial_transaction:{r.id}" for r in self.rows])
        self.assertEqual(made["basis"]["invalid_citations"], 1)  # m9 names nothing it was given
        self.assertIn("120.00", gen.calls[0])  # it read the ledger rows themselves
        lens = self.loupe(link_id)
        members = {m["ref"] for m in lens["members"]}
        self.assertTrue({c["ref"] for c in made["citations"]} <= members)
        done = T.confirm_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"], narrative_id=made["id"],
                                   user=self.user)
        self.assertEqual(done["words"], "Model reading · stub-model-1 · confirmed by Investigator")
        self.assertEqual(done["origin"], "agent")

    def test_a_reading_that_cites_nothing_given_is_not_saved(self):
        added = self.add(surface="graph", items=[{"target_type": "graph_entity", "target_id": "person:ann"}])
        with self.assertRaises(T.AdditionError):
            T.infer_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"],
                              link_id=added["added_link_ids"][0], user=self.user, generator=stub("Ann is key.", ["m7"]))
        self.assertEqual(self.db.query(TheoryNarrative).count(), 0)

    def test_editing_keeps_the_original_visible(self):
        added = self.add(surface="graph", items=[{"target_type": "graph_entity", "target_id": "person:ann"}])
        link_id = added["added_link_ids"][0]
        first = T.infer_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"], link_id=link_id,
                                  user=self.user, generator=stub("Ann is in the graph [m1].", []))
        mine = T.write_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"], link_id=link_id,
                                 text="Ann is the account holder named on every statement.", user=self.user)
        self.assertEqual(mine["replaces_id"], first["id"])
        self.assertEqual(mine["words"], "Written by Investigator")
        lens = self.loupe(link_id)
        self.assertEqual([h["id"] for h in lens["history"]], [mine["id"], first["id"]])
        self.assertEqual(lens["addition"]["narrative"]["id"], mine["id"])
        with self.assertRaises(T.AdditionError):  # the replaced reading can no longer be confirmed as current
            T.confirm_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"], narrative_id=first["id"],
                                user=self.user)

    def test_a_narrative_given_with_the_addition_is_the_persons(self):
        added = self.add(surface="evidence", why="the statement itself", narrative="Shows the January balance.",
                         items=[{"target_type": "evidence", "target_id": str(self.evidence_id)}])
        row = self.reading()["additions"][0]
        self.assertEqual(row["link_id"], added["added_link_ids"][0])
        self.assertEqual(row["narrative"]["origin"], "person")
        self.assertEqual(row["narrative"]["text"], "Shows the January balance.")

    # -- H: the theory as a whole -------------------------------------------------------------------------------

    def test_how_it_fits_together_cites_the_additions(self):
        a = self.add(surface="graph", items=[{"target_type": "graph_entity", "target_id": "person:ann"}])
        b = self.group("financial_selection", [{"type": "financial_transaction", "id": str(self.rows[0].id)}], {},
                       "the large payment", "financial")
        fit = T.infer_narrative(self.db, case_id=self.case.id, entry_id=self.theory["id"], link_id=None,
                                user=self.user, generator=stub("Ann [a1] received the large payment [a2].", []))
        self.assertEqual([c["ref"] for c in fit["citations"]],
                         [f"link:{a['added_link_ids'][0]}", f"link:{b['added_link_ids'][0]}"])
        whole = self.reading()
        self.assertEqual(whole["fit"]["id"], fit["id"])
        self.assertEqual([x["link_id"] for x in whole["additions"]], a["added_link_ids"] + b["added_link_ids"])

    def test_new_theory_from_a_selection(self):
        made = T.new_theory(self.db, case_id=self.case.id, user=self.user, title="Bob is a mule", surface="graph",
                            group={"group_type": "graph_selection", "members": [{"type": "graph_entity", "id": "person:bob"}],
                                   "how": {"filter": {"name": "bob"}}, "words": "Bob"})
        whole = T.reading(self.db, case_id=self.case.id, entry_id=made["entry_id"])
        self.assertEqual(whole["entry"]["entry_type"], "theory")
        self.assertEqual(len(whole["additions"]), 1)
