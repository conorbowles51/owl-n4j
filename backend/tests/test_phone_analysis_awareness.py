"""05-S7, approach 4 group roles (05 section 7.3 step 5, 7.8 test 4). Invented data only."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from services.phone_analysis import awareness as A
from services.phone_analysis import framework as F
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def _group(c, case, ext, base, n_parties, admin_index=None, chat_type=None, activities=()):
    fields = [("ChatType", "ChatType", chat_type)] if chat_type else []
    record(c, case, ext, base, "Chat", fields)
    for i in range(n_parties):
        f = [("Name", "String", "Synthetic Person %d" % i)]
        if admin_index == i:
            f.append(("IsGroupAdmin", "Boolean", "True"))
        record(c, case, ext, base + 1 + i, "Party", f, parent=base)
    for j, (action, instant, who) in enumerate(activities):
        o = base + 50 + 2 * j
        record(c, case, ext, o, "ChatActivity", [("Action", "ChatActivityAction", action)], parent=base,
               times=[("SystemMessageTimeStamp", instant)] if instant else ())
        record(c, case, ext, o + 1, "Party", [("Name", "String", who)], parent=o, top=base)


@needs_template
def test_group_admins_and_membership_changes_with_and_without_time(engine):
    """7.3 step 5; 7.8.4: a ChatActivity with no timestamp appears with its time not recorded."""
    t = at(2023, 5, 1, 10)
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[])
        _group(c, case, ext, 1000, 4, admin_index=2,
               activities=[("ParticipantAdded", t, "Synthetic Person 3"), ("ParticipantLeft", None, "Synthetic X")])
        _group(c, case, ext, 2000, 2, admin_index=0)  # a one-to-one chat: not a group (19.S7-a)
        _group(c, case, ext, 3000, 2, chat_type="Group")  # a group with no roles: counted, no result (19.S7-c)
    with engine.connect() as c:
        res, counts = A.analyse(c, case, {})
    assert counts["groups"] == 2 and counts["groups_without_roles"] == 1
    (g,) = res
    m = g["measures"]
    assert [a["display"] for a in m["admins"]] == ["Synthetic Person 2"]
    assert m["participants"] == 4 and m["timed_changes"] == 1
    assert m["changes"] == [{"action": "ParticipantAdded", "instant": t, "participants": ["Synthetic Person 3"]},
                            {"action": "ParticipantLeft", "instant": None, "participants": ["Synthetic X"]}]
    codes = [u["code"] for u in g["directions"]["undercuts"]]
    assert "time_not_recorded" in codes and "participant_role_unknown" in codes
    assert g["period_start"] == t and g["strength"] == "timed"
    assert sorted(r["role"] for r in g["records"]) == ["admin", "group_chat", "membership_change",
                                                         "membership_change"]


@needs_template
def test_runs_through_the_framework(engine):
    F.register(A)
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[])
        _group(c, case, ext, 1000, 3, admin_index=0)
        run, _ = F.request_run(c, case, "awareness", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"])
        cov = F.get_run(c, case, run["id"])["coverage"]["sentence"]
    assert page["total"] == 1 and page["items"][0]["label"] == "Lead for enquiry"
    assert "Group chats exist on all 1 phones." in cov


# ---- steps 1 to 4 (05 7.3; 7.8 tests 1 to 3; cb-gated-aware F) ----------------------------------------------------

OWNER = "phone:+12025550100"
OTHER = "phone:+12025550143"
PARAMS = {k: v["default"] for k, v in A.PARAMETERS.items()}


def _inc(t, read=None, played=None, status=None, level="reviewed", thread="one"):
    return {"instant": t, "direction": "incoming", "thread": thread, "status": status, "level": level,
            "parties": [(OTHER, "sender", False, "Synthetic Sender", "+12025550143"),
                        (OWNER, "recipient", True, None, "+12025550100", None, read, played)]}


def _out(t, thread="one"):
    return {"instant": t, "direction": "outgoing", "thread": thread,
            "parties": [(OWNER, "sender", True, None, "+12025550100"),
                        (OTHER, "recipient", False, "Synthetic Sender", "+12025550143")]}


def _kinds(res, kind):
    return [r for r in res if r["kind"] == kind]


@needs_template
def test_reply_latency_and_read_to_reply(engine):
    """7.8.1: incoming 10:00, read 10:05, reply 10:20: latency 20 min, read-to-reply 15 min. Fails on 4.1-groups,
    which gives no reply-latency result for a phone with owner read times."""
    t = at(2023, 5, 1, 10)
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=[_inc(t, read=t + timedelta(minutes=5)), _out(t + timedelta(minutes=20))])
    with engine.connect() as c:
        res, counts = A.analyse(c, case, PARAMS)
    (lat,) = _kinds(res, "reply_latency")
    assert lat["measures"]["latency"]["median_s"] == 1200.0 and lat["measures"]["latency"]["n"] == 1
    assert lat["measures"]["read_to_reply"]["median_s"] == 900.0
    # one reply pair, mapped: substantiation 0, fit 2 -> weak, listed with its reasons, never dropped
    assert lat["strength"] == "weak"
    assert any(d["code"] == "strength_rule" and d["detail"].startswith("Weak: 1 reply.")
               for d in lat["directions"]["supports"])
    assert _kinds(res, "read_events")[0]["measures"]["incoming_owner_read"] == 1
    assert counts["reply_pairs"] == 1


def test_run_of_incoming_counts_once_from_its_last_message():
    """7.8.2: three incoming then one reply: one latency, from the third."""
    t = at(2023, 5, 1, 10)
    seq = [{"direction": "incoming", "t": t + timedelta(minutes=m), "id": m} for m in (0, 1, 2)]
    seq.append({"direction": "outgoing", "t": t + timedelta(minutes=10), "id": 10})
    pairs = A.reply_pairs(seq)
    assert len(pairs) == 1 and pairs[0][0]["id"] == 2


def test_read_without_reply_and_its_window():
    """7.8.3: read, no reply for 3 days: counted at 48 h; with the window at 96 h, not counted."""
    t = at(2023, 5, 1, 10)
    seq = [{"direction": "incoming", "t": t, "owner_read": t, "owner_played": None},
           {"direction": "outgoing", "t": t + timedelta(days=3)}]
    assert len(A.without_reply(seq, timedelta(hours=48))) == 1
    assert A.without_reply(seq, timedelta(hours=96)) == []


@needs_template
def test_read_without_reply_and_unread_through_the_run(engine):
    t = at(2023, 5, 1, 10)
    with engine.begin() as c:
        case = make_case(c)
        quick = [x for d in range(20) for x in (_inc(t + timedelta(days=d), thread="two"),
                                                _out(t + timedelta(days=d, minutes=5), thread="two"))]
        phone(c, case, events=[_inc(t, read=t + timedelta(minutes=1)), _out(t + timedelta(days=3)),
                               _inc(t + timedelta(days=4), status="Unread")] + quick)
    with engine.connect() as c:
        res, counts = A.analyse(c, case, PARAMS)
        res96, _ = A.analyse(c, case, dict(PARAMS, no_reply_hours=96))
    (nr,) = _kinds(res, "read_without_reply")
    assert nr["measures"]["without_reply"] == 1 and nr["measures"]["window_basis"] == "parameter"
    assert _kinds(res96, "read_without_reply") == []
    (un,) = _kinds(res, "unread")
    assert un["measures"]["unread"] == 1 and un["strength"] == "weak"
    assert counts["no_reply_window_hours"] == 48


@needs_template
def test_generic_reading_is_graded_down_and_a_phone_without_read_times_still_gets_reply_times(engine):
    t = at(2023, 5, 1, 10)
    evs = []
    for d in range(12):
        evs += [_inc(t + timedelta(days=d), level="generic"), _out(t + timedelta(days=d, minutes=30))]
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=evs)
    with engine.connect() as c:
        res, _ = A.analyse(c, case, PARAMS)
        cov = F.coverage(c, case, "awareness")
    (lat,) = _kinds(res, "reply_latency")
    # 12 pairs (well) but generic interpretation (fit 1): moderate, with the undercut named
    assert lat["strength"] == "moderate" and lat["measures"]["read_to_reply"] is None
    assert "generic_interpretation" in [u["code"] for u in lat["directions"]["undercuts"]]
    assert _kinds(res, "read_events") == []
    assert cov["totals"]["phones_with_read_times"] == 0 and cov["totals"]["one_to_one_incoming"] == 12
    assert "Owner read or play times on 0 of 1 phones" in cov["notes"][0]
    assert "Rule of thumb (no measurement behind it)" in cov["notes"][2]


@needs_template
def test_window_widens_to_the_cases_95th_percentile_of_reply_latency(engine):
    """7.3 step 3 reverse: with every reply later than 48 hours, the window is the 95th percentile."""
    t = at(2023, 5, 1, 10)
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=[_inc(t, read=t + timedelta(minutes=1)), _out(t + timedelta(days=3))])
    with engine.connect() as c:
        res, counts = A.analyse(c, case, PARAMS)
    assert _kinds(res, "read_without_reply") == [] and counts["no_reply_window_hours"] == 72.0
