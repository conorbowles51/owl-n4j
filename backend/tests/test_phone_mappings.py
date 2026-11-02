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
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs

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


def call_extraction(c, case, *, timestamp_type="TimeStamp", calls=3):
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
    return make_extraction(c, case, records, timestamps=stamps)


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
            assert [r[0] for r in j] == ["Call.end_time", "Call.event_time", "Call.record", "Call.role.From",
                                         "Call.role.To"]
            assert {r[1] for r in j} == {"open"} and {r[4] for r in j} == {None}
            assert {r[0]: r[2] for r in j}["Call.event_time"] == 3
            assert {r[0]: r[3] for r in j} == {r[0]: 3 for r in j}, j
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
        assert seen and not [s for s in seen if "phone_mapping_proposals" in s]


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
