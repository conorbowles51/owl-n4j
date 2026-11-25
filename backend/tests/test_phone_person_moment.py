"""Phones redesign screens 3 (one person across every phone) and 4 (around a moment). Invented data only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.phone import compare as C
from services.phone import moment as MO
from services.phone import person_across as PA
from tests.phone_pg import fresh_engine, make_case
from tests.phone_streams_fixture import at, phone

PRIYA, MARISOL, DORIAN = "phone:+12025550101", "phone:+12025550102", "phone:+12025550103"


def _m(instant, body, sender, recip, owner, deleted="Intact", app="WhatsApp"):
    return dict(kind="message", instant=instant, body=body, app=app, thread="t-%s-%s" % tuple(sorted((sender, recip))),
                deleted_state=deleted, direction="outgoing" if sender == owner else "incoming",
                parties=[(sender, "sender", sender == owner, None, None), (recip, "recipient", recip == owner, None, None)])


T0 = at(2024, 3, 11, 9, 0)


def _case(c):
    case = make_case(c)
    shared = _m(T0, "can you cover the front desk at two", PRIYA, DORIAN, PRIYA)
    x, _ = phone(c, case, label="P1", owner=PRIYA, contacts={DORIAN: "Dorian (office)"}, events=[
        shared, _m(T0 + timedelta(days=5), "last thing on this phone ok", PRIYA, MARISOL, PRIYA)])
    y, _ = phone(c, case, label="P2", owner=MARISOL, contacts={DORIAN: "D Pell"}, events=[
        _m(T0 + timedelta(days=1), "checks are in the drawer now", MARISOL, DORIAN, MARISOL),
        _m(T0 + timedelta(days=2), "transfer went through fine", DORIAN, MARISOL, MARISOL)])
    z, _ = phone(c, case, label="P3", owner=DORIAN, events=[
        _m(T0, "can you cover the front desk at two", PRIYA, DORIAN, DORIAN),
        _m(T0 + timedelta(minutes=1), "leave me your login please", DORIAN, PRIYA, DORIAN),     # missing on P1
        _m(T0 + timedelta(days=9), "after her phone stopped recording", DORIAN, PRIYA, DORIAN),  # outside P1's span
        _m(T0 + timedelta(days=1), "checks are in the drawer now", MARISOL, DORIAN, DORIAN, deleted="Deleted"),
        _m(T0 + timedelta(days=2, seconds=30), "transfer went through fine", DORIAN, MARISOL, DORIAN)])
    return case, str(x), str(y), str(z)


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def test_match_pairs_is_the_set_compare_counts():
    ev = (lambda e, t, body, d: SimpleNamespace(extraction_id=e, kind="message", app="WhatsApp", at=T0 + timedelta(
        seconds=t), body=body, d=None, direction=d))
    evs = [ev("a", 0, "hello there friend", "outgoing"), ev("b", 5, "hello there friend", "incoming"),
           ev("a", 600, "something else entirely", "outgoing"), ev("b", 4000, "something else entirely", "incoming")]
    assert C.match_pairs(evs, "a", "b") == [(0, 1)]
    assert C.match(evs, "a", "b") == {0, 1}


def test_person_across_every_phone(engine):
    with engine.begin() as c:
        case, x, y, z = _case(c)
        out = PA.person_across(c, case, [DORIAN])
    assert sorted(p["extraction_id"] for p in out["phones"]) == sorted([x, y, z])
    cards = {p["extraction_id"]: p for p in out["phones"]}
    assert cards[x]["saved_as"] == ["Dorian (office)"] and cards[y]["saved_as"] == ["D Pell"]
    assert cards[z]["is_own"] and not cards[x]["is_own"]
    assert (cards[x]["messages"], cards[y]["messages"], cards[z]["messages"]) == (1, 2, 5)
    # five contacts: the shared one, two only on P3, and two P2 and P3 both hold
    assert out["records_total"] == 5 and out["summary"]["messages"] == 5
    on = sorted(tuple(sorted(r["on"])) for r in out["records"])
    assert on == sorted(tuple(sorted(t)) for t in [(x, z), (z,), (z,), (y, z), (y, z)])
    d = {k["code"]: k for k in out["differs"]}
    assert (d["missing"]["n"], d["missing"]["explained"]) == (2, 1)
    lab = {p["extraction_id"]: p["label"] for p in out["phones"]}
    assert d["deleted"]["n"] == 1 and "1 deleted on %s and still on %s." % (lab[z], lab[y]) == d["deleted"]["body"]
    assert d["names"]["n"] == 2
    assert d["clocks"]["n"] == 1
    assert out["next_steps"][0]["code"] == "open_unexplained" and out["next_steps"][0]["filter"] == "missing_unexplained"
    assert {s["code"] for s in out["next_steps"]} >= {"open_deleted", "open_clocks", "compare", "export"}
    assert {tuple(sorted(s["on"])): s["messages"] for s in out["compare"]} == {
        tuple(sorted((x, z))): 1, tuple(sorted((y, z))): 2, (z,): 2}


def test_each_difference_opens_its_records(engine):
    with engine.begin() as c:
        case, x, y, z = _case(c)
        unexplained = PA.person_across(c, case, [DORIAN], only="missing_unexplained")
        recorded = PA.person_across(c, case, [DORIAN], only="missing_not_recording")
        deleted = PA.person_across(c, case, [DORIAN], only="deleted")
        with pytest.raises(ValueError):
            PA.person_across(c, case, [DORIAN], only="anything")
    assert [r["row"]["body"] for r in unexplained["records"]] == ["leave me your login please"]
    assert [r["row"]["body"] for r in recorded["records"]] == ["after her phone stopped recording"]
    assert deleted["records_total"] == 1 and deleted["records"][0]["deleted_on"] == [z]
    assert unexplained["contacts_total"] == 5


def test_between_two_people_and_phone_scope(engine):
    with engine.begin() as c:
        case, x, y, z = _case(c)
        pair = PA.person_across(c, case, [DORIAN], with_keys=[MARISOL])
        two = PA.person_across(c, case, [DORIAN], phones=[x, z])
        with pytest.raises(PA.NotInCase):
            PA.person_across(c, case, [DORIAN], phones=["00000000-0000-0000-0000-000000000000"])
    assert pair["records_total"] == 2 and pair["with"]["keys"] == [MARISOL]
    assert sorted(p["extraction_id"] for p in two["phones"]) == sorted([x, z]) and two["records_total"] == 5


def test_not_recording_stretches_merge_hours_and_clip(monkeypatch):
    from services.phone import timeline_lens
    a, b = at(2024, 3, 12, 9, 30), at(2024, 3, 12, 12, 15)
    hours = {at(2024, 3, 12, h) for h in (9, 10, 12)}
    monkeypatch.setattr(timeline_lens, "_no_data_hours", lambda conn, ext, s, e: hours)
    got = MO.not_recording(None, "p", a, b)
    assert got == [{"start": a, "end": at(2024, 3, 12, 11)}, {"start": at(2024, 3, 12, 12), "end": b}]


def test_strip_reads_together_apart_and_unknown():
    a = at(2024, 3, 12, 9)
    eps = [{"kind": "together", "start": a + timedelta(minutes=5), "end": a + timedelta(minutes=25), "breadth": "tight"},
           {"kind": "apart", "start": a + timedelta(minutes=65), "end": a + timedelta(minutes=85), "breadth": None}]
    s = [x["state"] for x in MO.strip(eps, a, a + timedelta(hours=2), slots=4)]
    assert s == ["together", "unknown", "apart", "unknown"]
    assert MO.hm(at(2024, 3, 13, 1), a, a + timedelta(days=2)) == "13 Mar 01:00"


def test_moment_lanes_and_records_on_every_phone(engine):
    with engine.begin() as c:
        case, x, y, z = _case(c)
        out = MO.moment(c, case, T0.isoformat(), (T0 + timedelta(hours=3)).isoformat())
        with pytest.raises(ValueError):
            MO.moment(c, case, T0.isoformat(), (T0 + timedelta(days=8)).isoformat())
    assert sorted(p["extraction_id"] for p in out["phones"]) == sorted([x, y, z])
    assert len(out["pairs"]) == 3 and all(len(p["strip"]) == MO.STRIP_SLOTS for p in out["pairs"])
    msgs = [r for r in out["records"] if r["kind"] == "message"]
    assert [sorted(r["on"]) for r in msgs] == [sorted([x, z]), [z]]
    assert out["summary"].startswith("2 records in this window on 2 phones.")
    counts = {p["extraction_id"]: p["counts"]["messages"] for p in out["phones"]}
    assert counts == {x: 1, y: 0, z: 2}
