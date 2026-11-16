"""Saving a group to look into, growing it, and running the analysis on it (lx-overlaps D)."""
from __future__ import annotations

from unittest import mock

from postgres.base import Base
from postgres.models.case_selection import CaseSelection
from postgres.models.relation_run import RelationRun
from services import case_selections
from services.relations import engine, runs
from tests.test_financial_duplicates import DuplicateTestCase


class Fake:
    def __init__(self, db, case):
        pass

    def load_items(self, members):
        return [{"ref": f"{m['type']}:{m['id']}", "type": m["type"], "id": m["id"], "label": m["id"], "at": None,
                 "identifiers": [], "names": []} for m in members]

    def base(self, items):
        return {"period_days": 0, "days_with": {}}

    def identifier_counts(self, *a):
        return None


class RunTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[CaseSelection.__table__, RelationRun.__table__])
        p = mock.patch.object(case_selections, "graph_keys_in_case",
                              side_effect=lambda case_id, keys: {k for k in keys if k.startswith("ok:")})
        p.start()
        self.addCleanup(p.stop)

    def test_growing_a_query_saves_a_new_group_holding_the_old_members(self):
        first = runs.save_group(self.db, case_id=self.case.id, members=[{"type": "graph_entity", "id": "ok:a"}])
        grown = runs.save_group(self.db, case_id=self.case.id, extends=first["id"],
                                members=[{"type": "graph_entity", "id": "ok:b"}, {"type": "graph_entity", "id": "ok:a"}])
        self.assertNotEqual(first["id"], grown["id"])
        old = case_selections.describe(self.db, self.case.id, first["id"])
        new = case_selections.describe(self.db, self.case.id, grown["id"])
        self.assertEqual([m["id"] for m in old["members"]], ["ok:a"])  # never rewritten
        self.assertEqual([m["id"] for m in new["members"]], ["ok:a", "ok:b"])
        self.assertEqual(new["how"]["extends"], first["id"])

    def test_extending_a_group_of_another_case_is_refused(self):
        other = case_selections.freeze(self.db, case_id=self.other_case.id, group_type="relation_query", words="x", how={},
                                       members=[{"type": "place", "id": "1,1,10"}])
        with self.assertRaises(case_selections.SelectionError):
            runs.save_group(self.db, case_id=self.case.id, extends=other["id"], members=[{"type": "place", "id": "2,2,10"}])

    def test_run_records_result_and_progress_and_stays_in_its_case(self):
        group = runs.save_group(self.db, case_id=self.case.id, members=[{"type": "graph_entity", "id": "ok:a"},
                                                                       {"type": "place", "id": "51.5,-0.1,50"}])
        with mock.patch.object(runs, "DbSources", Fake):
            view = runs.start(self.db, case_id=self.case.id, selection_id=group["id"], inline=True,
                              session_factory=lambda: self.db)
        self.assertEqual(view["status"], "done")
        self.assertEqual(view["result"]["counts"]["items"], 2)
        self.assertEqual(view["progress"]["items"], 2)
        self.assertIn("do not show why", view["result"]["says"])
        with self.assertRaises(LookupError):
            runs.view(self.db, self.other_case.id, view["id"])

    def test_a_failed_run_says_why(self):
        group = runs.save_group(self.db, case_id=self.case.id, members=[{"type": "place", "id": "51.5,-0.1,50"}])
        with mock.patch.object(engine, "run", side_effect=RuntimeError("the phone tables are not reachable")):
            view = runs.start(self.db, case_id=self.case.id, selection_id=group["id"], inline=True,
                              session_factory=lambda: self.db)
        self.assertEqual(view["status"], "failed")
        self.assertIn("not reachable", view["error"])


class HypothesisTests(DuplicateTestCase):
    def test_coincidence_and_routine_are_always_named_and_each_explanation_says_how_to_tell_it_apart(self):
        from services.relations import hypotheses as H
        good = {"kind": "coincidence", "statement": "Both happened by chance.", "distinguishing_record": "A third phone at the place",
                "search": "Searched all phones for that day: nothing found"}
        routine = {**good, "kind": "routine", "statement": "Routine"}
        with self.assertRaises(H.HypothesisError) as one:
            H.validate([good])
        self.assertIn("routine", str(one.exception))
        planned = {"kind": "planned_meeting", "statement": "Arranged", "for": [{"cite": "rec://x"}],
                   "distinguishing_record": "A message arranging it", "search": "Searched messages 2 days before: 3 found"}
        self.assertEqual(len(H.validate([good, routine, planned])), 3)
        with self.assertRaises(H.HypothesisError):
            H.validate([good, routine, {**planned, "for": []}])  # a named cause with no cited record
        with self.assertRaises(H.HypothesisError):
            H.validate([good, routine, {**planned, "search": ""}])
