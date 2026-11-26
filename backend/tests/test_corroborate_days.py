"""The evidence day by day (lx-corroredo C): the relation in one sentence naming the phones and owners, one tile per
event with its outcome and time, the ordinary days counted with no-data days apart. Fails on the code before it: the
engine's result had no ``days`` block."""
import json
from datetime import datetime, timedelta, timezone

from services.corroborate import days as D, engine, model as M, questions as Q
from routers import corroborate as R
from routers.case_access import require_case_view

from tests.corroborate_world import INCIDENTS, FakeStore


def _run(members, question):
    res = engine.run(FakeStore(), members, question)
    json.dumps(res)
    return res


def test_together_question_tiles_every_incident_with_outcome_and_time_and_counts_ordinary_days():
    members = [{"type": "record", "id": f"pB:{d}"} for d in INCIDENTS] + \
              [{"type": "record", "id": f"pC:{d}"} for d in INCIDENTS]
    res = _run(members, {"kind": "together"})
    days = res["days"]
    rel = days["relation"]
    assert rel["link_kind"] == "together" and rel["word"] == "together"
    # the definition names each owner's phone, so "together" says for which phones
    # a person with a dossier is named with their phone; a phone whose user is unknown is named by its own label
    assert "Bob Brook's phone (phB)" in rel["definition"] and "and phC were placed" in rel["definition"]
    assert "the user of Phone C's phone" not in rel["definition"]
    assert "15 minutes" in rel["definition"]
    assert [t["instance"] for t in days["tiles"]] == [i["id"] for i in res["comparison"]["incident"]]
    assert len(days["tiles"]) == 3
    for t in days["tiles"]:
        assert t["outcome"] == "present" and t["outcome_words"] == "Together"
        assert t["detail"] == "11:30 PM to 11:35 PM", t
        assert t["events"] == ["2 locations"] and len(t["event_refs"]) == 2
        assert t["records"]
    o = days["ordinary"]
    assert o["of"] == len(res["comparison"]["ordinary"]) == o["present"] + o["absent"] + o["no_data"]
    assert len(o["cells"]) == o["of"]
    assert o["words"].startswith(f"Together on {o['present']}, apart on {o['absent']}, no location data on {o['no_data']}")


def test_each_question_kind_gets_a_relation_from_the_engine_rows():
    seed = [{"type": "record", "id": f"m1:{INCIDENTS[0]}"}, {"type": "record", "id": f"m2:{INCIDENTS[0]}"}]
    res = _run(seed, {"kind": "every_time"})
    assert res["days"]["relation"] is not None
    assert len(res["days"]["tiles"]) == len(res["comparison"]["incident"]) == 3
    assert res["days"]["events_phrase"]


def test_a_check_payment_reads_as_its_number_and_amount():
    p = {"kind": "payment", "amount_minor": 246000, "memo": "REFUND CHECK # 2204 deposited", "direction": "credit"}
    assert D.event_words(p) == "Check 2204 · $2,460.00"
    assert D.event_words({"kind": "payment", "amount_minor": 1000, "memo": "transfer", "direction": "debit"}) == \
        "Payment · $10.00"
    phrase, source = D._events_phrase([dict(p, at=datetime(2026, 3, 4, tzinfo=timezone.utc))] * 7, 7)
    assert phrase == "the 7 check deposit days" and source == "from the financial records"


def test_a_no_data_tile_names_the_phone_without_locations_and_is_counted_apart():
    utc = timezone.utc
    mk = lambda d, side: M.make_instance(d, datetime.min.time(), timedelta(hours=24), utc, side, "UTC")  # noqa: E731
    inc, ordi = mk(INCIDENTS[0], "incident"), mk(INCIDENTS[1], "ordinary")
    people = {"a": {"key": "a", "label": "Ann", "dossier_id": "a", "phones": ["pa"], "phone_labels": {"pa": "Phone 1"}},
              "b": {"key": "b", "label": "Bob", "dossier_id": "b", "phones": ["pb"], "phone_labels": {"pb": "Phone 2"}}}
    row = {"id": "together:a:b", "link_kind": "together", "label": "Ann and Bob in the same place", "people": ["a", "b"],
           "cells": {inc["id"]: "no_data", ordi["id"]: "no_data"}, "records": {}, "weight": "full",
           "incident": {"present": 0, "absent": 0, "no_data": 1, "of": 1},
           "ordinary": {"present": 0, "absent": 0, "no_data": 1, "of": 1}}
    recs = [{"ref": "x", "kind": "position", "owner": "a", "at": inc["start"] + timedelta(hours=1),
             "place": {"lat": 0, "lon": 0, "radius_m": 5}}]
    out = D.build([row], [inc, ordi], recs, [], people, "together", {"ordinary_noun": "other days"}, "UTC")
    t = out["tiles"][0]
    assert t["outcome"] == "no_data" and t["outcome_words"] == "No location data"
    assert t["detail"] == "Bob's phone has no locations that day, so it counts neither way."
    assert out["ordinary"]["no_data"] == 1 and out["ordinary"]["present"] == 0
    assert "Ann's phone (Phone 1) and Bob's phone (Phone 2)" in out["relation"]["definition"]


def test_repeated_records_on_a_day_are_said_once_with_their_count():
    assert D.collapse(["Message"] * 8 + ["Document: badge B-20417", "Message"]) == ["9 messages", "Document: badge B-20417"]
    assert D.collapse(["Check 2204 · $2,460.00", "Check 2205 · $2,310.00"]) == ["Check 2204 · $2,460.00", "Check 2205 · $2,310.00"]


def test_people_a_question_can_name_include_phone_users_without_a_dossier():
    got = Q.people_choices(FakeStore())
    by = {p["key"]: p for p in got}
    assert by["pre"] == {"key": "pre", "label": "the user of Phone C", "dossier": False, "phones": ["phC"], "accounts": 0}
    assert by["ann"]["accounts"] == 1 and by["ann"]["dossier"]
    assert [p["dossier"] for p in got] == sorted((p["dossier"] for p in got), reverse=True)  # named people first
    route = next(r for r in R.router.routes if r.path == "/api/cases/{case_id}/corroborate/people")
    assert require_case_view in {d.dependency for d in route.dependencies}


def test_the_verdicts_numbers_name_their_link_so_they_read_against_the_right_day_count():
    """Live 26 Nov: "Strong link: … (5 of 5 instances asked about, none of the 74 ordinary days)" sat above a strip of
    "104 ordinary days, in contact on 3" for another link, and read as a contradiction."""
    from services.corroborate import levels as L
    comp = {"incident_noun": "instances asked about", "ordinary_noun": "ordinary days", "words": "w"}
    row = {"label": "Ann and Bob in contact through a third number", "link_kind": "contact", "weight": "full",
           "incident": {"present": 5, "of": 5}, "ordinary": {"present": 0, "of": 74}}
    lvl = {"key": "strong", "rule": "kinds_repeat_rare", "separating_kinds": ["contact"]}
    got = L.sentence(lvl, [row], [row], comp, [{}] * 5, [], [])
    assert got.endswith("(strongest, Ann and Bob in contact through a third number: 5 of 5 instances asked about, "
                        "none of the 74 ordinary days)."), got
    lvl = {"key": "possible", "rule": "one_kind", "separating_kinds": ["contact"]}
    assert "(Ann and Bob in contact through a third number: 5 of 5" in L.sentence(lvl, [row], [row], comp, [{}] * 5, [], [])


def test_a_run_still_working_can_be_read_while_its_answer_is_partial():
    """Live 26 Nov 04:06: the Corroborate page polls the answer right after Ask; the run had saved only its
    corroboration ({"corroboration", "partial"}), and the run view failed with KeyError 'candidates' (500)."""
    from services.relations import runs
    out = runs._first_page({"corroboration": {"level": {"name": "Possible link"}}, "partial": True})
    assert out["candidates"] == [] and out["no_links"] == [] and out["paging"]["candidates"]["total"] == 0
    assert out["corroboration"]["level"]["name"] == "Possible link" and out["partial"] is True
    json.dumps(out)
