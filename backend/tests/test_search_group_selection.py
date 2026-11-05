"""A whole search group kept as one phone selection for Add to… (07 J-5, 6.1). Invented data only."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from services.search import search as S
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def msg(n, body):
    return dict(kind="message", instant=at(2023, 3, 14, 9, n), body=body, thread="t", direction="incoming",
                parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)])


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, evs = phone(c, case, label="C1", events=[msg(1, "the blue ledger"), msg(2, "blue ledger again"),
                                                          msg(3, "nothing here")])
        with Session(bind=engine) as db:
            yield {"db": db, "case": case, "ext": str(ext), "evs": evs}


def test_a_message_group_is_held_whole_with_its_counts(world):
    w = world
    out = S.freeze_group(w["db"], None, w["case"], "blue ledger", "messages")
    assert out["event_count"] == 2 == out["group_total"] and out["left_out"] == 0 and out["record_count"] == 2
    from services.phone.selections import describe
    held = describe(w["db"], w["case"], out["id"])
    assert held["event_count"] == 2 and "blue ledger" in held["words"]


def test_named_records_keep_only_this_case_and_say_how_many_went(world):
    import uuid

    from services.phone import selections
    from services.phone.filters import StreamFilter
    w = world
    f = StreamFilter(case_id=str(w["case"]))
    real = [e["record_uid"] for e in w["evs"]]
    out = selections.freeze_records(w["db"], f, list(real) + [str(uuid.uuid4())], None, "Three records")
    assert out["record_count"] == 3 and out["left_out"] == 1


def test_nothing_matching_is_refused_not_saved_empty(world):
    import pytest as p

    from services.phone import selections
    with p.raises(selections.SelectionError):
        S.freeze_group(world["db"], None, world["case"], "no such words anywhere", "messages")
