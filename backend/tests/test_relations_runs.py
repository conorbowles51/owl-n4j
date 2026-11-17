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

    def test_a_group_with_a_question_carries_the_corroborate_result_and_its_level(self):
        from services.corroborate import engine as corroborate
        q = {"kind": "every_time", "text": "Does this happen every time?", "chips": {"hours": {"start": "22:00", "length_h": 6}}}
        group = runs.save_group(self.db, case_id=self.case.id, members=[{"type": "place", "id": "51.5,-0.1,50"}],
                                question=q)
        self.assertEqual(case_selections.describe(self.db, self.case.id, group["id"])["how"]["question"],
                         {**q, "chips": {"hours": {"start": "22:00", "length_h": 6.0}}})
        seen = []
        level = {"key": "cant_tell", "name": "Can't tell", "sentence": "Can't tell: no dated records."}
        with mock.patch.object(runs, "DbSources", Fake), \
                mock.patch("services.corroborate.store.CaseStore", lambda db, case: None), \
                mock.patch.object(corroborate, "run", side_effect=lambda store, members, question, progress:
                                  seen.append(question) or {"schema": "loupe.corroborate/1", "level": level}):
            view = runs.start(self.db, case_id=self.case.id, selection_id=group["id"], inline=True,
                              session_factory=lambda: self.db)
        self.assertEqual(seen, [q])
        self.assertEqual(view["status"], "done")
        self.assertEqual(view["result"]["corroboration"]["level"], level)
        self.assertEqual(view["progress"]["level"], "Can't tell")
        self.assertEqual(view["result"]["counts"]["items"], 1)

    def test_a_run_from_a_sessionmaker_closes_its_session(self):
        """The background runner gets a sessionmaker (no __name__): the session is closed once the run is saved."""
        group = runs.save_group(self.db, case_id=self.case.id, members=[{"type": "place", "id": "51.5,-0.1,50"}])
        view = runs.start(self.db, case_id=self.case.id, selection_id=group["id"], inline=True,
                          session_factory=lambda: self.db)
        closed = []

        class Maker:  # a sessionmaker-like factory: callable, no __name__
            def __call__(self_inner):
                s = mock.Mock(wraps=self.db)
                s.bind = self.db.bind
                s.get, s.commit, s.rollback = self.db.get, self.db.commit, self.db.rollback
                s.execute, s.scalars, s.query = self.db.execute, self.db.scalars, self.db.query
                s.close = lambda: closed.append(True)
                return s

        with mock.patch.object(runs, "DbSources", Fake):
            runs.work(view["id"], str(self.case.id), session_factory=Maker())
        self.assertEqual(closed, [True])

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


def test_a_marked_passage_becomes_its_document_with_the_quote():
    from unittest import mock
    from services.relations import runs
    with mock.patch("services.evidence_page_text.passage_anchor", return_value=("Contract, page 2", {"quote": "Harbor Trading LLC"})):
        out = runs.normalise(None, "c", [{"type": "evidence_passage", "id": "abc:def:1:9"}, {"type": "place", "id": "1,1,5"}])
    assert out[0] == {"type": "evidence", "id": "abc", "label": "Contract, page 2", "quote": "Harbor Trading LLC"}
    assert out[1]["type"] == "place"


def test_a_passage_that_cannot_be_read_is_refused_with_the_reason():
    import pytest
    from unittest import mock
    from services import case_selections
    from services.evidence_page_text import PassageError
    from services.relations import runs
    with mock.patch("services.evidence_page_text.passage_anchor", side_effect=PassageError("read again since")):
        with pytest.raises(case_selections.SelectionError, match="read again"):
            runs.normalise(None, "c", [{"type": "evidence_passage", "id": "abc:def:1:9"}])


class SizeTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[CaseSelection.__table__, RelationRun.__table__])

    def test_a_group_too_big_to_compare_is_refused_before_anything_is_saved(self):
        members = [{"type": "place", "id": f"1,{n / 1000},5"} for n in range(runs.MAX_ITEMS + 1)]
        with self.assertRaises(case_selections.SelectionError) as raised:
            runs.save_group(self.db, case_id=self.case.id, members=members)
        self.assertIn("pairs to compare", str(raised.exception))
        self.assertEqual(self.db.query(CaseSelection).count(), 0)

    def test_the_screen_reads_a_page_and_says_how_many_of_how_many_and_the_rest_is_one_call_away(self):
        group = runs.save_group(self.db, case_id=self.case.id, members=[{"type": "place", "id": "1,1,5"}])
        result = {"candidates": [{"n": n} for n in range(250)], "no_links": [{"n": n} for n in range(7)], "items": [], "analyses": [],
                  "counts": {"items": 1}}
        row = RelationRun(case_id=self.case.id, selection_id=__import__("uuid").UUID(group["id"]), status="done", result=result)
        self.db.add(row)
        self.db.commit()
        view = runs.view(self.db, self.case.id, str(row.id))
        self.assertEqual(len(view["result"]["candidates"]), runs.PAGE)
        self.assertEqual(view["result"]["paging"]["candidates"], {"total": 250, "shown": runs.PAGE})
        more = runs.rows(self.db, self.case.id, str(row.id), "candidates", offset=runs.PAGE, limit=200)
        self.assertEqual((more["returned"], more["next_offset"], more["rows"][0]["n"]), (150, None, runs.PAGE))
        with self.assertRaises(LookupError):
            runs.rows(self.db, self.other_case.id, str(row.id), "candidates")
