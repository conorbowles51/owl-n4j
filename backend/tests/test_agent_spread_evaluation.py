"""The agent evaluation set, spread questions (cb-gated-spread F): 8 questions on devices and accounts shared across
phones (approach 6), plans against location (approach 10) and near-identical pictures (approach 8's perceptual tier),
with known answers written by hand from the records below, measured through the agent's own tools (the StructuredTool
layer the model calls, with the run's case) under both case layers.

All data: every question's stated total equals its known answer, and its counts by strength and the extra check hold.
Significant: every question is refused with the Significant boundary sentence and returns no records. Set
LOUPE_AGENT_EVAL_OUT to append the measured table as JSON lines. A tool or approach that does not exist scores the
question as missed (this is how the score before the build is measured). Invented data only; needs the PostgreSQL
template.
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
T0 = at(2023, 3, 6, 10)


def _obs(c, case, ext, uid, kind, lat, lon, radius, t):
    c.execute(text(
        "INSERT INTO pol_place_observation (case_id, extraction_id, record_uid, record_type, kind, source_kind, lat, "
        "lon, radius_m, radius_basis, start_utc, end_utc, offset_status, time_semantics) VALUES (:c, :e, :u, 'x', :k, "
        "'gps', :la, :lo, :r, 'gps_accuracy_x2', :t, :t, 'explicit', 'event_instant')"),
        {"c": case, "e": ext, "u": uid, "k": kind, "la": lat, "lo": lon, "r": radius, "t": t})


def _picture(c, ext, ordinal, md5, ph, dh):
    uid = uuid.uuid4()
    if c.execute(text("SELECT to_regclass('phone_file_perceptual_hashes')")).scalar() is None:
        return str(uid)  # before the build: no hashes table (its questions miss)
    c.execute(text(
        "INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, declared_md5, tags, "
        "outcome, body) VALUES (:e, 0, :o, :f, :lp, :m, 'Image', 'no_hash', CAST(:b AS jsonb))"),
        {"e": ext, "o": ordinal, "f": uid, "lp": "files/Image/synthetic-%d.jpg" % ordinal, "m": md5,
         "b": json.dumps(["file", {"path": "DCIM/Camera/synthetic.jpg", "id": str(uid)}, None, None])})
    case = c.execute(text("SELECT case_id FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()
    c.execute(text("INSERT INTO phone_file_perceptual_hashes (file_uid, case_id, extraction_id, algorithm, state, phash, "
                   "dhash) VALUES (:f, :c, :e, 'phash64+dhash64/1', 'done', :p, :d)"),
              {"f": uid, "c": case, "e": ext, "p": ph, "d": dh})
    return str(uid)


@pytest.fixture(scope="module")
def world():
    from services.phone_analysis import approaches, framework as F
    approaches.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            x, _ = phone(c, case, label="C1", events=[])
            y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
            for e, other in ((x, "aa:bb:cc:00:00:01"), (y, "aa:bb:cc:00:00:02")):
                record(c, case, e, 100, "WirelessNetwork", fields=[("BSSId", "String", "aa:bb:cc:00:11:22"),
                                                                    ("SSId", "String", "Office")])
                record(c, case, e, 101, "WirelessNetwork", fields=[("BSSId", "String", other), ("SSId", "String", "Home")])
                record(c, case, e, 102, "Password", fields=[("Service", "String", "mail.example.com"),
                                                             ("Account", "String", "someone@example.com")])
            record(c, case, x, 103, "DeviceConnectivity", fields=[
                ("DeviceName", "String", "Car Kit"), ("ConnectivityMethod", "ConnectivityMethod", "Bluetooth"),
                ("ConnectivityNature", "ConnectivityNature", "Detected")])
            record(c, case, y, 103, "DeviceConnectivity", fields=[
                ("DeviceName", "String", "Car Kit"), ("ConnectivityMethod", "ConnectivityMethod", "Bluetooth"),
                ("ConnectivityNature", "ConnectivityNature", "Connected")])
            cal = record(c, case, x, 110, "CalendarEntry", fields=[("Subject", "String", "Meeting")],
                         times=[("StartDate", T0), ("EndDate", T0 + timedelta(hours=1))])
            _obs(c, case, x, cal, "planned", 40.0, -75.0, 25.0, T0)
            _obs(c, case, x, None, "presence", 40.0002, -75.0, 30.0, T0 + timedelta(minutes=10))
            ci = record(c, case, y, 111, "SocialMediaActivity",
                        fields=[("SocialActivityType", "SocialMediaActivityType", "CheckIn")],
                        times=[("TimeStamp", T0 + timedelta(days=1))])
            _obs(c, case, y, ci, "declared", 51.5, -0.1, None, T0 + timedelta(days=1))
            _obs(c, case, y, None, "presence", 51.5 + 50 / 111.2, -0.1, 40.0, T0 + timedelta(days=1, minutes=20))
            ids = {"pic_x": _picture(c, x, 9001, "a" * 32, 123456789, -987654321),
                   "pic_y": _picture(c, y, 9001, "b" * 32, 123456789, -987654321),
                   "far_y": _picture(c, y, 9002, "c" * 32, 0x0F0F0F0F, 0x3C3C3C3C)}
            runs = []
            for code in ("other_devices", "plans"):
                try:
                    runs.append(F.request_run(c, case, code, {}, "eval@example.com")[0]["id"])
                except Exception:  # noqa: BLE001 - before the build the approach does not exist: its questions miss
                    pass
        for rid in runs:
            assert F.execute(engine, rid)["status"] == "completed"
        yield {"engine": engine, "case": case, "ids": ids}


def _tools(w, significant):
    from services.agent.tools import AgentToolContext, make_agent_tools

    @contextmanager
    def session():
        with Session(bind=w["engine"]) as s:
            yield s
    ctx = AgentToolContext(case_id=str(w["case"]), ledger_session_factory=session,
                           allowed_entity_keys=set() if significant else None)
    return {t.name: t for t in make_agent_tools(ctx)}


A, P = "get_analysis_results", "get_near_identical_pictures"
OD = {"approach": "other_devices", "kind": "shared_key"}
# (id, question, tool, args, known total, extra check)
QUESTIONS = [
    ("S01", "Which networks, devices and accounts do the two phones share?", A, OD, 5,
     lambda d: d["by_strength"] == {"strong": 1, "moderate": 1, "weak": 2, "faint": 1}),
    ("S02", "Which shared keys are of moderate strength?", A, dict(OD, strength="moderate"), 1,
     lambda d: d["items"][0]["measures"]["key_kind"] == "saved_login" and d["items"][0]["measures"]["value"] is None),
    ("S03", "Which shared keys are only weak matches?", A, dict(OD, strength="weak"), 2,
     lambda d: sorted(i["measures"]["key_kind"] for i in d["items"]) == ["service", "ssid"]),
    ("S04", "Was the shared Bluetooth device connected on both phones?", A, dict(OD, strength="faint"), 1,
     lambda d: [p["nearby_only"] for p in d["items"][0]["measures"]["phones"]] == [True, False]),
    ("S05", "Was any check-in made away from where the phone was?", A, {"approach": "plans", "kind": "inconsistent"}, 1,
     lambda d: d["items"][0]["measures"]["source"] == "checkin" and d["items"][0]["strength"] == "moderate"),
    ("S06", "Which calendar entries agree with the phone's location?", A, {"approach": "plans", "kind": "consistent"},
     1, lambda d: d["items"][0]["strength"] == "strong"),
    ("S07", "Which pictures look the same on both phones?", P, {}, 1,
     lambda d: sorted(p["file_uid"] for p in d["items"][0]["pictures"]) == sorted([d["_ids"]["pic_x"],
                                                                                    d["_ids"]["pic_y"]])),
    ("S08", "Are there strong near-identical pictures, and how many of each strength?", P, {"strength": "strong"}, 1,
     lambda d: d["by_strength"] == {"strong": 1, "moderate": 0, "weak": 0, "faint": 0}),
]


def _measure(w, tools, q):
    qid, _, tool, args, total, check = q
    if tool not in tools:
        return None, None, False
    try:
        out = tools[tool].invoke(args)
    except Exception:  # noqa: BLE001 - an argument the tool refuses (an approach it does not know) is a miss
        return None, None, False
    data = dict(out.get("data") or {}, _ids=w["ids"])
    got = data.get("total_matching")
    try:
        ok_check = got == total and bool(check(data))
    except Exception:  # noqa: BLE001
        ok_check = False
    return out, got, ok_check


def test_the_spread_set_has_8_questions_each_with_a_known_answer():
    assert len(QUESTIONS) == 8 and len({q[0] for q in QUESTIONS}) == 8


def test_all_data_every_spread_question_states_the_known_answer(world):
    tools = _tools(world, significant=False)
    table, wrong = [], []
    for q in QUESTIONS:
        out, got, ok_check = _measure(world, tools, q)
        table.append({"id": q[0], "setting": "all data", "question": q[1], "total_ok": got == q[4],
                      "check_ok": ok_check, "known_total": q[4], "stated_total": got})
        if not (got == q[4] and ok_check):
            wrong.append((q[0], q[4], got, ok_check, str((out or {}).get("summary"))[:300]))
    _record(table)
    assert not wrong, wrong


def test_significant_every_spread_question_is_refused_with_the_boundary_and_no_records(world):
    tools = _tools(world, significant=True)
    table, wrong = [], []
    for q in QUESTIONS:
        if q[2] not in tools:
            table.append({"id": q[0], "setting": "significant", "question": q[1], "refused": False, "no_records": True})
            wrong.append((q[0], "no tool"))
            continue
        out = tools[q[2]].invoke(q[3])
        data = out.get("data") or {}
        refused = out.get("status") == "error" and "Significant layer" in str(out.get("summary"))
        table.append({"id": q[0], "setting": "significant", "question": q[1], "refused": refused,
                      "no_records": not data.get("items")})
        if not (refused and not data.get("items")):
            wrong.append((q[0], out.get("status"), out.get("summary")))
    _record(table)
    assert not wrong, wrong


def _record(rows):
    path = os.environ.get("LOUPE_AGENT_EVAL_OUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
