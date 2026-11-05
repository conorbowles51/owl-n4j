"""05 section 4.4: phone money readings on the Timeline's money lane, labelled p4 and "from the phone", in no total."""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta

from sqlalchemy import text

from services.phone import timeline_lens as TL
from services.phone import timeline_money as TM
from services.phone_analysis import framework as F
from tests.phone_pg import fresh_engine, make_case
from tests.test_phone_analysis_money_signals import WHEN, _actor, _alert_case, _run, directory  # noqa: F401 (fixture)
from tests.test_phone_analysis_money_signals import pytestmark  # noqa: F401 (needs the template)

START, END = WHEN - timedelta(days=30), WHEN + timedelta(days=30)


def _f(case, **kw):
    return TL.TimelineLensFilter(case_id=str(case), **kw)


def test_the_lane_counts_readings_and_each_is_labelled_p4_from_the_phone():
    with fresh_engine() as engine:
        case, ext, *_ = _alert_case(engine)
        _run(engine, case, {"phase": "1a"})
        with engine.connect() as c:
            lane = TM.lane(c, _f(case), start=START, end=END, bucket="day")
            assert lane["proof_class"] == "p4" and "p4" in lane["label"] and "from the phone" in lane["label"]
            assert lane["readings"] == 3 == sum(b["count"] for b in lane["buckets"])
            got = TM.items(c, _f(case), start=START, end=END)
            assert got["total"] == 3 and len(got["items"]) == 3
            assert {(i["proof_class"], i["from_the_phone"]) for i in got["items"]} == {("p4", True)}
            assert all(i["record_uid"] for i in got["items"])  # each reading cites its phone record
            assert TM.lane(c, _f(case, phones=[str(ext)]), start=START, end=END, bucket="day")["readings"] == 3


def test_p4_is_never_summed_and_is_in_no_total_of_the_lens():
    with fresh_engine() as engine:
        case, ext, *_ = _alert_case(engine)
        with engine.connect() as c:
            before = TL.index(c, _f(case))["total"]
        _run(engine, case, {"phase": "1a"})
        with engine.connect() as c:
            assert TL.index(c, _f(case))["total"] == before  # the lens's total does not move when readings exist
            lane = TM.lane(c, _f(case), start=START, end=END, bucket="week")
            words = json.dumps(lane, default=str)
            for amount in ("12.50", "99.00", "41.00", "152.50", "15250"):
                assert amount not in words  # the lane holds counts of readings, no amount and no sum of amounts
            assert not [k for k in lane if "sum" in k or "amount" in k or "total" in k]
    src = inspect.getsource(TM)
    assert "amount_minor" not in src  # the module never reads the parsed value, so it cannot add it


def test_a_rejected_reading_leaves_the_counts_and_a_replaced_phone_leaves_the_lane():
    with fresh_engine() as engine:
        case, ext, *_ = _alert_case(engine)
        _, items = _run(engine, case, {"phase": "1a"})
        one = next(i for i in items if i["kind"] == "money_reading")
        with engine.begin() as c:
            actor = _actor(c, case)
        from sqlalchemy.orm import Session
        with Session(engine) as db:
            F.decide(db, case, one["id"], "rejected", "not a payment", actor)
            db.commit()
        with engine.connect() as c:
            lane = TM.lane(c, _f(case), start=START, end=END, bucket="day")
            assert (lane["readings"], lane["rejected"]) == (2, 1)
        with engine.begin() as c:
            c.execute(text("UPDATE phone_extractions SET standing = 'superseded' WHERE id = :e"), {"e": ext})
        with engine.connect() as c:
            assert TM.lane(c, _f(case), start=START, end=END, bucket="day")["readings"] == 0


def test_a_mark_counts_its_whole_bucket_so_it_equals_the_list_it_opens():
    with fresh_engine() as engine:
        case, ext, *_ = _alert_case(engine)
        _, items = _run(engine, case, {"phase": "1a"})
        at = min(datetime.fromisoformat(i["period_start"]) for i in items if i["kind"] == "money_reading")
        with engine.connect() as c:
            # a span that starts after the reading, inside its day: the day is whole, as in the lens
            lane = TM.lane(c, _f(case), start=at + timedelta(minutes=1), end=at + timedelta(hours=2), bucket="day")
            assert lane["readings"] == 3 and len(lane["buckets"]) == 1
            b = lane["buckets"][0]
            got = TM.items(c, _f(case), start=datetime.fromisoformat(b["start"]), end=datetime.fromisoformat(b["end"]))
        assert got["total"] == b["count"] == 3


def test_no_run_says_so_rather_than_showing_nothing():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
        with engine.connect() as c:
            lane = TM.lane(c, _f(case), start=START, end=END, bucket="day")
        assert lane["run"] is None and lane["absent_words"] == TM.NO_RUN_WORDS and lane["buckets"] == []
