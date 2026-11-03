"""05-S5, approach 2: cross-phone message reconciliation (05 section 5.8 acceptance tests). Invented data only."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from services.phone_analysis import framework as F
from services.phone_analysis import message_reconciliation as R
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

X_OWNER, Y_OWNER, Z_OWNER = "phone:+12025550100", "phone:+12025550111", "phone:+12025550122"
PARAMS = {k: v["default"] for k, v in R.PARAMETERS.items()}


def _msg(instant, body, sender, recips, owner, deleted="Intact", app="WhatsApp", sender_key=True):
    """One copy as it sits on the phone of ``owner``."""
    parties = [(sender if sender_key else None, "sender", sender == owner, None, None)]
    parties += [(r, "recipient", r == owner, None, None) for r in recips]
    return dict(kind="message", instant=instant, body=body, app=app, thread="t-%s" % body[:3], deleted_state=deleted,
                direction="outgoing" if sender == owner else "incoming", parties=parties)


def _start(c, ext, instant):
    c.execute(text(
        "INSERT INTO phone_timestamps (extraction_id, document_index, owner_kind, owner_ordinal, body_path, model_type, "
        "field_name, value_type, original_text, instant, offset_state, parse_rule) VALUES (:e, 0, 'skeleton', 0, "
        "'skeleton/0', NULL, 'DeviceInfoExtractionStartDateTime', 'TimeStamp', :t, :i, 'explicit', 'synthetic')"),
        {"e": ext, "t": instant.isoformat(), "i": instant})


def _pair(engine, x_events, y_events, z_events=None):
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", owner=X_OWNER, events=x_events)
        y, _ = phone(c, case, label="C2", owner=Y_OWNER, events=y_events)
        z = phone(c, case, label="C3", owner=Z_OWNER, events=z_events)[0] if z_events else None
    return case, x, y, z


def _of(results, kind):
    return [r for r in results if r["kind"] == kind]


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def test_body_normalisation_keeps_emoji_and_drops_zero_width():
    assert R.norm_body("  Hello​  World 👍 ") == "hello world 👍"
    assert R.norm_body("𝐇𝐞𝐥𝐥𝐨") == "hello"
    assert R.family("WhatsApp", "AppMessage") == "whatsapp" and R.family("Native Messages", "Sms") == "sms"


def test_offset_and_spread_by_hand():
    """5.8.4 arithmetic: median 305, MAD 5, spread 7.413."""
    d = [290, 300, 305, 310, 900]
    assert sorted(d)[2] == 305 and abs(R.mad_spread(d) - 1.4826 * 5) < 1e-9
    slope, lo, hi = R.theil_sen(list(range(30)), [2.0 * i for i in range(30)])
    assert slope == 2.0 and lo <= 2.0 <= hi


@needs_template
def test_sms_sent_and_received_40_seconds_apart_is_matched_strong(engine):
    """5.8.1 and 5.8.2: one message on X to Y's owner, its copy on Y 40 s later: matched_strong. A different body is
    never matched, whatever the record identifiers say."""
    t = at(2023, 3, 1, 10)
    case, x, y, _ = _pair(engine,
                          [_msg(t, "meet at the usual place", X_OWNER, [Y_OWNER], X_OWNER),
                           _msg(t + timedelta(hours=1), "first body here", X_OWNER, [Y_OWNER], X_OWNER)],
                          [_msg(t + timedelta(seconds=40), "meet at the usual place", X_OWNER, [Y_OWNER], Y_OWNER),
                           _msg(t + timedelta(hours=1), "another body", X_OWNER, [Y_OWNER], Y_OWNER)])
    with engine.connect() as c:
        res, counts = R.analyse(c, case, PARAMS)
    (m,) = _of(res, "both_sides")
    assert m["strength"] == "matched_strong" and m["measures"]["seconds_apart"] == 40
    assert {r["extraction_id"] for r in m["records"]} == {str(x), str(y)}
    assert counts["candidate_pairs"] == 1


@needs_template
def test_common_body_matches_only_with_participants(engine):
    """5.8.3: "ok" 50 times on each phone, participants and times agreeing: matched; with the senders unresolved:
    not matched."""
    t = at(2023, 3, 1)
    xs = [_msg(t + timedelta(minutes=10 * i), "ok", X_OWNER, [Y_OWNER], X_OWNER) for i in range(50)]
    ys = [_msg(t + timedelta(minutes=10 * i, seconds=5), "ok", X_OWNER, [Y_OWNER], Y_OWNER) for i in range(50)]
    case, *_ = _pair(engine, xs, ys)
    with engine.connect() as c:
        assert len(_of(R.analyse(c, case, PARAMS)[0], "both_sides")) == 50
    xs = [_msg(t + timedelta(minutes=10 * i), "ok", X_OWNER, [Y_OWNER], X_OWNER, sender_key=False) for i in range(50)]
    ys = [_msg(t + timedelta(minutes=10 * i, seconds=5), "ok", X_OWNER, [Y_OWNER], Y_OWNER, sender_key=False)
          for i in range(50)]
    case, *_ = _pair(engine, xs, ys)
    with engine.connect() as c:
        assert _of(R.analyse(c, case, PARAMS)[0], "both_sides") == []


@needs_template
def test_device_stamped_offset_and_the_outlier_left_unassigned(engine):
    """5.8.4: five pairs 290, 300, 305, 310 and 900 s apart: offset 305 s, spread from MAD, the 900 s pair is not
    assigned once tau applies and stays one_side_only."""
    t = at(2023, 3, 1)
    deltas = [290, 300, 305, 310, 900]
    xs = [_msg(t + timedelta(hours=i), "distinct message %d" % i, X_OWNER, [Y_OWNER], X_OWNER)
          for i in range(5)]
    ys = [_msg(t + timedelta(hours=i, seconds=d), "distinct message %d" % i, X_OWNER, [Y_OWNER], Y_OWNER)
          for i, d in enumerate(deltas)]
    case, *_ = _pair(engine, xs, ys)
    with engine.connect() as c:
        res, _ = R.analyse(c, case, PARAMS)
    (o,) = _of(res, "clock_offset")
    assert o["strength"] == "device_stamped" and o["measures"]["offset_s"] == 305
    assert abs(o["measures"]["spread_s"] - 1.4826 * 5) < 1e-6
    assert sorted(m["measures"]["seconds_apart"] for m in _of(res, "both_sides")) == [290, 300, 305, 310]
    assert len(_of(res, "one_side_only")) == 2   # the outlier's copy on each phone


@needs_template
def test_server_stamped_pairs_report_no_device_offset(engine):
    """5.8.5: eighteen app pairs with equal times: server_stamped; no offset."""
    t = at(2023, 3, 1)
    xs = [_msg(t + timedelta(hours=i), "server message %d" % i, X_OWNER, [Y_OWNER], X_OWNER) for i in range(18)]
    ys = [_msg(t + timedelta(hours=i), "server message %d" % i, X_OWNER, [Y_OWNER], Y_OWNER) for i in range(18)]
    case, *_ = _pair(engine, xs, ys)
    with engine.connect() as c:
        res, _ = R.analyse(c, case, PARAMS)
    (o,) = _of(res, "clock_offset")
    assert o["strength"] == "server_stamped" and o["measures"]["offset_s"] == 0
    assert all("server_stamped" in [u["code"] for u in m["directions"]["undercuts"]] for m in _of(res, "both_sides"))


@needs_template
def test_group_message_matches_once_on_each_other_phone(engine):
    """5.8.6: X sends to a group with Y and Z: matched once on Y and once on Z."""
    t = at(2023, 3, 1, 9)
    body = "group note for both of you"
    case, x, y, z = _pair(engine, [_msg(t, body, X_OWNER, [Y_OWNER, Z_OWNER], X_OWNER)],
                          [_msg(t + timedelta(seconds=2), body, X_OWNER, [Y_OWNER, Z_OWNER], Y_OWNER)],
                          [_msg(t + timedelta(seconds=3), body, X_OWNER, [Y_OWNER, Z_OWNER], Z_OWNER)])
    with engine.connect() as c:
        res, _ = R.analyse(c, case, PARAMS)
    pairs = sorted(tuple(m["measures"]["phones"]) for m in _of(res, "both_sides"))
    assert pairs == [("C1", "C2"), ("C1", "C3")]


@needs_template
def test_two_equally_close_candidates_are_ambiguous(engine):
    """5.8.7: two copies on Y at equal distance: ambiguous_pair, no assignment."""
    t = at(2023, 3, 1, 9)
    body = "the same words twice"
    case, *_ = _pair(engine, [_msg(t, body, X_OWNER, [Y_OWNER], X_OWNER)],
                     [_msg(t - timedelta(seconds=30), body, X_OWNER, [Y_OWNER], Y_OWNER),
                      _msg(t + timedelta(seconds=30), body, X_OWNER, [Y_OWNER], Y_OWNER)])
    with engine.connect() as c:
        res, _ = R.analyse(c, case, PARAMS)
    assert _of(res, "both_sides") == [] and len(_of(res, "ambiguous_pair")) == 1
    assert len(_of(res, "ambiguous_pair")[0]["records"]) == 3


@needs_template
def test_deleted_on_one_side_is_recovered_from_the_other(engine):
    """5.8.8: X's copy Deleted, Y's Intact: one result naming Y as the copy it is read from; X's record unchanged."""
    t = at(2023, 3, 1, 9)
    body = "please remove this later"
    case, x, y, _ = _pair(engine, [_msg(t, body, X_OWNER, [Y_OWNER], X_OWNER, deleted="Deleted")],
                          [_msg(t + timedelta(seconds=1), body, X_OWNER, [Y_OWNER], Y_OWNER)])
    with engine.connect() as c:
        res, counts = R.analyse(c, case, PARAMS)
        state = c.execute(text("SELECT deleted_state FROM pv_comm_event WHERE extraction_id = :e"), {"e": x}).scalar()
    (d,) = _of(res, "deleted_one_side")
    assert d["measures"]["recovered_from"] == "C2"
    assert {r["role"]: r["extraction_id"] for r in d["records"]} == {"deleted_copy": str(x), "recovered_copy": str(y)}
    assert state == "Deleted" and counts["deleted_one_side"] == 1


@needs_template
def test_counterpart_extracted_before_the_message(engine):
    """5.8.9: Y was extracted before X's message: one_side_only with counterpart_extraction_ended."""
    t = at(2023, 3, 1, 9)
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, label="C1", owner=X_OWNER, events=[
            _msg(t, "earlier both", X_OWNER, [Y_OWNER], X_OWNER),
            _msg(t + timedelta(days=10), "after Y was extracted", X_OWNER, [Y_OWNER], X_OWNER)])
        y, _ = phone(c, case, label="C2", owner=Y_OWNER, events=[
            _msg(t + timedelta(seconds=1), "earlier both", X_OWNER, [Y_OWNER], Y_OWNER)])
        _start(c, y, t + timedelta(days=5))
    with engine.connect() as c:
        res, _ = R.analyse(c, case, PARAMS)
    (o,) = _of(res, "one_side_only")
    assert o["measures"]["not_on"] == "C2"
    assert "counterpart_extraction_ended" in [u["code"] for u in o["directions"]["undercuts"]]


@needs_template
def test_runs_through_the_framework_with_unique_keys_and_the_lead_label(engine):
    F.register(R)
    t = at(2023, 3, 1)
    xs = [_msg(t + timedelta(hours=i), "distinct message %d" % i, X_OWNER, [Y_OWNER], X_OWNER) for i in range(6)]
    ys = [_msg(t + timedelta(hours=i, seconds=300), "distinct message %d" % i, X_OWNER, [Y_OWNER], Y_OWNER)
          for i in range(5)]
    case, *_ = _pair(engine, xs, ys)
    with engine.begin() as c:
        run, _ = F.request_run(c, case, "message_reconciliation", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"], kind="both_sides")
        assert page["total"] == 5 and {i["label"] for i in page["items"]} == {"Lead for enquiry"}
        assert F.results(c, case, run["id"], kind="one_side_only")["total"] == 1
        assert F.results(c, case, run["id"], kind="clock_offset")["total"] == 1


@needs_template
def test_measurement_m2_counts_the_tiers_against_the_gate(engine):
    """m2.2: ten messages deleted on one phone and intact on the other meet the gate (10 deleted_one_side)."""
    from services.phone_analysis import measurements as M
    t = at(2023, 3, 1)
    xs = [_msg(t + timedelta(hours=i), "deleted later %d" % i, X_OWNER, [Y_OWNER], X_OWNER, deleted="Deleted")
          for i in range(10)]
    ys = [_msg(t + timedelta(hours=i, seconds=1), "deleted later %d" % i, X_OWNER, [Y_OWNER], Y_OWNER)
          for i in range(10)]
    case, *_ = _pair(engine, xs, ys)
    with engine.connect() as c:
        version, result, gate = M.run(c, case, "message_reconciliation")
    assert version == "m2.2" and result["m2d_deleted_one_side"] == 10 and gate == "build"
    assert result["m2b_matched_strong"] == 10
