"""05 section 17.3: the report's records against the rows an independent tool read, by each disagreement kind.

Synthetic phone and synthetic tool rows; needs ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"


def msg(instant, other, body, incoming=True):
    parties = [(other, "sender" if incoming else "recipient", False, None, None),
               (OWNER, "recipient" if incoming else "sender", True, None, None)]
    return dict(kind="message", app="SMS", instant=instant, body=body, parties=parties,
                direction="incoming" if incoming else "outgoing", thread="t")


def call(instant, other, duration):
    return dict(kind="call", app="Phone", instant=instant, body=None, direction="outgoing", call_duration_s=duration,
                parties=[(OWNER, "caller", True, None, None), (other, "callee", None, None, None)], thread="c")


T1, T2, T3, T4, T5, T6 = (at(2023, 3, 14, 19, 7, 12), at(2023, 3, 14, 20), at(2023, 3, 15, 10), at(2023, 3, 16),
                          at(2023, 3, 17), at(2023, 3, 14, 18))


def _tool_rows(c, run_id, rows):
    for k, (artefact, kind, instant, roles) in enumerate(rows):
        c.execute(text(
            "INSERT INTO phone_reparse_rows (run_id, artefact, row_index, kind, instant, instant_text, values) VALUES "
            "(:r, :a, :i, :k, :t, :tt, CAST(:v AS jsonb))"),
            {"r": run_id, "a": artefact, "i": k + 1, "k": kind, "t": instant,
             "tt": str(int(instant.timestamp())) if instant else None,
             "v": json.dumps({"app": "SMS", "roles": roles, "columns": {}, "row": roles})})


@pytest.fixture
def world():
    from services.phone_analysis import approaches
    approaches.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, evs = phone(c, case, owner=OWNER, events=[
                msg(T1, ANA, "synthetic one"), msg(T2, ANA, "synthetic two"), msg(T3, BEN, "synthetic three"),
                msg(T4, ANA, "only in the report"), call(T6, ANA, 61)])
            run_id = uuid.uuid4()
            c.execute(text(
                "INSERT INTO phone_reparse_runs (id, case_id, extraction_id, tool, tool_version, tool_commit, "
                "tool_licence, status, mapping_version, requested_by, output_manifest_sha256, finished_at, "
                "artefact_counts) VALUES (:i, :c, :e, 'aleapp', 'v2026.4.5', :commit, 'MIT', 'completed', '1', "
                "'synthetic', :h, now(), CAST(:ac AS jsonb))"),
                {"i": run_id, "c": case, "e": ext, "commit": "7a8dc905283b868bcc4767be8bea470e1a231ea2", "h": "0" * 64,
                 "ac": json.dumps({"mapped": {"sms": 4, "call": 2}})})
            _tool_rows(c, run_id, [
                ("get_sms_mms", "sms", T1, {"party": "+12025550143", "body": "synthetic one", "direction": "Received"}),
                ("get_sms_mms", "sms", T2 + timedelta(hours=5), {"party": "+1 202-555-0143", "body": "synthetic two"}),
                ("get_sms_mms", "sms", T3, {"party": "+12025550188", "body": "synthetic 3"}),
                ("get_sms_mms", "sms", T5, {"party": "+12025550143", "body": "only the tool read this"}),
                ("get_calllog", "call", T6, {"party": "+12025550143", "direction": "2", "duration": "61"}),
                ("get_calllog", "call", T5, {"party": "+12025550188", "direction": "3", "duration": "0"})])
        yield engine, case, ext, evs, run_id


def test_each_disagreement_kind_on_a_synthetic_phone(world):
    from services.phone_analysis import framework as F
    engine, case, ext, evs, run_id = world
    with engine.begin() as c:
        run, created = F.request_run(c, case, "reparse_comparison", {}, "synthetic@example.org")
    assert created
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        rows = c.execute(text("SELECT kind, measures FROM phone_analysis_results WHERE run_id = :r"),
                         {"r": run["id"]}).fetchall()
        done = F.get_run(c, case, run["id"])
    kinds = sorted((r.kind, r.measures["compared"]) for r in rows)
    assert kinds == sorted([("present_in_both", "sms"), ("time_differs", "sms"), ("value_differs", "sms"),
                            ("only_in_report", "sms"), ("only_in_reparse", "sms"), ("present_in_both", "call"),
                            ("only_in_reparse", "call"), ("count_differs", "call")])
    by = {(r.kind, r.measures["compared"]): r.measures for r in rows}
    t = by[("time_differs", "sms")]
    assert t["difference_hours"] == 5.0 and t["report"]["instant"] == T2.isoformat()
    assert t["reparse"]["instant"] == (T2 + timedelta(hours=5)).isoformat()
    assert t["reparse"]["original"] == str(int((T2 + timedelta(hours=5)).timestamp()))
    assert t["read_by"] == "read by ALEAPP v2026.4.5" and t["commit"].startswith("7a8dc905")
    v = by[("value_differs", "sms")]
    assert v["report"]["shown"]["body"] == "synthetic three" and v["reparse"]["shown"]["body"] == "synthetic 3"
    assert by[("count_differs", "call")]["report_count"] == 1 and by[("count_differs", "call")]["reparse_count"] == 2
    assert done["counts"]["compared"]["sms"]["present_in_both"] == 1
    assert done["coverage"]["sentence"] == "Re-parsed records (an independent tool's reading) exist on all 1 phones."


def test_the_tools_rows_are_never_merged_into_the_report(world):
    from services.phone_analysis import framework as F
    from services.phone_analysis import reparse_comparison as RC
    engine, case, ext, evs, run_id = world
    with engine.begin() as c:
        before = c.execute(text("SELECT count(*), md5(string_agg(body::text, '' ORDER BY ordinal)) FROM phone_records "
                                "WHERE extraction_id = :e"), {"e": ext}).first()
        run, _ = F.request_run(c, case, "reparse_comparison", {}, "synthetic@example.org")
    F.execute(engine, uuid.UUID(run["id"]))
    with engine.connect() as c:
        after = c.execute(text("SELECT count(*), md5(string_agg(body::text, '' ORDER BY ordinal)) FROM phone_records "
                               "WHERE extraction_id = :e"), {"e": ext}).first()
        beside = RC.reparse_for_record(c, case, evs[1]["record_uid"])
        events = c.execute(text("SELECT count(*) FROM pv_comm_event WHERE extraction_id = :e"), {"e": ext}).scalar()
    assert tuple(before) == tuple(after) and events == 5
    assert [(b["kind"], b["read_by"], b["difference_hours"]) for b in beside] == [
        ("time_differs", "read by ALEAPP v2026.4.5", 5.0)]


def test_a_kind_the_tool_wrote_nothing_for_is_not_compared_rather_than_only_in_the_report(world):
    from services.phone_analysis import framework as F
    engine, case, ext, evs, run_id = world
    with engine.begin() as c:
        c.execute(text("UPDATE phone_reparse_runs SET artefact_counts = CAST(:ac AS jsonb) WHERE id = :i"),
                  {"ac": json.dumps({"mapped": {"call": 2}}), "i": run_id})  # the tool wrote no SMS table
        run, _ = F.request_run(c, case, "reparse_comparison", {}, "synthetic@example.org")
    F.execute(engine, uuid.UUID(run["id"]))
    with engine.connect() as c:
        rows = c.execute(text("SELECT kind, measures FROM phone_analysis_results WHERE run_id = :r"),
                         {"r": run["id"]}).fetchall()
    sms = [(r.kind, r.measures.get("reason")) for r in rows if r.measures["compared"] == "sms"]
    assert sms == [("not_compared", "ALEAPP v2026.4.5 wrote no text messages for this phone, so the report's 4 text "
                                    "messages are not compared.")]
    assert sorted(r.kind for r in rows if r.measures["compared"] == "call") == [
        "count_differs", "only_in_reparse", "present_in_both"]


def test_web_history_compares_the_tools_apps_one_item_per_url():
    """Measured on P12: the report's web history held another app's records and one record per visit, while
    ALEAPP's Chrome history has one row per URL; compared as they were, 1,488 of 1,789 were "only in the report"."""
    from datetime import datetime, timezone
    from services.phone_analysis.reparse_comparison import web_scope, compare, _unit

    def t(h):
        return datetime(2024, 1, 1, h, tzinfo=timezone.utc)

    def rep(uid, url, h, app="Chrome"):
        return {"record_uid": uid, "party": url, "instant": t(h), "instant_text": None, "content": "", "app": app,
                "shown": {"url": url}}

    def tool(i, url, h, browser="Chrome"):
        return {"locator": "reparse:r:get_chrome:%d" % i, "artefact": "get_chrome", "row_index": i, "party": url,
                "instant": t(h), "instant_text": None, "content": "", "browser": browser, "app": "Chrome",
                "shown": {"url": url}}

    report = [rep("a1", "u1", 1), rep("a2", "u1", 3), rep("a3", "u1", 2), rep("b1", "u2", 4),
              rep("g1", "u9", 5, app="Mail"), rep("g2", "u8", 6, app="Mail")]
    tools = [tool(0, "u1", 3), tool(1, "u2", 4), tool(2, "u3", 7)]
    kept, other = web_scope(report, tools)
    assert other == {"Mail": 2}
    by_url = {r["party"]: r for r in kept}
    assert sorted(by_url) == ["u1", "u2"]
    assert by_url["u1"]["record_uid"] == "a2" and by_url["u1"]["visits"] == 3 and by_url["u1"]["shown"]["visits"] == 3
    m = compare(kept, tools, 26)
    assert len(m["present"]) == 2 and m["only_report"] == [] and [tools[j]["party"] for j in m["only_tool"]] == ["u3"]
    assert _unit(kept) == {"report_unit": "url", "report_records": 4}
    # a tool with one row per visit (the same URL twice) is compared visit by visit
    kept2, _ = web_scope(report, tools + [tool(3, "u1", 1)])
    assert len(kept2) == 4 and _unit(kept2) == {}

