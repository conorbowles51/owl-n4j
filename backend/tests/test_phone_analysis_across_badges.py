"""05 section 5.4: approach 2's per-message badge in Conversations, read from the latest completed run. Invented
data only."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from services.phone_analysis import across_badges as B
from services.phone_analysis import framework as F
from services.phone_analysis import message_reconciliation as R
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_analysis_message_reconciliation import X_OWNER, Y_OWNER, _msg


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


@needs_template
def test_badges_say_also_on_the_other_phone_or_only_on_this_one_with_the_reasons(engine):
    F.register(R)
    t = at(2023, 3, 1, 9)
    with engine.begin() as c:
        case = make_case(c)
        x, xs = phone(c, case, label="C1", owner=X_OWNER, events=[
            _msg(t, "a message on both phones", X_OWNER, [Y_OWNER], X_OWNER),
            _msg(t + timedelta(hours=2), "a deleted copy here", X_OWNER, [Y_OWNER], X_OWNER, deleted="Deleted"),
            _msg(t + timedelta(days=10), "after the other phone was extracted", X_OWNER, [Y_OWNER], X_OWNER)])
        y, ys = phone(c, case, label="C2", owner=Y_OWNER, events=[
            _msg(t + timedelta(seconds=1), "a message on both phones", X_OWNER, [Y_OWNER], Y_OWNER),
            _msg(t + timedelta(hours=2, seconds=1), "a deleted copy here", X_OWNER, [Y_OWNER], Y_OWNER)])
    uids = [e["record_uid"] for e in xs] + [e["record_uid"] for e in ys]
    with engine.connect() as c:
        assert B.badges(c, case, uids) == {"run": None, "items": {}}   # no run: no badge, never a guess
    with engine.begin() as c:
        run, _ = F.request_run(c, case, "message_reconciliation", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        out = B.badges(c, case, uids)
    assert out["run"]["id"] == run["id"] and out["run"]["current"] is True
    items = out["items"]
    both_x, del_x, late_x = (str(e["record_uid"]) for e in xs)
    both_y, del_y = (str(e["record_uid"]) for e in ys)
    assert [b["words"] for b in items[both_x]] == ["Also on C2"] and items[both_x][0]["other_record_uid"] == both_y
    assert [b["words"] for b in items[both_y]] == ["Also on C1"]
    assert [b["words"] for b in items[del_x]] == ["Also on C2: deleted here, intact on C2"]
    assert [b["words"] for b in items[del_y]] == ["Also on C1: deleted on C1, intact here"]
    (late,) = items[late_x]
    assert late["words"] == "Only on this phone, not on C2" and late["kind"] == "one_side_only"
    assert late["reasons"] and all(isinstance(r, str) for r in late["reasons"])


def test_more_than_the_limit_is_refused_with_the_count():
    with pytest.raises(B.TooMany, match="501 were asked"):
        B.badges(None, "c", ["u%d" % i for i in range(B.MAX_RECORDS + 1)])
