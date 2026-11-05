"""03 section 8.3, Download originals and Copy file list. Synthetic phone, invented files. Needs the PostgreSQL template."""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from services.phone import media, originals
from tests.test_phone_media import LINKED, LOOSE, MISSING, world  # noqa: F401 (fixture)
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)
from tests.phone_pg import needs_template

pytestmark = needs_template
GOOD = b"synthetic bytes, exact"
OTHER = b"\x00\xffsynthetic bytes that do not match"


def _user(c, case):
    return c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar_one()


@pytest.fixture
def files(world, tmp_path, monkeypatch):  # noqa: F811
    engine, case, other, ext = world
    monkeypatch.setattr("config.EVIDENCE_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("LOUPE_PHONE_BUNDLE_DIR", str(tmp_path / "bundles"))
    root = tmp_path / str(case) / "up" / "root"
    (root / "chats").mkdir(parents=True)
    (root / "contacts").mkdir(parents=True)
    (root / "chats" / "synthetic-a.jpg").write_bytes(GOOD)
    (root / "contacts" / "synthetic-c.vcf").write_bytes(OTHER)
    with engine.begin() as c:
        c.execute(text("UPDATE phone_files SET disk_relpath = 'chats/synthetic-a.jpg', disk_size = :n, disk_sha256 = :h, "
                       "disk_md5 = :m WHERE file_uid = :f"),
                  {"f": LINKED, "n": len(GOOD), "h": hashlib.sha256(GOOD).hexdigest(), "m": hashlib.md5(GOOD).hexdigest()})
        # the stored hash of this one is wrong: it must be reported, the file still delivered
        c.execute(text("UPDATE phone_files SET disk_relpath = 'contacts/synthetic-c.vcf', disk_size = :n, disk_sha256 = "
                       ":h, outcome = 'mismatch' WHERE file_uid = :f"), {"f": LOOSE, "n": len(OTHER), "h": "ab" * 32})
        cid = c.execute(text("SELECT first_container_id FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()
        c.execute(text("UPDATE phone_extraction_containers SET container_kind = 'folder', stored_path = 'up' WHERE id = :i"),
                  {"i": cid})
        c.execute(text("DELETE FROM phone_extraction_container_links WHERE extraction_id = :e"), {"e": ext})
        c.execute(text("INSERT INTO phone_extraction_container_links (extraction_id, container_id, root_path) VALUES "
                       "(:e, :i, 'root')"), {"e": ext, "i": cid})
    return engine, case, other, ext, tmp_path


def _bundle(engine, case, uids):
    with engine.begin() as c:
        return originals.create(c, case_id=case, user_id=_user(c, case), file_uids=uids, scope_words="C1 synthetic")


def test_the_zip_holds_exact_bytes_and_a_mismatch_or_absent_file_is_reported_never_dropped(files):
    engine, case, *_ = files
    made = _bundle(engine, case, [LINKED, LOOSE, MISSING])
    assert made["state"] == "queued" and made["files_total"] == 3 and made["bytes_total"] == len(GOOD) + len(OTHER)
    assert originals.run_pending(engine)[0]["state"] == "done"
    with engine.connect() as c:
        out = originals.get(c, case, made["bundle_id"])
        row = originals.file_of(c, case, made["bundle_id"])
    assert (out["files_done"], out["bytes_done"]) == (3, len(GOOD) + len(OTHER))  # true progress, ending at the totals
    assert (out["matched"], out["mismatched"], out["not_included"]) == (1, 1, 1)
    assert out["matched"] + out["mismatched"] + out["no_stored_hash"] + out["not_included"] == out["files_total"]
    assert out["file"]["sha256"] == hashlib.sha256(open(row.storage_path, "rb").read()).hexdigest()
    with zipfile.ZipFile(row.storage_path) as z:
        assert z.testzip() is None
        names = z.namelist()
        lines = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode())))
        by = {x["file_uid"]: x for x in lines}
        assert len(lines) == 3  # one line for every file asked for
        good, bad, gone = by[LINKED], by[LOOSE], by[MISSING]
        assert z.read(good["path_in_zip"]) == GOOD and z.getinfo(good["path_in_zip"]).compress_type == zipfile.ZIP_STORED
        assert z.read(bad["path_in_zip"]) == OTHER  # exact bytes of a mismatched file are delivered
    assert good["sha256_computed"] == hashlib.sha256(GOOD).hexdigest() and good["comparison"] == "match"
    assert bad["sha256_computed"] == hashlib.sha256(OTHER).hexdigest() and bad["comparison"] == "mismatch"
    assert "disk_sha256" in bad["note"]
    assert gone["comparison"] == "not_included" and "not in the production" in gone["note"] and not gone["path_in_zip"]
    assert "summary.txt" in names and all(not n.startswith(("/", "..")) for n in names)


def test_a_file_that_cannot_be_opened_has_no_path_in_the_zip(files, monkeypatch):
    engine, case, *_ = files
    real = media.content

    def broken(conn, case_id, file_uid, max_bytes=None):
        name, size, _opener = real(conn, case_id, file_uid, max_bytes=max_bytes)

        def fails():
            raise OSError("synthetic open failure")
        return name, size, fails
    monkeypatch.setattr(media, "content", broken)
    made = _bundle(engine, case, [LINKED])
    originals.run_pending(engine)
    with engine.connect() as c:
        row = originals.file_of(c, case, made["bundle_id"])
    with zipfile.ZipFile(row.storage_path) as z:
        (line,) = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode())))
        assert line["comparison"] == "not_included" and line["path_in_zip"] == "" and "could not be opened" in line["note"]


def test_a_file_that_cannot_be_read_stays_in_the_manifest_and_a_failed_read_says_so(files, monkeypatch):
    engine, case, *_ = files
    real = media.content

    def broken(conn, case_id, file_uid, max_bytes=None):
        name, size, opener = real(conn, case_id, file_uid, max_bytes=max_bytes)
        if str(file_uid) != LOOSE:
            return name, size, opener

        class Half(io.BytesIO):
            def read(self, n=-1):
                raise OSError("synthetic read failure")
        return name, size, lambda: Half(b"x")
    monkeypatch.setattr(media, "content", broken)
    made = _bundle(engine, case, [LINKED, LOOSE])
    originals.run_pending(engine)
    with engine.connect() as c:
        out = originals.get(c, case, made["bundle_id"])
        row = originals.file_of(c, case, made["bundle_id"])
    assert (out["matched"], out["not_included"], out["state"]) == (1, 1, "done")
    with zipfile.ZipFile(row.storage_path) as z:
        by = {x["file_uid"]: x for x in csv.DictReader(io.StringIO(z.read("manifest.csv").decode()))}
    assert by[LOOSE]["comparison"] == "not_included" and "not the whole file" in by[LOOSE]["note"]


def test_a_cancelled_job_leaves_no_file_and_a_finished_one_is_removed_when_its_days_are_up(files, monkeypatch):
    engine, case, *_, tmp_path = files
    made = _bundle(engine, case, [LINKED])
    with engine.begin() as c:
        uid = _user(c, case)
        assert originals.cancel(c, case, made["bundle_id"], uid)
        assert not originals.cancel(c, case, made["bundle_id"], uid)
        assert originals.get(c, case, made["bundle_id"])["state"] == "cancelled"
    assert originals.run_pending(engine) == []
    again = _bundle(engine, case, [LINKED])
    originals.run_pending(engine)
    with engine.connect() as c:
        path = originals.file_of(c, case, again["bundle_id"]).storage_path
    assert originals.sweep_expired(engine) == 0
    later = datetime.now(timezone.utc) + timedelta(days=originals.KEEP_DAYS + 1)
    assert originals.sweep_expired(engine, later) == 1
    with engine.connect() as c:
        assert originals.get(c, case, again["bundle_id"])["state"] == "removed"
    import os
    assert not os.path.exists(path)
    assert [p.name for p in (tmp_path / "bundles").iterdir()] == []  # nothing left behind


def test_a_failed_write_or_heartbeat_fails_the_job_and_never_calls_a_good_file_damaged(files, monkeypatch):
    engine, case, *_, tmp_path = files
    made = _bundle(engine, case, [LINKED])

    def down(*a, **k):
        raise RuntimeError("synthetic database failure")
    monkeypatch.setattr(originals, "PROGRESS_SECONDS", 0)
    monkeypatch.setattr(originals, "_beat", down)
    assert originals.run_pending(engine)[0]["state"] == "failed"
    with engine.connect() as c:
        out = originals.get(c, case, made["bundle_id"])
    assert out["state"] == "failed" and out["file"] is None and "Nothing was delivered" in out["error"]
    assert list((tmp_path / "bundles").iterdir()) == []  # nothing half-made is left


def test_the_sweep_removes_a_left_part_and_the_zip_of_a_deleted_case_and_keeps_a_live_one(files):
    engine, case, *_, tmp_path = files
    made = _bundle(engine, case, [LINKED])
    originals.run_pending(engine)
    with engine.connect() as c:
        kept = originals.file_of(c, case, made["bundle_id"]).storage_path
    left = tmp_path / "bundles" / ("00000000-0000-4000-8000-00000000dead.zip.part")
    orphan = tmp_path / "bundles" / ("00000000-0000-4000-8000-00000000beef.zip")
    left.write_bytes(b"x")
    orphan.write_bytes(b"x")
    originals.sweep_expired(engine)
    assert sorted(p.name for p in (tmp_path / "bundles").iterdir()) == [made["bundle_id"] + ".zip"]
    assert open(kept, "rb").read(2) == b"PK"


def test_a_stopped_worker_is_taken_up_from_the_start_and_gives_up_with_a_reason(files):
    engine, case, *_ = files
    made = _bundle(engine, case, [LINKED])
    with engine.begin() as c:
        c.execute(text("UPDATE phone_original_bundles SET state = 'running', attempts = :a, files_done = 1, heartbeat_at "
                       "= now() - interval '1 hour' WHERE bundle_id = :i"), {"a": originals.MAX_ATTEMPTS - 1, "i": made["bundle_id"]})
    assert originals.run_pending(engine)[0]["state"] == "done"
    other = _bundle(engine, case, [LINKED])
    with engine.begin() as c:
        c.execute(text("UPDATE phone_original_bundles SET state = 'running', attempts = :a, heartbeat_at = now() - "
                       "interval '1 hour' WHERE bundle_id = :i"), {"a": originals.MAX_ATTEMPTS, "i": other["bundle_id"]})
    assert originals.run_pending(engine) == []
    with engine.connect() as c:
        got = originals.get(c, case, other["bundle_id"])
    assert got["state"] == "failed" and "stopped" in got["error"]


def test_a_set_the_disk_cannot_hold_is_refused_with_numbers_and_another_cases_file_is_refused(files, monkeypatch):
    engine, case, other, *_ = files
    with engine.begin() as c:
        with pytest.raises(originals.BundleError, match="not in this case"):
            originals.create(c, case_id=other, user_id=_user(c, other), file_uids=[LINKED], scope_words="x")
    import shutil
    monkeypatch.setattr(shutil, "disk_usage", lambda p: type("D", (), {"free": 1024})())
    with engine.begin() as c:
        with pytest.raises(originals.BundleError, match="Nothing was started"):
            originals.create(c, case_id=case, user_id=_user(c, case), file_uids=[LINKED], scope_words="x")


def test_too_many_files_is_refused_with_its_numbers(monkeypatch):
    monkeypatch.setattr(originals, "FILES_MAX", 2)
    assert originals.count_refusal(2) is None
    assert "at most 2 files; this one has 3" in originals.count_refusal(3)


def test_a_path_never_climbs_out_of_the_zip_and_two_files_with_one_path_both_stay():
    taken = set()
    assert originals.zip_path("C1", r"..\..\etc\passwd", "u1", taken) == "files/C1/etc/passwd"
    assert originals.zip_path("C1", "/etc/passwd", "u2", taken) == "files/C1/etc/passwd_u2"
    assert originals.zip_path("C1", None, "u3", taken) == "files/C1/u3"


def test_compare_checks_every_stored_hash():
    computed = {"md5": "aa", "sha256": "bb"}
    assert originals.compare(computed, {"md5": None, "sha256": None}) == ("no_stored_hash", [])
    assert originals.compare(computed, {"md5": "AA", "disk_sha256": "bb"}) == ("match", [])
    assert originals.compare(computed, {"declared_md5": "aa", "disk_sha256": "cc"}) == ("mismatch", ["disk_sha256"])
