"""07 J-17: How this was found. Generated from a finding's phone links; its counts equal the links and decisions
behind it, and the label is "Result for report" only when nothing rests on the system alone.

Invented data only: 555 numbers and made-up text. Needs the PostgreSQL phone template.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def _msg(instant, body, level=None):
    return dict(kind="message", instant=instant, body=body, thread="t", direction="incoming",
                parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)],
                **({"level": level} if level else {}))


def _entry(c, case, links):
    eid = uuid.uuid4()
    c.execute(text("INSERT INTO workspace_entries (id, case_id, entry_type, title, body, lifecycle_state) VALUES "
                   "(:i, :c, 'finding', 'Synthetic finding', 'synthetic', 'active')"), {"i": eid, "c": case})
    for t, target, label in links:
        c.execute(text("INSERT INTO workspace_entry_links (id, entry_id, case_id, target_type, target_id, "
                       "target_label) VALUES (:i, :e, :c, :t, :x, :l)"),
                  {"i": uuid.uuid4(), "e": eid, "c": case, "t": t, "x": target, "l": label})
    return eid


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, events = phone(c, case, device_zone="America/New_York", events=[
                _msg(at(2023, 3, 14, 12), "first synthetic"),
                _msg(at(2023, 3, 14, 13), "second synthetic", level="applied_unconfirmed"),
                _msg(at(2023, 3, 14, 14), "third synthetic")])
        yield {"engine": engine, "case": case, "other": other, "ext": ext, "events": events}


def _explain(w, entry, case=None):
    from services.phone import explain
    with w["engine"].connect() as c:
        return explain.explain(c, case or w["case"], entry)


def test_j17_the_counts_equal_the_links_and_the_unconfirmed_reading_makes_it_a_lead(world):
    ev = world["events"]
    with world["engine"].begin() as c:
        sid = uuid.uuid4()
        filt = {"case_id": str(world["case"]), "text": {"query": "synthetic", "exact_characters": False}}
        c.execute(text("INSERT INTO phone_selections (id, case_id, filter, words, record_uids, record_count, "
                       "event_count, mapping_versions) VALUES (:i, :c, CAST(:f AS jsonb), 'Two synthetic messages', "
                       "CAST(:u AS uuid[]), 2, 2, CAST(:m AS jsonb))"),
                  {"i": sid, "c": world["case"], "f": json.dumps(filt), "u": [ev[0]["record_uid"], ev[1]["record_uid"]],
                   "m": json.dumps({"phones": [{"extraction_id": str(world["ext"])}]})})
        entry = _entry(c, world["case"], [("phone_selection", str(sid), "Two synthetic messages"),
                                          ("phone_record", ev[2]["record_uid"], "synthetic"),
                                          ("phone_record", ev[0]["record_uid"], "synthetic"),
                                          ("phone_identity", ANA, "synthetic")])
    out = _explain(world, entry)
    assert out["heading"] == "How this was found" and out["has_phone_links"]
    assert out["links"] == {"total": 4, "by_type": {"phone_selection": 1, "phone_record": 2, "phone_identity": 1}}
    # three distinct records: two frozen in the selection, one linked directly (one record is in both)
    # the fixture's messages are confirmed ("reviewed") unless marked otherwise
    assert out["readings"] == {"records": 3, "confirmed": 2, "unconfirmed": 1, "as_recorded": 0,
                               "not_in_current_reading": 0}
    assert out["searches"] == [{"query": "synthetic", "exact": False}]
    assert out["scope"][0]["records"] == 2 and out["scope"][0]["words"] == "Two synthetic messages"
    assert out["identities"] == [{"identity": out["identities"][0]["identity"], "decisions": 0,
                                  "linked_to_person": False, "missing": False}]
    codes = {a["code"] for a in out["assumptions"]}
    assert codes == {"owner_computed", "zone_recorded", "counts_not_reconciled"}
    assert out["label"] == "Lead for enquiry"
    words = " ".join(out["label_reasons"])
    assert "1 reading is mapped by the system and not yet confirmed by a person." in words
    assert "1 linked identity has no decision by a person." in words


def test_j17_a_finding_without_phone_links_has_no_block_and_another_case_sees_nothing(world):
    from services.phone import explain
    with world["engine"].begin() as c:
        plain = _entry(c, world["case"], [])
        held = _entry(c, world["case"], [("phone_record", world["events"][0]["record_uid"], "synthetic")])
    assert _explain(world, plain) == {"entry_id": str(plain), "entry_type": "finding", "heading": "How this was found",
                                      "has_phone_links": False, "links": {"total": 0, "by_type": {}}}
    with pytest.raises(explain.NotFound):
        _explain(world, held, case=world["other"])


def test_j17_a_record_no_longer_in_the_current_reading_is_counted_not_dropped(world):
    with world["engine"].begin() as c:
        entry = _entry(c, world["case"], [("phone_record", str(uuid.uuid4()), "gone"),
                                          ("phone_record", world["events"][0]["record_uid"], "synthetic")])
    out = _explain(world, entry)
    assert out["readings"]["records"] == 2 and out["readings"]["not_in_current_reading"] == 1
    assert out["label"] == "Lead for enquiry"


def test_j17_settled_readings_on_one_phone_are_a_result_for_report(world):
    from services.phone import explain, identities
    with world["engine"].begin() as c:
        c.execute(text("UPDATE phone_comm_events SET interpretation_level = 'reviewed' WHERE extraction_id = :e"),
                  {"e": world["ext"]})
        entry = _entry(c, world["case"], [("phone_record", world["events"][0]["record_uid"], "synthetic")])
    settled = {"owner_basis": "manual", "owner_identity_keys": [OWNER]}
    real_owner = identities.owner
    try:
        identities.owner = lambda conn, ext: settled
        with world["engine"].connect() as c:
            c.execute(text("CREATE TEMP VIEW pv_extraction AS SELECT extraction_id, case_id, 'ingested'::text AS "
                           "state, device_zone, 'exact'::text AS reconciliation_state FROM public.pv_extraction"))
            out = explain.explain(c, world["case"], entry)
    finally:
        identities.owner = real_owner
    assert out["readings"]["confirmed"] == 1 and not out["label_reasons"]
    assert out["label"] == "Result for report"
