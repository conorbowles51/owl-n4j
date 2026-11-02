"""Recount a captured document from what was stored (01 section 8.2), never reading the XML.

Streams the document's skeleton, records, files and extra infos back in ordinal order, rejoins them through the
capture's markers (``capture.py``: nested ``["@"|"@f"|"@x", ordinal]`` inside a body, spans
``["@r"|"@f"|"@x", first, last]`` in the skeleton) and computes the counter's measures with the same
``CountSink``. It also counts the rows it consumed: a stored row no marker reaches would be invisible to the
measures, so ``rows_unreached`` is reported and reconciliation treats any as a difference.

Rows come from ``DbRows`` (Postgres, server-side cursors) or ``MemoryRows`` (unit tests).
"""
from __future__ import annotations

from app.phone.counts import CountSink, local_name

TABLE = {"r": "phone_records", "f": "phone_files", "x": "phone_extra_infos"}
SPAN = {"@r": "r", "@f": "f", "@x": "x"}
NESTED = {"@": "r", "@f": "f", "@x": "x"}
ROW_KIND = {"model": "r", "file": "f", "extraInfo": "x"}
ITERSIZE = 2000


def _attrs(attrs):
    out = {}
    for k, v in (attrs or {}).items():
        out.setdefault(local_name(k), []).append(v)
    return out


def is_marker(node) -> bool:
    return (isinstance(node, list) and len(node) in (2, 3) and isinstance(node[0], str) and node[0][:1] == "@"
            and all(isinstance(x, int) for x in node[1:]))


class DbRows:
    def __init__(self, conn, extraction_id, document_index):
        self.conn = conn
        self.key = (extraction_id, document_index)
        self.n = 0

    def skeleton(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT skeleton, parse_state FROM phone_extraction_documents WHERE extraction_id = %s "
                        "AND document_index = %s", self.key)
            return cur.fetchone()

    def stored(self):
        out = {}
        with self.conn.cursor() as cur:
            for kind, table in TABLE.items():
                cur.execute("SELECT count(*) FROM %s WHERE extraction_id = %%s AND document_index = %%s" % table,
                            self.key)
                out[kind] = cur.fetchone()[0]
        return out

    def iter_from(self, kind, first):
        parent = "parent_ordinal" if kind != "x" else "NULL::integer"
        self.n += 1
        cur = self.conn.cursor(name="recount_%s_%d" % (kind, self.n))
        cur.itersize = ITERSIZE
        try:
            cur.execute("SELECT ordinal, %s, body FROM %s WHERE extraction_id = %%s AND document_index = %%s AND "
                        "ordinal >= %%s ORDER BY ordinal" % (parent, TABLE[kind]), self.key + (first,))
            for row in cur:
                yield row
        finally:
            cur.close()


class MemoryRows:
    """``rows[kind][ordinal] = (parent_ordinal, body)``."""

    def __init__(self, skeleton, rows, parse_state="complete"):
        self._skeleton = skeleton
        self.rows = rows
        self.parse_state = parse_state

    def skeleton(self):
        return self._skeleton, self.parse_state

    def stored(self):
        return {k: len(self.rows.get(k, {})) for k in TABLE}

    def iter_from(self, kind, first):
        for o in sorted(o for o in self.rows.get(kind, {}) if o >= first):
            parent, body = self.rows[kind][o]
            yield o, parent, body


class Recount:
    def __init__(self, rows, on_progress=None):
        self.rows = rows
        self.sink = CountSink()
        self.consumed = {"r": 0, "f": 0, "x": 0}
        self.unreached_nested = 0
        self.on_progress = on_progress
        self.stored = {"r": 0, "f": 0, "x": 0}

    def walk(self, node, group):
        if is_marker(node):
            if len(node) == 2:
                kind = NESTED[node[0]]
                body = group[kind].pop(node[1], None)
                if body is None:
                    raise ValueError("a marker names row %s%d, which is not stored" % (kind, node[1]))
                self.consumed[kind] += 1
                self.walk(body, group)
            else:
                self._span(SPAN[node[0]], node[1], node[2])
            return
        tag, attrs, text, children = node[0], node[1], node[2], node[3]
        is_open = len(node) > 4 and bool((node[4] or {}).get("open"))
        self.sink.open(local_name(tag), _attrs(attrs))
        for c in children or ():
            self.walk(c, group)
        self.sink.close(None if is_open else text, children is None)

    def _span(self, kind, first, last):
        top = None
        group = {"r": {}, "f": {}, "x": {}}
        for ordinal, parent, body in self.rows.iter_from(kind, first):
            if parent is None:
                if top is not None:
                    self._walk_top(top, group)
                    group = {"r": {}, "f": {}, "x": {}}
                    top = None
                if ordinal > last:
                    break
                top = body
            else:
                group[kind][ordinal] = body
        if top is not None:
            self._walk_top(top, group)

    def _walk_top(self, body, group):
        self.consumed[ROW_KIND[local_name(body[0])]] += 1
        self.walk(body, group)
        self.unreached_nested += sum(len(v) for v in group.values())
        if self.on_progress is not None:
            self.on_progress(self)

    def run(self) -> dict:
        skeleton, parse_state = self.rows.skeleton()
        stored = self.rows.stored()
        self.stored = stored
        if skeleton is not None:
            self.walk(skeleton, {"r": {}, "f": {}, "x": {}})
        res = self.sink.result({"source": "capture", "parse_state": parse_state})
        res["rows"] = {"stored": stored, "consumed": dict(self.consumed)}
        res["rows_unreached"] = sum(stored.values()) - sum(self.consumed.values())
        return res


def recount_document(conn, extraction_id, document_index, on_progress=None) -> dict:
    with conn.transaction():  # server-side cursors need one; the connection runs in autocommit
        return Recount(DbRows(conn, extraction_id, document_index), on_progress).run()
