"""05-S16c, approach 16 number switching (05 section 16c.8). Invented data only."""
from __future__ import annotations

import pytest

from services.phone_analysis import number_switching as N
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER = "phone:+12025550100"
X, Y, W = "phone:+12025550111", "phone:+12025550122", "phone:+12025550199"
OTHERS = ["phone:+120255502%02d" % i for i in range(10)]
PARAMS = {k: v["default"] for k, v in N.PARAMETERS.items()}


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def group(t, sender, to):
    return dict(kind="message", instant=t, body="synthetic", thread="g", direction="incoming",
                parties=[(sender, "sender", False, None, None), (OWNER, "recipient", True, None, None)] +
                        [(k, "recipient", False, None, None) for k in to])


def plain(t, other):
    return dict(kind="message", instant=t, body="synthetic", thread="p", direction="outgoing",
                parties=[(OWNER, "sender", True, None, None), (other, "recipient", False, None, None)])


@needs_template
def test_pair_listed_and_phone_end_is_not_a_stop(engine):
    """16c.8 tests 1 to 3: X talks to 8 counterparts until day 30, Y to 7 of them from day 35: listed with the
    similarity and shared count; on a phone whose data ends at day 30 nobody is paired; nothing is merged."""
    day = lambda d: at(2023, 1, 1, 12) + __import__("datetime").timedelta(days=d)  # noqa: E731
    with engine.begin() as c:
        case = make_case(c)
        evs = [plain(day(0), W), plain(day(100), W)]
        evs += [group(day(d), X, OTHERS[:7]) for d in (5, 15, 30)]
        evs += [group(day(d), Y, OTHERS[:6]) for d in (35, 50)]
        phone(c, case, label="C1", owner=OWNER, events=evs)
        short = "phone:+12025550300"
        evs2 = [plain(day(0), W)] + [group(day(d), "phone:+12025550444", OTHERS[:7]) for d in (5, 30)]
        phone(c, case, label="C2", owner=short, events=[dict(e, parties=[(short if p[0] == OWNER else p[0],) + p[1:]
                                                                         for p in e["parties"]]) for e in evs2])
    with engine.connect() as c:
        res, counts = N.analyse(c, case, PARAMS)
    (r,) = res
    m = r["measures"]
    assert (m["from"], m["to"]) == (X, Y)
    assert m["shared"] == 7 and m["similarity"] == round(7 / 8, 3) and m["gap_days"] == 5.0
    assert "never_same_day" in m["markers"]
    assert any(d["code"] == "not_merged" for d in r["directions"]["undercuts"])
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM pv_identity WHERE person_id IS NOT NULL").scalar() == 0


@needs_template
def test_a_pair_under_the_defaults_is_listed_as_faint_and_owner_only_pairs_are_counted(engine):
    """Neil 2026-11-04: no cutoff hides a match. X and Y share one counterpart besides the owner, under the default
    5 shared: listed as a faint switch_possible (the old code dropped it). Z talked only to the owner, so Z and Y share
    only the owner, which every number on the phone shares: counted and stated, not listed."""
    day = lambda d: at(2023, 1, 1, 12) + __import__("datetime").timedelta(days=d)  # noqa: E731
    Z = "phone:+12025550133"
    with engine.begin() as c:
        case = make_case(c)
        evs = [plain(day(0), W), plain(day(100), W), plain(day(10), Z), plain(day(28), Z)]
        evs += [group(day(d), X, OTHERS[:1]) for d in (5, 30)]
        evs += [group(day(d), Y, OTHERS[:1] + OTHERS[5:9]) for d in (35, 50)]
        phone(c, case, label="C1", owner=OWNER, events=evs)
    with engine.connect() as c:
        res, counts = N.analyse(c, case, PARAMS)
    by_pair = {(r["measures"]["from"], r["measures"]["to"]): r for r in res}
    r = by_pair[(X, Y)]
    assert r["kind"] == "switch_possible" and r["measures"]["level"] == "faint"
    assert r["measures"]["shared_besides_owners"] == 1
    assert r["measures"]["strength_reasons"]["match"][1] == "under similarity 0.50 or 5 shared"
    assert (Z, Y) not in by_pair
    assert counts["share_only_owners"] >= 1
    assert "only a phone's owner" in N.counts_words(counts)

    assert all(r["measures"]["level"] in ("strong", "moderate") for r in res if r["kind"] == "switch_candidate")


def test_the_left_out_sentence_is_the_servers_and_reaches_every_stored_run():
    from types import SimpleNamespace
    from services.phone_analysis import framework as F
    F.APPROACHES[N.CODE] = N
    def run(counts):
        return F._run_out(SimpleNamespace(_mapping={
            "id": "1", "case_id": "2", "created_at": None, "started_at": None, "finished_at": None,
            "approach": N.CODE, "counts": counts}))
    assert run({"share_only_owners": 44278, "share_nothing": 1})["left_out_words"] == (
        "Counted, not listed: 44,278 more pairs share only a phone's owner (every number on a phone does); "
        "1 more pair shares no counterpart.")
    assert "left_out_words" not in run({})
