"""The Phones page (screen 1): copies on other phones, and the exact What / Who / State counts beside the list.

Invented data only: 555 numbers and made-up text. Needs the PostgreSQL phone template.
"""
from __future__ import annotations

import pytest

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_timeline_lens import _entry

pytestmark = needs_template
OWNER1, OWNER2, ANA = "phone:+12025550100", "phone:+12025550101", "phone:+12025550143"


def _m(instant, sender, recips, body, owner, deleted=None):
    parties = [(sender, "sender", sender == owner, None, None)] + [(r, "recipient", r == owner, None, None)
                                                                   for r in recips]
    e = dict(kind="message", instant=instant, body=body, thread="t", parties=parties,
             direction="outgoing" if sender == owner else "incoming")
    if deleted:
        e["deleted_state"] = deleted
    return e


def _call(instant, owner, other, seconds):
    return dict(kind="call", instant=instant, thread="c", call_duration_s=seconds, direction="outgoing",
                parties=[(owner, "sender", True, None, None), (other, "recipient", False, None, None)])


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            p1, _ = phone(c, case, label="P1", owner=OWNER1, events=[
                _m(at(2024, 1, 5, 11, 40), OWNER2, [OWNER1], "Sent you the invoice", OWNER1),   # also on P2
                _m(at(2024, 1, 5, 12, 0), ANA, [OWNER1], "half now, half on Friday", OWNER1),   # P1 only
                _m(at(2024, 1, 6, 9, 0), ANA, [OWNER1], "gone", OWNER1, deleted="Deleted"),      # P1 only, deleted
                _call(at(2024, 1, 7, 9, 2), OWNER1, OWNER2, 120)])                                # also on P2
            p2, _ = phone(c, case, label="P2", owner=OWNER2, events=[
                _m(at(2024, 1, 5, 11, 40), OWNER2, [OWNER1], "Sent you the invoice", OWNER2),
                _m(at(2024, 1, 5, 11, 40), OWNER2, [ANA], "Something else", OWNER2),             # same minute, other text
                _call(at(2024, 1, 7, 9, 2), OWNER1, OWNER2, 120),
                _call(at(2024, 1, 7, 9, 2), OWNER2, ANA, 30)])                                    # same minute, other length
            _entry(c, case, p1, 100, "Location", at(2024, 1, 5, 12, 30), keys=[ANA])
        yield {"engine": engine, "case": str(case), "p1": str(p1), "p2": str(p2)}


def _f(w, **kw):
    from services.phone.timeline_lens import TimelineLensFilter
    return TimelineLensFilter.model_validate({"case_id": w["case"], **kw})


def test_copies_on_another_phone_need_the_same_minute_and_text_or_call_length(world):
    from services.phone import timeline_lens as TL
    with world["engine"].connect() as c:
        many = TL.index(c, _f(world, lens_kinds=["messages", "calls"], copies_on="many"))
        one = TL.index(c, _f(world, lens_kinds=["messages", "calls"], copies_on="one"))
        every = TL.index(c, _f(world, lens_kinds=["messages", "calls"]))
    # the invoice message and the 120 s call, on each phone: 4 rows
    assert many["total"] == 4
    assert one["total"] == 4
    assert one["total"] + many["total"] == every["total"] == 8


def test_copies_are_judged_only_against_the_phones_in_scope(world):
    from services.phone import timeline_lens as TL
    with world["engine"].connect() as c:
        many = TL.index(c, _f(world, lens_kinds=["messages", "calls"], phones=[world["p1"]], copies_on="many"))
    assert many["total"] == 0  # Phone 2 is off: nothing on Phone 1 is "on more than one phone"


def test_copies_on_leaves_out_records_that_are_not_messages_or_calls(world):
    from services.phone import timeline_lens as TL
    with world["engine"].connect() as c:
        out = TL.index(c, _f(world, lens_kinds=["messages", "calls", "locations"], copies_on="one"))
    assert out["total"] == 4 and out["counts"]["other"] == 0


def test_every_facet_count_equals_the_list_it_opens(world):
    from services.phone import phone_home as H, timeline_lens as TL
    with world["engine"].connect() as c:
        f = _f(world, lens_kinds=["messages", "calls"])
        out = H.facets(c, f)
        kinds = {k["key"]: k["count"] for k in out["kinds"]}
        assert kinds["messages"] == 5 and kinds["calls"] == 3 and kinds["locations"] == 1
        for k in ("messages", "calls", "locations"):
            assert TL.index(c, _f(world, lens_kinds=[k]))["total"] == kinds[k]
        states = {s["key"]: s["count"] for s in out["states"]}
        assert states == {"deleted": 1, "one": 4, "many": 4}
        assert TL.index(c, _f(world, lens_kinds=["messages", "calls"], deleted_states=["Deleted", "Trash"]))["total"] == 1
        # Who: the owners of the phones in scope are on their cards, not in the list
        people = {p["key"]: p["count"] for p in out["people"]}
        assert set(people) == {ANA} and out["people_total"] == 1
        assert TL.index(c, _f(world, lens_kinds=["messages", "calls"], participants=[ANA]))["total"] == people[ANA]


def test_each_group_is_counted_without_its_own_choice(world):
    from services.phone import phone_home as H
    with world["engine"].connect() as c:
        out = H.facets(c, _f(world, lens_kinds=["calls"], participants=[ANA], copies_on="many"))
    kinds = {k["key"]: k for k in out["kinds"]}
    assert kinds["calls"]["on"] and not kinds["messages"]["on"]
    assert next(s for s in out["states"] if s["key"] == "many")["on"]
    assert [p["key"] for p in out["people"]] == [ANA] and out["people"][0]["on"]


def test_one_part_is_answered_alone():
    from services.phone import phone_home as H
    assert H.PARTS == ("kinds", "people", "states", "phones")


def test_each_phone_card_has_its_first_and_last_day(world):
    from services.phone import phone_home as H
    with world["engine"].connect() as c:
        spans = {s["extraction_id"]: s for s in H.facets(c, _f(world), "phones")["phones"]}
    assert spans[world["p1"]]["first_day"] == "2024-01-05" and spans[world["p1"]]["last_day"] == "2024-01-07"
    assert spans[world["p2"]]["first_day"] == "2024-01-05" and spans[world["p2"]]["last_day"] == "2024-01-07"


def test_the_facets_route_takes_a_part():
    from routers import phones
    route = next(r for r in phones.router.routes if getattr(r, "path", "").endswith("/home/facets"))
    assert "POST" in route.methods
