"""02-U5 and 02-U6: mapping files as versioned data, the applier, suspension and judgement calls (02 section 6;
Neil 2026-10-29: a mapping row the job writes is applied at once as ``applied_unconfirmed`` and shown as one
judgement call per rule for a person to confirm or correct)."""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, text

from services.phone import ids, registry, sweep
from services.phone.mappings import apply, loader, rows
from tests.phone_pg import (corpus_connection, fld, fresh_engine, make_case, make_extraction, model, needs_corpus,
                            needs_template, refs)

T1 = datetime(2023, 3, 14, 19, 7, 12, tzinfo=timezone.utc)

CALL = {
    "kind": "type", "name": "Call", "version": 1, "status": "applied_unconfirmed", "origin": "ai_draft",
    "review": {"reviewed_by": None, "reviewed_on": None, "basis": "synthetic test mapping",
               "registry_requirements": [["Call", "TimeStamp", "field", "TimeStamp"],
                                         ["Call", "Direction", "field", "ModelDirections"]]},
    "body": {"applies_to": "Call", "comm_kind": "call", "event_time": {"field": "TimeStamp"},
             "end_time": {"field": None, "duration_field": "Duration"},
             "participants": {"containers": ["Parties"], "role_map": {"From": "caller", "To": "callee"},
                              "owner_flag": "IsPhoneOwner", "direction_field": "Direction"},
             "thread": {"strategy": "counterpart_set"}},
}


def write(dirpath, content):
    d = os.path.join(dirpath, content["kind"])
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "%s.json" % content["name"])
    with open(p, "w") as fh:
        json.dump(content, fh)
    return p


@pytest.fixture
def hooks(tmp_path):
    """The sweep's hooks and the loader's folder are process-wide: install for one test and restore after."""
    saved = copy.copy(sweep._hooks), list(sweep._hooks["apply"]), dict(apply._hooks)
    loader.use_data_dir(str(tmp_path))
    sweep.register_mapping_set(loader.current_set)
    sweep.register_planner(apply.plan)
    sweep._hooks["apply"] = [apply.apply_extraction]
    yield tmp_path
    sweep._hooks.clear()
    sweep._hooks.update(saved[0])
    sweep._hooks["apply"] = saved[1]
    apply._hooks.clear()
    apply._hooks.update(saved[2])
    loader.use_data_dir(loader.DATA_DIR)


# ---- loader (no database) --------------------------------------------------------------------------------------

def test_a_draft_is_never_loaded(tmp_path):
    write(str(tmp_path), dict(CALL, status="draft"))
    assert loader.load_files(str(tmp_path)) == []


@pytest.mark.parametrize("reviewer,message", [(None, "must name the person"), ("  ", "must name the person"),
                                               ("Claude", "names a model"), ("GPT-5 assistant", "names a model")])
def test_a_reviewed_file_must_name_a_person(tmp_path, reviewer, message):
    c = copy.deepcopy(CALL)
    c.update(status="reviewed", origin="human")
    c["review"]["reviewed_by"] = reviewer
    write(str(tmp_path), c)
    with pytest.raises(loader.LoadError, match=message):
        loader.load_files(str(tmp_path))


def test_an_unconfirmed_file_is_never_stored_under_a_name(tmp_path):
    c = copy.deepcopy(CALL)
    c["review"]["reviewed_by"] = "Neil Byrne"
    write(str(tmp_path), c)
    with pytest.raises(loader.LoadError, match="carries no reviewer"):
        loader.load_files(str(tmp_path))


def test_unknown_keys_and_a_wrong_folder_are_refused(tmp_path):
    c = copy.deepcopy(CALL)
    c["body"]["evnt_time"] = {"field": "TimeStamp"}
    write(str(tmp_path), c)
    with pytest.raises(loader.LoadError):
        loader.load_files(str(tmp_path))
    other = tmp_path / "other"
    os.makedirs(other / "attribution")
    with open(other / "attribution" / "Call.json", "w") as fh:
        json.dump(CALL, fh)
    with pytest.raises(loader.LoadError, match="wrong folder"):
        loader.load_files(str(other))


def test_the_set_id_changes_with_any_file_and_not_with_order(tmp_path):
    write(str(tmp_path), CALL)
    a = loader.mapping_set_id(loader.load_files(str(tmp_path)))
    assert a == loader.mapping_set_id(list(reversed(loader.load_files(str(tmp_path)))))
    write(str(tmp_path), dict(CALL, version=2, body=dict(CALL["body"], text_fields=["Account"])))
    assert loader.mapping_set_id(loader.load_files(str(tmp_path))) != a


def _rows_mapping(tmp_path, rowlist, kind="activity_strength"):
    write(str(tmp_path), {"kind": kind, "name": "DeviceEvent", "version": 1, "status": "applied_unconfirmed",
                          "origin": "ai_draft", "review": {"basis": "synthetic", "registry_requirements": []},
                          "body": {"rows": rowlist}})
    return loader.load_files(str(tmp_path))


def _row(row_id, preds=(), ctx=(), cls="interaction", basis="field_name"):
    return {"row_id": row_id, "type": "DeviceEvent", "field": "StartTime", "predicates": list(preds),
            "context": list(ctx), "outputs": {"class": cls, "actor": "owner", "physical": False}, "basis": basis,
            "reasoning": "synthetic", "would_change": "synthetic"}


def test_two_rows_that_could_both_match_at_equal_specificity_are_refused(tmp_path):
    with pytest.raises(loader.LoadError, match="r1 and r2"):
        _rows_mapping(tmp_path, [_row("r1", [{"field": "EventType", "op": "in", "value": ["A", "B"]}]),
                                 _row("r2", [{"field": "EventType", "op": "eq", "value": "B"}])])
    with pytest.raises(loader.LoadError, match="r1 and r2"):
        _rows_mapping(tmp_path, [_row("r1", [{"field": "Level", "op": "lt", "value": 10}]),
                                 _row("r2", [{"field": "Level", "op": "ge", "value": 5}])])
    with pytest.raises(loader.LoadError, match="r1 and r2"):  # different names constrained: both can hold
        _rows_mapping(tmp_path, [_row("r1", [{"field": "EventType", "op": "eq", "value": "A"}]),
                                 _row("r2", ctx=[{"name": "direction", "op": "eq", "value": "Outgoing"}])])
    assert len(_rows_mapping(tmp_path, [_row("r1", [{"field": "Level", "op": "lt", "value": 5}]),
                                        _row("r2", [{"field": "Level", "op": "ge", "value": 5}])])) == 1
    assert len(_rows_mapping(tmp_path, [_row("r3", [{"field": "EventType", "op": "present"}]),
                                        _row("r4", [{"field": "EventType", "op": "absent"}])])) == 1
    assert len(_rows_mapping(tmp_path, [_row("r5", [{"field": "EventType", "op": "eq", "value": "A"}]),
                                        _row("r6", [{"field": "EventType", "op": "in", "value": ["B", "C"]}])])) == 1


def test_the_most_specific_row_wins_and_no_match_is_none(tmp_path):
    ms = _rows_mapping(tmp_path, [
        _row("general", [{"field": "EventType", "op": "eq", "value": "TextInput"}]),
        _row("owner-out", [{"field": "EventType", "op": "eq", "value": "TextInput"}],
             [{"name": "party_is_owner", "op": "eq", "value": True}], cls="passive"),
        _row("unknown-basis", [{"field": "EventType", "op": "eq", "value": "Lock"}], cls="interaction",
             basis="not_established")])
    base = {"type": "DeviceEvent", "field": "StartTime", "fields": {"EventType": ["TextInput"]}, "context": {}}
    assert rows.evaluate("activity_strength", base, ms)["row_id"] == "general"
    assert rows.evaluate("activity_strength", dict(base, context={"party_is_owner": True}), ms)["row_id"] == "owner-out"
    lock = rows.evaluate("activity_strength", dict(base, fields={"EventType": ["Lock"]}), ms)
    assert lock["outputs"]["class"] == "unknown" and lock["outputs"]["actor"] == "unknown"
    assert rows.evaluate("activity_strength", dict(base, fields={"EventType": ["Other"]}), ms) is None
    assert rows.evaluate("activity_strength", dict(base, field="EndTime"), ms) is None


def test_the_shipped_mapping_files_load():
    ms = loader.load_files()
    assert all(m.status in ("applied_unconfirmed", "reviewed") for m in ms)
    assert all(m.reviewed_by is None for m in ms if m.status == "applied_unconfirmed")
    assert ("KeyValueModel", "Value") in loader.sensitive_fields(ms)


# ---- applier (scratch database) --------------------------------------------------------------------------------

def stamp(ordinal, body_path, field, mt):
    return {"o": ordinal, "bp": body_path, "mt": mt, "fn": field, "ot": "2023-03-14T15:07:12-04:00", "i": T1,
            "os": "explicit", "off": -240, "ft": None, "lw": None}


def call_extraction(c, case, *, timestamp_type="TimeStamp", calls=3, label="C77"):
    records, stamps, o = [], [], 0
    for _ in range(calls):
        top = o
        call = model("Call", [fld("TimeStamp", (timestamp_type, "2023-03-14T15:07:12-04:00")),
                              fld("Duration", ("TimeSpan", "00:01:05")), fld("Direction", ("ModelDirections", "Outgoing")),
                              refs("Parties", top + 1, top + 2)])
        me = model("Party", [fld("Identifier", ("String", "+12025550100")), fld("Role", ("PartyRole", "From")),
                             fld("IsPhoneOwner", ("Boolean", "True"))])
        them = model("Party", [fld("Identifier", ("String", "+12025550143")), fld("Role", ("PartyRole", "To")),
                               fld("IsPhoneOwner", ("Boolean", "False"))])
        records += [(top, None, top, call), (top + 1, top, top, me), (top + 2, top, top, them)]
        if timestamp_type == "TimeStamp":
            stamps.append(stamp(top, "0.0", "TimeStamp", "Call"))
        o += 3
    return make_extraction(c, case, records, timestamps=stamps, label=label)


def _setup(engine, **kw):
    with engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        return case, call_extraction(c, case, **kw)


@needs_template
def test_a_mapping_is_applied_at_once_unconfirmed_with_one_judgement_call_per_rule(hooks):
    write(str(hooks), CALL)
    write(str(hooks), dict(CALL, name="Email", status="draft", body=dict(CALL["body"], applies_to="Email")))
    with fresh_engine() as engine:
        case, ext = _setup(engine)
        out = sweep.interpret_one(engine, ext)
        assert out["status"] == "done" and out["applied:mappings_applied"] == 1
        with engine.connect() as c:
            et = c.execute(text("SELECT count(*), bool_and(is_event_time), min(interpretation_level), "
                                "min(mapping_row_id) FROM phone_time_values WHERE extraction_id = :e AND "
                                "model_type = 'Call'"), {"e": ext}).one()
            assert tuple(et) == (3, True, "applied_unconfirmed", "Call.event_time")
            roles = c.execute(text("SELECT role, role_basis, mapping_row_id, interpretation_level, count(*) FROM "
                                   "phone_participations WHERE extraction_id = :e GROUP BY 1, 2, 3, 4 ORDER BY 1"),
                              {"e": ext}).fetchall()
            assert [tuple(r) for r in roles] == [("callee", "mapping", "Call.role.To", "applied_unconfirmed", 3),
                                                 ("caller", "mapping", "Call.role.From", "applied_unconfirmed", 3)]
            assert c.execute(text("SELECT count(*) FROM phone_record_summaries WHERE extraction_id = :e AND "
                                  "interpretation_level = 'reviewed'"), {"e": ext}).scalar() == 0
            j = c.execute(text("SELECT rule_id, status, records_touched, cardinality(sample_record_uids), resolved_by, "
                               "summary, evidence FROM phone_mapping_judgements WHERE extraction_id = :e ORDER BY rule_id"),
                          {"e": ext}).fetchall()
            assert [r[0] for r in j] == ["Call.end_time", "Call.event_time", "Call.owner_implicit", "Call.record",
                                         "Call.role.From", "Call.role.To", "Call.thread"]
            assert {r[1] for r in j} == {"open"} and {r[4] for r in j} == {None}
            touched = {r[0]: (r[2], r[3]) for r in j}
            assert touched.pop("Call.owner_implicit") == (0, 0)  # every synthetic call lists its owner
            assert touched == {r: (3, 3) for r in touched}, j
            ev = {r[0]: r[6] for r in j}["Call.event_time"]
            assert ev["fields"][0]["value_type"] == "TimeStamp" and ev["fields"][0]["records_here"] == 3
            assert ev["mapping"]["status"] == "applied_unconfirmed" and ev["mapping"]["origin"] == "ai_draft"
            v = c.execute(text("SELECT status, reviewed_by, origin FROM phone_mapping_versions")).fetchall()
            assert [tuple(r) for r in v] == [("applied_unconfirmed", None, "ai_draft")]
            app = c.execute(text("SELECT records_matched, records_suspended FROM phone_mapping_applications WHERE "
                                 "extraction_id = :e"), {"e": ext}).one()
            assert tuple(app) == (3, 0)


CAPTURE_TABLES = ("phone_records", "phone_timestamps", "phone_extraction_documents", "phone_extractions",
                  "phone_extraction_containers")


@needs_template
def test_a_new_version_re_derives_without_touching_the_capture_and_keeps_the_old_call(hooks):
    write(str(hooks), CALL)
    with fresh_engine() as engine:
        case, ext = _setup(engine)
        sweep.interpret_one(engine, ext)
        with engine.begin() as c:
            c.execute(text("CREATE TABLE capture_writes (t text, op text)"))
            c.execute(text("CREATE FUNCTION log_capture_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                           "INSERT INTO capture_writes VALUES (TG_TABLE_NAME, TG_OP); RETURN NULL; END $$"))
            for t in CAPTURE_TABLES:
                c.execute(text("CREATE TRIGGER log_%s AFTER INSERT OR UPDATE OR DELETE ON %s FOR EACH STATEMENT "
                               "EXECUTE FUNCTION log_capture_write()" % (t, t)))
        corrected = copy.deepcopy(CALL)
        corrected["version"] = 2
        corrected["body"]["participants"]["role_map"] = {"From": "callee", "To": "caller"}
        write(str(hooks), corrected)
        loader.use_data_dir(str(hooks))
        with engine.connect() as c:
            assert [str(x) for x in sweep.candidates(c)] == [str(ext)]
        out = sweep.interpret_one(engine, ext)
        assert out["generation"] == 2
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM capture_writes")).scalar() == 0
            roles = dict(c.execute(text("SELECT role_in_record, min(role) FROM phone_participations WHERE "
                                        "extraction_id = :e GROUP BY 1"), {"e": ext}).fetchall())
            assert roles == {"From": "callee", "To": "caller"}
            versions = c.execute(text("SELECT version FROM phone_mapping_versions ORDER BY version")).fetchall()
            assert [r[0] for r in versions] == [1, 2]
            calls = c.execute(text("SELECT v.version, j.generation FROM phone_mapping_judgements j JOIN "
                                   "phone_mapping_versions v ON v.id = j.mapping_version_id WHERE j.rule_id = "
                                   "'Call.role.From' ORDER BY 1")).fetchall()
            assert [tuple(r) for r in calls] == [(1, 1), (2, 2)]  # the original call stays visible
        write(str(hooks), dict(CALL, body=dict(CALL["body"], text_fields=["Account"])))
        loader.use_data_dir(str(hooks))
        with engine.connect() as c, pytest.raises(loader.LoadError, match="lower than"):
            loader.current_set(c)


@needs_template
def test_an_open_drift_flag_suspends_the_mapping_on_that_extraction_only(hooks):
    write(str(hooks), CALL)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            drifted = call_extraction(c, case, timestamp_type="String", calls=2)
            steady = call_extraction(c, case)
        a = sweep.interpret_one(engine, drifted)
        b = sweep.interpret_one(engine, steady)
        assert a["applied:mappings_suspended"] == 1 and a["applied:mappings_applied"] == 0
        assert b["applied:mappings_applied"] == 1
        with engine.connect() as c:
            sus = c.execute(text("SELECT records_suspended, suspension_reasons FROM phone_mapping_applications WHERE "
                                 "extraction_id = :e"), {"e": drifted}).one()
            assert sus[0] == 2
            assert {r["reason"] for r in sus[1]} == {"open_flag"}
            assert {r["observed_value_type"] for r in sus[1]} == {"String"}
            assert c.execute(text("SELECT count(*) FROM phone_participations WHERE extraction_id = :e AND "
                                  "mapping_row_id IS NOT NULL"), {"e": drifted}).scalar() == 0
            assert c.execute(text("SELECT count(*) FROM phone_mapping_judgements WHERE extraction_id = :e"),
                             {"e": drifted}).scalar() == 0
            assert c.execute(text("SELECT count(*) FROM phone_participations WHERE extraction_id = :e AND "
                                  "mapping_row_id IS NOT NULL"), {"e": steady}).scalar() == 6


@needs_template
def test_the_applier_never_reads_proposals(hooks):
    write(str(hooks), CALL)
    with fresh_engine() as engine:
        case, ext = _setup(engine)
        seen = []
        event.listen(engine, "before_cursor_execute", lambda *a: seen.append(a[2]))
        sweep.interpret_one(engine, ext)
        assert seen and not [s for s in seen if "phone_mapping_proposals" in s or "phone_mapping_draft_runs" in s]


@needs_template
def test_a_confirmation_raises_the_level_and_a_correction_replaces_the_choice(hooks):
    write(str(hooks), CALL)
    with fresh_engine() as engine:
        case, ext = _setup(engine)
        vid = str(loader.load_files(str(hooks))[0].id)
        apply.register_reading_decisions(lambda conn, e: {
            ("Call.event_time", vid): {"decision": "confirm", "by": "Synthetic Person", "by_email": "p@x.test",
                                       "at": T1, "reason": "Standard reason", "decision_id": None},
            ("Call.role.From", vid): {"decision": "correct", "choice": "callee", "by": "Synthetic Person",
                                      "by_email": "p@x.test", "at": T1, "reason": "typed", "decision_id": None}})
        sweep.interpret_one(engine, ext)
        with engine.connect() as c:
            lv = dict(c.execute(text("SELECT mapping_row_id, min(interpretation_level) FROM phone_time_values WHERE "
                                     "extraction_id = :e GROUP BY 1"), {"e": ext}).fetchall())
            assert lv["Call.event_time"] == "reviewed"
            roles = dict(c.execute(text("SELECT mapping_row_id, min(role) || '/' || min(interpretation_level) FROM "
                                        "phone_participations WHERE extraction_id = :e GROUP BY 1"), {"e": ext}).fetchall())
            assert roles == {"Call.role.From": "callee/reviewed", "Call.role.To": "callee/applied_unconfirmed"}
            st = dict(c.execute(text("SELECT rule_id, status || '/' || coalesce(resolved_by, '') FROM "
                                     "phone_mapping_judgements WHERE extraction_id = :e"), {"e": ext}).fetchall())
            assert st["Call.event_time"] == "confirmed/Synthetic Person"
            assert st["Call.role.From"] == "corrected/Synthetic Person"
            assert st["Call.role.To"] == "open/"


# ---- shipped type mappings on a real capture (02-U7 acceptance; counts only) ------------------------------------

@needs_corpus
def test_c3_calls_messages_and_emails_under_the_shipped_mappings():
    from services.phone import generic
    from tests.test_phone_generic import _by_records
    with corpus_connection() as c:
        registry.apply_seed(c)
        ext = _by_records(c, 71045)
        if ext is None:
            pytest.skip("C3 is not captured in this database")
        ms = loader.load_files()
        loader.record_versions(c, ms)
        p = apply.plan(c, ext, ms)
        assert not p["suspended"]
        generic.interpret(c, ext, 9999, marks=p["marks"])
        out = apply.apply_extraction(c, ext, 9999, p)
        q = lambda sql: c.execute(text(sql), {"e": ext}).fetchall()  # noqa: E731
        both = q("SELECT count(*) FILTER (WHERE caller AND callee), count(*) FROM (SELECT ev.record_uid, "
                 "bool_or(p.role = 'caller' OR p.implied_role = 'caller') caller, bool_or(p.role = 'callee' OR "
                 "p.implied_role = 'callee') callee FROM phone_comm_events ev LEFT JOIN phone_participations p ON "
                 "p.record_uid = ev.record_uid AND p.generation = ev.generation WHERE ev.extraction_id = :e AND "
                 "ev.generation = 9999 AND ev.kind = 'call' GROUP BY 1) x")
        assert tuple(both[0]) == (1657, 1657)
        assert out["comms:owner_implicit:Call"] == 862  # 545 outgoing with only the callee, 317 incoming with only the caller
        msgs = q("SELECT count(*) FILTER (WHERE thread_key LIKE 'chat:%'), count(*) FILTER (WHERE thread_key LIKE "
                 "'set:%'), count(*) FILTER (WHERE thread_key IS NULL) FROM phone_comm_events WHERE extraction_id = :e "
                 "AND generation = 9999 AND kind = 'message'")
        assert tuple(msgs[0]) == (2716, 201, 0)
        mail = q("SELECT count(*), count(body), count(*) FILTER (WHERE length(body) > 2000) FROM phone_comm_events "
                 "WHERE extraction_id = :e AND generation = 9999 AND kind = 'email'")
        assert tuple(mail[0]) == (294, 293, 291)
        captured_bodies = q("SELECT count(*) FROM phone_texts WHERE extraction_id = :e AND generation = 9999 AND "
                            "model_type = 'Email' AND field_name = 'Body'")
        assert captured_bodies[0][0] == 293  # every captured Body reaches its email, whole
        unequal = q("SELECT count(*) FROM phone_comm_events ev JOIN phone_texts t ON t.record_uid = ev.record_uid AND "
                    "t.generation = ev.generation AND t.field_name = 'Body' WHERE ev.extraction_id = :e AND "
                    "ev.generation = 9999 AND ev.kind = 'email' AND ev.body <> t.value")
        assert unequal[0][0] == 0
        levels = q("SELECT DISTINCT interpretation_level FROM phone_comm_events WHERE extraction_id = :e AND "
                   "generation = 9999")
        assert [r[0] for r in levels] == ["applied_unconfirmed"]
        meaning = q("SELECT count(*), count(meaning_mapping_row_id), count(*) FILTER (WHERE semantics = 'unknown') "
                    "FROM phone_time_values WHERE extraction_id = :e AND generation = 9999")
        assert meaning[0][0] == 22881 and meaning[0][1] == 22881  # every time value has its meaning row
        assert out["meaning_calls"] > 0


# ---- 04-U1: timestamp meaning, activity strength and attribution rows ------------------------------------------

def test_every_time_field_in_the_catalogue_has_a_meaning_row():
    seed = registry.load_seed()
    time_fields = {(f["type_name"], f["field_name"]) for f in seed["fields"] if f["value_type"] in ("TimeStamp", "TimeSpan")}
    ms = loader.load_files()
    tm = [m for m in ms if m.kind == "timestamp_meaning"]
    assert len(tm) == 1 and tm[0].status == "applied_unconfirmed" and tm[0].reviewed_by is None
    covered = {(r["type"], r["field"]) for r in tm[0].body["rows"]}
    assert len(time_fields) == 85 and time_fields <= covered
    for r in tm[0].body["rows"]:  # a row whose basis is not established says unknown
        if r["basis"] == "not_established":
            assert r["outputs"]["semantics"] == "unknown", r["row_id"]
    acts = [m for m in ms if m.kind == "activity_strength"][0].body["rows"]
    devev = {p["value"] for r in acts if r["type"] == "DeviceEvent" for p in r["predicates"] if p["field"] == "EventType"}
    m1 = {"AirplaneMode", "AudioInputRoute", "AudioOutputRoute", "CameraState", "DeviceLockStatus", "DevicePluginStatus",
          "DisplayOnOff", "DoNotDisturbState", "FlashlightState", "MotionState", "NotificationAction",
          "OrientationChange", "PowerEvent", "TextInput", "WifiState"}  # every EventType M1 measured on the 14 reports
    assert m1 <= devev


def _shipped(tmp_path, kinds):
    import shutil
    for k in kinds:
        shutil.copytree(os.path.join(loader.DATA_DIR, k), os.path.join(str(tmp_path), k))


@needs_template
def test_read_times_and_device_event_times_take_their_meaning_from_the_record(hooks):
    _shipped(hooks, ["timestamp_meaning"])
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            msg = model("InstantMessage", [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
                                           refs("To", 1, 2, kind="multiModelField")])
            owner = model("Party", [fld("Identifier", ("String", "+12025550100")), fld("IsPhoneOwner", ("Boolean", "True")),
                                    fld("DateRead", ("TimeStamp", "2023-03-14T15:08:00-04:00"))])
            other = model("Party", [fld("Identifier", ("String", "+12025550143")), fld("IsPhoneOwner", ("Boolean", "False")),
                                    fld("DateRead", ("TimeStamp", "2023-03-14T15:09:00-04:00"))])
            ev_point = model("DeviceEvent", [fld("StartTime", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
                                             fld("EventType", ("DeviceEventTypes", "TextInput"))])
            ev_span = model("DeviceEvent", [fld("StartTime", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
                                            fld("EndTime", ("TimeStamp", "2023-03-14T15:17:12-04:00")),
                                            fld("EventType", ("DeviceEventTypes", "DisplayOnOff"))])
            ext = make_extraction(c, case, [(0, None, 0, msg), (1, 0, 0, owner), (2, 0, 0, other), (3, None, 3, ev_point),
                                            (4, None, 4, ev_span)],
                                  timestamps=[stamp(0, "0.0", "TimeStamp", "InstantMessage"),
                                              stamp(1, "2.0", "DateRead", "Party"), stamp(2, "2.0", "DateRead", "Party"),
                                              stamp(3, "0.0", "StartTime", "DeviceEvent"),
                                              stamp(4, "0.0", "StartTime", "DeviceEvent"),
                                              stamp(4, "1.0", "EndTime", "DeviceEvent")])
        sweep.interpret_one(engine, ext)
        with engine.connect() as c:
            got = {(r[0], r[1]): (r[2], r[3], r[4]) for r in c.execute(text(
                "SELECT ordinal, field_name, semantics, meaning_mapping_row_id, meaning_level FROM phone_time_values "
                "WHERE extraction_id = :e"), {"e": ext})}
            P = "timestamp_meaning/catalogue/"
            assert got[(0, "TimeStamp")] == ("event_instant", P + "tm-instantmessage-timestamp", "applied_unconfirmed")
            assert got[(1, "DateRead")][:2] == ("event_instant", P + "tm-party-dateread-owner")
            assert got[(2, "DateRead")][:2] == ("counterpart_action", P + "tm-party-dateread-other")
            assert got[(3, "StartTime")][:2] == ("event_instant", P + "tm-deviceevent-starttime-noend")
            assert got[(4, "StartTime")][:2] == ("interval_start", P + "tm-deviceevent-starttime")
            assert got[(4, "EndTime")][:2] == ("interval_end", P + "tm-deviceevent-endtime")
            tl = c.execute(text("SELECT count(*) FROM pv_timeline_entry WHERE extraction_id = :e AND semantics IS NOT "
                                "NULL AND meaning_level = 'applied_unconfirmed'"), {"e": ext}).scalar()
            assert tl == 6
            calls = dict(c.execute(text("SELECT rule_id, records_touched FROM phone_mapping_judgements WHERE "
                                        "extraction_id = :e AND rule_part = 'meaning'"), {"e": ext}).fetchall())
            assert calls == {P + "tm-instantmessage-timestamp": 1, P + "tm-party-dateread-owner": 1,
                             P + "tm-party-dateread-other": 1, P + "tm-deviceevent-starttime-noend": 1,
                             P + "tm-deviceevent-starttime": 1, P + "tm-deviceevent-endtime": 1}


def test_a_timespan_compares_in_seconds():
    """04 decision 51: ApplicationUsage ``ActiveTime > 0`` is a numeric predicate on a TimeSpan."""
    from services.phone.mappings import rows as R
    p = {"field": "ActiveTime", "op": "gt", "value": 0}
    assert R._holds(p, {"fields": {"ActiveTime": ["00:00:01"]}}) is True
    assert R._holds(p, {"fields": {"ActiveTime": ["1.00:00:00"]}}) is True
    assert R._holds(p, {"fields": {"ActiveTime": ["00:00:00"]}}) is False
    assert R._holds(p, {"fields": {}}) is False
    assert R._holds({"field": "Level", "op": "lt", "value": 5}, {"fields": {"Level": ["not a time"]}}) is False


def test_email_drafts_and_app_summaries_take_the_measured_rows():
    """cb-statements-rest E: sent mail and app use count as phone use (04 section 3.2, M2)."""
    from services.phone.mappings import rows as R
    body = json.load(open(os.path.join(os.path.dirname(loader.__file__), "data", "activity_strength", "catalogue.json")))
    rows = body["body"]["rows"]

    def row(t, f, fields=None, **ctx):
        m = R.match(rows, t, f, {"fields": fields or {}, "context": ctx})
        return m and m["row_id"]

    assert row("Email", "TimeStamp", {"Folder": ["[Gmail]/Sent Mail"], "Status": ["Sent"]}) == "email-sent"
    assert row("Email", "TimeStamp", {"Folder": ["Enviados"], "Status": ["Sent"]}) == "email-sent"
    assert row("Email", "TimeStamp", {"Folder": ["Outbox"]}) == "email-composed"
    assert row("Email", "TimeStamp", {"Folder": ["[Gmail]/Drafts"]}) == "email-composed"
    assert row("Email", "TimeStamp", {"Folder": ["Borradores"]}) == "email-composed"
    assert row("Email", "TimeStamp", {"Folder": ["Recents"], "Source": ["Recents"]}) == "email-recents"
    assert row("Email", "TimeStamp", {"Folder": ["INBOX"], "Status": ["Unread"]}) == "email-other-folders"
    assert row("Email", "TimeStamp", {}) == "email-nofolder"
    assert row("Email", "TimeStamp", {"Status": ["Default"]}) == "email-nofolder-default"
    assert row("ApplicationUsage", "StartTime", {"ActiveTime": ["00:04:10"]}) == "appusage-summary-active"
    assert row("ApplicationUsage", "StartTime", {"ActiveTime": ["00:00:00"]}) is None
    assert row("ApplicationUsage", "LastLaunch", {"ActiveTime": ["00:04:10"]}) == "appusage-lastlaunch-active"
    assert row("InstantMessage", "TimeStamp", {"Folder": ["Draft"]}, direction="unknown") == "im-draft"
    assert row("InstantMessage", "TimeStamp", {"Folder": ["Draft"]}, direction="outgoing") == "im-out-noplatform"
