"""02-U1: body walker, identifiers and value parsers (02 sections 1.2 and 4).

Unit tests use synthetic bodies. The corpus test is opt-in: ``LOUPE_TEST_PHONE_PG_URL`` (a PostgreSQL holding
captured extractions) and ``LOUPE_PHONE_COUNTER_DIR`` (the counter's per-path outputs, 01 section 8, kept on the
server outside the repo); it compares counts only and prints no value.
"""
from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal

import pytest

from services.phone import body as B
from services.phone import ids, values as V


def _val(t, text, **a):
    return ["value", dict({"type": t}, **a), text, None]


SYNTH = ["model", {"type": "ZzzUnknown", "id": "x"}, None, [
    ["field", {"name": "Label"}, None, [_val("String", "one"), _val("String", "two")]],
    ["field", {"name": "When"}, None, [_val("TimeStamp", "2023-03-14T15:07:12-04:00", format="TimeStampKnown")]],
    ["field", {"name": "Label"}, None, [["empty", None, None, None]]],
    ["multiModelField", {"name": "Parties"}, None, [["@", 7], ["@", 8]]],
    ["modelField", {"name": "Position"}, None, [["@", 9]]],
    ["multiField", {"name": "Reminders"}, None, [_val("TimeStamp", "a"), _val("TimeStamp", "b")]],
    ["jumptargets", {"name": "x"}, None, [["targetid", None, "1", None]]],
    ["dataField", {"name": "Blob"}, None, [["@f", 4]]],
]]


def test_fields_yield_every_field_kind_in_order_with_paths():
    fs = list(B.fields(SYNTH))
    assert [(f.name, f.kind) for f in fs] == [
        ("Label", "field"), ("When", "field"), ("Label", "field"), ("Parties", "multiModelField"),
        ("Position", "modelField"), ("Reminders", "multiField"), ("Blob", "dataField")]
    assert fs[0].body_path == "0" and [v.body_path for v in fs[0].values] == ["0.0", "0.1"]
    assert fs[3].children == [7, 8] and fs[4].children == [9] and fs[6].files == [4]
    assert fs[2].values[0].is_empty and fs[2].real_values == []


def test_a_repeated_field_name_is_kept_twice():
    assert len(B.field_map(SYNTH)["Label"]) == 2


def test_count_matches_the_counter_definition():
    assert B.count(SYNTH) == {"fields": 7, "values": 5, "empties": 1}


def test_body_path_matches_the_capture_timestamp_path():
    # evidence-engine/app/phone/timestamps.py walks children by index from the model element.
    when = B.first_value(SYNTH, "When")
    assert when.body_path == "1.0" and when.type == "TimeStamp"


def test_record_uid_is_a_function_of_the_positional_key():
    e = uuid.UUID("11111111-1111-1111-1111-111111111111")
    assert ids.record_uid(e, 0, 5) == ids.record_uid(str(e), 0, 5)
    assert ids.record_uid(e, 0, 5) != ids.record_uid(e, 0, 6) != ids.file_uid(e, 0, 5)
    assert str(ids.PHONE_NS) == "8fa2f9a7-e6b9-4809-a082-208cf14fa25c"


@pytest.mark.parametrize("text,seconds", [
    ("00:01:05", Decimal(65)), ("01:00:00", Decimal(3600)), ("00:00:01.1234567", Decimal("1.1234567")),
    ("2.03:04:05", Decimal(2 * 86400 + 3 * 3600 + 4 * 60 + 5)), ("1.00:00:00.5", Decimal("86400.5"))])
def test_timespan_forms(text, seconds):
    assert V.parse_timespan(text) == (seconds, None)


@pytest.mark.parametrize("text", ["", "1:2", "00:61:00", "abc", None, "00:00:00.12345678"])
def test_unparseable_timespans(text):
    assert V.parse_timespan(text) == (None, "unparseable")


def test_coordinates_flags_and_accuracy_order():
    ok = V.parse_coordinate("38.9", "-77.03", coordinate_accuracy="5")
    assert ok["is_point"] and ok["accuracy_basis"] == "gps_horizontal" and ok["accuracy_m"] == Decimal(5)
    assert V.parse_coordinate("38.9", "-77.03", parent_accuracy="12")["accuracy_m"] == Decimal(12)
    p = V.parse_coordinate("38.9", "-77.03", parent_precision="High")
    assert p["accuracy_basis"] == "precision_field" and p["precision_text"] == "High"
    assert V.parse_coordinate("38.9", "-77.03")["accuracy_basis"] == "none"
    zz = V.parse_coordinate("0", "0.0")
    assert zz["is_point"] and zz["flags"] == ["zero_zero"]
    assert V.parse_coordinate("91", "0")["flags"] == ["out_of_range"]
    assert not V.parse_coordinate("x", "1")["is_point"] and V.parse_coordinate("x", "1")["flags"] == ["unparseable"]
    assert V.parse_coordinate(None, "1")["flags"] == ["missing_axis"]
    assert V.parse_coordinate("nan", "1")["flags"] == ["unparseable"]


def test_double_is_decimal_and_booleans_verbatim():
    assert V.parse_by_type("Double", "0.1") == Decimal("0.1")
    assert isinstance(V.parse_by_type("Double", "0.1"), Decimal)
    assert V.parse_by_type("Int64", "-12") == -12 and V.parse_by_type("UInt32", "x") is None
    assert V.parse_by_type("Boolean", "True") is True and V.parse_by_type("Boolean", "true") is None


def test_format_mismatch_rules():
    assert V.format_mismatch("TimeStampKnown", "absent")
    assert not V.format_mismatch("TimeStampKnown", "explicit")
    assert V.format_mismatch("DateTimeOnly", "explicit")
    assert not V.format_mismatch("DateTimeOnly", "absent")
    assert not V.format_mismatch(None, "absent")


# ---- corpus: walker counts equal the counter's counts per document --------------------------------------------

PG = os.getenv("LOUPE_TEST_PHONE_PG_URL")
COUNTER = os.getenv("LOUPE_PHONE_COUNTER_DIR")


def counter_expected(path):
    with open(path) as fh:
        paths = json.load(fh)["paths"]
    out = {"fields": 0, "values": 0, "empties": 0}
    for p, c in paths.items():
        segs = p.split("/")
        if len(segs) < 2:
            continue
        last, prev = segs[-1].split("[")[0], segs[-2].split("[")[0]
        if last in B.FIELD_KINDS and prev == "model":
            out["fields"] += c["elements"]
        elif last in ("value", "empty") and prev in B.FIELD_KINDS and "model" in [s.split("[")[0] for s in segs]:
            out["values" if last == "value" else "empties"] += c["elements"]
    return out


@pytest.mark.skipif(not (PG and COUNTER), reason="Requires LOUPE_TEST_PHONE_PG_URL and LOUPE_PHONE_COUNTER_DIR")
def test_walker_counts_equal_the_counter_per_document():
    import psycopg
    with open(os.path.join(COUNTER, "extractions.json")) as fh:
        wanted = json.load(fh)  # {extraction_id: counter file name}, written by the person running the test
    with psycopg.connect(PG) as conn:
        for ext, counter_file in wanted.items():
            got = {"fields": 0, "values": 0, "empties": 0}
            with conn.cursor(name="u1_%s" % ext[:8]) as cur:
                cur.itersize = 5000
                cur.execute("SELECT body FROM phone_records WHERE extraction_id = %s AND document_index = 0", (ext,))
                for (body,) in cur:
                    for k, v in B.count(body).items():
                        got[k] += v
            assert got == counter_expected(os.path.join(COUNTER, counter_file)), counter_file
