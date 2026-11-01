"""File outcomes, references and time storage (01 units 1.5 and 1.6), plus the whole capture job end to end.

Pure rules run everywhere. The end-to-end test runs the job on a synthetic phone against a scratch PostgreSQL at
the alembic head, opt-in through ``LOUPE_TEST_PHONE_PG_URL`` (``postgresql://user:pw@127.0.0.1:<port>/<db>``).
"""
import datetime as dt
import os
import shutil
import uuid

import pytest

from app.phone.files import EMPTY_MD5, outcome_for, walk_body
from app.phone.timestamps import extraction_header, parse, rows_for_items, rows_for_record

from . import fixture_builder as fb


# -- 7.2, first matching rule wins ---------------------------------------------------------------------------

@pytest.mark.parametrize("args,expected", [
    (("", 3, "a" * 32, None, (3, "a" * 32, "s")), "no_local_path"),
    (("files/a", 3, "a" * 32, None, None), "missing"),
    (("files/a", 0, "a" * 32, None, (0, EMPTY_MD5, "s")), "empty_placeholder"),
    (("files/a", 0, EMPTY_MD5, None, (0, EMPTY_MD5, "s")), "match"),
    (("files/a", 5, "a" * 32, None, (0, EMPTY_MD5, "s")), "size_mismatch"),
    (("files/a", 3, "a" * 32, None, (4, "a" * 32, "s")), "size_mismatch"),
    (("files/a", 3, "A" * 32, None, (3, "a" * 32, "s")), "match"),
    (("files/a", 3, "b" * 32, None, (3, "a" * 32, "s")), "mismatch"),
    (("files/a", 3, "a" * 32, "t" * 64, (3, "a" * 32, "s" * 64)), "mismatch"),
    (("files/a", 3, None, None, (3, "a" * 32, "s")), "no_hash"),
])
def test_verification_outcomes(args, expected):
    assert outcome_for(*args) == expected


# -- 9.2 -----------------------------------------------------------------------------------------------------

def test_parse_rules():
    v = parse("2021-03-04T05:06:07.123456789+00:00")
    assert v["parse_rule"] == "iso8601_offset" and v["offset_state"] == "explicit"
    assert v["instant"] == dt.datetime(2021, 3, 4, 5, 6, 7, 123456, tzinfo=dt.timezone.utc)
    v = parse("2021-03-04T05:06:07-05:00")
    assert v["original_offset_minutes"] == -300
    v = parse("2021-03-04T05:06:07")
    assert (v["parse_rule"], v["instant"], v["local_wall_time"]) == ("iso8601_no_offset", None,
                                                                     dt.datetime(2021, 3, 4, 5, 6, 7))
    v = parse("1/18/2023 4:05:06 PM -05:00")
    assert v["parse_rule"] == "us_ampm_offset" and v["instant"].hour == 16 and v["original_offset_minutes"] == -300
    v = parse("1/18/2023 12:05:06 AM(UTC-5)")
    assert v["parse_rule"] == "us_ampm_utc_label" and v["instant"].hour == 0 and v["original_offset_minutes"] == -300
    assert parse("1/18/2023 4:05:06 PM")["parse_rule"] == "us_ampm_no_offset"
    assert parse("2023:01:18 16:05:06")["parse_rule"] == "exif"
    v = parse("13/01/2023 16:05:06")
    assert v["parse_rule"] == "slash_24h_no_offset" and v["local_wall_time"] == dt.datetime(2023, 1, 13, 16, 5, 6)
    v = parse("01/02/2023 16:05:06")
    assert (v["parse_rule"], v["local_wall_time"], v["offset_state"]) == ("slash_24h_ambiguous", None, "absent")
    v = parse("0.004")
    assert (v["parse_rule"], v["offset_state"], v["instant"]) == ("unparsed", "unparsed", None)
    assert parse("2021-02-30T00:00:00+00:00")["parse_rule"] == "unparsed"


def test_record_timestamp_rows_carry_field_type_and_formatted_text():
    body = ["model", {"type": "Call"}, None, [
        ["field", {"name": "TimeStamp"}, None, [["value", {"type": "TimeStamp", "formattedTimestamp": "f"},
                                                "2021-01-01T00:00:00+00:00", None]]],
        ["field", {"name": "Other"}, None, [["value", {"type": "String"}, "x", None]]],
        ["@", 9]]]
    assert list(rows_for_record(body)) == [("0.0", "Call", "TimeStamp", "TimeStamp", "2021-01-01T00:00:00+00:00", "f")]


def test_file_rows_take_access_times_and_time_named_items_only():
    body = ["file", {"id": "1"}, None, [
        ["accessInfo", None, None, [["timestamp", {"name": "ModifyTime", "formattedTimestamp": "f"}, "t1", None]]],
        ["metadata", {"section": "MetaData"}, None, [["item", {"name": "EXIFCaptureTime"}, "t2", None],
                                                     ["item", {"name": "Inode Number"}, "7", None]]]]]
    assert sorted(r[2:5] for r in rows_for_items(body)) == [("EXIFCaptureTime", "metadata_item", "t2"),
                                                          ("ModifyTime", "accessInfo", "t1")]


def test_device_zone_only_from_the_device_setting_and_examiner_zone_kept_as_the_examiners():
    sk = ["project", {"reportVersion": "5.x", "extractionType": "Logical"}, None, [
        ["metadata", {"section": "Extraction Data"}, None, [["item", {"name": "Time zone settings (ID)"},
                                                            "_Europe/Dublin", None],
                                                           ["item", {"name": "UFED_PA_Version"}, "7.1", None]]],
        ["projectConfigurations", None, None, [["timeZoneConfigurations", {
            "selectedTimeZone": "_America/New_York", "enableAutomaticallyConvertToUTC": "True"}, None, None]]]]]
    h = extraction_header([(0, sk)])
    assert (h["device_zone"], h["device_zone_source"]) == ("Europe/Dublin", "device_metadata")
    assert h["flags"]["examiner_selected_zone"]["zone"] == "America/New_York"
    assert (h["report_version"], h["producer_version"], h["extraction_type"]) == ("5.x", "7.1", "Logical")
    sk[3][0][3] = []  # no device setting: the examiner's zone is never used for the phone
    h = extraction_header([(0, sk)])
    assert (h["device_zone"], h["device_zone_source"]) == (None, None) and h["flags"]["device_zone_not_stated"]


def test_walk_body_positions_skip_markers():
    body = ["a", None, None, [["b", None, None, None], ["@", 3], ["c", None, None, [["d", None, "x", None]]]]]
    assert [(p, el[0]) for p, el in walk_body(body)] == [("", "a"), ("2", "c"), ("2.0", "d"), ("0", "b")]


# -- the whole job, opt-in PostgreSQL ------------------------------------------------------------------------

PG = os.getenv("LOUPE_TEST_PHONE_PG_URL")


@pytest.fixture
def pg_case():
    from app.phone import store
    conn = store.connect(PG)
    uid, cid = uuid.uuid4(), uuid.uuid4()
    conn.execute("INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) VALUES "
                 "(%s,%s,'synthetic','x','user',true,now(),now())", (uid, "s%s@x.test" % uid.hex[:8]))
    conn.execute("INSERT INTO cases (id,title,status,archived,created_by_user_id,owner_user_id,created_at,updated_at) "
                 "VALUES (%s,'synthetic phone test','active',false,%s,%s,now(),now())", (cid, uid, uid))
    yield conn, cid
    conn.execute("DELETE FROM phone_extractions WHERE case_id = %s", (cid,))
    conn.execute("DELETE FROM phone_extraction_containers WHERE case_id = %s", (cid,))
    conn.execute("DELETE FROM cases WHERE id = %s", (cid,))
    conn.execute("DELETE FROM users WHERE id = %s", (uid,))
    conn.close()


@pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")
def test_capture_job_end_to_end_folder_then_zip_of_the_same_report(pg_case, tmp_path):
    from app.phone.runner import run_capture
    conn, case_id = pg_case
    root = tmp_path / str(case_id)
    people = fb.invent_people(6, seed=3)
    spec = fb.PhoneSpec("S1", like="P09", scale=0.1, contacts=[p.key for p in people[1:]], seed=11)
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(root / "S1")
    # one listed file absent, one replaced by an empty placeholder
    files = sorted(p for p in (root / "S1" / "files").rglob("*") if p.is_file())
    files[0].unlink()
    files[1].write_bytes(b"")
    res = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S1", root_path="")
    assert res["state"] == "captured", res
    ext = res["extraction_id"]
    q = lambda sql: conn.execute(sql, (ext,)).fetchall()
    assert q("SELECT result, difference_count FROM phone_reconciliations WHERE extraction_id = %s") == [("exact", 0)]
    outcomes = dict(q("SELECT outcome, count(*) FROM phone_files WHERE extraction_id = %s GROUP BY 1"))
    assert outcomes.get("missing", 0) >= 1 and sum(outcomes.values()) == res["files"]
    assert q("SELECT standing, capture_state FROM phone_extractions WHERE id = %s") == [("active", "captured")]
    assert q("SELECT count(*) FROM phone_timestamps WHERE extraction_id = %s AND owner_kind = 'record'")[0][0] > 0
    # a zip of the same folder: same report bytes, so one extraction with two containers (6.3, D22)
    fb.zip_folder(root / "S1", root / "S1.zip")
    res2 = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S1.zip", root_path="S1")
    assert res2["already_in_case"] and res2["extraction_id"] == ext
    assert res2["message"] == ("This phone report is already in the case. The new upload is recorded as a second "
                               "copy of the same report.")
    links = q("SELECT root_path FROM phone_extraction_container_links WHERE extraction_id = %s ORDER BY 1")
    assert links == [("",), ("S1",)]
    assert q("SELECT count(*) FROM phone_records WHERE extraction_id = %s")[0][0] == res["records"]


@pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")
def test_a_report_whose_files_are_all_absent_completes_and_says_so(pg_case, tmp_path):
    from app.phone.runner import run_capture
    conn, case_id = pg_case
    root = tmp_path / str(case_id)
    people = fb.invent_people(4, seed=5)
    spec = fb.PhoneSpec("S2", like="P09", scale=0.01, contacts=[p.key for p in people[1:]], seed=12)
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(root / "S2")
    shutil.rmtree(root / "S2" / "files")  # P10's shape: the report and nothing else
    res = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S2", root_path="")
    assert res["state"] == "captured"
    assert res["summary"]["verify_files"]["outcomes"] == {"missing": res["files"]}
    assert ("None of the %s files the report lists is in the production; each is marked absent."
            % format(res["files"], ",")) in res["message"]
    flags = conn.execute("SELECT flags FROM phone_extractions WHERE id = %s", (res["extraction_id"],)).fetchone()[0]
    assert flags["all_files_absent"] == res["files"]
