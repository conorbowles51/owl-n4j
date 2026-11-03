"""05-S6, approach 3: deletion and concealment timeline (05 section 6.8). Invented data only."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from services.phone import ids
from services.phone_analysis import deletion_timeline as D
from services.phone_analysis import framework as F
from services.phone_analysis import measurements as M
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_analysis_fixture import add_fields as _add_fields, record as _record
from tests.phone_streams_fixture import GEN, at, phone

OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550177"
SPREAD = {1, 52, 103, 154, 205, 251, 302, 353, 404, 455}  # two deletions in each of the five baseline conversations
PARAMS = {k: v["default"] for k, v in D.PARAMETERS.items()}


def _m(instant, sender, body, thread="t", deleted="Intact", app="WhatsApp"):
    recip = OWNER if sender != OWNER else ANA
    return dict(kind="message", instant=instant, body=body, thread=thread, app=app, deleted_state=deleted,
                direction="outgoing" if sender == OWNER else "incoming",
                parties=[(sender, "sender", sender == OWNER, None, None), (recip, "recipient", recip == OWNER, None,
                                                                            None)])


def _start(c, ext, instant):
    c.execute(text(
        "INSERT INTO phone_timestamps (extraction_id, document_index, owner_kind, owner_ordinal, body_path, model_type, "
        "field_name, value_type, original_text, instant, offset_state, parse_rule) VALUES (:e, 0, 'skeleton', 0, "
        "'skeleton/0', NULL, 'DeviceInfoExtractionStartDateTime', 'TimeStamp', :t, :i, 'explicit', 'synthetic')"),
        {"e": ext, "t": instant.isoformat(), "i": instant})


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def _run(engine, case):
    with engine.connect() as c:
        return D.analyse(c, case, PARAMS)


def _kind(results, kind):
    return [r for r in results if r["kind"] == kind]


@needs_template
def test_deleted_message_interval_runs_from_its_time_to_the_extraction(engine):
    """6.8.1: deleted at t, extraction at E, no DateDeleted: interval [t, E]."""
    t, e = at(2023, 3, 2, 9), at(2023, 6, 1, 8)
    with engine.begin() as c:
        case = make_case(c)
        ext, ev = phone(c, case, events=[_m(t, ANA, "gone", deleted="Deleted"), _m(at(2023, 3, 3), ANA, "kept")])
        _start(c, ext, e)
    res, counts = _run(engine, case)
    (d,) = _kind(res, "deleted_record")
    assert d["measures"]["earliest"] == t and d["measures"]["latest"] == e
    assert d["measures"]["latest_basis"] == "extraction_start"
    assert d["period_start"] == t and d["period_end"] == e
    assert d["measures"]["explanation"] == "unexplained"
    assert "bounded_by_extraction_only" in [u["code"] for u in d["directions"]["undercuts"]]
    assert d["records"] == [{"extraction_id": str(ext), "record_uid": ev[0]["record_uid"], "field_path": None,
                             "role": "deleted_record"}]


@needs_template
def test_self_destruct_setting_explains_and_is_left_out_of_the_clearing_score(engine):
    """6.8.2: SelfDestructDuration 7 days: explained_by_setting, excluded from the clearing score."""
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[_m(at(2023, 3, 2, 9), ANA, "gone", deleted="Deleted")])
        _add_fields(c, ext, 0, ("SelfDestructDuration", "TimeSpan", "7.00:00:00"))
    res, counts = _run(engine, case)
    (d,) = _kind(res, "deleted_record")
    assert d["measures"]["explanation"] == "explained_by_setting"
    assert "auto_delete_setting" in [u["code"] for u in d["directions"]["undercuts"]]
    assert D.explanation({"SelfDestructDuration": ["00:00:00"]}) == "unexplained"
    assert D.explanation({"DeletionReason": ["UserViewed"]}) == "explained_by_view_once"
    assert D.explanation({"DeletionReason": ["UserDeleted"]}) == "user_deleted"
    assert D.explanation({"Label": ["Recalled"]}) == "recalled_by_sender"


@needs_template
def test_selective_clearing_against_the_phone_baseline_with_bh(engine):
    """6.8.3: 40 messages, 20 deleted, on a phone whose baseline is 2 percent: selective_clearing with p and q."""
    base = at(2023, 1, 1)
    events = []
    for i in range(40):
        events.append(_m(base + timedelta(hours=i), ANA, "target %d" % i, thread="target",
                         deleted="Deleted" if i % 2 else "Intact"))
    for i in range(500):  # baseline: 10 of 500 deleted (2 percent) across other conversations of the same app
        events.append(_m(base + timedelta(hours=i, minutes=30), BEN, "other %d" % i, thread="o%d" % (i % 5),
                         deleted="Deleted" if i in SPREAD else "Intact"))
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=events)
    res, counts = _run(engine, case)
    sel = _kind(res, "selective_clearing")
    assert [s["measures"]["thread_key"].rsplit(":", 1)[-1] for s in sel] == ["target"]
    m = sel[0]["measures"]
    assert (m["messages"], m["deleted"]) == (40, 20)
    assert m["baseline_share"] == 0.02
    assert m["p"] < 1e-10 and m["q"] <= 0.05
    assert len([r for r in sel[0]["records"] if r["role"] == "deleted_message"]) == 20


def test_binomial_tail_and_bh_by_hand():
    assert D.binomial_upper_tail(0, 10, 0.3) == 1.0
    assert abs(D.binomial_upper_tail(1, 1, 0.3) - 0.3) < 1e-12
    assert abs(D.binomial_upper_tail(2, 2, 0.5) - 0.25) < 1e-12
    assert D.benjamini_hochberg([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.04, 0.04])


@needs_template
def test_reply_to_a_message_the_phone_does_not_hold(engine):
    """6.8.4: a reply whose quoted message is absent: referenced_message_absent, opening to the reply."""
    with engine.begin() as c:
        case = make_case(c)
        ext, ev = phone(c, case, events=[_m(at(2023, 3, 2, 9), ANA, "first"), _m(at(2023, 3, 2, 10), OWNER, "re")])
        # the first message carries Identifier 101; the reply refers to 101 (present) and a second reply to 999 (absent)
        c.execute(text(
            "INSERT INTO phone_texts (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
            "locator, model_type, generation, text_uid, body_path, field_name, field_path, value_index, value, "
            "value_folded, effective_value) VALUES (:c, :e, 0, 0, :u, :u, 'l', 'InstantMessage', :g, :tu, '0', "
            "'Identifier', 'Identifier', 0, '101', '101', '101')"),
            {"c": case, "e": ext, "u": ev[0]["record_uid"], "g": GEN, "tu": uuid.uuid4()})
        _record(c, case, ext, 1000, "ReplyMessageData", [("OriginalMessageID", "String", "101")], parent=1)
        _record(c, case, ext, 1001, "ReplyMessageData", [("OriginalMessageID", "String", "999")], parent=1)
    res, counts = _run(engine, case)
    (r,) = _kind(res, "referenced_message_absent")
    assert counts["references"] == 2 and counts["referenced_absent"] == 1
    reply = [x for x in r["records"] if x["role"] == "reply"]
    assert reply == [{"extraction_id": str(ext), "record_uid": ev[1]["record_uid"], "field_path": None,
                      "role": "reply"}]


@needs_template
def test_hole_needs_the_app_recording_elsewhere_during_the_gap(engine):
    """6.8.5: a 30-day gap with intact messages either side inside the app's recording: hole; the same gap where the
    app recorded nothing on the phone: no hole (19.S6-b)."""
    base = at(2023, 1, 1)
    convo = [_m(base + timedelta(days=d), ANA, "c%d" % d, thread="c") for d in (0, 1, 2, 3, 4, 34, 35, 36)]
    other = [_m(base + timedelta(days=d), BEN, "o%d" % d, thread="o") for d in (10, 20)]
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=convo + other)
        case2 = make_case(c)
        phone(c, case2, events=convo)
    res, _ = _run(engine, case)
    holes = _kind(res, "hole")
    assert len(holes) == 1 and holes[0]["measures"]["gap_days"] == 30.0
    assert holes[0]["measures"]["thread_key"].endswith(":c")
    res2, counts2 = _run(engine, case2)
    assert _kind(res2, "hole") == [] and counts2["gaps_without_app_data"] == 1


def test_hole_threshold_is_leave_one_out():
    base = at(2023, 1, 1)
    times = [base + timedelta(days=d) for d in (0, 1, 2, 3, 33)]
    assert D.holes_in(times, timedelta(days=7)) == [(times[3], times[4])]
    assert D.holes_in(times[:2], timedelta(days=0)) == []


@needs_template
def test_wipe_is_shown_and_never_bounds_an_interval(engine):
    """6.8.6: a Wipe event is listed and the deletion interval still ends at the extraction."""
    t, wipe, e = at(2023, 3, 2, 9), at(2023, 4, 1), at(2023, 6, 1)
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[_m(t, ANA, "gone", deleted="Deleted")])
        _start(c, ext, e)
        _record(c, case, ext, 2000, "DeviceEvent", [("EventType", "DeviceEventTypes", "Wipe")],
                times=[("StartTime", wipe)])
        _record(c, case, ext, 2001, "InstalledApplication", [("Categories", "String", "HideFilesPictures")],
                times=[("InstallDate", at(2023, 2, 1)), ("DeletedDate", at(2023, 5, 1))])
        _record(c, case, ext, 2002, "PoweringEvent", [("Event", "PowerEventType", "Off")],
                times=[("TimeStamp", at(2023, 4, 2))])
    res, counts = _run(engine, case)
    (w,) = _kind(res, "wipe")
    assert w["period_start"] == wipe
    assert "wipe_scope_unknown" in [u["code"] for u in w["directions"]["undercuts"]]
    (d,) = _kind(res, "deleted_record")
    assert d["measures"]["latest"] == e and d["measures"]["latest_basis"] == "extraction_start"
    assert len(_kind(res, "concealment_app")) == 1 and len(_kind(res, "app_removed")) == 1
    assert len(_kind(res, "power_off")) == 1


@needs_template
def test_runs_through_the_framework_and_states_no_state_of_mind(engine):
    """Registered, run end to end; results carry the lead label; no result words state a state of mind (05 3.5);
    total is the full count under the filter."""
    F.register(D)
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, events=[_m(at(2023, 3, 2, 9) + timedelta(minutes=i), ANA, "m%d" % i,
                                  deleted="Deleted" if i < 3 else "Intact") for i in range(6)])
    with engine.begin() as c:
        run, created = F.request_run(c, case, "deletion_timeline", None, "synthetic@example.org")
    assert created
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"], kind="deleted_record", limit=2)
        assert page["total"] == 3 and len(page["items"]) == 2
        assert all(i["label"] == "Lead for enquiry" for i in page["items"])
        cov = F.get_run(c, case, run["id"])["coverage"]
        assert cov["sentence"].startswith("Deleted records exist on all 1 phones.")
    words = json.dumps([r["directions"] for r in D.analyse(engine.connect(), case, PARAMS)[0]]).lower()
    for banned in ("intend", "wanted to", "tried to hide", "knew", "deliberately", "conceal "):
        assert banned not in words


@needs_template
def test_measurement_m3_counts_reasons_and_absent_references(engine):
    """M-3b to M-3d from the captured bodies (named sets are not in phone_texts)."""
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[_m(at(2023, 3, 2, 9), ANA, "a", deleted="Deleted"),
                                        _m(at(2023, 3, 2, 10), OWNER, "b")])
        _add_fields(c, ext, 0, ("DeletionReason", "MessageDeletionReason", "UserDeleted"))
        _record(c, case, ext, 1000, "ReplyMessageData", [("OriginalMessageID", "String", "404")], parent=1)
    with engine.connect() as c:
        version, result, gate = M.run(c, case, "deletion_timeline")
    assert version == "m3.2"
    (label,) = result["m3a_deleted_messages"]
    assert result["m3a_deleted_messages"][label] == 1
    assert result["m3c_deletion_reasons"] == {"UserDeleted": 1}
    assert result["m3d_referenced_absent"] == {label: 1}
    assert gate == "build"  # M-3d non-zero on a phone (6.6)
