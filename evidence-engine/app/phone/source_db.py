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
MODULE_VERSION = "2"


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


NO_ROW_NAMED = "The report does not say which row this record came from."


def _has_rowid(conn, table) -> bool:
    try:
        run(conn, "SELECT rowid FROM %s LIMIT 0" % _q(table))
        return True
    except Refused:
        return False


def _varint(b: bytes, i: int):
    v = 0
    for k in range(8):
        c = b[i + k]
        v = (v << 7) | (c & 0x7F)
        if c < 0x80:
            return v, i + k + 1
    return (v << 8) | b[i + 8], i + 9


class _Pages:
    """The pages of a database copy, read straight from the copy's bytes (05 section 19: the report's ``offset`` is a
    byte position in the file, measured on P12; SQLite cannot be asked which row holds a byte)."""

    def __init__(self, path):
        self.fh = open(path, "rb")
        head = self.fh.read(100)
        ps = int.from_bytes(head[16:18], "big")
        self.size = 65536 if ps == 1 else ps
        self.usable = self.size - head[20]
        self.count = os.fstat(self.fh.fileno()).st_size // self.size

    def page(self, n: int) -> bytes:  # 1-based, as SQLite numbers pages
        self.fh.seek((n - 1) * self.size)
        return self.fh.read(self.size)

    def bytes_at(self, offset: int, n: int) -> bytes:
        self.fh.seek(offset)
        return self.fh.read(n)

    def close(self):
        self.fh.close()


def _page_header(n: int, data: bytes):
    h = 100 if n == 1 else 0
    kind = data[h]
    cells = int.from_bytes(data[h + 3:h + 5], "big")
    first = h + (12 if kind in (2, 5) else 8)
    ptrs = [int.from_bytes(data[first + 2 * k:first + 2 * k + 2], "big") for k in range(cells)]
    right = int.from_bytes(data[h + 8:h + 12], "big") if kind in (2, 5) else None
    return kind, ptrs, right


def _leaf_cell(data: bytes, start: int, usable: int):
    """``(rowid, end)`` of a table leaf cell: its header, the payload kept on this page and any overflow pointer."""
    p, i = _varint(data, start)
    rowid, j = _varint(data, i)
    x = usable - 35
    if p <= x:
        local, extra = p, 0
    else:
        m = ((usable - 12) * 32 // 255) - 23
        k = m + ((p - m) % (usable - 4))
        local, extra = (k if k <= x else m), 4
    return rowid, j + local + extra


def position(pages: _Pages, offset: int) -> dict:
    """The table row holding byte ``offset`` of the file: its page and rowid, or the reason there is none."""
    n = offset // pages.size + 1
    if offset < 0 or n > pages.count:
        return {"reason": "The report's position is beyond the end of this file."}
    data = pages.page(n)
    kind, ptrs, _ = _page_header(n, data)
    at = offset - (n - 1) * pages.size
    header_end = (100 if n == 1 else 0) + 8 + 2 * len(ptrs)
    if kind != 13 or at < header_end:
        return {"page": n, "reason": "The report's position is not inside a table row of this file."}
    for p in ptrs:
        if p <= at:
            rowid, end = _leaf_cell(data, p, pages.usable)
            if at < end:
                return {"page": n, "rowid": rowid, "byte_in_row": at - p}
    return {"page": n, "reason": "The report's position is in unused space of this file: the row it points to is no "
                                 "longer in any table (for example a deleted record). The bytes there are shown as "
                                 "they are."}


def _leaf_for_rowid(pages: _Pages, root: int, rowid: int):
    """The leaf page a table's b-tree leads to for ``rowid``, walking from its root page (a few page reads)."""
    n = root
    for _ in range(64):
        if not 1 <= n <= pages.count:
            return None
        data = pages.page(n)
        kind, ptrs, right = _page_header(n, data)
        if kind == 13:
            return n
        if kind != 5:
            return None
        nxt = right
        for p in ptrs:  # in key order
            key, _ = _varint(data, p + 4)
            if rowid <= key:
                nxt = int.from_bytes(data[p:p + 4], "big")
                break
        n = nxt
    return None


def _named_tables(table) -> list:
    """The report's ``tableName`` is one table or a comma-separated list of the tables a record was built from
    (measured on P12: "visits, urls"); the position is in a row of one of them."""
    return [t.strip() for t in str(table or "").split(",") if t.strip()]


def _owner(conn, pages: _Pages, page_no: int, rowid: int, named: list):
    """The table whose rows lead to ``page_no`` for ``rowid``: the named tables first, then every other table."""
    _, roots = run(conn, "SELECT name, rootpage FROM sqlite_master WHERE type = 'table' AND rootpage > 0")
    lower = {n.lower() for n in named}
    order = sorted(roots, key=lambda r: (r[0] not in named, (r[0] or "").lower() not in lower, r[0]))
    for name, root in order:
        if _leaf_for_rowid(pages, int(root), rowid) == page_no:
            return name
    return None


def named_row(conn, path: str, table, offset) -> dict:
    """The row at the report's position (a byte position in the file), with the table that holds it. The bytes at the
    position are always returned raw. Says plainly when no live row is there."""
    text_offset = None if offset is None else str(offset).strip()
    if not text_offset:
        return {"found": False, "reason": NO_ROW_NAMED}
    if not text_offset.isdigit():
        return {"found": False, "reason": "The report's position for this record is not a byte position."}
    off = int(text_offset)
    pages = _Pages(path)
    try:
        pos = position(pages, off)
        out = {"found": False, "named_table": table,
               "position": {"byte": off, "page": pos.get("page"), "byte_in_row": pos.get("byte_in_row"),
                            "page_size": pages.size},
               "bytes_at_position": raw(pages.bytes_at(off, BLOB_PREVIEW_BYTES))}
        if "reason" in pos:
            out["reason"] = pos["reason"]
            return out
        names = _named_tables(table)
        owner = _owner(conn, pages, pos["page"], pos["rowid"], names)
    finally:
        pages.close()
    if owner is None:
        out["reason"] = "The report's position is inside a row on page %d, but no table of this file holds that " \
                        "page now." % pos["page"]
        return out
    cols, rows = run(conn, "SELECT rowid AS \"(rowid)\", * FROM %s WHERE rowid = ?" % _q(owner), (pos["rowid"],))
    if not rows:
        out["reason"] = "The row at the report's position could not be read from table %s." % owner
        return out
    out.update(found=True, table=owner, rowid=pos["rowid"], columns=cols, values=[raw(v) for v in rows[0]])
    if names and owner not in names:
        out["note"] = "The report names table %s; the row at its position is in table %s." % (table, owner)
    elif not names:
        out["note"] = "The report gives a position but no table; the row there is in table %s." % owner
    return out


def view(path, table=None, offset=None, browse=None, page_no=1) -> dict:
    """Everything the panel shows for one database copy, timed."""
    t0 = time.monotonic()
    with open_read_only(path) as conn:
        out = {"open_mode": conn.open_mode, "tables": tables(conn),
               "named_row": named_row(conn, path, table, offset) if table or offset else None}
        if out["named_row"] and conn.open_mode != "read-only, immutable":
            out["named_row"]["log_note"] = ("This file has a write-ahead log beside it; the report's position is read "
                                            "in the main file, and the log may hold a newer copy of that page.")
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
