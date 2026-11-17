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
        self.assertEqual((out["members"], out["selected"]), (3, 3))
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

    def test_one_selected_item_is_counted_in_the_singular(self):
        # 17 Nov: a one-photo selection read "1 items" in the question menu
        taken = {"people": [], "times": {"from": None, "to": None, "dated": 0, "days": 0, "undated": 1},
                 "places": [], "items": [{"type": "phone_record", "count": 1, "words": "1 phone record"}]}
        self.assertEqual(preview.questions(taken, 1)[-1]["count_words"], "1 item")
        self.assertEqual(preview.questions(taken, 2)[-1]["count_words"], "2 items")

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


class _Conn:
    """Like a real connection: the statement takes execution options, the result is only iterated."""
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params=None):
        assert hasattr(statement, "compile"), "execute takes a statement, as a real connection does"
        return iter(self.rows)


def _row(uid, ext, model, lon, lat):
    from types import SimpleNamespace
    return SimpleNamespace(record_uid=uid, extraction_id=ext, model_type=model, lon=lon, lat=lat)


def test_a_drawn_area_takes_every_position_inside_it_and_the_places_and_counts_photos_apart():
    from services.corroborate import area
    square = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    rows = [_row("u1", "e1", "Location", 0.5, 0.5), _row("u2", "e1", "Location", 0.5001, 0.5001),  # share one cluster
            _row("u3", "e2", "Image", 0.2, 0.2), _row("u4", "e2", "Location", 5, 5),  # outside, same bbox query
            _row("u1", "e1", "Location", 0.5, 0.5)]  # the same record twice counts once
    places = lambda case, bbox: [{"key": "wh", "name": "Warehouse", "lat": 0.4, "lon": 0.4}, {"key": "far", "name": "Far", "lat": 3, "lon": 3}]
    out = area.members_in_areas(_Conn(rows), "c", [square], places=places)
    ids = [m["id"] for m in out["members"]]
    assert ids == ["u1", "u2", "u3", "wh"]
    assert out["phones"] == 2 and out["places"] == 1 and out["by_kind"] == {"positions": 2, "photos": 1}


def test_an_area_with_fewer_than_three_corners_is_refused():
    import pytest
    from services.corroborate import area
    with pytest.raises(ValueError, match="three corners"):
        area.members_in_areas(_Conn([]), "c", [[[0, 0], [1, 1]]], places=lambda *a: [])


def _it(kind, at, names=()):
    return {"ref": kind + str(at), "type": kind, "id": str(at), "label": kind, "at": at, "names": list(names)}


def test_a_recurring_friday_night_window_holds_saturday_small_hours_and_names_what_is_outside():
    from services.corroborate import scope
    items = [_it("phone_record", "2026-05-15T23:30:00+00:00"),   # Friday 23:30
             _it("phone_record", "2026-05-16T02:00:00+00:00"),   # Saturday 02:00, still Friday night
             _it("phone_record", "2026-05-16T12:00:00+00:00"),   # Saturday midday
             _it("financial_transaction", "2026-05-15T10:00:00+00:00"),  # Friday morning
             _it("evidence", None)]
    out = scope.apply(items, {"recurring": {"weekday": 4, "from_hour": 22, "to_hour": 4}})
    assert [i["at"] for i in out["kept"]] == ["2026-05-15T23:30:00+00:00", "2026-05-16T02:00:00+00:00", None]
    assert out["outside"] == {"phone_record": 1, "financial_transaction": 1}
    assert out["no_time"] == 1  # an item with no time stays in scope and is counted, not dropped unseen
    assert "every Friday, 22:00 to 04:00 (UTC)" in out["words"]


def test_the_zone_decides_the_hour_and_is_named():
    from services.corroborate import scope
    item = _it("phone_record", "2026-05-15T23:30:00+00:00")  # 19:30 in New York
    assert scope.apply([item], {"recurring": {"weekday": 4, "from_hour": 22, "to_hour": 4}, "zone": "America/New_York"})["outside_total"] == 1
    assert scope.apply([item], {"from": "2026-05-15", "zone": "America/New_York"})["words"] == ["2026-05-15 to end (America/New_York)"]


def test_kinds_and_people_narrow_and_an_empty_scope_changes_nothing():
    from services.corroborate import scope
    items = [_it("phone_record", "2026-05-15T23:30:00+00:00", ["Kell"]), _it("financial_transaction", "2026-05-15T23:30:00+00:00", ["Marsh"])]
    assert scope.apply(items, {})["active"] is False and len(scope.apply(items, {})["kept"]) == 2
    out = scope.apply(items, {"people": ["Marsh"], "kinds": ["financial_transaction"]})
    assert [i["type"] for i in out["kept"]] == ["financial_transaction"] and out["outside"] == {"phone_record": 1}


def test_a_zone_loupe_does_not_know_is_refused_in_words():
    import pytest
    from services.corroborate import scope
    with pytest.raises(scope.ScopeError, match="not a time zone"):
        scope.apply([_it("evidence", "2026-05-15T23:30:00+00:00")], {"from": "2026-05-01", "zone": "Mars/Base"})


def test_a_relative_window_keeps_what_is_within_minutes_of_each_payment_and_says_date_only_payments_cannot_anchor():
    from services.corroborate import scope
    pay = {**_it("financial_transaction", "2026-05-15T10:00:00+00:00", ["Marsh"]), "precision": "minute"}
    dated = {**_it("financial_transaction", "2026-05-16T00:00:00+00:00", ["Marsh"]), "precision": "day"}
    near = _it("phone_record", "2026-05-15T09:45:00+00:00")
    far = _it("phone_record", "2026-05-15T08:00:00+00:00")
    after = _it("phone_record", "2026-05-15T10:20:00+00:00")
    rel = {"relative": {"anchor_kind": "financial_transaction", "person": "Marsh", "before_min": 30, "after_min": 0}}
    out = scope.apply([pay, dated, near, far, after], rel)
    assert [i["at"][11:16] for i in out["kept"] if i["type"] == "phone_record"] == ["09:45"]
    assert out["anchors"] == 1 and out["anchors_date_only"] == 1
    assert out["outside"] == {"phone_record": 2}
    assert out["words"] == ["30 min before to 0 min after each financial transaction involving Marsh"]


class SubsetTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[CaseSelection.__table__])
        p = mock.patch.object(case_selections, "graph_keys_in_case", side_effect=lambda case_id, keys: set(keys))
        p.start()
        self.addCleanup(p.stop)

    def test_saved_subsets_are_listed_by_name_and_set_operations_count_both_sides(self):
        from services.corroborate import subsets
        a = subsets.save(self.db, case_id=self.case.id, name="Kell's circle", members=[{"type": "graph_entity", "id": x} for x in "abc"])
        b = subsets.save(self.db, case_id=self.case.id, name="Friday nights", members=[{"type": "graph_entity", "id": x} for x in "bcd"])
        self.assertEqual([s["name"] for s in subsets.listing(self.db, self.case.id)], ["Friday nights", "Kell's circle"])
        def ids(op):
            out = subsets.combine(self.db, self.case.id, a["id"], b["id"], op)
            return [m["id"] for m in out["members"]], out["first"], out["second"]
        self.assertEqual(ids("both"), (["b", "c"], 3, 3))
        self.assertEqual(ids("either")[0], ["a", "b", "c", "d"])
        self.assertEqual(ids("a_not_b")[0], ["a"])
        self.assertEqual(ids("b_not_a")[0], ["d"])

    def test_a_subset_of_another_case_is_not_found_and_an_unnamed_one_is_refused(self):
        from services.corroborate import subsets
        other = subsets.save(self.db, case_id=self.other_case.id, name="x", members=[{"type": "graph_entity", "id": "a"}])
        mine = subsets.save(self.db, case_id=self.case.id, name="y", members=[{"type": "graph_entity", "id": "a"}])
        with self.assertRaises(case_selections.SelectionError):
            subsets.combine(self.db, self.case.id, mine["id"], other["id"], "both")
        with self.assertRaises(case_selections.SelectionError):
            subsets.save(self.db, case_id=self.case.id, name="  ", members=[{"type": "graph_entity", "id": "a"}])
