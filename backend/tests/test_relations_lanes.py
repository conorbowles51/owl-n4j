"""Story lanes lay out only the records the result cites, one lane per person, numbered in time order."""
from services.corroborate import engine
from services.relations import lanes

from tests.corroborate_world import INCIDENTS, FakeStore


def _result():
    d = INCIDENTS[0]
    store = FakeStore()
    res = engine.run(store, [{"type": "record", "id": f"m1:{d}"}, {"type": "record", "id": f"m2:{d}"}], {"kind": "every_time"})
    return store, res


def test_lanes_hold_only_cited_records_in_time_order_with_one_lane_per_person():
    store, res = _result()
    inst = res["comparison"]["incident"][0]["id"]
    out = lanes.build(store, res, inst)
    cited = set(lanes.cited_refs(res, inst))
    assert cited, "the seed night cites records"
    laid = [e for lane in out["lanes"] for e in lane["events"]]
    assert laid, "the cited records are laid out"
    assert {e["ref"] for e in laid} <= cited
    assert sorted(e["n"] for e in laid) == list(range(1, len(laid) + 1))
    ordered = sorted(laid, key=lambda e: e["n"])
    assert [e["at"] for e in ordered] == sorted(e["at"] for e in ordered)
    assert len({lane["person"] for lane in out["lanes"]}) == len(out["lanes"])
    assert out["events"] + len(out["not_laid_out"]) == len(cited)


def test_an_instance_not_in_the_result_is_refused():
    store, res = _result()
    try:
        lanes.build(store, res, "1999-01-01")
    except LookupError:
        return
    raise AssertionError("expected LookupError")


def test_trail_walks_the_extends_chain_oldest_first_and_names_what_each_step_added(monkeypatch):
    from services import case_selections
    from services.relations import runs, trail

    groups = {
        "a": {"id": "a", "group_type": "relation_query", "how": {}, "members": [{"type": "person", "id": "1", "label": "One"}]},
        "b": {"id": "b", "group_type": "relation_query", "how": {"extends": "a"},
              "members": [{"type": "person", "id": "1"}, {"type": "person", "id": "2", "label": "Two"}]},
        "c": {"id": "c", "group_type": "relation_query", "how": {"extends": "b"},
              "members": [{"type": "person", "id": "1"}, {"type": "person", "id": "2"}]},
    }
    monkeypatch.setattr(case_selections, "describe", lambda db, c, s, member_limit=0: groups.get(s))
    monkeypatch.setattr(runs, "latest_for", lambda db, c, s: f"run-{s}")
    keys = {"run-a": "possible", "run-b": "strong", "run-c": "strong"}
    monkeypatch.setattr(runs, "full_result", lambda db, c, r: {"corroboration": {"level": {"key": keys[r], "name": keys[r], "sentence": ""}, "grid": []}})
    out = trail.build(None, "case", "c")
    assert [s["selection_id"] for s in out["steps"]] == ["a", "b", "c"]
    assert [s["added_count"] for s in out["steps"]] == [1, 1, 0]
    assert out["steps"][1]["level_moved"] == "raised"
    assert out["steps"][2]["adds_nothing"] is True
