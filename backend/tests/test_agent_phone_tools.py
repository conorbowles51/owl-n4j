"""The agent's read-only phone tools (07 section 7.1, 06 item 61a): case scope, the Conversations counts, the ledger-tool
standard (total, has more, coverage, limitation, unconfirmed named, rec:// per record). Synthetic data only; needs
the PostgreSQL template."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.agent import phone_tools as PT
from services.phone import streams
from services.phone.filters import StreamFilter
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA, BEN, ZED = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188", "phone:+12025550199"


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, evs = phone(c, case, label="C3", contacts={ANA: "Maria Lopez", BEN: "Ben Synthetic"}, events=[
                msg(at(2023, 3, 13, 9), ANA, [OWNER], body="the day before the payment", thread="t1"),
                msg(at(2023, 3, 14, 10), OWNER, [ANA], body="payment sent", thread="t1",
                    level="applied_unconfirmed"),
                msg(at(2023, 3, 14, 11), BEN, [OWNER], body="unrelated", thread="t2"),
                dict(kind="call", instant=at(2023, 3, 14, 12), body=None, thread=None, call_duration_s=65,
                     parties=[(OWNER, "caller", True, None, None), (ANA, "callee", False, None, None)])])
            # a phone and a person that exist only in the other case
            phone(c, other, label="C9", owner="phone:+12025550111", contacts={ZED: "Zed Elsewhere"},
                  events=[msg(at(2023, 3, 14, 9), ZED, ["phone:+12025550111"], body="other case only")])
        yield {"engine": engine, "case": case, "other": other, "ext": ext, "evs": evs}


def _conn(w):
    return w["engine"].connect()


def test_people_and_phones_of_another_case_are_not_in_this_case(world):
    with _conn(world) as c:
        for out in (PT.find_people(c, world["case"], "Zed Elsewhere"),
                    PT.find_people(c, world["case"], "+1 202 555 0199"),
                    PT.messages(c, world["case"], people=["Zed Elsewhere"]),
                    PT.messages(c, world["case"], phones=["C9"]),
                    PT.places(c, world["case"], phones=["C9"]),
                    PT.contact_summary(c, world["case"], ZED)):
            assert out["available"] is False and out["not_in_case"] is True, out
            assert out["reason"].startswith("Not in this case.") and out["items"] == []
            assert "other case only" not in str(out)
        # and the other case does see its own phone
        assert PT.messages(c, world["other"], phones=["C9"])["total_matching"] == 1


def test_messages_between_two_people_equal_conversations_and_cite_every_record(world):
    with _conn(world) as c:
        out = PT.messages(c, world["case"], people=["Maria Lopez", OWNER], mode="between")
        f = StreamFilter.model_validate({"case_id": str(world["case"]), "participants": [ANA, OWNER],
                                         "participant_mode": "between", "zone": {"mode": "case"}})
        screen = streams.index_comm_events(c, f)["counts"]["events"]
    assert out["schema"] == "loupe.agent.phone_messages/1"
    assert out["total_matching"] == screen == 3 and out["returned"] == 3 and out["has_more"] is False
    assert all(i["rec"].startswith("rec://") for i in out["items"])
    assert [i["body"] for i in out["items"] if i["kind"] == "message"] == ["the day before the payment",
                                                                           "payment sent"]
    assert out["coverage"].startswith("Read 3 of 3 messages and calls on 1 phone")
    assert len(out["unconfirmed"]) == 1 and "not yet confirmed" in out["unconfirmed_sentence"]


def test_a_window_pages_with_has_more_and_says_what_was_left_out(world):
    with _conn(world) as c:
        first = PT.messages(c, world["case"], start="2023-03-14", end="2023-03-14", limit=2)
        rest = PT.messages(c, world["case"], start="2023-03-14", end="2023-03-14", offset=first["next_offset"])
    assert first["total_matching"] == 3 and first["returned"] == 2 and first["has_more"] is True
    assert "Only 2 of 3 are in this result" in first["limitation"]
    assert rest["returned"] == 1 and rest["has_more"] is False
    assert {i["rec"] for i in first["items"]}.isdisjoint({i["rec"] for i in rest["items"]})


def test_record_search_contact_summary_coverage_and_one_record_in_full(world):
    with _conn(world) as c:
        hit = PT.messages(c, world["case"], search="payment")
        assert hit["total_matching"] == 2
        s = PT.contact_summary(c, world["case"], "Maria Lopez")
        assert s["counts"]["messages"] == 2 and s["counts"]["calls"] == 1
        assert s["first_contact"]["body"] == "the day before the payment"
        assert s["last_contact"]["kind"] == "call"
        cov = PT.coverage(c, world["case"])
        assert [i["phone"] for i in cov["items"]] == ["C3"]
        rec = PT.record(c, world["case"], hit["items"][0]["rec"])
        assert rec["available"] and "payment" in rec["items"][0]["text"]
        other_rec = c.execute(text("SELECT record_uid FROM pv_comm_event WHERE case_id = :c"),
                              {"c": str(world["other"])}).scalar()
        assert PT.record(c, world["case"], other_rec)["not_in_case"] is True


def test_the_agent_tools_read_with_the_runs_case_and_never_the_models(world):
    from services.agent.tools import AgentToolContext, make_agent_tools

    @contextmanager
    def session():
        with Session(bind=world["engine"]) as s:
            yield s
    ctx = AgentToolContext(case_id=str(world["case"]), ledger_session_factory=session)
    tools = {t.name: t for t in make_agent_tools(ctx)}
    for name in ("phone_find_people", "phone_messages", "phone_contact_summary", "phone_coverage", "phone_places",
                 "phone_money_readings", "phone_colocation_results", "phone_record"):
        assert name in tools
        assert "case_id" not in tools[name].args  # the model cannot name another case
    out = tools["phone_messages"].invoke({"people": ["Maria Lopez"], "mode": "any"})
    assert out["status"] == "success" and out["data"]["total_matching"] == 3
    assert "Read 3 of 3" in out["summary"]
    gone = tools["phone_messages"].invoke({"phones": ["C9"]})
    assert gone["data"]["not_in_case"] is True and gone["summary"].startswith("Not in this case.")


def test_a_person_is_one_identity_or_the_tool_asks_which_and_nobody_is_dropped(world):
    from tests.phone_streams_fixture import ensure_identity
    with world["engine"].begin() as c:
        # another identity whose value only contains "maria": neither it nor "Maria Lopez" is exactly "maria"
        ensure_identity(c, world["case"], "app:synthchat:maria.l")
    with _conn(world) as c:
        # Zed is not in this case: the answer says so instead of answering for Maria alone
        out = PT.messages(c, world["case"], people=["Maria Lopez", "Zed Elsewhere"])
        assert out["not_in_case"] is True and "Zed Elsewhere" in out["reason"] and out["items"] == []
        # an exact name wins over a name that only contains it
        assert PT.messages(c, world["case"], people=["Maria Lopez", OWNER])["total_matching"] == 3
        amb = PT.messages(c, world["case"], people=["maria"])
        assert amb["available"] is False and amb["not_in_case"] is False and "say which one" in amb["reason"]
        assert sorted(amb["candidates"]["maria"]) == sorted([ANA, "app:synthchat:maria.l"])


def test_the_agent_keeps_to_the_identities_a_question_names():
    """Agent evaluation on live (docs/cellebrite/measurements/agent-eval): asked about two app handles, an answer once
    counted the same people's other identities too (5 for the handles' 3). The instructions now keep to the named
    identities and make a wider total say what it covers."""
    from services.agent.graph import _PHONE_PROMPT
    assert "Keep to the identities the question names" in _PHONE_PROMPT
    assert "say which identities the total covers" in _PHONE_PROMPT
