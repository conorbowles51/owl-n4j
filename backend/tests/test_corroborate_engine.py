"""Corroborate (lx-corroengine B-H) on an invented case: levels come from the rules, every check is returned, copies
count once, missing data is Can't tell, and the rules never name the demo case's people."""
import json
import re
from pathlib import Path

from services.corroborate import engine, levels, model as M, questions

from tests.corroborate_world import FRIDAYS, INCIDENTS, SHOP, FakeStore, at

RULES = Path(__file__).resolve().parents[1] / "services" / "corroborate"


def _run(members, question=None, **kw):
    res = engine.run(FakeStore(**kw), members, question)
    json.dumps(res)  # a run's result is stored as JSON: nothing else may be in it
    return res


def _seed():
    d = INCIDENTS[0]
    return [{"type": "record", "id": f"m1:{d}"}, {"type": "record", "id": f"m2:{d}"}]


def test_one_night_asked_every_time_finds_the_others_and_grades_strong_against_ordinary_fridays():
    res = _run(_seed(), {"kind": "every_time"})
    lvl = res["level"]
    assert lvl["key"] == "strong", lvl
    inc = {i["id"] for i in res["comparison"]["incident"]}
    assert inc == {d.isoformat() for d in INCIDENTS}
    assert len(res["comparison"]["ordinary"]) == 7
    assert "3 of 3" in lvl["sentence"] and "none of the 7 other Fridays" in lvl["sentence"]
    assert "picked them" in res["comparison"]["words"]
    money = next(g for g in res["grid"] if g["link_kind"] == "money")
    assert money["incident"] == {"present": 3, "absent": 0, "no_data": 0, "of": 3}
    assert money["ordinary"]["present"] == 0
    # the payment is one record seen twice (ledger row and alert): counted once, both cited
    cell = money["records"][INCIDENTS[0].isoformat()]
    assert set(cell) == {f"pay:{INCIDENTS[0]}", f"alert:{INCIDENTS[0]}"}
    picked = [g for g in res["grid"] if g.get("picked_by")]
    assert picked and all(not g["separates"] for g in picked)


def test_every_check_is_returned_with_an_outcome():
    res = _run(_seed(), {"kind": "every_time"})
    got = {c["check"]: c["outcome"] for c in res["checks"]}
    assert set(got) == {"routine", "household", "workplace", "stock_phrase", "busy_place", "clock_zone",
                        "recycled_number", "same_name", "shared_device", "duplicate_copy", "received_media"}
    assert all(v in ("checked", "ruled_out", "weighed_low", "no_data") for v in got.values())
    assert got["clock_zone"] == "ruled_out" and "America/Chicago" in next(
        c["words"] for c in res["checks"] if c["check"] == "clock_zone")
    assert got["recycled_number"] == "ruled_out" and "Old Owner" in next(
        c["words"] for c in res["checks"] if c["check"] == "recycled_number")
    assert got["same_name"] == "ruled_out"
    assert got["duplicate_copy"] == "ruled_out" and "counted once" in next(
        c["words"] for c in res["checks"] if c["check"] == "duplicate_copy")
    # a photo received on Dan's phone never places Dan, and is never a link
    assert got["received_media"] == "ruled_out"
    assert not any("dan" in g["people"] for g in res["grid"])


def test_routine_contact_is_weighed_low_and_never_separates():
    d = INCIDENTS[0]
    res = _run([{"type": "record", "id": f"r:{d}"}], {"kind": "in_contact"})
    row = next(g for g in res["grid"] if g["signal"] == "contact:ann:bob")
    assert row["weight"] == "low" and "routine" in row["why_low"]
    assert res["level"]["key"] == "coincidence"
    assert next(c for c in res["checks"] if c["check"] == "routine")["outcome"] == "weighed_low"


def test_together_once_with_no_contact_ever_is_coincidence_likely():
    res = _run([{"type": "record", "id": "shopB"}, {"type": "record", "id": "shopD"}], {"kind": "together"})
    assert res["level"]["key"] == "coincidence", res["level"]
    assert res["level"]["rule"] == "together_once_no_contact"
    assert "no contact" in res["level"]["sentence"]


def test_a_person_with_nothing_on_the_pattern_nights_is_no_link_found_with_its_search():
    res = _run(_seed(), {"kind": "every_time"})
    dan = next(n for n in res["not_in_pattern"] if n["who"] == "Dan Dale")
    assert not dan["found"] and "not proof" in dan["says"]
    assert dan["searched"] and dan["counts"]["instances"] == 3


def test_no_dated_item_is_cant_tell_naming_what_is_missing():
    res = _run([{"type": "person", "id": "dan"}], {"kind": "in_contact"})
    assert res["level"]["key"] == "cant_tell"
    assert res["gaps"] and "date" in res["level"]["sentence"]


def test_case_fact_weighs_a_signal_low_and_is_named():
    fact = {"id": "f1", "kind": "live_together", "text": "Bob and the prepaid phone's user share a flat",
            "people": ["bob", "pre"], "by_name": "Test Person", "at": "2026-11-17T00:00:00+00:00", "state": "active"}
    res = _run(_seed(), {"kind": "every_time"}, facts=[fact])
    row = next(g for g in res["grid"] if g["signal"] == "together:bob:pre")
    assert row["weight"] == "low" and "Test Person" in row["why_low"]
    assert res["case_facts_used"] and res["case_facts_used"][0]["id"] == "f1"


def test_comparison_same_weekday_hours_states_its_set():
    incidents, hours = M.incidents_from_selection([{"at": at(INCIDENTS[0], 22), "kind": "message"}], "UTC")
    ordinary, comp = M.comparison_set("same_weekday_hours", incidents, (FRIDAYS[0], FRIDAYS[-1]), "UTC", hours)
    assert {o["weekday"] for o in ordinary} == {"Friday"} and len(ordinary) == 9
    assert "every other Friday" in comp["words"] and "UTC" in comp["words"]
    before, comp2 = M.comparison_set("same_people_ordinary", incidents, (FRIDAYS[0], FRIDAYS[1]), "UTC", hours)
    assert len(before) == 8 - 0 and "every other day" in comp2["words"]


def test_money_after_a_night_joins_that_night():
    groups = M.cluster([{"at": at(INCIDENTS[0], 23), "kind": "doc_row"},
                        {"at": at(INCIDENTS[0], 12) + __import__("datetime").timedelta(days=1), "kind": "payment",
                         "day_only": True}])
    assert len(groups) == 1


def test_preview_lists_questions_with_checks_and_counts_quickly():
    out = questions.preview(FakeStore(), _seed())
    assert out["seconds"] < 2
    assert 3 <= len(out["questions"]) <= 5
    kinds = [q["kind"] for q in out["questions"]]
    assert "every_time" in kinds
    q = next(q for q in out["questions"] if q["kind"] == "every_time")
    assert q["checks"] and q["count"] == 9 and q["chips"]["compare_with"] == "same_weekday_hours"
    assert {p["key"] for p in out["taken"]["people"]} >= {"ann", "bob", "pre"}


def test_level_rules_never_name_the_demo_case():
    """The rules are written for any case: none of the demo case's people, places or numbers appears in them."""
    key = json.loads((Path(__file__).resolve().parents[2] / "evidence-engine" / "tests" / "phone" /
                      "planted-truths.json").read_text())
    names = set()
    for e in key["entries"]:
        names |= set(re.findall(r"\b([A-Z][a-z]{2,} [A-Z][a-z]{2,})\b", e["statement"]))
    names |= {"Kell", "Okafor", "Marsh", "Mateo", "Quillan", "Brightwater", "Pocketwire", "Fallowby", "Stowell", "555-01"}
    text = "\n".join(p.read_text() for p in RULES.glob("*.py"))
    hits = sorted(n for n in names if n in text)
    assert not hits, hits


def test_level_names_are_neils_five():
    assert list(levels.LEVELS.values()) == ["Strong link", "Probable link", "Possible link", "Coincidence likely",
                                            "Can't tell"]


def test_who_used_a_phone_names_the_phone_it_travels_with_and_weighs_contact_against_it():
    res = _run([{"type": "phone", "id": "phC"}], {"kind": "who_used"})
    top = res["candidates"][0]
    assert top["key"] == "bob" and top["days_together"] == 3
    # the two phones message each other, so they are more likely two people: never above Possible
    assert top["level"]["key"] == "possible" and "contact each other" in top["level"]["sentence"]
    assert res["level"]["key"] == "possible" and "Bob Brook" in res["level"]["sentence"]
    assert levels.who_used({"present": 18, "of": 20}, 0)["key"] == "strong"
    assert levels.who_used({"present": 4, "of": 6}, 0)["key"] == "probable"
    assert levels.who_used({"present": 0, "of": 0}, 0)["key"] == "cant_tell"


def test_document_rows_are_tested_against_the_phones_at_the_times_they_give():
    d = INCIDENTS[0]
    res = _run([{"type": "record", "id": f"doc:{d}"}], {"kind": "document"})
    row = next(g for g in res["grid"] if g["link_kind"] == "statement") if any(
        g["link_kind"] == "statement" for g in res["grid"]) else None
    # the document puts Ann at the gate at 23:00 while her phone is silent: no agreement is claimed
    assert row is None or row["incident"]["present"] == 0
    assert res["level"]["key"] != "strong"
