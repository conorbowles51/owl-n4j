"""02-U2: registry tables and seed (02 section 3.5)."""
from __future__ import annotations

import json
import os
import re

from sqlalchemy import text

from services.phone import registry
from tests.phone_pg import fresh_engine, needs_template

MEASUREMENTS = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "cellebrite", "measurements")
SEED = registry.load_seed()
NOT_NAMED_SETS = ("DecodingSourceOptions", "@decoding_confidence")


def test_seed_file_counts():
    assert len(SEED["types"]) == 62
    assert sum(t["seed_record_count"] for t in SEED["types"]) == 3405526
    typed = [f for f in SEED["fields"] if f["value_type"] not in registry.PLACEHOLDERS]
    assert len(typed) == 471
    assert len({(f["type_name"], f["field_name"], f["field_kind"]) for f in typed}) == 470
    named = [s for s in SEED["set_values"] if s["set_name"] not in NOT_NAMED_SETS]
    assert len({s["set_name"] for s in named}) == 55 and len(named) == 210
    assert {(s["set_name"], s["value"]) for s in SEED["set_values"] if s["set_name"] in NOT_NAMED_SETS} == {
        ("DecodingSourceOptions", "Decoding"), ("@decoding_confidence", "High")}


def test_seed_nesting_is_the_union_of_the_local_and_server_lists():
    from scripts.phone_registry_seed_build import LOCAL_NESTING
    assert len(set(LOCAL_NESTING)) == 47
    with open(os.path.join(MEASUREMENTS, "a3", "summary.json")) as fh:
        server = {tuple(r) for r in json.load(fh)["seed_02_U2"]["total"]["nesting_relations_list"]}
    assert len(server) == 95
    union = set(LOCAL_NESTING) | server
    got = {(n["parent_type"], n["field_name"], n["field_kind"], n["child_type"]) for n in SEED["nesting"]}
    assert got == union
    assert sum(1 for r in server if r[2] == "RelatedModels") == 18


def test_seed_rebuilds_identically_from_the_committed_catalogues_without_the_counter_rows():
    from scripts.phone_registry_seed_build import build
    rebuilt = build(MEASUREMENTS, None)
    catalogue_rows = [f for f in SEED["fields"] if f["basis"] == "catalogue"]
    assert rebuilt["fields"] == catalogue_rows
    assert rebuilt["types"] == SEED["types"] and rebuilt["set_values"] == SEED["set_values"]
    assert rebuilt["nesting"] == SEED["nesting"]


GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def test_seed_holds_no_path_and_no_basic_value():
    raw = json.dumps(SEED, ensure_ascii=False)
    assert not GUID.search(raw)
    assert "/mnt/" not in raw and "ingestion-data" not in raw and "\\\\" not in raw
    for s in SEED["set_values"]:
        assert s["set_name"] not in registry.BASIC
        assert "/" not in s["value"] and not re.fullmatch(r"[+\d][\d\s()-]{6,}", s["value"])
    assert "Guid" not in {s["set_name"] for s in SEED["set_values"]}


def test_attributes_include_the_names_02_measured():
    attrs = {(a["element"], a["attribute"]) for a in SEED["attributes"]}
    for a in ("decoding_confidence", "deleted_state", "extractionId", "file_id", "id", "isrelated", "labels",
              "source_index", "type", "originalId"):
        assert ("model", a) in attrs
    for a in ("IsPartialData", "IsSelectiveExtraction", "IsStoppedByUser", "IsTriageExtraction"):
        assert ("extractionInfo", a) in attrs


@needs_template
def test_apply_seed_counts_and_is_idempotent():
    with fresh_engine() as engine:
        with engine.begin() as c:
            first = registry.apply_seed(c)
        assert first["types"] == 62 and first["typed_fields"] == 471
        assert first["fields"] == len(SEED["fields"]) and first["nesting"] == len(SEED["nesting"])
        assert first["set_values"] == 212 and first["flags"] == 1
        with engine.connect() as c:
            snap1 = [c.execute(text("SELECT * FROM %s ORDER BY 1, 2" % t)).fetchall() for t in (
                "phone_schema_types", "phone_schema_fields", "phone_schema_set_values", "phone_schema_nesting",
                "phone_schema_attributes", "phone_schema_flags", "phone_schema_flag_events")]
            flag = c.execute(text(
                "SELECT f.state, s.type_name, s.field_name, s.value_type FROM phone_schema_flags f JOIN "
                "phone_schema_fields s ON s.id = f.registry_id")).one()
        assert tuple(flag) == ("acknowledged", "ChatActivity", "SystemMessageId", "String")
        with engine.begin() as c:
            assert registry.apply_seed(c) == first
        with engine.connect() as c:
            snap2 = [c.execute(text("SELECT * FROM %s ORDER BY 1, 2" % t)).fetchall() for t in (
                "phone_schema_types", "phone_schema_fields", "phone_schema_set_values", "phone_schema_nesting",
                "phone_schema_attributes", "phone_schema_flags", "phone_schema_flag_events")]
        assert snap1 == snap2
