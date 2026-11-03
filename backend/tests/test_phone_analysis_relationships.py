"""05-S9, approach 11: relationships over time (05 section 14.8). Invented data only."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from services.phone_analysis import framework as F
from services.phone_analysis import measurements as M
from services.phone_analysis import relationships as R
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, OWNER2, ANA, BEN = "phone:+12025550100", "phone:+12025550111", "phone:+12025550143", "phone:+12025550177"
PARAMS = {k: v["default"] for k, v in R.PARAMETERS.items()}


def _m(instant, sender, recip, body, owner=OWNER, kind="message"):
    return dict(kind=kind, instant=instant, body=body, thread="t-%s" % (sender if sender != owner else recip),
                direction="outgoing" if sender == owner else "incoming",
                parties=[(sender, "sender", sender == owner, None, None), (recip, "recipient", recip == owner, None,
                                                                            None)])


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def test_pelt_finds_the_week_contact_stopped():
    """14.8.1: weekly counts 10, 10, 10, 0, 0, 0: one changepoint at week 4."""
    assert R.pelt([10, 10, 10, 0, 0, 0]) == [3]
    assert R.pelt([5] * 20) == []
    assert R.pelt([3, 4]) == []


@needs_template
def test_contact_stops_while_the_phone_keeps_recording(engine):
    """14.8.1 end to end: three weeks of 10 messages with Ana, then none while the phone carries on with Ben."""
    base = at(2023, 1, 2)  # a Monday
    events = [_m(base + timedelta(days=7 * w, hours=h), ANA, OWNER, "a%d-%d" % (w, h)) for w in range(3)
              for h in range(10)]
    events += [_m(base + timedelta(days=7 * w + 1), BEN, OWNER, "b%d" % w) for w in range(6)]
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=events, contacts={ANA: "Ana Synthetic"})
    with engine.connect() as c:
        res, counts = R.analyse(c, case, PARAMS)
    ana = [r for r in res if r["kind"] == "relationship" and r["measures"]["group"] == ANA]
    assert len(ana) == 1 and ana[0]["measures"]["communications"] == 30
    assert ana[0]["measures"]["names_here"] == ["Ana Synthetic"]
    assert ana[0]["measures"]["monthly"] == {"2023-01": {"message_incoming": 30}}
    assert ana[0]["measures"]["last"]["message"] == base + timedelta(days=14, hours=9)
    roles = sorted(r["role"] for r in ana[0]["records"])
    assert roles == ["first_communication", "last_communication"]
    (ch,) = [r for r in res if r["kind"] == "volume_change" and r["measures"]["group"] == ANA]
    assert ch["strength"] == "fall" and ch["measures"]["week_start"] == (base + timedelta(days=21)).date().isoformat()
    assert (ch["measures"]["rate_before"], ch["measures"]["rate_after"]) == (10.0, 0.0)
    assert not [r for r in res if r["kind"] == "volume_change" and r["measures"]["group"] == BEN]


@needs_template
def test_two_phones_name_one_person_differently(engine):
    """14.8.2: both names are shown, each with its phone; M-11c counts the person."""
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, label="C1", events=[_m(at(2023, 3, 1), ANA, OWNER, "hi")], contacts={ANA: "Ana S"})
        phone(c, case, label="C2", owner=OWNER2, events=[_m(at(2023, 3, 2), ANA, OWNER2, "hi", owner=OWNER2)],
              contacts={ANA: "Mum"})
    with engine.connect() as c:
        res, counts = R.analyse(c, case, PARAMS)
    rel = {r["measures"]["phone_label"]: r["measures"] for r in res if r["kind"] == "relationship"}
    assert rel["C1"]["names_here"] == ["Ana S"] and rel["C1"]["names_elsewhere"] == {"C2": ["Mum"]}
    assert rel["C2"]["names_here"] == ["Mum"] and rel["C2"]["names_elsewhere"] == {"C1": ["Ana S"]}
    assert counts["named_differently"] == 1
    with engine.connect() as c:
        version, result, gate = M.run(c, case, "relationships")
    assert version == "m11.2" and result["m11c_named_differently"] == 1


@needs_template
def test_runs_through_the_framework_with_unique_keys_and_the_lead_label(engine):
    """A group message with two people gives two relationship results resting on the same message; their keys
    differ (the person is part of the locator), so the run completes."""
    F.register(R)
    msg = dict(kind="message", instant=at(2023, 3, 1), body="to both", thread="g", direction="outgoing",
               parties=[(OWNER, "sender", True, None, None), (ANA, "recipient", False, None, None),
                        (BEN, "recipient", False, None, None)])
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=[msg])
        run, _ = F.request_run(c, case, "relationships", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"], kind="relationship")
    assert page["total"] == 2 and {i["label"] for i in page["items"]} == {"Lead for enquiry"}
