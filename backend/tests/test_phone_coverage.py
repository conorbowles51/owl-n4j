"""02-U7 (brief item I): the coverage map of one extraction and its endpoint (02 section 7)."""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

from services.phone import coverage, registry, sweep
from services.phone.mappings import loader
from tests.phone_pg import corpus_connection, fresh_engine, make_case, needs_corpus, needs_template
from tests.test_phone_mappings import CALL, call_extraction, hooks, write  # noqa: F401 (fixture)


def _field(cov, t, f):
    [ty] = [x for x in cov["types"] if x["type"] == t]
    return [x for x in ty["fields"] if x["field"] == f]


def test_generic_levels_follow_the_rule_table():
    g = coverage.generic_level
    assert g("Call", "TimeStamp", "TimeStamp") == ("generic_role", "time")
    assert g("Call", "Duration", "TimeSpan") == ("generic_role", "duration")
    assert g("Call", "Direction", "ModelDirections") == ("generic_role", "direction")
    assert g("Party", "IsPhoneOwner", "Boolean") == ("generic_role", "owner_flag")
    assert g("Location", "DeviceLocationAffiliation", "LocationAffiliation") == ("generic_role", "affiliation")
    assert g("Contact", "contactphoto_extracted_path", "String") == ("generic_role", "file_reference")
    assert g("Note", "Body", "String") == ("generic_text", "text")
    assert g("UserAccount", "Password", "String", sensitive={("UserAccount", "Password")}) == ("generic_text",
                                                                                                "sensitive")
    assert g("Call", "VideoCall", "Boolean") == ("captured_only", None)
    assert g("Call", "Parties", "Party", child=True) == ("generic_role", "party")
    assert g("Location", "Position", "Coordinate", child=True) == ("generic_role", "coordinate")
    assert g("Contact", "Entries", "WebAddress", child=True) == ("generic_text", "text")
    assert g("Chat", "Messages", "InstantMessage", child=True) == ("captured_only", "nested_record")


def _skeleton(infos):
    return ["project", {"reportVersion": "7.0"}, None, [
        ["extractionInfos", None, None, [["extractionInfo", a, None, None] for a in infos]],
        ["decodedData", None, None, [["@r", 0, 6]]]]]


@needs_template
def test_a_field_is_unconfirmed_when_its_mapping_loads_reviewed_once_confirmed_and_generic_when_removed(hooks):
    path = write(str(hooks), CALL)
    infos = [{"index": "0", "name": "Logical", "type": "Logical", "IsPartialData": "False",
              "IsSelectiveExtraction": "True", "IsStoppedByUser": "False"},
             {"index": "1", "name": "File system", "type": "FileSystem", "IsPartialData": "True",
              "IsSelectiveExtraction": "True", "IsStoppedByUser": "False"}]
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = call_extraction(c, case)
            c.execute(text("UPDATE phone_extraction_documents SET skeleton = CAST(:s AS jsonb) WHERE extraction_id = :e"),
                      {"s": json.dumps(_skeleton(infos)), "e": ext})
        sweep.interpret_one(engine, ext)
        with engine.connect() as c:
            cov = coverage.compute(c, ext, case)
            [ts] = _field(cov, "Call", "TimeStamp")
            assert (ts["level"], ts["generic_level"], ts["rules"]) == ("applied_unconfirmed", "generic_role",
                                                                       ["Call.event_time"])
            [parties] = _field(cov, "Call", "Parties")
            assert parties["level"] == "applied_unconfirmed" and parties["value_type"] == "Party"
            [ty] = [x for x in cov["types"] if x["type"] == "Call"]
            assert ty["level"] == "applied_unconfirmed" and ty["mapping_name"] == "Call"
            assert cov["summary"]["unconfirmed_calls"] == 7
            assert cov["summary"]["records_by_level"]["applied_unconfirmed"] == 3
            [owner] = _field(cov, "Party", "IsPhoneOwner")
            assert (owner["level"], owner["level_detail"]) == ("generic_role", "owner_flag")
            sel = cov["selection"]
            assert sel["IsSelectiveExtraction"] == "True" and sel["IsStoppedByUser"] == "False"
            assert sel["IsPartialData"] == ["False", "True"]  # elements disagree: both stated, never folded
            assert sel["IsTriageExtraction"] is None
            assert [i["index"] for i in sel["per_extraction_info"]] == ["0", "1"]
            assert "IsTriageExtraction" not in sel["per_extraction_info"][0]
        with engine.begin() as c:  # a person confirms the event-time rule on this extraction
            c.execute(text("UPDATE phone_mapping_judgements SET status = 'confirmed' WHERE extraction_id = :e AND "
                           "rule_id = 'Call.event_time'"), {"e": ext})
        with engine.connect() as c:
            cov = coverage.compute(c, ext, case)
            assert _field(cov, "Call", "TimeStamp")[0]["level"] == "reviewed"
            assert _field(cov, "Call", "Parties")[0]["level"] == "applied_unconfirmed"
            assert [x for x in cov["types"] if x["type"] == "Call"][0]["level"] == "applied_unconfirmed"
        os.remove(path)
        loader.use_data_dir(str(hooks))
        with engine.connect() as c:
            cov = coverage.compute(c, ext, case)
            [ts] = _field(cov, "Call", "TimeStamp")
            assert (ts["level"], ts["level_detail"]) == ("generic_role", "time") and "rules" not in ts
            assert [x for x in cov["types"] if x["type"] == "Call"][0]["level"] == "generic"
        with engine.connect() as c, pytest.raises(coverage.NotFound):
            coverage.compute(c, ext, "00000000-0000-0000-0000-000000000000")


@needs_template
def test_a_suspended_mapping_shows_suspended_with_its_reason(hooks):
    write(str(hooks), CALL)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            drifted = call_extraction(c, case, timestamp_type="String", calls=2)
        sweep.interpret_one(engine, drifted)
        with engine.connect() as c:
            cov = coverage.compute(c, drifted, case)
            [ty] = [x for x in cov["types"] if x["type"] == "Call"]
            assert ty["level"] == "suspended" and {r["reason"] for r in ty["suspension_reasons"]} == {"open_flag"}
            assert {f["level"] for f in _field(cov, "Call", "TimeStamp")} == {"suspended"}
            assert any(fl["flag_kind"] == "new_value_type" for fl in cov["flags"])


@needs_corpus
def test_c3_coverage_lists_35_types_178_combinations_and_the_selection_verbatim():
    from tests.test_phone_generic import _by_records
    with corpus_connection() as c:
        ext = _by_records(c, 71045)
        if ext is None:
            pytest.skip("C3 is not captured in this database")
        cov = coverage.compute(c, ext, mappings=loader.load_files())
        s = cov["summary"]
        assert (s["types"], s["fields"]) == (35, 178)
        assert s["top_level_types"] == 20 and s["nested_only_types"] > 0
        assert s["combinations_listed"] == sum(len(t["fields"]) for t in cov["types"])
        assert sum(s[lvl] for lvl in coverage.LEVELS) == s["combinations_listed"]
        sel = cov["selection"]
        assert len(sel["per_extraction_info"]) == 3
        for k in ("IsSelectiveExtraction", "IsPartialData", "IsStoppedByUser"):
            vals = [i.get(k) for i in sel["per_extraction_info"]]
            assert all(isinstance(v, str) for v in vals)  # strings as captured, never booleans
        assert sel["IsTriageExtraction"] is None
        [call] = [t for t in cov["types"] if t["type"] == "Call"]
        assert call["records"] == 1657 and call["level"] == "applied_unconfirmed"
        assert {f["level"] for f in call["fields"] if f["field"] == "TimeStamp"} == {"applied_unconfirmed"}
