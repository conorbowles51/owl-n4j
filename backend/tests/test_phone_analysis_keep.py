"""Keeping an approach result and linking it (02 decision 50; J-14b). Invented data only."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from postgres import link_types
from services.pattern_of_life import snapshots
from services.phone_analysis import framework as F
from services.phone_analysis import keep as K
from services.phone_analysis import message_reconciliation as R
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_analysis_message_reconciliation import X_OWNER, Y_OWNER, _msg


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


@needs_template
def test_a_kept_result_is_a_frozen_snapshot_the_phone_analysis_resolver_resolves(engine):
    F.register(R)
    snapshots.register()
    t = at(2023, 3, 1, 9)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", owner=X_OWNER, events=[_msg(t, "a kept line of text", X_OWNER, [Y_OWNER],
                                                                      X_OWNER)])
        y, _ = phone(c, case, label="C2", owner=Y_OWNER, events=[_msg(t + timedelta(seconds=2), "a kept line of text",
                                                                      X_OWNER, [Y_OWNER], Y_OWNER)])
        run, _ = F.request_run(c, case, "message_reconciliation", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        (item,) = F.results(c, case, run["id"], kind="both_sides")["items"]
    with Session(engine) as db:
        kept = K.keep(db, case, item["id"])
        again = K.keep(db, case, item["id"])
        db.commit()
    assert kept["id"] == again["id"] and kept["id"].startswith("pa_")
    assert kept["kind"] == "analysis_result" and kept["record_count"] == 2 and kept["stale"] is False
    assert kept["label"] == "Messages across phones: both sides, C1 and C2 (Lead for enquiry)"
    snap = kept["snapshot"]
    assert snap["subject"]["approach"] == "message_reconciliation" and snap["subject"]["result_key"] == item["result_key"]
    assert sorted(snap["mapping_versions"]["extractions"]) == sorted([str(x), str(y)])
    with Session(engine) as db:
        target = link_types.resolve_phone_target(db, case, "phone_analysis", kept["id"])
        assert target.snapshot["kind"] == "analysis_result" and len(target.members) == 2
        with pytest.raises(link_types.LinkTargetError):
            link_types.resolve_phone_target(db, make_case(db.connection()), "phone_analysis", kept["id"])
