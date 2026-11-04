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
    out = S.view(copy["path"], table="messages", offset=_at(copy["path"], b"synthetic 9"), browse="messages", page_no=3)
    assert out["open_mode"] == "read-only, write-ahead log read"
    assert [t["row_count"] for t in out["tables"] if t["name"] == "messages"] == [1202]
    assert out["page"]["rows"][-1][2] == "only in log"
    assert out["named_row"]["found"] and out["named_row"]["log_note"].startswith("This file has a write-ahead log")
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


def _at(path, needle: bytes, nth: int = 0) -> str:
    """The byte position of a field's bytes in the file, as a report gives it."""
    data, i = open(path, "rb").read(), -1
    for _ in range(nth + 1):
        i = data.index(needle, i + 1)
    return str(i)


def test_the_row_at_the_reports_byte_position_and_each_reason_it_cannot_be_shown(tmp_path):
    src = str(tmp_path / "app.db")
    _db(src)
    w = sqlite3.connect(src)
    w.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
    w.execute("INSERT INTO notes VALUES (1, ?)", ("synthetic long note " + "x" * 9000,))  # overflows its page
    w.execute("INSERT INTO notes VALUES (2, 'synthetic gone')")
    w.commit()
    w.execute("PRAGMA secure_delete = OFF")
    w.execute("DELETE FROM notes WHERE id = 2")  # its bytes stay in the page's unused space
    w.commit()
    w.close()
    with S.open_read_only(src) as c:
        # 1,200 rows: a b-tree with interior pages; the position is inside row 777's body text
        ok = S.named_row(c, src, "messages", _at(src, b"synthetic 777"))
        assert ok["found"] and ok["table"] == "messages" and ok["rowid"] == 777
        assert ok["values"][1:3] == [777, "synthetic 777"] and "note" not in ok
        # a record built from several tables: the report lists them, comma-separated; the row is in one of them
        listed = S.named_row(c, src, "messages, settings", _at(src, b"synthetic 777"))
        assert listed["found"] and listed["table"] == "messages" and "note" not in listed
        assert ok["position"]["byte_in_row"] > 0 and ok["bytes_at_position"]["hex_preview"].startswith(b"synthetic 777".hex())
        # the report names another table: the row is shown with the table that holds it
        other = S.named_row(c, src, "notes", _at(src, b"synthetic 120"))
        assert other["found"] and other["table"] == "messages"
        assert other["note"] == "The report names table notes; the row at its position is in table messages."
        assert S.named_row(c, src, None, _at(src, b"synthetic 5"))["note"].endswith("the row there is in table messages.")
        # a row whose text continues on overflow pages: the position in its first part finds it
        assert S.named_row(c, src, "notes", _at(src, b"synthetic long note"))["rowid"] == 1
        gone = S.named_row(c, src, "notes", _at(src, b"synthetic gone"))
        assert not gone["found"] and gone["reason"].startswith("The report's position is in unused space of this file")
        assert gone["bytes_at_position"]["hex_preview"].startswith(b"synthetic gone".hex())
        size = os.path.getsize(src)
        assert S.named_row(c, src, "messages", str(size + 10))["reason"] == "The report's position is beyond the end of this file."
        assert S.named_row(c, src, "messages", "0x1f")["reason"] == "The report's position for this record is not a byte position."
        assert S.named_row(c, src, "messages", None)["reason"] == "The report does not say which row this record came from."
        assert S.named_row(c, src, "messages", "40")["reason"] == "The report's position is not inside a table row of this file."


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
        assert S.view(got["path"], table="messages", offset=_at(got["path"], b"synthetic 42"))["named_row"]["rowid"] == 42
        with pytest.raises(S.Refused, match="does not match"):
            S.prepared_copy({"open": main, "siblings": {}, "sha256": "0" * 64}, str(tmp_path / (kind + "-bad")))
    writer.close()
