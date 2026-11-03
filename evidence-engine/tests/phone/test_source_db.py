"""05 section 17.2: the read-only source database opener. Synthetic databases only."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import zipfile

import pytest

from app.phone import source_db as S


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _db(path, wal=False):
    """A synthetic app database; with ``wal`` two rows stay only in the write-ahead log (the writer is returned
    open so the log is not checkpointed away)."""
    w = sqlite3.connect(path)
    if wal:
        w.execute("PRAGMA journal_mode = WAL")
        w.execute("PRAGMA wal_autocheckpoint = 0")
    w.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT, sent INTEGER, data BLOB)")
    w.execute("CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT) WITHOUT ROWID")
    w.executemany("INSERT INTO messages (id, body, sent, data) VALUES (?, ?, ?, ?)",
                  [(i, "synthetic %d" % i, 1700000000000 + i, bytes(range(i % 200))) for i in range(1, 1201)])
    w.commit()
    if wal:
        w.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        w.executemany("INSERT INTO messages (id, body) VALUES (?, ?)", [(5001, "only in log"), (5002, "only in log")])
        w.commit()
        return w
    w.close()
    return None


def _copy(src, dest):
    sib = {s: (lambda p=src + s: open(p, "rb")) for s in S.SIBLING_SUFFIXES if os.path.exists(src + s)}
    return S.copy_with_siblings(lambda: open(src, "rb"), sib, dest)


@pytest.mark.parametrize("sql", [
    "DELETE FROM messages", "INSERT INTO messages (id) VALUES (9)", "UPDATE messages SET body = 'x'",
    "CREATE TABLE t (x)", "DROP TABLE messages", "ATTACH DATABASE 'file:x.db?mode=rwc' AS z",
    "PRAGMA journal_mode = DELETE", "PRAGMA wal_checkpoint(TRUNCATE)", "VACUUM"])
def test_a_write_statement_is_refused(tmp_path, sql):
    src = str(tmp_path / "app.db")
    _db(src)
    copy = _copy(src, str(tmp_path / "copy"))
    with S.open_read_only(copy["path"]) as c:
        with pytest.raises(S.Refused, match="only reads"):
            S.run(c, sql)
        assert S.run(c, "SELECT count(*) FROM messages")[1] == [(1200,)]
    assert not (tmp_path / "x.db").exists()


def test_a_six_second_query_is_stopped_with_the_reason(tmp_path):
    src = str(tmp_path / "app.db")
    _db(src)
    with S.open_read_only(src) as c:
        t0 = time.monotonic()
        with pytest.raises(S.TimedOut, match="Stopped after 5 seconds"):
            # runs well past 6 s unchecked
            S.run(c, "WITH RECURSIVE r(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM r) SELECT count(*) FROM r")
        assert time.monotonic() - t0 < 6.0
        assert S.run(c, "SELECT count(*) FROM messages")[1] == [(1200,)]  # the connection still answers


def test_the_source_files_sha256_is_unchanged_after_every_open(tmp_path):
    src = str(tmp_path / "app.db")
    writer = _db(src, wal=True)
    before = {s: _sha(src + s) for s in ("", "-wal")}
    for k in range(3):
        copy = _copy(src, str(tmp_path / ("copy%d" % k)))
        out = S.view(copy["path"], table="messages", offset="5", browse="messages", page_no=3)
        assert {s: _sha(src + s) for s in ("", "-wal")} == before
        assert copy["sha256"] == before[""]
        assert out["tables"][0]["name"] == "messages"
    writer.close()


def test_rows_only_in_the_copied_write_ahead_log_are_read_and_the_log_is_listed(tmp_path):
    src = str(tmp_path / "app.db")
    writer = _db(src, wal=True)
    copy = _copy(src, str(tmp_path / "copy"))
    assert [s["suffix"] for s in copy["siblings"]] == ["-wal", "-shm"]
    db_sha, wal_sha = _sha(copy["path"]), _sha(copy["path"] + "-wal")
    out = S.view(copy["path"], table="messages", offset="5002")
    assert out["open_mode"] == "read-only, write-ahead log read"
    assert [t["row_count"] for t in out["tables"] if t["name"] == "messages"] == [1202]
    assert out["named_row"]["found"] and out["named_row"]["values"][2] == "only in log"
    # no checkpoint: the copy's database and log bytes are as copied
    assert _sha(copy["path"]) == db_sha and _sha(copy["path"] + "-wal") == wal_sha
    writer.close()


def test_pages_of_500_with_the_total_stated_and_raw_values(tmp_path):
    src = str(tmp_path / "app.db")
    _db(src)
    with S.open_read_only(src) as c:
        p1, p3 = S.page(c, "messages", 1), S.page(c, "messages", 3)
        no_rowid = S.page(c, "settings", 1)
    assert p1["total"] == 1200 and len(p1["rows"]) == 500 and len(p3["rows"]) == 200
    assert p1["columns"] == ["(rowid)", "id", "body", "sent", "data"]
    row = p1["rows"][99]  # id 100
    assert row[0] == 100 and isinstance(row[3], int) and row[3] == 1700000000100
    assert row[4] == {"blob_bytes": 100, "hex_preview": bytes(range(64)).hex(), "preview_complete": False}
    assert no_rowid["columns"] == ["k", "v"] and no_rowid["total"] == 0


def test_the_named_row_and_each_reason_it_cannot_be_shown(tmp_path):
    src = str(tmp_path / "app.db")
    _db(src)
    with S.open_read_only(src) as c:
        ok = S.named_row(c, "messages", "7")
        assert ok["found"] and ok["rowid"] == 7 and ok["values"][1:3] == [7, "synthetic 7"]
        assert S.named_row(c, "messages", "99999")["reason"].startswith("No row of this table")
        assert S.named_row(c, "nosuch", "1")["reason"] == "The report names a table this database does not have."
        assert S.named_row(c, "messages", "0x1f")["reason"] == "The report's position for this record is not a row number."
        assert "no row numbers" in S.named_row(c, "settings", "1")["reason"]
        assert S.named_row(c, None, None)["reason"] == "The report does not say which row this record came from."


def test_a_file_that_is_not_sqlite_is_refused(tmp_path):
    p = tmp_path / "notes.db"
    p.write_bytes(b"synthetic, not a database")
    with pytest.raises(S.Refused, match="not an SQLite database"):
        with S.open_read_only(str(p)):
            pass


def test_a_member_of_a_zip_and_of_a_folder_is_copied_with_its_log_and_a_mismatched_copy_is_not_opened(tmp_path):
    case = tmp_path / "case"
    folder = case / "up" / "root" / "files" / "Database"
    folder.mkdir(parents=True)
    src = str(folder / "app.db")
    writer = _db(src, wal=True)
    with zipfile.ZipFile(case / "up.zip", "w") as z:
        for s in ("", "-wal"):
            z.write(src + s, "root/files/Database/app.db" + s)
    want = _sha(src)
    for kind, stored in (("folder", "up"), ("zip", "up.zip")):
        main = S._member_opener(str(case), kind, stored, "root", "files/Database/app.db")
        wal = S._member_opener(str(case), kind, stored, "root", "files/Database/app.db-wal")
        assert main is not None and wal is not None
        assert S._member_opener(str(case), kind, stored, "root", "../../etc/passwd") is None
        got = S.prepared_copy({"open": main, "siblings": {"-wal": wal}, "sha256": want}, str(tmp_path / kind))
        assert got["reused"] is False and got["sha256"] == want
        assert S.prepared_copy({"open": main, "siblings": {"-wal": wal}, "sha256": want},
                               str(tmp_path / kind))["reused"] is True
        assert S.view(got["path"], table="messages", offset="5001")["named_row"]["found"]
        with pytest.raises(S.Refused, match="does not match"):
            S.prepared_copy({"open": main, "siblings": {}, "sha256": "0" * 64}, str(tmp_path / (kind + "-bad")))
    writer.close()
