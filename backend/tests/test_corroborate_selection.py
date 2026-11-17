"""Corroborate from a selection: what Loupe takes from a mixed selection, the questions, and a pasted list (lx-corroselect)."""
from __future__ import annotations

from unittest import mock

from postgres.base import Base
from postgres.models.case_selection import CaseSelection
from services import case_selections
from services.corroborate import pasted, preview
from tests.test_financial_duplicates import DuplicateTestCase


class Fake:
    def __init__(self, items):
        self.items = items

    def load_items(self, members):
        by = {f"{i['type']}:{i['id']}": i for i in self.items}
        return [by[f"{m['type']}:{m['id']}"] for m in members]


def item(kind, ident, label, at=None, names=(), place=None):
    return {"ref": f"{kind}:{ident}", "type": kind, "id": ident, "label": label, "at": at, "names": list(names),
            "identifiers": [], **({"place": place} if place else {})}


NODES = {"ok:kell": {"labels": ["Person"], "name": "Kell"}, "ok:okafor": {"labels": ["Person"], "name": "Okafor"},
         "ok:wh": {"labels": ["Location"], "name": "Warehouse"}}


class PreviewTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[CaseSelection.__table__])
        p = mock.patch.object(case_selections, "graph_keys_in_case",
                              side_effect=lambda case_id, keys: {k for k in keys if k.startswith("ok:")})
        p.start()
        self.addCleanup(p.stop)

    def run_preview(self, members, items):
        return preview.preview(self.db, self.case.id, members, sources=Fake(items), graph=lambda c, k: {x: NODES[x] for x in k if x in NODES})

    def test_a_mixed_selection_is_read_as_people_places_times_and_items(self):
        members = [{"type": "graph_entity", "id": "ok:kell"}, {"type": "graph_entity", "id": "ok:okafor"},
                   {"type": "graph_entity", "id": "ok:wh"}, {"type": "graph_entity", "id": "bad:x"}]
        items = [item("graph_entity", "ok:kell", "Kell", at="2026-05-18T01:00:00+00:00"),
                 item("graph_entity", "ok:okafor", "Okafor", at="2026-05-19T01:00:00+00:00"),
                 item("graph_entity", "ok:wh", "Warehouse")]
        out = self.run_preview(members, items)
        self.assertEqual(out["members"], 3)
        self.assertEqual(out["left_out"]["count"], 1)  # said, not dropped
        self.assertEqual([p["label"] for p in out["taken"]["people"]], ["Kell", "Okafor"])
        self.assertEqual(out["taken"]["places"], [{"label": "Warehouse", "count": 1}])
        self.assertEqual(out["taken"]["times"]["from"], "2026-05-18")
        self.assertEqual(out["taken"]["times"]["days"], 2)
        kinds = [q["kind"] for q in out["questions"]]
        self.assertIn("in_contact", kinds)
        self.assertEqual(kinds[-1], "who_else")
        self.assertTrue(3 <= len(kinds) <= 5 or len(kinds) == 2)
        self.assertEqual(out["questions"][-1]["count"], 3)  # the whole set, not a page

    def test_questions_fit_the_mix_and_stay_within_five(self):
        taken = {"people": [{"label": n, "count": 1, "key": n} for n in ("A", "B")],
                 "times": {"from": "2026-05-01", "to": "2026-05-09", "dated": 9, "days": 9, "undated": 0},
                 "places": [], "items": [{"type": "financial_transaction", "count": 5, "words": "5 payments"},
                                         {"type": "phone_record", "count": 4, "words": "4 phone records"},
                                         {"type": "evidence", "count": 1, "words": "1 document"}]}
        qs = preview.questions(taken, 10)
        self.assertLessEqual(len(qs), 5)
        self.assertEqual(qs[-1]["kind"], "who_else")
        self.assertTrue(all(q["count"] > 0 and q["chips"]["compare_with"] for q in qs))

    def test_a_selection_of_nothing_in_the_case_has_no_questions(self):
        out = self.run_preview([{"type": "graph_entity", "id": "bad:x"}], [])
        self.assertEqual((out["members"], out["left_out"]["count"], out["questions"]), (0, 1, []))


def fake_finder(db, case, kind, value):
    return {"+44 7700 900123": [{"type": "financial_account", "id": "a1", "label": "acct", "via": "an account number"},
                                {"type": "phone_record", "id": "r1", "label": "rec", "via": "a number on the phones"}],
            "KX19 ABC": [{"type": "graph_entity", "id": "ok:car", "label": "KX19 ABC", "via": "a name in the graph"}]}.get(value, [])


def test_pasted_list_matches_each_entry_and_lists_the_unmatched():
    out = pasted.match(None, "c", "+44 7700 900123\nKX19 ABC, 12345\n99887766554;", finders=(fake_finder,))
    assert [t["token"] for t in out["tokens"]] == ["+44 7700 900123", "KX19 ABC", "12345", "99887766554"]
    assert out["matched"] == 2
    assert [u["token"] for u in out["unmatched"]] == ["12345", "99887766554"]
    assert "under 7 digits" in out["unmatched"][0]["unmatched_reason"]
    assert out["unmatched"][1]["unmatched_reason"]
    assert [m["id"] for m in out["members"]] == ["a1", "r1", "ok:car"]


def test_a_finder_that_fails_is_said_not_read_as_no_match():
    def broken(*a):
        raise RuntimeError("graph down")
    out = pasted.match(None, "c", "99887766554", finders=(broken,))
    assert "could not be searched" in out["unmatched"][0]["unmatched_reason"]


def test_a_paste_over_the_limit_is_refused_with_the_number():
    import pytest
    with pytest.raises(ValueError, match="2,001"):
        pasted.match(None, "c", "\n".join(str(1000000 + i) for i in range(2001)), finders=())
