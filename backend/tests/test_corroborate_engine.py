"""Corroborate (lx-corroengine B-H) on an invented case: levels come from the rules, every check is returned, copies
count once, missing data is Can't tell, and the rules never name the demo case's people."""
import json
from datetime import datetime, timedelta, timezone
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
    assert res["level"]["reasons"] == ["The selection holds no date or time."]
    assert res["gaps"][0]["words"] == "The selection holds no date or time."


def test_cant_tell_reasons_read_as_sentences():
    """Each reason is its own sentence: never "holds no a ..." or "holds no another ..."."""
    import re
    src = open(engine.__file__).read()
    assert not re.search(r"holds no \{", src)
    res = _run([{"type": "person", "id": "dan"}], {"kind": "in_contact"})
    for r in res["level"]["reasons"] + [g["words"] for g in res["gaps"]]:
        assert not re.search(r"\bno (a|an|another)\b", r), r


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


def test_group_vs_group_sets_one_groups_links_against_the_others_on_the_same_nights():
    members = [{"type": "record", "id": f"m2:{d}"} for d in INCIDENTS]
    res = _run(members, {"kind": "in_contact", "chips": {"people": ["bob", "pre"], "against": ["ann", "dan"],
                                                         "compare_with": "group_vs_group"}})
    assert res["comparison"]["kind"] == "group_vs_group" and res["comparison"]["ordinary"] == []
    assert "Ann Arden and Dan Dale" in res["comparison"]["words"]
    row = next(g for g in res["grid"] if g["signal"] == "contact:bob:pre")
    # Bob and the prepaid phone on 3 of 3 nights; Ann and Dan never, on the same 3 nights
    assert row["incident"]["present"] == 3 and row["ordinary"] == {"present": 0, "absent": 3, "no_data": 0, "of": 3}
    # a pair never in contact is counted, then left out of the grid; a pair across the groups is shown, not weighed
    assert not any(g["signal"] == "contact:ann:dan" for g in res["grid"])
    across = next(g for g in res["grid"] if g["signal"] == "contact:ann:pre")
    assert across["context"]
    # only contact can be compared (Ann has no positions, so "together" has no data on the other side): one kind
    assert res["level"]["key"] == "possible", res["level"]
    assert "none of the 3 pair-instances in the other group" in res["level"]["sentence"]


def test_group_vs_group_with_no_other_group_is_cant_tell():
    store = FakeStore()
    store.people = lambda: [p for p in __import__("tests.corroborate_world", fromlist=["PEOPLE"]).PEOPLE
                            if p["key"] in ("bob", "pre")]
    res = engine.run(store, [{"type": "record", "id": f"m2:{INCIDENTS[0]}"}],
                     {"kind": "in_contact", "chips": {"compare_with": "group_vs_group"}})
    assert res["level"]["key"] == "cant_tell" and "another group" in res["level"]["sentence"]
    assert res["level"]["reasons"] == ["The selection names no other group to compare with."]


def test_the_composers_kind_names_reach_the_same_rules_and_an_unknown_kind_is_said():
    assert questions.canonical("repeats") == "every_time" and questions.canonical("document_agrees") == "document"
    assert questions.canonical("guess") is None
    res = _run(_seed(), {"kind": "repeats"})
    assert res["question"]["kind"] == "every_time" and res["level"]["key"] == "strong"
    res = _run(_seed(), {"kind": "guess"})
    assert any("not one Corroborate weighs" in n for n in res["notes"])


def test_a_saved_question_keeps_the_text_chips_and_the_engine_chips_in_their_form():
    from services.relations.runs import _question
    q = _question({"kind": "repeats", "text": "Does this happen every time?",
                   "chips": {"who": "Ann and Bob", "compare_with": "ordinary days of the period", "people": ["ann", "bob"],
                             "against": ["dan"], "hours": {"start": "22:00", "length_h": 6}, "after": "2025-02-01",
                             "nonsense": "x"}})
    c = q["chips"]
    assert c["who"] == "Ann and Bob" and c["people"] == ["ann", "bob"] and c["against"] == ["dan"]
    assert c["hours"] == {"start": "22:00", "length_h": 6.0} and c["after"] == "2025-02-01" and "nonsense" not in c
    # the composer's words are kept to read; only a set the engine knows chooses the comparison
    assert "compare_with" not in c and c["compare_words"] == "ordinary days of the period"
    assert _question({"chips": {"compare_with": "group_vs_group"}})["chips"]["compare_with"] == "group_vs_group"
    assert "hours" not in _question({"chips": {"hours": {"start": "late", "length_h": 6}}})["chips"]


def test_every_level_sentence_states_its_counts():
    """Every level states its comparison and the counts on both sides (Can't tell states what is missing)."""
    d = INCIDENTS[0]
    for members, q in ((_seed(), {"kind": "every_time"}), ([{"type": "record", "id": f"r:{d}"}], {"kind": "in_contact"}),
                       ([{"type": "record", "id": "shopB"}, {"type": "record", "id": "shopD"}], {"kind": "together"})):
        lvl = _run(members, q)["level"]
        assert re.search(r"\d+ of \d+|none of the \d+|on the \d+ ", lvl["sentence"]), lvl


def test_a_phones_coverage_sets_aside_clock_errors_and_lone_days():
    from datetime import date, timedelta
    real = [date(2022, 3, 1) + timedelta(days=n) for n in range(0, 60, 2)]
    junk = [date(1, 1, 1), date(1970, 1, 20), date(2057, 8, 30)]
    spans, aside = M.phone_spans(real + junk)
    assert len(spans) == 1 and aside == 3
    assert spans[0][0].date() == date(2022, 3, 1) and spans[0][1].date() == real[-1]
    # a phone used once a week is still covered; two lone days far apart are not a stretch
    weekly = [date(2023, 1, 2) + timedelta(days=7 * n) for n in range(6)]
    assert len(M.phone_spans(weekly)[0]) == 1 and M.phone_spans(weekly[:1] + [date(2024, 1, 1)]) == ([], 2)


def test_searched_lists_only_the_kinds_this_question_computed():
    res = _run([{"type": "record", "id": f"r:{INCIDENTS[0]}"}], {"kind": "in_contact"})
    checked = set(res["searched"]["kinds_checked"])
    assert "contact" in checked and not checked & {"statement", "same_person"}
    assert set(res["searched"]["kinds_with_nothing"]) <= checked


def test_coincidence_names_the_link_between_people_before_one_persons_own_records():
    from services.corroborate.levels import sentence
    inst = [{"id": "a", "side": "incident"}]
    comp = {"incident_noun": "instances asked about", "ordinary_noun": "ordinary days"}
    alone = {"label": "Ann Arden's phone silent for 4 hours or more", "people": ["ann"], "weight": "full",
             "incident": {"present": 3, "of": 5}, "ordinary": {"present": 99, "of": 103}}
    pair = {"label": "Ann Arden and Bob Brook in contact", "people": ["ann", "bob"], "weight": "full",
            "incident": {"present": 1, "of": 5}, "ordinary": {"present": 3, "of": 103}}
    words = sentence({"key": "coincidence", "rule": "as_often_or_explained", "separating_kinds": []}, [],
                     [alone, pair], comp, inst * 5, [], [])
    assert words.startswith("Coincidence likely: Ann Arden and Bob Brook in contact on too few") and "1 of 5" in words


def test_a_map_area_of_every_day_someone_was_there_is_the_place_asked_about_not_seventy_nights():
    """A Map area brings in every position inside it (here Bob at the yard each day at 10:00). Beside the seed's
    messages those positions say where, not when: the instances stay the pattern nights and the level holds."""
    from datetime import timedelta
    from tests.corroborate_world import YARD, build_records
    recs = build_records()
    days = [FRIDAYS[0] + timedelta(days=n) for n in range(70)]
    recs += [{"ref": f"work:{d}", "kind": "position", "at": at(d, 10), "phone": "phB", "owner": "bob",
              "place": {"lat": YARD[0], "lon": YARD[1], "radius_m": 10}} for d in days]
    area = [{"type": "record", "id": f"work:{d}"} for d in days] + [{"type": "record", "id": f"pB:{INCIDENTS[0]}"}]
    res = _run(_seed() + area, {"kind": "every_time"}, recs=recs)
    assert res["level"]["key"] == "strong", res["level"]
    assert {i["id"] for i in res["comparison"]["incident"]} == {d.isoformat() for d in INCIDENTS}
    assert any("70 positions chosen fall outside the hours" in n and "1 within 2 hours" in n for n in res["notes"]), res["notes"]


def test_positions_alone_are_left_as_the_selection():
    from tests.corroborate_world import YARD
    pts = [{"ref": f"p{n}", "kind": "position", "at": at(FRIDAYS[n], 10), "place": {"lat": YARD[0], "lon": YARD[1],
                                                                                   "radius_m": 10}} for n in range(3)]
    assert engine.fold_positions(pts) == (pts, [])


def test_an_unnamed_phone_inside_the_area_every_evening_is_a_place_row_not_a_second_phone_of_someone():
    """lx-demo, 17 Nov: a Map area of 404 positions beside the mixed selection stopped the run (StopIteration in the
    shared-device check): the row "the user of Phone C inside the area chosen" names one person, so there is no
    other person whose second phone it could be."""
    from datetime import timedelta
    from tests.corroborate_world import YARD, build_records
    recs = build_records()
    days = [FRIDAYS[0] + timedelta(days=n) for n in range(70)]
    recs += [{"ref": f"eve:{d}", "kind": "position", "at": at(d, 19), "phone": "phC", "owner": "pre",
              "place": {"lat": YARD[0], "lon": YARD[1], "radius_m": 10}} for d in days]
    res = _run(_seed() + [{"type": "record", "id": f"eve:{d}"} for d in days], {"kind": "every_time"}, recs=recs)
    device = next(c for c in res["checks"] if c["check"] == "shared_device")
    assert device["outcome"] == "checked", device
    assert res["level"]["key"] in ("strong", "probable"), res["level"]


def _old_activity_row(people, activity, instances, window=timedelta(minutes=30)):
    """The row as it was computed before 18 Nov (every list sorted per instance, every pair compared)."""
    from services.corroborate import signals as S
    keys = sorted(people)
    row = S._row("activity:all", "activity", "x", keys, instances, context=True)
    for inst in instances:
        per = {k: S._between(sorted(activity[k]), inst["start"], inst["end"]) for k in keys}
        if any(not v for v in per.values()):
            covered = all(S._between(sorted(activity[k]), inst["start"] - timedelta(hours=24),
                                     inst["end"] + timedelta(hours=24)) for k in keys)
            S._set(row, inst, False, covered=covered)
            continue
        hit = None
        for t in sorted(x for v in per.values() for x in v):
            if all(any(t <= x <= t + window for x in v) for v in per.values()):
                hit = t
                break
        S._set(row, inst, hit is not None, [], hit, True)
    return row


def test_activity_row_reads_each_phone_once_and_finds_the_same_bursts():
    """Phone reference 1, 18 Nov: the row sorted every phone's whole activity once per instance (83% of a weighing)."""
    import random
    from services.corroborate import signals as S
    rnd = random.Random(5)
    t0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
    reads = {"n": 0}

    class Times(list):
        def __iter__(self):
            reads["n"] += 1
            return super().__iter__()
    activity = {k: Times(sorted(t0 + timedelta(minutes=rnd.randint(0, 60 * 24 * 60)) for _ in range(rnd.randint(50, 900))))
                for k in ("ann", "bob", "pre")}
    people = {k: {"key": k} for k in activity}
    instances = [{"id": f"i{d}", "start": t0 + timedelta(days=d, hours=18), "end": t0 + timedelta(days=d, hours=23)}
                 for d in range(0, 62)]
    new = S.activity_row(people, activity, instances)
    assert reads["n"] <= len(activity)
    old = _old_activity_row(people, {k: list(v) for k, v in activity.items()}, instances)
    assert new["cells"] == old["cells"] and new["times"] == old["times"]
    assert "present" in new["cells"].values() and "absent" in new["cells"].values()
