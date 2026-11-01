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


# -- the folder container digest, shared with the backend ------------------------------------------------------

# The backend computes the same digest from the upload manifest (backend/tests/test_resumable_upload_groups.py
# pins the same value), so the capture job can check a folder upload end to end (01 section 3 step 1).
FOLDER_DIGEST = "18211b100413cb6b6017f0c5e0a21ec95ecd4925d8a08ffcc54553f365049d44"


def _synthetic_folder(base):
    for rel, value in {"a.txt": b"one", "sub/b.bin": b"two!", ".DS_Store": b"x", "__MACOSX/._a.txt": b"y"}.items():
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_bytes(value)


def test_folder_container_digest_is_over_the_sorted_manifest_lines_of_non_skipped_files(tmp_path):
    from app.phone.runner import hash_container
    _synthetic_folder(tmp_path / "R")
    sha, _, size, members = hash_container(str(tmp_path / "R"))
    assert (sha, size, sorted(members)) == (FOLDER_DIGEST, 7, ["a.txt", "sub/b.bin"])


def test_a_folder_whose_bytes_differ_from_its_upload_digest_is_not_read(tmp_path):
    from app.phone.runner import CaptureFailed, run_capture
    _synthetic_folder(tmp_path / "case" / "R")
    with pytest.raises(CaptureFailed) as e:  # stops before anything is written: no connection is used
        run_capture(None, data_root=str(tmp_path), case_id="case", container_path="R", root_path="",
                    upload_sha256="0" * 64)
    assert e.value.code == "container_changed_since_upload"


# -- the same-phone notice (01 section 10.7 step 2, decision D36) ------------------------------------------------

def test_device_keys_read_the_project_id_and_extraction_ids_from_the_skeletons():
    from app.phone.runner import device_keys, same_device
    sk = ["project", {"id": "p-1"}, None, [["@ns", None, None, None],
                                           ["extractionInfos", {}, None, [["extractionInfo", {"id": "0"}, None, []],
                                                                          ["extractionInfo", {"id": "2"}, None, []]]]]]
    keys = device_keys([sk, ["project", {"id": "p-other"}, None, [["extractionInfo", {"id": "1"}, None, []]]]])
    assert keys == {"project_id": "p-1", "extraction_info_ids": ["0", "1", "2"]}
    assert same_device(keys, {"project_id": "p-1", "extraction_info_ids": []})
    # the same extractionInfo ordinals on two different phones are not the same phone (measured, D36)
    assert not same_device({"project_id": "a", "extraction_info_ids": ["0"]}, {"project_id": "b", "extraction_info_ids": ["0"]})
    assert not same_device({"project_id": None}, {"project_id": None})


@pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")
def test_a_second_report_of_the_same_phone_is_flagged_and_both_stay_active(pg_case, tmp_path):
    from app.phone.runner import run_capture
    conn, case_id = pg_case
    root = tmp_path / str(case_id)
    people = fb.invent_people(4, seed=7)
    for label, seed in (("S3", 21), ("S5", 22)):
        spec = fb.PhoneSpec(label, like="P09", scale=0.01, contacts=[p.key for p in people[1:]], seed=seed)
        fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(root / label)
    # S4: S3 with one attribute value changed, so a different report of the same project
    shutil.copytree(root / "S3", root / "S4")
    xml = next(p for p in (root / "S4").rglob("*.xml") if b"<project " in p.read_bytes()[:4096])
    data = xml.read_bytes()
    assert data.count(b'name="Synthetic S3"') == 1
    xml.write_bytes(data.replace(b'name="Synthetic S3"', b'name="Synthetic S4"'))
    first = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S3", root_path="")
    other = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S5", root_path="")
    second = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S4", root_path="")
    assert first["extraction_id"] != second["extraction_id"]
    flags = lambda ext: conn.execute("SELECT flags FROM phone_extractions WHERE id = %s", (ext,)).fetchone()[0]
    assert flags(second["extraction_id"])["possible_same_device"] == [{"extraction_id": first["extraction_id"], "name": "S3"}]
    assert "possible_same_device" not in flags(other["extraction_id"])
    assert flags(first["extraction_id"])["device_keys"]["project_id"] == flags(second["extraction_id"])["device_keys"]["project_id"]
    assert "appears to be from the same phone (S3). Both are kept." in second["message"]
    standings = conn.execute("SELECT standing, count(*) FROM phone_extractions WHERE case_id = %s GROUP BY 1",
                             (case_id,)).fetchall()
    assert standings == [("active", 3)]


def test_files_with_no_location_count_as_absent_with_the_missing_ones():
    """P10's shape, measured: every listed file missing except one the report gives no location for. No file is in
    the production, so the report is flagged all absent and the sentence gives the split."""
    from app.phone.files import absent_count, absent_text
    assert absent_count({"missing": 18952, "no_local_path": 1}) == 18953
    assert absent_count({"missing": 3, "match": 1}) == 3
    assert absent_text({"missing": 18952, "no_local_path": 1}, 18953) == (
        " None of the 18,953 files the report lists is in the production: 18,952 are missing and 1 has no location in "
        "the production. Each is marked absent.")
    assert absent_text({"missing": 4}, 4) == (
        " None of the 4 files the report lists is in the production; each is marked absent.")


@pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")
def test_the_row_digest_is_equal_for_two_captures_of_one_report_and_names_a_changed_table(pg_case, tmp_path):
    """01 units 2.2 and 2.4 compare captures by this digest: it ignores the extraction's id and wall-clock columns."""
    from app.phone.digest import extraction_digest
    from app.phone.runner import run_capture
    conn, case_id = pg_case
    root = tmp_path / str(case_id)
    people = fb.invent_people(4, seed=9)
    spec = fb.PhoneSpec("S6", like="P09", scale=0.01, contacts=[p.key for p in people[1:]], seed=31)
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(root / "S6")
    first = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S6", root_path="")
    a = extraction_digest(conn, first["extraction_id"])
    assert a["phone_records"]["rows"] == first["records"] and a["phone_files"]["rows"] == first["files"]
    # the same report again in a fresh case: a second extraction with its own id, every row equal
    other = uuid.uuid4()
    conn.execute("INSERT INTO cases (id,title,status,archived,created_by_user_id,owner_user_id,created_at,updated_at) "
                 "SELECT %s, title, status, archived, created_by_user_id, owner_user_id, now(), now() FROM cases "
                 "WHERE id = %s", (other, case_id))
    shutil.copytree(root, tmp_path / str(other))
    try:
        second = run_capture(conn, data_root=str(tmp_path), case_id=other, container_path="S6", root_path="")
        assert second["extraction_id"] != first["extraction_id"]
        assert extraction_digest(conn, second["extraction_id"]) == a
        conn.execute("UPDATE phone_records SET deleted_state = 'deleted' WHERE extraction_id = %s AND ordinal = "
                     "(SELECT min(ordinal) FROM phone_records WHERE extraction_id = %s)",
                     (second["extraction_id"], second["extraction_id"]))
        b = extraction_digest(conn, second["extraction_id"])
        assert [t for t in a if a[t] != b[t]] == ["phone_records"]
    finally:
        for t in ("phone_extractions", "phone_extraction_containers"):
            conn.execute("DELETE FROM %s WHERE case_id = %%s" % t, (other,))
        conn.execute("DELETE FROM cases WHERE id = %s", (other,))


def _another_case(conn, like):
    other = uuid.uuid4()
    conn.execute("INSERT INTO cases (id,title,status,archived,created_by_user_id,owner_user_id,created_at,updated_at) "
                 "SELECT %s, title, status, archived, created_by_user_id, owner_user_id, now(), now() FROM cases "
                 "WHERE id = %s", (other, like))
    return other


def _drop_case(conn, case_id):
    for t in ("phone_extractions", "phone_extraction_containers"):
        conn.execute("DELETE FROM %s WHERE case_id = %%s" % t, (case_id,))
    conn.execute("DELETE FROM cases WHERE id = %s", (case_id,))


@pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")
def test_pause_during_capturing_then_resume_equals_an_uninterrupted_run_and_cancel_keeps_the_container(
        pg_case, tmp_path, monkeypatch):
    """01 unit 2.2: pause stops after a committed flush; resume completes with every row and the reconciliation equal
    to an uninterrupted run (row digest); cancel on a pending extraction removes its rows and keeps the container."""
    import functools
    from app.phone import runner, store
    from app.phone.digest import extraction_digest
    from app.phone.job import cancel_rows
    monkeypatch.setattr(runner, "CopySink", functools.partial(store.CopySink, flush_rows=40))  # many flushes
    conn, case_id = pg_case
    people = fb.invent_people(5, seed=13)
    spec = fb.PhoneSpec("S7", like="P09", scale=0.05, contacts=[p.key for p in people[1:]], seed=41)
    built = tmp_path / "built"
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(built / "S7")

    state = {"now": None}
    real_set_state = runner.set_state

    def set_state(conn_, ext_, value, *a, **k):
        state["now"] = value
        return real_set_state(conn_, ext_, value, *a, **k)
    monkeypatch.setattr(runner, "set_state", set_state)

    class PauseInCapturing(runner.Reporter):
        def __init__(self, after):
            self.asks, self.after = 0, after

        def should_stop(self):
            if state["now"] != "capturing":
                return False
            self.asks += 1
            return self.asks > self.after

    cases = [case_id, _another_case(conn, case_id), _another_case(conn, case_id)]
    try:
        for c in cases:
            shutil.copytree(built, tmp_path / str(c))
        run = lambda c, rep=None: runner.run_capture(conn, data_root=str(tmp_path), case_id=c, container_path="S7",
                                                     root_path="", reporter=rep)
        whole = run(cases[0])
        assert whole["state"] == "captured"
        reference = extraction_digest(conn, whole["extraction_id"])

        with pytest.raises(runner.StopRequested):
            run(cases[1], PauseInCapturing(after=3))
        ext = conn.execute("SELECT id, capture_state, standing FROM phone_extractions WHERE case_id = %s",
                           (cases[1],)).fetchone()
        assert ext[1:] == ("capturing", "pending")
        partial = conn.execute("SELECT count(*) FROM phone_records WHERE extraction_id = %s", (ext[0],)).fetchone()[0]
        assert 0 < partial < whole["records"]  # stopped after a committed flush, not at the end
        resumed = run(cases[1])
        assert resumed["state"] == "captured" and resumed["extraction_id"] == str(ext[0])
        assert extraction_digest(conn, ext[0]) == reference

        with pytest.raises(runner.StopRequested):
            run(cases[2], PauseInCapturing(after=2))
        pending = conn.execute("SELECT id, first_container_id FROM phone_extractions WHERE case_id = %s",
                               (cases[2],)).fetchone()
        assert cancel_rows(conn, pending[0]) is True
        q = lambda sql, arg: conn.execute(sql, (arg,)).fetchone()
        assert q("SELECT count(*) FROM phone_records WHERE extraction_id = %s", pending[0]) == (0,)
        assert q("SELECT capture_state::text FROM phone_extractions WHERE id = %s", pending[0]) == ("cancelled",)
        assert q("SELECT count(*) FROM phone_extraction_containers WHERE id = %s", pending[1]) == (1,)
        assert cancel_rows(conn, whole["extraction_id"]) is False  # an active extraction is never cancelled away
        assert extraction_digest(conn, whole["extraction_id"]) == reference
    finally:
        for c in cases[1:]:
            _drop_case(conn, c)


SUBPATH_REPORT = """<?xml version="1.0" encoding="utf-8"?>
<project id="p-sub" extractionType="Logical" xmlns="http://pa.cellebrite.com/report/2.0">
  <sourceExtractions><extractionInfo id="0" name="E" /></sourceExtractions>
  <taggedFiles>
    <file id="t1" path="/Root/data/app/a.db" size="1" />
    <file id="t2" path="/Root/data/app/b.db" size="1" />
    <file id="t3" path="/dup/x.db" size="1" />
    <file id="t4" path="/DUP/x.db" size="1" />
  </taggedFiles>
  <decodedData />
  <extraInfos>
    <extraInfo id="r1" type="Model"><sourceInfo><nodeInfos>
      <nodeInfo id="t1" name="a" path="elsewhere" />
      <nodeInfo id="q1" name="b" path="\\Root\\data\\app\\b.db" />
      <nodeInfo id="q2" name="a" path="Image1.bin/Root/data/app/a.db" />
      <nodeInfo id="q3" name="x" path="Image1.bin/dup/x.db" />
      <nodeInfo id="q4" name="n" path="Image1.bin/none.db" />
      <nodeInfo id="q5" name="n" path="data/app/a.db" />
    </nodeInfos></sourceInfo></extraInfo>
  </extraInfos>
</project>
"""


@pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")
def test_extra_info_nodes_resolve_by_id_then_path_then_path_without_its_source_name(pg_case, tmp_path):
    """D24 and D38: by id; else by path in one form; else by the path without its first segment (P01's source
    names); only when exactly one tagged file has that form. Two files with one form are not chosen between."""
    from app.phone.runner import run_capture
    conn, case_id = pg_case
    folder = tmp_path / str(case_id) / "S8"
    folder.mkdir(parents=True)
    (folder / "report.xml").write_text(SUBPATH_REPORT)
    res = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S8", root_path="")
    assert res["state"] == "captured", res
    rows = conn.execute("SELECT n.node_id, n.resolution, f.source_file_id FROM phone_extra_info_nodes n LEFT JOIN "
                        "phone_files f ON f.extraction_id = n.extraction_id AND f.document_index = "
                        "n.file_document_index AND f.ordinal = n.file_ordinal WHERE n.extraction_id = %s "
                        "ORDER BY n.body_path", (res["extraction_id"],)).fetchall()
    assert sorted(rows) == sorted([("t1", "tagged_file_id", "t1"), ("q1", "tagged_file_path", "t2"),
                                   ("q2", "tagged_file_subpath", "t1"), ("q3", "unresolved", None),
                                   ("q4", "unresolved", None), ("q5", "unresolved", None)])
    assert res["summary"]["store_extra_nodes"]["tagged_file_subpath"] == 1


@pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")
def test_the_phone_report_evidence_row_follows_its_reading_and_no_other_row_is_touched(pg_case):
    from app.phone.job import CANCELLED_TEXT, set_evidence_status
    conn, case_id = pg_case
    phone, other = uuid.uuid4(), uuid.uuid4()
    for i, source in ((phone, "phone_extraction"), (other, None)):
        conn.execute("INSERT INTO evidence_files (id, case_id, original_filename, stored_path, sha256, status, "
                     "source_type) VALUES (%s, %s, 'x', 'x', %s, 'processing', %s)", (i, case_id, "a" * 64, source))
    try:
        state = lambda i: conn.execute("SELECT status, last_error, processed_at IS NOT NULL FROM evidence_files "
                                       "WHERE id = %s", (i,)).fetchone()
        set_evidence_status(conn, phone, "failed", CANCELLED_TEXT)
        assert state(phone) == ("failed", CANCELLED_TEXT, False)
        set_evidence_status(conn, phone, "processing")
        set_evidence_status(conn, phone, "processed")
        assert state(phone) == ("processed", None, True)
        set_evidence_status(conn, other, "processed")  # an ordinary row is never changed by the phone job
        assert state(other) == ("processing", None, False)
        set_evidence_status(conn, None, "processed")  # a job with no evidence row does nothing
    finally:
        conn.execute("DELETE FROM evidence_files WHERE id IN (%s, %s)", (phone, other))
