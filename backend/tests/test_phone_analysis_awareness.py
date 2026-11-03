"""05-S7, approach 4 group roles (05 section 7.3 step 5, 7.8 test 4). Invented data only."""
from __future__ import annotations

import uuid

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
    from services.phone_analysis import approaches
    approaches.install()
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
