"""A read between two people under one kind of identity counts what the same people's other identities hold in the
window (demo P4, 22 Nov 2026, followups m112223403630727: a read between the two phone numbers left out the
price-list email between the same people's addresses). Synthetic data only; needs the PostgreSQL template."""
from __future__ import annotations

import pytest

from services.agent import phone_tools as PT
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER = "phone:+12025550100"
ANA, ANA_MAIL = "phone:+12025550143", "email:ana@example.com"
BEN, BEN_MAIL = "phone:+12025550188", "email:ben@example.com"
DECOY = "email:ana.lookalike@example.com"


def ev(kind, instant, sender, recips, body):
    return dict(kind=kind, instant=instant, body=body, thread=None, direction="incoming",
                parties=[(sender, "sender", False, None, None)] + [(r, "recipient", False, None, None) for r in recips])


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            phone(c, case, label="C3", owner=OWNER,
                  contacts={ANA: "Maria Lopez", ANA_MAIL: "Maria Lopez", BEN: "Ben Synthetic",
                            BEN_MAIL: "Ben Synthetic", DECOY: "Maria L"},
                  events=[ev("message", at(2024, 5, 3, 9), ANA, [BEN], "see you at 7"),
                          ev("email", at(2024, 5, 4, 14), ANA_MAIL, [BEN_MAIL], "price list"),
                          ev("email", at(2024, 5, 5, 14), DECOY, [BEN_MAIL], "not the same person"),
                          ev("email", at(2024, 7, 1, 14), ANA_MAIL, [BEN_MAIL], "outside the window")])
        yield {"engine": engine, "case": case}


def test_a_between_read_counts_the_same_peoples_other_identities_with_the_read_for_them(world):
    with world["engine"].connect() as c:
        out = PT.messages(c, world["case"], people=[ANA, BEN], mode="between", start="2024-05-01", end="2024-05-31")
    assert out["total_matching"] == 1
    other = out["other_identities"]
    assert [(p["people"], p["records"], p["emails"]) for p in other["pairs"]] == [([ANA_MAIL, BEN_MAIL], 1, 1)]
    assert other["pairs"][0]["read_with"] == {"tool": "phone_messages", "arguments": {
        "people": [ANA_MAIL, BEN_MAIL], "mode": "between", "start": "2024-05-01", "end": "2024-05-31"}}
    sentence = out["other_identities_sentence"]
    assert "1 email between %s and %s" % (ANA_MAIL, BEN_MAIL) in sentence
    assert "C3 names both Maria Lopez" in sentence and "not by a person's link" in sentence
    assert DECOY not in sentence  # a different name on the phone is not the same person


def test_a_read_with_no_other_identities_says_nothing_extra(world):
    with world["engine"].connect() as c:
        out = PT.messages(c, world["case"], people=[DECOY, BEN_MAIL], mode="between")
        assert "other_identities" not in out or out["other_identities"]["pairs"] == []
        out = PT.messages(c, world["case"], people=[ANA], mode="any")
        assert "other_identities" not in out
