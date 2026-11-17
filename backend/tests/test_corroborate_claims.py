"""Corroborate a free-text claim (lx-corrostatement): the parser reads who, when, where and what with their source
words; a chip the sentence does not fill says so; only a confirmed claim is weighed; a confirmed claim is weighed to
fits, contradicts or can't tell from the phones' positions and contacts. Invented people and places only."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.corroborate import claim_weigh, claims as saved, model as M
from services.relations import claims as P

from tests.corroborate_world import PEOPLE, FakeStore

UTC = timezone.utc
HOME = {"lat": 51.5, "lon": -0.1, "radius_m": 150.0, "positions": 9, "how": "read from the phone: 9 positions at night"}


class Store(FakeStore):
    def __init__(self, recs=None, home=HOME):
        super().__init__(recs=recs or [])
        self.home = home

    def known_places(self):
        return [{"name": "Dale's Shop (address of Dan Dale)", "match": "Dale's Shop", "label": "Shop", "owner": "dan",
                 "address": "Dale's Shop, 1 Mill Lane", "lat": None, "lon": None, "radius_m": 100.0}]

    def routine_place(self, person, kind):
        return self.home if person == "ann" and kind == "home" else None

    def records(self, people, windows, everyone):
        return [r for r in self.recs if any(lo <= r["at"] <= hi for lo, hi in windows)]

    def activity(self, people, windows):
        return {p["key"]: [r["at"] for r in self.recs if r.get("owner") == p["key"]] for p in people}


def _read(sentence, stmt="2025-01-10", speaker="ann", store=None):
    return P.read_claim(store or Store(), sentence, statement_date=date.fromisoformat(stmt) if stmt else None,
                        speaker=speaker)


def test_home_all_evening_on_the_nth_reads_all_four_chips_with_their_words():
    out = _read("I was home all evening on the 3rd.")
    c = out["chips"]
    assert c["who"]["value"][0]["key"] == "ann" and c["who"]["words"] == "I"
    w = c["when"]["value"]
    assert w["start"].startswith("2025-01-03T18:00") and w["end"].startswith("2025-01-04T00:00")
    assert "3rd" in c["when"]["words"] and "evening" in c["when"]["words"]
    assert c["where"]["status"] == "read" and c["where"]["value"]["located"] and c["where"]["words"].lower() == "home"
    assert c["what"]["value"]["action"] == "presence" and c["what"]["value"]["negated"] is False
    assert out["missing"] == [] and out["read_by"] == "Read by Loupe · not confirmed"
    assert all(c[f]["read_by"] == "Read by Loupe · not confirmed" for f in c)
    json.dumps(out)


def test_a_line_with_no_place_says_where_is_not_stated():
    out = _read("I spoke to Bob Brook at 9pm on 3 January 2025.")
    assert out["chips"]["where"]["status"] == "not_stated" and "where: not stated" in out["chips"]["where"]["note"]
    assert "where" in out["missing"]
    assert out["chips"]["what"]["value"]["action"] == "contact" and out["chips"]["what"]["value"]["with"] == ["bob"]


def test_a_place_with_no_position_is_not_located_never_guessed():
    out = _read("On 3 January I was at Dale's Shop at 8pm.")
    w = out["chips"]["where"]
    assert w["status"] == "not_located" and w["value"]["located"] is False and "no position" in w["note"]
    home_unknown = _read("I was home on the 3rd.", speaker="bob")["chips"]["where"]
    assert home_unknown["status"] == "not_located" and "no position" in home_unknown["note"]


def test_a_day_that_needs_the_statement_date_is_left_unread_without_one():
    out = _read("I was home at 9pm on the 3rd.", stmt=None)
    assert out["chips"]["when"]["status"] in ("unread", "not_stated") and out["chips"]["when"]["value"] is None
    assert "when" in out["missing"]
    year_missing = _read("I was home at 9pm on May 31.", stmt=None)["chips"]["when"]
    assert year_missing["value"] is None and "year" in year_missing["note"]


def test_night_of_a_date_runs_into_the_next_morning_and_an_early_hour_belongs_to_it():
    c = _read("On the night of May 31 I was at the gate at about 1 am.", stmt="2024-06-12")["chips"]["when"]
    assert c["value"]["start"].startswith("2024-06-01T00:30") and c["value"]["end"].startswith("2024-06-01T01:30")
    assert "about" in c["note"] or "hedge" in c["note"]
    n = _read("On the night of May 31 I was out.", stmt="2024-06-12")["chips"]["when"]["value"]
    assert n["start"].startswith("2024-05-31T22:00") and n["end"].startswith("2024-06-01T06:00")


def test_after_work_is_shown_as_an_assumed_window():
    c = _read("I was home after work on 3 January.")["chips"]["when"]
    assert c["assumed"] is True and "assumed" in c["note"] and c["confidence"] == "low"


def test_names_resolve_through_people_numbers_and_unique_first_names_not_ambiguous_ones():
    out = _read("Bob phoned Ann Arden on 3 January at 10pm, from 15550002.", speaker=None)
    keys = {w["key"] for w in out["chips"]["who"]["value"]}
    assert keys == {"bob", "ann"}
    ppl = [dict(p) for p in PEOPLE] + [dict(PEOPLE[1], key="bob2", label="Bob Bright", names=["Bob Bright"])]
    store = Store()
    store.people = lambda: ppl
    amb = P.read_who("Bob called at 9pm", ppl, None)
    assert amb["status"] == "not_stated" and "more than one person" in amb["note"]


def test_i_without_a_speaker_is_not_read():
    out = _read("I was home on the 3rd.", speaker=None)
    assert out["chips"]["who"]["status"] == "not_stated" and "speaker" in out["chips"]["who"]["note"]


def test_the_parser_names_no_case_people():
    text = (Path(P.__file__)).read_text().lower()
    for name in ("kell", "marsh", "ruiz", "okafor", "penn", "larkmont", "wexmoor"):
        assert name not in text


# ---- weighing --------------------------------------------------------------------------------------------------

def _claim(chips_who="ann", when=("2025-01-03T18:00:00+00:00", "2025-01-03T23:59:00+00:00"), where=HOME, what=None):
    what = what or {"action": "presence", "negated": False, "with": []}
    conf = {"who": [{"key": chips_who, "label": chips_who}],
            "when": {"start": when[0], "end": when[1], "zone": "UTC", "label": "x"}, "where": where, "what": what}
    return SimpleNamespace(id="c1", sentence="I was home all evening on the 3rd.", confirmed=conf, edited=[],
                           confirmed_by_name="Test Person", status="confirmed")


def _pos(n, owner, hour, lat, lon, minute=0):
    return {"ref": f"p{n}", "kind": "position", "at": datetime(2025, 1, 3, hour, minute, tzinfo=UTC), "phone": "phA",
            "owner": owner, "place": {"lat": lat, "lon": lon, "radius_m": 30.0}}


def test_a_false_alibi_contradicts_with_the_positions_cited():
    recs = [_pos(i, "ann", 19 + i // 2, 51.60, -0.30, 10 * (i % 2)) for i in range(4)]
    res = claim_weigh.run(Store(recs), _claim())
    assert res["level"]["verdict"] == "contradicts" and res["level"]["name"] == "Contradicts"
    assert {c["ref"] for c in res["cited"]} == {"p0", "p1", "p2", "p3"}
    assert "0 inside" in " ".join(res["level"]["reasons"]) and "4 outside" in " ".join(res["level"]["reasons"])
    json.dumps(res)


def test_a_true_claim_fits_and_a_negated_claim_flips():
    recs = [_pos(i, "ann", 19 + i, 51.5001, -0.1001) for i in range(3)]
    assert claim_weigh.run(Store(recs), _claim())["level"]["verdict"] == "fits"
    neg = _claim(what={"action": "presence", "negated": True, "with": []})
    assert claim_weigh.run(Store(recs), neg)["level"]["verdict"] == "contradicts"


def test_mixed_positions_and_no_positions_are_cant_tell_with_the_reason():
    mixed = [_pos(0, "ann", 19, 51.5, -0.1), _pos(1, "ann", 21, 51.7, -0.5)]
    res = claim_weigh.run(Store(mixed), _claim())
    assert res["level"]["verdict"] == "cant_tell" and "disagree" in res["level"]["sentence"]
    none = claim_weigh.run(Store([]), _claim())
    assert none["level"]["verdict"] == "cant_tell" and "no positions" in none["level"]["sentence"]
    assert none["gaps"][0]["missing"].startswith("positions of")


def test_mostly_elsewhere_contradicts_and_the_counts_are_stated():
    recs = [_pos(0, "ann", 19, 51.5, -0.1), _pos(1, "ann", 20, 51.7, -0.5), _pos(2, "ann", 21, 51.7, -0.5)]
    res = claim_weigh.run(Store(recs), _claim())
    assert res["level"]["verdict"] == "contradicts" and "1 inside" in res["level"]["reasons"][0] and "2 outside" in res["level"]["reasons"][0]


def test_a_place_with_no_position_is_named_in_the_cant_tell_reason():
    claim = _claim(where=None)
    claim.confirmed["where_text"] = "“Dale's Shop” is an address on a dossier with no position on a map"
    res = claim_weigh.run(Store([_pos(0, "ann", 19, 51.5, -0.1)]), claim)
    assert res["level"]["verdict"] == "cant_tell" and "Dale's Shop" in res["level"]["sentence"]


def test_no_place_stays_cant_tell_and_names_the_missing_field():
    res = claim_weigh.run(Store([_pos(0, "ann", 19, 51.5, -0.1)]), _claim(where=None))
    assert res["level"]["verdict"] == "cant_tell" and "where" in res["level"]["sentence"]
    assert res["gaps"][0]["missing"] == "where"


def test_contact_claim_fits_with_a_message_and_is_cant_tell_without_phone_records():
    msg = {"ref": "m1", "kind": "message", "at": datetime(2025, 1, 3, 20, 0, tzinfo=UTC), "phone": "phA", "owner": "ann",
           "parties": ["bob"], "body": "hi"}
    what = {"action": "contact", "negated": False, "with": ["bob"], "mode": "called"}
    assert claim_weigh.run(Store([msg]), _claim(what=what, where=None))["level"]["verdict"] == "fits"
    res = claim_weigh.run(Store([]), _claim(what=what, where=None))
    assert res["level"]["verdict"] == "cant_tell" and "would leave none" in res["level"]["sentence"]
    absent = claim_weigh.run(Store([dict(msg, ref="m2", parties=["dan"])]), _claim(what=what, where=None))
    assert absent["level"]["verdict"] == "cant_tell"  # a contact not found is never a contradiction


# ---- the confirm step ------------------------------------------------------------------------------------------

@pytest.fixture()
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from postgres.models.corroborate import CorroborateClaim
    eng = create_engine("sqlite://")
    CorroborateClaim.__table__.create(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


CASE = "5f1ddc0e-2f6d-4c3b-9d54-0a1b2c3d4e5f"


def _user():
    return SimpleNamespace(id=None, full_name="Test Person")


def test_parse_saves_a_draft_and_an_unconfirmed_claim_is_refused_with_409(db):
    out = saved.parse(db, Store(), CASE, text="I was home all evening on the 3rd.", statement_date="2025-01-10",
                      speaker="ann", source={"type": "statement", "id": "x"}, user=_user())
    assert out["status"] == "draft" and out["read_by"] == "Read by Loupe · not confirmed" and out["chips"]["when"]
    with pytest.raises(saved.ClaimError) as err:
        saved.require_confirmed(db, CASE, out["id"])
    assert err.value.status == 409 and "not been confirmed" in str(err.value)
    from services.corroborate import engine
    st = Store()
    st.db, st.case = db, CASE
    with pytest.raises(saved.ClaimError):
        engine.run(st, [{"type": "claim", "id": out["id"]}], {"kind": "statement"})


def test_confirm_keeps_loupes_reading_saves_the_edit_under_the_person_and_lists_what_changed(db):
    out = saved.parse(db, Store(), CASE, text="I was home all evening on the 3rd.", statement_date="2025-01-10",
                      speaker="ann", source=None, user=_user())
    chips = {"who": [{"key": "ann", "label": "Ann Arden"}],
             "when": {"start": "2025-01-03T19:00:00+00:00", "end": "2025-01-03T23:00:00+00:00", "zone": "UTC"},
             "where": out["chips"]["where"]["value"], "what": out["chips"]["what"]["value"]}
    done = saved.confirm(db, CASE, out["id"], chips, _user())
    assert done["status"] == "confirmed" and done["confirmed_by"] == "Test Person" and done["edited"] == ["when"]
    row = saved.get(db, CASE, out["id"])
    assert row.read["chips"]["when"]["value"]["start"].startswith("2025-01-03T18:00")  # the reading is kept
    assert saved.require_confirmed(db, CASE, out["id"]).confirmed["when"]["start"].startswith("2025-01-03T19:00")
    with pytest.raises(saved.ClaimError):
        saved.confirm(db, CASE, out["id"], {**chips, "who": []}, _user())
    with pytest.raises(LookupError):
        saved.get(db, "6f1ddc0e-2f6d-4c3b-9d54-0a1b2c3d4e5f", out["id"])


def test_a_claim_run_result_can_be_read_back_like_any_run_result():
    """Found live: the run view paged result['candidates'] and a claim's result had none (500)."""
    from services.relations import runs
    out = runs._first_page(runs.claim_only_result({"claim": {"id": "c"}, "level": {"name": "Fits"}}, 1))
    assert out["candidates"] == [] and out["no_links"] == [] and out["paging"]["candidates"]["total"] == 0
    assert out["corroboration"]["claim"] == {"id": "c"}
    json.dumps(out)
