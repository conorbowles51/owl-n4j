"""05-S16b, approach 15 from/to matrix (05 section 16b.8). Invented data only."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.phone_analysis import contact_matrix as M
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

X, Y, Z = "phone:+12025550100", "phone:+12025550111", "phone:+12025550200"
PARAMS = {k: v["default"] for k, v in M.PARAMETERS.items()}


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def msg(t, sender, to, owner, body="synthetic"):
    return dict(kind="message", instant=t, body=body, thread="t", direction="outgoing" if sender == owner else "incoming",
                parties=[(sender, "sender", sender == owner, None, None), (to, "recipient", to == owner, None, None)])


def call(t, caller, callee, owner, status):
    return dict(kind="call", instant=t, body=None, thread=None, call_duration_s=60, call_status=status,
                direction="outgoing" if caller == owner else "incoming",
                parties=[(caller, "caller", caller == owner, None, None), (callee, "callee", callee == owner, None, None)])


def _cell(res, a, b):
    return next((r for r in res if r["measures"]["from_display"].endswith(a) and r["measures"]["to_display"]
                 .endswith(b)), None)


@needs_template
def test_cells_by_direction_channel_and_call_status(engine):
    """16b.8 tests 1 and 3: X sends Y 3 messages and Y calls X twice, one missed: cell (X, Y) messages 3, cell (Y, X)
    calls 2 with missed 1; the cells add up to the records."""
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, label="C1", owner=X, events=[
            msg(at(2023, 1, 2, 9), X, Y, X), msg(at(2023, 1, 2, 10), X, Y, X), msg(at(2023, 1, 2, 11), X, Y, X),
            call(at(2023, 1, 3, 9), Y, X, X, "Established"), call(at(2023, 1, 3, 10), Y, X, X, "Missed")])
    with engine.connect() as c:
        res, counts = M.analyse(c, case, PARAMS)
    xy = [r for r in res if r["measures"]["to"] != r["measures"]["from"] and r["measures"]["from"].startswith("owner")]
    yx = [r for r in res if r["measures"]["to"].startswith("owner")]
    assert len(xy) == 1 and len(yx) == 1
    assert xy[0]["measures"]["by_channel"] == {"message": 3} and xy[0]["measures"]["reverse_total"] == 2
    assert yx[0]["measures"]["by_channel"] == {"call": 2}
    assert yx[0]["measures"]["calls_by_status"] == {"Established": 1, "Missed": 1}
    assert yx[0]["measures"]["connected_call_seconds"] == 60
    assert sum(r["measures"]["total"] for r in res) == 5


@needs_template
def test_a_message_matched_by_approach_2_counts_once(engine):
    """16b.8 test 2: one message on both owners' phones, matched by approach 2, counts once; an unmatched one is
    counted on each phone and the result says so."""
    with engine.begin() as c:
        case = make_case(c)
        p1, e1 = phone(c, case, label="C1", owner=X, events=[msg(at(2023, 1, 2, 9), X, Z, X, "matched"),
                                                             msg(at(2023, 1, 3, 9), X, Z, X, "unmatched")])
        p2, e2 = phone(c, case, label="C2", owner=Z, events=[msg(at(2023, 1, 2, 9), X, Z, Z, "matched"),
                                                             msg(at(2023, 1, 3, 9), X, Z, Z, "unmatched")])
        run, res_id = uuid.uuid4(), uuid.uuid4()
        c.execute(text(
            "INSERT INTO phone_analysis_runs (id, case_id, approach, approach_version, parameters, parameters_sha256, "
            "input_manifest, input_revision, status, requested_by, finished_at) VALUES (:r, :c, 'message_reconciliation', "
            "'2.3', '{}', :h, '{}', :h, 'completed', 'synthetic', now())"), {"r": run, "c": case, "h": "0" * 64})
        c.execute(text(
            "INSERT INTO phone_analysis_results (id, run_id, case_id, result_key, kind, strength, measures, directions) "
            "VALUES (:i, :r, :c, :k, 'both_sides', 'matched_strong', '{}', '{}')"),
            {"i": res_id, "r": run, "c": case, "k": "1" * 64})
        for ext, ev in ((p1, e1[0]), (p2, e2[0])):
            c.execute(text("INSERT INTO phone_analysis_result_records (id, result_id, extraction_id, record_uid, role) "
                           "VALUES (:i, :r, :e, :u, 'copy')"), {"i": uuid.uuid4(), "r": res_id, "e": ext,
                                                                 "u": ev["record_uid"]})
    with engine.connect() as c:
        res, counts = M.analyse(c, case, PARAMS)
    (cell,) = [r for r in res if r["kind"] == "between_owners"]
    assert cell["measures"]["by_channel"] == {"message": 3}  # matched once, unmatched on each phone
    assert cell["measures"]["unmatched_owner_copies"] == 3
    assert counts["matched_copies_counted_once"] == 1
    assert any(d["code"] == "unmatched_copies" for d in cell["directions"]["undercuts"])
