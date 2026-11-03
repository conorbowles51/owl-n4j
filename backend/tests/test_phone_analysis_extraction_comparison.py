"""05-S15, approach 12 extraction comparison on a synthetic pair (05 section 15.8). Invented data only."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from services.phone_analysis import extraction_comparison as E
from services.phone_analysis import framework as F
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550111"
PARAMS = {k: v["default"] for k, v in E.PARAMETERS.items()}


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def _header(c, ext, items, selective=None):
    meta = ["metadata", {"section": "Additional Fields"}, None,
            [["item", {"name": k}, v, None] for k, v in items.items()]]
    children = [meta]
    if selective is not None:
        children.append(["extractionInfo", {"index": "0", "IsSelectiveExtraction": selective}, None, []])
    c.execute(text("UPDATE phone_extraction_documents SET skeleton = CAST(:s AS jsonb) WHERE extraction_id = :e"),
              {"e": ext, "s": json.dumps(["project", {"reportVersion": "7.70"}, None, children])})


def msg(t, body, deleted="Intact"):
    return dict(kind="message", instant=t, body=body, thread="t", deleted_state=deleted, direction="incoming",
                parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)])


def test_identity_verdicts_by_hand():
    """15.8 test 1 on the identifier rule alone."""
    assert E._norm("35-209900-176148-1") == "352099001761481"


@needs_template
def test_same_device_diff_kinds_and_attribution(engine):
    """15.8 tests 1 to 4: equal IMEI is same_device_established; a message intact in the earlier and deleted in the
    later is state_changed; a message newer than the earlier extraction's end is only_in_later, created after the
    first extraction; a Note type the selective earlier extraction holds none of is attributed to selection; a
    message only in the earlier and unexplained is listed."""
    with engine.begin() as c:
        case = make_case(c)
        e1, _ = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "kept"), msg(at(2023, 1, 3, 9), "later deleted"),
                                                   msg(at(2023, 1, 4, 9), "gone")])
        e2, _ = phone(c, case, label="C1 again", events=[msg(at(2023, 1, 2, 9), "kept"),
                                                         msg(at(2023, 1, 3, 9), "later deleted", "Deleted"),
                                                         msg(at(2023, 3, 1, 9), "new")])
        record(c, case, e2, 900, "Note", texts=[("Title", "synthetic note")])
        _header(c, e1, {"IMEI": "352099001761481", "DeviceInfoExtractionStartDateTime": "2023-02-01T00:00:00+00:00",
                        "DeviceInfoExtractionEndDateTime": "2023-02-01T01:00:00+00:00"}, selective="True")
        _header(c, e2, {"IMEI": "35-209900-176148-1", "DeviceInfoExtractionStartDateTime": "2023-04-01T00:00:00+00:00"})
    with engine.connect() as c:
        res, counts = E.analyse(c, case, PARAMS)
    (idc,) = [r for r in res if r["kind"] == "identity_check"]
    assert idc["strength"] == "same_device_established" and idc["measures"]["earlier"] == str(e1)
    kinds = sorted((r["kind"], r["strength"]) for r in res if r["kind"] not in ("identity_check", "type_summary"))
    assert kinds == [("only_in_earlier", "unexplained"), ("only_in_later", "created_after_first"),
                     ("only_in_later", "not_selected_in_other"), ("state_changed", "recorded")]
    with engine.connect() as c:
        dc = E.diff_counts(c, case, str(e1), str(e2))
    assert dc == {"present_in_both": 2, "only_in_earlier": 1, "only_in_later": 2, "state_changed": 1, "field_changed": 0}


@needs_template
def test_contradicting_identifiers_are_undetermined_and_no_diff_is_made(engine):
    """15.8 test 1: equal IMEI with a different serial is flagged and undetermined; no diff is listed."""
    with engine.begin() as c:
        case = make_case(c)
        e1, _ = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "a")])
        e2, _ = phone(c, case, label="C2", events=[msg(at(2023, 1, 2, 9), "b")])
        _header(c, e1, {"IMEI": "352099001761481", "Serial": "AAA111"})
        _header(c, e2, {"IMEI": "352099001761481", "Serial": "BBB222"})
    with engine.connect() as c:
        res, _ = E.analyse(c, case, PARAMS)
    assert [r["kind"] for r in res] == ["identity_check"]
    assert res[0]["strength"] == "undetermined" and res[0]["measures"]["contradiction"] is True


@needs_template
def test_runs_through_the_framework(engine):
    F.register(E)
    with engine.begin() as c:
        case = make_case(c)
        e1, _ = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "a")])
        e2, _ = phone(c, case, label="C2", events=[msg(at(2023, 1, 2, 9), "a", "Deleted")])
        _header(c, e1, {"IMEI": "352099001761481"})
        _header(c, e2, {"IMEI": "352099001761481"})
        run, _ = F.request_run(c, case, "extraction_comparison", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        assert F.results(c, case, run["id"], kind="state_changed")["total"] == 1


@needs_template
def test_compare_phones_counts_equal_approach_12_counts_for_one_device(engine):
    """15.8 test 5 (07 J-16): on a synthetic pair shown to be one device, Compare phones' "on both", "only on one"
    and "only on the other" equal this approach's present_in_both, only_in_earlier and only_in_later; a pair not
    shown to be one device keeps Compare phones' own keys."""
    from services.phone import compare as C
    with engine.begin() as c:
        case = make_case(c)
        e1, _ = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "kept"), msg(at(2023, 1, 3, 9), "later deleted"),
                                                   msg(at(2023, 1, 4, 9), "gone"),
                                                   msg(at(2023, 1, 5, 9), "a message whose time moved")])
        e2, _ = phone(c, case, label="C1 again", events=[msg(at(2023, 1, 2, 9), "kept"),
                                                         msg(at(2023, 1, 3, 9), "later deleted", "Deleted"),
                                                         msg(at(2023, 3, 1, 9), "new"),
                                                         msg(at(2023, 1, 5, 9, 1), "a message whose time moved")])
        e3, _ = phone(c, case, label="C9", events=[msg(at(2023, 1, 2, 9), "kept")])
        _header(c, e1, {"IMEI": "352099001761481"})
        _header(c, e2, {"IMEI": "35-209900-176148-1"})
    with engine.connect() as c:
        dc = E.diff_counts(c, case, str(e1), str(e2))
        cp = C.compare(c, case, e1, e2)
        other = C.compare(c, case, e1, e3)
    m = cp["kinds"]["message"]
    assert cp["basis"] == "approach_12" and cp["key"] == C.SAME_DEVICE_WORDS
    assert (m["both"], m["only_a"], m["only_b"]) == (dc["present_in_both"], dc["only_in_earlier"], dc["only_in_later"])
    # a time that moved a minute is not the equal key, though Compare phones' own 2-minute window would pair it
    assert (m["both"], m["only_a"], m["only_b"]) == (2, 2, 2)
    assert other["basis"] == "record_keys" and other["key"] == C.KEY_WORDS
