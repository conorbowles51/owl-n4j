"""Read-only view of a phone app database named as a record's source (05 section 17.2, points 3 to 5).

The evidence file is never opened. Its bytes are copied to a scratch folder together with any WAL, shared-memory
or rollback-journal file beside it (listed, never checkpointed), and the copy is opened with
``file:<copy>?mode=ro&immutable=1``, ``PRAGMA query_only = ON``, extension loading off and a 5-second limit on every
statement. Rows come 500 to a page with the table's total stated. Values are shown raw: integers as integers, text
as text, blobs as their length and a hex preview of the first 64 bytes, never decoded. No hex editor, no carving.

Everything returned is what the file holds, read by this module; it is never presented as the report's record.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import time
import urllib.parse
from contextlib import contextmanager

STATEMENT_SECONDS = 5.0
PAGE_ROWS = 500
BLOB_PREVIEW_BYTES = 64
SIBLING_SUFFIXES = ("-wal", "-shm", "-journal")
SQLITE_MAGIC = b"SQLite format 3\x00"
MODULE_VERSION = "1"


class Refused(Exception):
    """A request the opener will not carry out, with the reason in words."""


class TimedOut(Refused):
    pass


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_siblings(open_main, siblings: dict, dest_dir: str, name: str = "source.db") -> dict:
    """Copy the database (``open_main()`` returns a binary reader) and each sibling (``{suffix: opener}``) into
    ``dest_dir``. Returns the copy's path, its SHA-256 and size, and the siblings copied with theirs."""
    os.makedirs(dest_dir, exist_ok=True)
    out = {"path": os.path.join(dest_dir, name), "siblings": []}

    def put(opener, target):
        h, n = hashlib.sha256(), 0
        with opener() as src, open(target, "wb") as dst:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                h.update(chunk)
                n += len(chunk)
                dst.write(chunk)
        os.chmod(target, 0o400)
        return h.hexdigest(), n

    out["sha256"], out["size"] = put(open_main, out["path"])
    for suffix in SIBLING_SUFFIXES:
        if suffix in siblings:
            sha, size = put(siblings[suffix], out["path"] + suffix)
            out["siblings"].append({"suffix": suffix, "sha256": sha, "size": size})
    return out


_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
_ALLOWED_PRAGMAS = {"table_info", "table_xinfo", "index_list", "index_info", "foreign_key_list"}


def _authorize(action, arg1, arg2, dbname, source):
    """Only reads: every write, schema change, ATTACH, transaction or PRAGMA outside a short read list is denied."""
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() in _ALLOWED_PRAGMAS and arg2 is None:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class _Conn(sqlite3.Connection):
    stmt_seconds = STATEMENT_SECONDS
    open_mode = ""


def has_wal(path) -> bool:
    w = str(path) + "-wal"
    return os.path.isfile(w) and os.path.getsize(w) > 0


@contextmanager
def open_read_only(path, seconds: float = STATEMENT_SECONDS):
    """A connection to a copy that cannot write, attach, load extensions or run past ``seconds`` per statement.

    ``immutable=1`` unless a non-empty write-ahead log was copied beside it: measured on SQLite 3.46, ``immutable``
    skips the log, so rows held only there would be hidden. Then the copy is opened ``mode=ro`` alone, which reads
    the log without checkpointing it (a read-only connection cannot); the copy's database and log bytes were
    measured unchanged, and SQLite adds a shared-memory file in the scratch folder only (05 section 19, J-1)."""
    with open(path, "rb") as fh:
        if fh.read(16) != SQLITE_MAGIC:
            raise Refused("This file is not an SQLite database.")
    wal = has_wal(path)
    uri = "file:%s?mode=ro%s" % (urllib.parse.quote(os.path.abspath(path)), "" if wal else "&immutable=1")
    conn = sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False, factory=_Conn)
    try:
        if hasattr(conn, "enable_load_extension"):
            conn.enable_load_extension(False)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA trusted_schema = OFF")
        conn.set_authorizer(_authorize)
        conn.text_factory = lambda b: b.decode("utf-8", "replace")
        conn.stmt_seconds = seconds
        conn.open_mode = "read-only, write-ahead log read" if wal else "read-only, immutable"
        yield conn
    finally:
        conn.close()


def run(conn, sql: str, params=(), *, max_rows=None):
    """Run one statement under the time limit. A statement that writes is refused before it runs."""
    seconds = getattr(conn, "stmt_seconds", STATEMENT_SECONDS)
    deadline = time.monotonic() + seconds
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall() if max_rows is None else cur.fetchmany(max_rows)
        return [d[0] for d in (cur.description or ())], rows
    except sqlite3.DatabaseError as exc:
        if "interrupted" in str(exc):
            raise TimedOut("Stopped after %g seconds: the statement took longer than the limit." % seconds) from None
        if any(k in str(exc) for k in ("readonly", "query_only", "attempt to write", "not authorized", "authorization denied")):
            raise Refused("Refused: this view only reads; the database copy cannot be changed.") from None
        raise Refused("The database could not answer: %s" % exc) from None
    finally:
        conn.set_progress_handler(None, 0)


def raw(value):
    """A value as stored: integers stay integers; blobs are length plus a hex preview, never decoded."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        b = bytes(value)
        return {"blob_bytes": len(b), "hex_preview": b[:BLOB_PREVIEW_BYTES].hex(),
                "preview_complete": len(b) <= BLOB_PREVIEW_BYTES}
    return value


def _q(name: str) -> str:
    return '"%s"' % name.replace('"', '""')


def tables(conn) -> list:
    """Every table and view with its schema and row count (a count past the limit says so)."""
    _, rows = run(conn, "SELECT type, name, sql FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name")
    out = []
    for kind, name, sql in rows:
        item = {"name": name, "type": kind, "schema": sql, "row_count": None, "count_note": None}
        try:
            _, n = run(conn, "SELECT count(*) FROM %s" % _q(name))
            item["row_count"] = n[0][0]
        except Refused as exc:
            item["count_note"] = str(exc)
        out.append(item)
    return out


def _table_names(conn):
    return {n for (n,) in run(conn, "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")[1]}


def page(conn, table: str, page_no: int = 1) -> dict:
    """One page of a table, 500 rows, in rowid order where the table has one, with the total stated."""
    if table not in _table_names(conn):
        raise Refused("This database has no table of that name.")
    page_no = max(1, int(page_no))
    _, total = run(conn, "SELECT count(*) FROM %s" % _q(table))
    has_rowid = _has_rowid(conn, table)
    sel = ("SELECT rowid AS \"(rowid)\", * FROM %s ORDER BY rowid" if has_rowid else "SELECT * FROM %s") % _q(table)
    cols, rows = run(conn, sel + " LIMIT ? OFFSET ?", (PAGE_ROWS, (page_no - 1) * PAGE_ROWS))
    return {"table": table, "total": total[0][0], "page": page_no, "page_rows": PAGE_ROWS, "columns": cols,
            "rows": [[raw(v) for v in r] for r in rows]}


def _has_rowid(conn, table) -> bool:
    try:
        run(conn, "SELECT rowid FROM %s LIMIT 0" % _q(table))
        return True
    except Refused:
        return False


def named_row(conn, table: str, offset) -> dict:
    """The row the report names by table and offset, read as that table's rowid. Says plainly when it cannot."""
    if not table:
        return {"found": False, "reason": "The report does not say which row this record came from."}
    if table not in _table_names(conn):
        return {"found": False, "reason": "The report names a table this database does not have."}
    try:
        rowid = int(str(offset).strip())
    except (TypeError, ValueError):
        return {"found": False, "reason": "The report's position for this record is not a row number."}
    if not _has_rowid(conn, table):
        return {"found": False, "reason": "This table has no row numbers, so the report's position cannot be read."}
    cols, rows = run(conn, "SELECT rowid AS \"(rowid)\", * FROM %s WHERE rowid = ?" % _q(table), (rowid,))
    if not rows:
        return {"found": False, "rowid": rowid,
                "reason": "No row of this table has the row number the report gives (%d)." % rowid}
    return {"found": True, "rowid": rowid, "columns": cols, "values": [raw(v) for v in rows[0]]}


def view(path, table=None, offset=None, browse=None, page_no=1) -> dict:
    """Everything the panel shows for one database copy, timed."""
    t0 = time.monotonic()
    with open_read_only(path) as conn:
        out = {"open_mode": conn.open_mode, "tables": tables(conn), "named_row": named_row(conn, table, offset) if table or offset else None}
        if browse:
            out["page"] = page(conn, browse, page_no)
    out["open_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return out


def clear_old(scratch_root: str, max_age_s: float = 3600.0) -> int:
    """Remove copies older than ``max_age_s`` (the scratch area is not a store). Returns folders removed."""
    if not os.path.isdir(scratch_root):
        return 0
    n, now = 0, time.time()
    for d in os.listdir(scratch_root):
        p = os.path.join(scratch_root, d)
        if os.path.isdir(p) and now - os.path.getmtime(p) > max_age_s:
            for root, dirs, files in os.walk(p):
                for f in files:
                    os.chmod(os.path.join(root, f), 0o600)
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n


# --- locating a captured file's bytes (folder or archive member) and the scratch copy -----------------------------

def _member_opener(case_root, kind, stored_path, root_path, relpath):
    """An opener for one file of a container, or None when the container does not hold it."""
    import posixpath
    import zipfile
    rel = posixpath.normpath(posixpath.join(root_path or "", relpath)).lstrip("/")
    if rel.startswith(".."):
        return None
    base = os.path.realpath(case_root)
    if kind == "folder":
        p = os.path.realpath(os.path.join(base, stored_path, rel))
        if not p.startswith(base + os.sep) or not os.path.isfile(p):
            return None
        return lambda: open(p, "rb")
    if kind in ("zip", "ufdr"):
        z = os.path.realpath(os.path.join(base, stored_path))
        if not z.startswith(base + os.sep) or not os.path.isfile(z):
            return None
        with zipfile.ZipFile(z) as zf:
            try:
                info = zf.getinfo(rel)
            except KeyError:
                return None

        class _Member:
            def __enter__(self):
                self.zf = zipfile.ZipFile(z)
                self.fh = self.zf.open(info)
                return self.fh

            def __exit__(self, *a):
                self.fh.close()
                self.zf.close()
        return _Member
    return None


def locate(conn, case_root, case_id, extraction_id, document_index, ordinal) -> dict:
    """The file's row and openers for it and its siblings. Refuses a file that is not a verified Database file."""
    row = conn.execute(
        "SELECT f.disk_relpath, f.tags, f.outcome, f.disk_sha256, f.disk_size, e.case_id FROM phone_files f JOIN "
        "phone_extractions e ON e.id = f.extraction_id WHERE f.extraction_id = %s AND f.document_index = %s AND "
        "f.ordinal = %s", (str(extraction_id), int(document_index), int(ordinal))).fetchone()
    if row is None or str(row[5]) != str(case_id):
        raise Refused("This file is not in this case.")
    relpath, tags, outcome, sha, size, _ = row
    if "Database" not in [t.strip() for t in (tags or "").split(",")]:
        raise Refused("The report does not tag this file as a database.")
    if outcome != "match" or not relpath:
        raise Refused("Only a file present in the production whose hash matches the report is opened.")
    conts = conn.execute(
        "SELECT c.container_kind, c.stored_path, l.root_path FROM phone_extraction_container_links l JOIN "
        "phone_extraction_containers c ON c.id = l.container_id WHERE l.extraction_id = %s ORDER BY l.linked_at, c.id",
        (str(extraction_id),)).fetchall()
    for kind, stored, root in conts:
        main = _member_opener(case_root, kind, stored, root, relpath)
        if main is None:
            continue
        sib = {}
        for suffix in SIBLING_SUFFIXES:
            o = _member_opener(case_root, kind, stored, root, relpath + suffix)
            if o is not None:
                sib[suffix] = o
        return {"open": main, "siblings": sib, "sha256": sha, "size": size}
    raise Refused("The container holding this file is not on disk.")


def prepared_copy(located: dict, scratch_root: str) -> dict:
    """A scratch copy of a verified file and its siblings, made once per content and reused; its SHA-256 must equal
    the capture's, or nothing is opened."""
    import json
    key = hashlib.sha256((located["sha256"] or "").encode() + b"|" +
                         ",".join(sorted(located["siblings"])).encode()).hexdigest()[:32]
    dest = os.path.join(scratch_root, key)
    marker = os.path.join(dest, "copy.json")
    if os.path.isfile(marker):
        os.utime(dest)
        with open(marker) as fh:
            return dict(json.load(fh), reused=True)
    tmp = dest + ".part-%d" % os.getpid()
    shutil.rmtree(tmp, ignore_errors=True)
    t0 = time.monotonic()
    info = copy_with_siblings(located["open"], located["siblings"], tmp)
    if located["sha256"] and info["sha256"] != located["sha256"]:
        shutil.rmtree(tmp, ignore_errors=True)
        raise Refused("The copy does not match the file's checked fingerprint, so it was not opened.")
    info["copy_ms"] = round((time.monotonic() - t0) * 1000, 1)
    try:
        os.rename(tmp, dest)
    except OSError:  # another request made it first
        shutil.rmtree(tmp, ignore_errors=True)
        with open(marker) as fh:
            return dict(json.load(fh), reused=True)
    info["path"] = os.path.join(dest, "source.db")
    with open(marker, "w") as fh:
        json.dump(info, fh)
    return dict(info, reused=False)
