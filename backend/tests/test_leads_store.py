"""Leads are one type in one store (lx-leads A): a Corroborate result saved as a lead keeps its origin, its engine
level, its people, period, kinds and records; a person's state changes are appended; corrections keep Loupe's words;
confirming adds a finding to the theory under the person's name with the reader named as its author; the finder's
lead is brought up to date on a re-run without losing what a person did to it; the list filters to a selection."""
from __future__ import annotations

import uuid
from unittest import mock

from postgres.base import Base
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.case_selection import CaseSelection
from postgres.models.collection_membership import CollectionMembership
from postgres.models.corroborate import CorroborateFact, CorroborateWatch, LeadFinderRun
from postgres.models.relation_run import RelationRun
from postgres.models.theory_narrative import TheoryNarrative
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import (
    WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink, WorkspaceEntryRevision, WorkspaceLegacyMapping,
)
from services import case_selections
from services.corroborate import facts
from services.leads import store as L
from services.workspace_entry_service import create_entry, get_entry, origin_label
from tests.test_financial_duplicates import DuplicateTestCase

EXTRA = [RelationRun.__table__, CaseProfile.__table__, CaseDeadline.__table__, CaseTask.__table__,
         WorkspaceEntry.__table__, WorkspaceEntryRevision.__table__, WorkspaceEntryLink.__table__,
         WorkspaceEntryEvent.__table__, WorkspaceLegacyMapping.__table__, CaseSelection.__table__,
         CollectionMembership.__table__, TheoryNarrative.__table__, CorroborateFact.__table__,
         CorroborateWatch.__table__, LeadFinderRun.__table__]


def result(level="strong", people=("person:a", "person:b"), refs=("phone_record:r1",), days=("2024-03-16",)):
    inc = [{"id": f"i{n}", "label": d, "start": f"{d}T02:00:00+00:00", "end": f"{d}T06:00:00+00:00",
            "money_until": f"{d}T06:00:00+00:00"} for n, d in enumerate(days)]
    return {
        "question": {"kind": "every_time", "text": "Does this happen every time?", "chips": {"when": ["x"]}},
        "level": {"key": level, "name": {"strong": "Strong link", "coincidence": "Coincidence likely"}.get(level, level),
                  "sentence": f"{level} sentence", "rule": "r", "separating_kinds": ["contact", "sequence"]},
        "comparison": {"incident": inc, "ordinary": []},
        "people": [{"key": k, "label": k.split(":")[1].upper()} for k in people],
        "grid": [{"label": "A and B in contact", "link_kind": "contact", "separates": True, "weight": "full",
                  "incident": {"present": 5, "of": 5}, "ordinary": {"present": 0, "of": 11},
                  "records": {"i0": list(refs)}},
                 {"label": "same phrase", "link_kind": "shared_content", "separates": False, "weight": "low",
                  "why_low": "used all over the case", "incident": {"present": 2, "of": 5},
                  "ordinary": {"present": 1, "of": 11}, "records": {}}],
        "checks": [{"kind": "busy_place", "outcome": "weighed_low", "words": "A busy store at midday."}],
        "searched": {"records_read": {"message": 20}},
    }


class LeadStoreTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=EXTRA)
        p = mock.patch.object(facts, "material", lambda db, case_id: {"phone_records": 1})
        p.start()
        self.addCleanup(p.stop)
        g = mock.patch.object(case_selections, "graph_keys_in_case", side_effect=lambda c, keys: set())
        g.start()
        self.addCleanup(g.stop)
        row = CaseSelection(id=uuid.uuid4(), case_id=self.case.id, group_type="relation_query", words="test", how={},
                            members=[{"type": "phone_record", "id": "m1"}], member_count=1, left_out=0)
        self.db.add(row)
        self.db.commit()
        self.sel = str(row.id)
        self.theory = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="theory",
                                   title="Crew", body="A crew acted together")

    def save(self, **kw):
        args = dict(origin="found_by_loupe", selection_id=self.sel, result=result(), title="Relay",
                    summary="Okafor and Marsh are told by the same number", members=[{"type": "phone_record",
                                                                                      "id": "m1"}])
        args.update(kw)
        return L.save(self.db, self.case.id, **args)

    def test_a_lead_keeps_origin_level_people_period_kinds_records_and_reasons(self):
        lead = self.save()
        self.assertEqual(lead["origin"], "found_by_loupe")
        self.assertEqual(lead["origin_words"], "Found by Loupe")
        self.assertEqual(lead["level"]["key"], "strong")
        self.assertEqual(lead["state"], "new")
        self.assertEqual([p["key"] for p in lead["people"]], ["person:a", "person:b"])
        self.assertEqual(lead["period"], {"from": "2024-03-16", "to": "2024-03-16"})
        self.assertEqual(lead["kinds"], ["contact", "sequence"])
        self.assertEqual(lead["record_refs"], ["phone_record:m1", "phone_record:r1"])
        self.assertEqual(lead["raises"], ["A and B in contact: 5 of 5, against 0 of 11 ordinary"])
        self.assertIn("same phrase: weighed low (used all over the case)", lead["lowers"])
        self.assertIn("A busy store at midday.", lead["lowers"])
        self.assertEqual(lead["read"]["words"], "Read by Loupe's lead finder · not confirmed")

    def test_a_lead_without_a_rule_level_is_refused(self):
        r = result()
        r["level"] = {}
        with self.assertRaises(L.LeadError):
            self.save(result=r)

    def test_state_changes_are_appended_with_who_and_in_theory_only_by_confirming(self):
        lead = self.save()
        L.set_state(self.db, self.case.id, lead["id"], state="looking", user=self.user)
        after = L.set_state(self.db, self.case.id, lead["id"], state="not_relevant", user=self.user, why="a shop")
        self.assertEqual([h["to"] for h in after["state_history"]], ["new", "looking", "not_relevant"])
        self.assertEqual(after["state_history"][-1]["by_name"], self.user.name)
        self.assertEqual(after["state_history"][-1]["why"], "a shop")
        with self.assertRaises(L.LeadError):
            L.set_state(self.db, self.case.id, lead["id"], state="in_theory", user=self.user)

    def test_a_correction_keeps_loupes_words_visible(self):
        lead = self.save()
        after = L.correct(self.db, self.case.id, lead["id"], field="title", value="Relay through the prepaid phone",
                          user=self.user)
        self.assertEqual(after["title"], "Relay through the prepaid phone")
        self.assertEqual(after["read"]["title"], "Relay")
        self.assertEqual(after["corrections"][0]["original"], "Relay")
        self.assertEqual(after["corrections"][0]["by_name"], self.user.name)
        with self.assertRaises(L.LeadError):
            L.correct(self.db, self.case.id, lead["id"], field="level", value="strong", user=self.user)

    def test_confirming_adds_a_finding_to_the_theory_under_the_person_with_the_reader_as_author(self):
        lead = self.save()
        after = L.confirm(self.db, self.case.id, lead["id"], theory_id=self.theory["id"], user=self.user)
        self.assertEqual(after["state"], "in_theory")
        self.assertEqual(after["confirmed"]["by"], self.user.name)
        self.assertEqual(after["read"]["words"], f"Read by Loupe's lead finder · confirmed by {self.user.name}")
        row = self.db.get(WorkspaceEntry, uuid.UUID(after["finding_id"]))
        self.assertEqual(row.entry_type, "finding")
        self.assertEqual(origin_label(row), f"Drafted by Loupe's lead finder, accepted by {self.user.name}")
        theory = get_entry(self.db, case_id=self.case.id, entry_id=uuid.UUID(self.theory["id"]))
        self.assertIn(after["finding_id"], [str(link["target_id"]) for link in theory["links"]])
        with self.assertRaises(L.LeadError):
            L.confirm(self.db, self.case.id, lead["id"], theory_id=self.theory["id"], user=self.user)

    def test_a_finder_rerun_updates_the_same_lead_and_keeps_state_and_corrections(self):
        lead = self.save(finder_key="relay:a:b")
        L.set_state(self.db, self.case.id, lead["id"], state="looking", user=self.user)
        L.correct(self.db, self.case.id, lead["id"], field="summary", value="mine", user=self.user)
        again = self.save(finder_key="relay:a:b", result=result(level="coincidence"))
        self.assertEqual(again["id"], lead["id"])
        self.assertEqual(again["state"], "looking")
        self.assertEqual(again["summary"], "mine")
        self.assertEqual(again["level"]["key"], "coincidence")
        self.assertEqual([h["to"]["key"] for h in again["history"]], ["strong", "coincidence"])
        self.assertEqual(self.db.query(CorroborateWatch).count(), 1)

    def test_the_list_is_strongest_first_and_filters_to_a_selections_records_people_or_period(self):
        self.save(title="weak", result=result(level="coincidence", people=("person:c",), refs=("phone_record:z",),
                                                days=("2024-05-18",)), members=[])
        self.save(title="strong")
        self.assertEqual([x["title"] for x in L.list_leads(self.db, self.case.id)], ["strong", "weak"])
        self.assertEqual([x["title"] for x in L.list_leads(self.db, self.case.id, records=["phone_record:z"])], ["weak"])
        self.assertEqual([x["title"] for x in L.list_leads(self.db, self.case.id, people=["person:a"])], ["strong"])
        self.assertEqual([x["title"] for x in L.list_leads(self.db, self.case.id, period=("2024-05-01", "2024-05-31"))],
                         ["weak"])
        self.assertEqual(L.list_leads(self.db, self.case.id, records=["phone_record:none"]), [])

    def test_the_count_leaves_out_set_aside_no_link_and_not_relevant(self):
        a = self.save(title="a")
        self.save(title="b", level=dict(L.SET_ASIDE, sentence="stock phrase"))
        self.save(title="c", result=result(level="no_link_found"))
        self.assertEqual(L.count(self.db, self.case.id)["count"], 1)
        L.set_state(self.db, self.case.id, a["id"], state="not_relevant", user=self.user)
        self.assertEqual(L.count(self.db, self.case.id)["count"], 0)

    def test_an_asked_answer_saves_once_per_run_and_says_who_asked(self):
        run = uuid.uuid4()
        lead = L.save_asked(self.db, self.case.id, selection_id=self.sel, run_id=run, result=result(),
                            members=[], user=self.user)
        self.assertEqual(lead["origin"], "asked")
        self.assertIsNone(L.save_asked(self.db, self.case.id, selection_id=self.sel, run_id=run, result=result(),
                                       members=[], user=self.user))
        mine = L.list_leads(self.db, self.case.id, me=self.user.id)[0]
        self.assertEqual(mine["origin_words"], "Asked by you")
        self.assertEqual(L.list_leads(self.db, self.case.id, me=uuid.uuid4())[0]["origin_words"],
                         f"Asked by {self.user.name}")

    def test_a_lead_of_another_case_is_not_found(self):
        lead = self.save()
        with self.assertRaises(L.LeadError) as cm:
            L.get(self.db, self.other_case.id, lead["id"])
        self.assertEqual(cm.exception.status, 404)
