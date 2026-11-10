"""Single streaming capture pass over one report document (01 section 5, unit 1.3).

The pass parses with the stdlib expat parser (``xml.etree.ElementTree.XMLPullParser``); the reconciliation
counter uses lxml (01 decision D4). Every element, attribute and text is kept, with no list of known tags.

Rows (01 section 6.2):

- every ``model`` element is a record row, unless it sits inside a tagged-file or extraInfo row, where it is
  kept inline in that row's body;
- every ``file`` element inside ``taggedFiles`` is a file row; a ``file`` under another file's
  ``RelatedNodes`` is a file row of its own with ``parent_ordinal`` naming its owner (decision D23);
- every ``extraInfo`` directly under ``extraInfos`` is an extra-info row (decision D24).

Encoding (01 section 5.3): an element is ``[tag, attrs, text, children]``. A nested row inside a row body is
``["@", ordinal]`` (record), ``["@f", ordinal]`` (file) or ``["@x", ordinal]`` (extra info). In the skeleton,
consecutive row children of one element are one span ``["@r"|"@f"|"@x", first_ordinal, last_ordinal]``,
meaning every row of that kind with ``parent_ordinal`` NULL whose ordinal lies in the range, in ordinal order.
An element still open when a truncated document stops gets a fifth item ``{"open": true}``; its text is kept
but, as in the counter, it is not counted (a text is complete only at its end tag).

Writes go to a ``sink`` (``capture_db.CopySink`` in production): ``row(kind, row_dict)``,
``flush_due()``, ``flush(cursor)``. Rows with an ordinal at or below the resume cursor are encoded and not
emitted (01 section 10.5).
"""
from __future__ import annotations

import json
import resource
import xml.etree.ElementTree as ET

PA_NS = "http://pa.cellebrite.com/report/2.0"
CHUNK = 1 << 20
XML_WS = " \t\r\n"
MARK = "\x00mark"
MEMORY_BUDGET_BYTES = 512 * 1024 * 1024
CAPTURE_CODE_VERSION = "phone-capture-1"

RECORD, FILE, EXTRA = "r", "f", "x"
NESTED_MARK = {RECORD: "@", FILE: "@f", EXTRA: "@x"}
SPAN_MARK = {RECORD: "@r", FILE: "@f", EXTRA: "@x"}


class CaptureMemoryBudgetExceeded(RuntimeError):
    message = ("Reading stopped because the report needed more memory than allowed. "
               "Nothing read so far is lost.")


def split_name(name: str):
    if name.startswith("{"):
        ns, local = name[1:].split("}", 1)
        return ns, local
    return None, name


def tag_of(name: str) -> str:
    ns, local = split_name(name)
    if ns is None or ns == PA_NS:
        return local
    return "{%s}%s" % (ns, local)


def attr_key(name: str) -> str:
    ns, local = split_name(name)
    return local if ns is None else "{%s}%s" % (ns, local)


def _is_ws(text: str) -> bool:
    return not text.strip(XML_WS)


def rss_bytes() -> int:
    """The memory this process holds now. ``ru_maxrss`` is the process's high-water mark since it started, and the
    phone worker is a long-lived process: after one large report took it past the budget, every later capture in it
    stopped at its first flush (10 Nov 2026: high-water 541 MB, current 84 MB, a 2,000-record report refused). The
    current figure comes from ``/proc/self/statm``; the high-water mark is the fallback where /proc is absent."""
    try:
        with open("/proc/self/statm") as fh:
            return int(fh.read().split()[1]) * resource.getpagesize()
    except (OSError, ValueError, IndexError):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def encode(el, open_ids=frozenset()):
    """The 01 section 5.3 array for an element whose row children are already marker elements."""
    if el.tag == MARK:
        return json.loads(el.text)
    attrs = {attr_key(k): v for k, v in el.attrib.items()} or None
    children = [encode(c, open_ids) for c in el] or None
    text = el.text
    if text is not None:
        if children is not None and _is_ws(text):
            text = None
    out = [tag_of(el.tag), attrs, text, children]
    if id(el) in open_ids:
        out.append({"open": True})
    return out


def _item_text(file_body, section, name):
    for c in file_body[3] or ():
        if c[0] == "metadata" and (c[1] or {}).get("section") == section:
            for it in c[3] or ():
                if it[0] == "item" and (it[1] or {}).get("name") == name:
                    return it[2]
    return None


def _int_or_none(v):
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


def file_columns(body) -> dict:
    a = body[1] or {}
    return {
        "source_file_id": a.get("id"),
        "local_path": _item_text(body, "File", "Local Path"),
        "declared_size": _int_or_none(a.get("size")),
        "declared_md5": (_item_text(body, "File", "MD5") or None),
        "declared_sha256": (_item_text(body, "File", "SHA256") or None),
        "tags": (_item_text(body, "File", "Tags") or None),
    }


def _index(parent, el):
    for i in range(len(parent) - 1, -1, -1):
        if parent[i] is el:
            return i
    raise ValueError("element not under its parent")


class _Open:
    __slots__ = ("el", "local", "kind", "ordinal", "row_parent")

    def __init__(self, el, local, kind, ordinal, row_parent):
        self.el = el
        self.local = local
        self.kind = kind            # RECORD / FILE / EXTRA when this element is a row, else None
        self.ordinal = ordinal
        self.row_parent = row_parent  # the nearest enclosing open row entry, or None


class Capture:
    """One pass over one document. ``run(stream)`` returns the result dictionary."""

    def __init__(self, sink, cursor=None, on_progress=None, on_flush=None,
                 memory_budget=MEMORY_BUDGET_BYTES):
        self.sink = sink
        cursor = cursor or {}
        self.skip = {RECORD: int(cursor.get("record_ordinal", 0)), FILE: int(cursor.get("file_ordinal", 0)),
                     EXTRA: int(cursor.get("extra_ordinal", 0))}
        self.ordinal = {RECORD: 0, FILE: 0, EXTRA: 0}
        self.emitted = {RECORD: 0, FILE: 0, EXTRA: 0}
        self.on_progress = on_progress
        self.on_flush = on_flush
        self.memory_budget = memory_budget
        self.stack = []
        self.root = None
        self.bytes_read = 0
        self.peak_rss = 0

    # -- row decisions -------------------------------------------------------------------------------
    def _row_kind(self, local):
        parent = self.stack[-1] if self.stack else None
        row_parent = parent.row_parent if parent is not None and parent.kind is None else parent
        if parent is None:
            return None, None
        enclosing = row_parent.kind if row_parent is not None else None
        if local == "model" and enclosing in (None, RECORD):
            return RECORD, row_parent
        if local == "file" and enclosing in (None, FILE) and any(e.local == "taggedFiles" for e in self.stack):
            return FILE, row_parent
        if local == "extraInfo" and enclosing is None and parent.local == "extraInfos":
            return EXTRA, None
        return None, row_parent

    def _start(self, el):
        _, local = split_name(el.tag)
        kind, row_parent = self._row_kind(local)
        ordinal = None
        if kind is not None:
            self.ordinal[kind] += 1
            ordinal = self.ordinal[kind]
        entry = _Open(el, local, kind, ordinal, row_parent)
        self.stack.append(entry)
        if self.root is None:
            self.root = el

    def _record_depth(self, entry):
        depth, top = 0, entry.ordinal
        p = entry.row_parent
        while p is not None and p.kind == RECORD:
            depth += 1
            top = p.ordinal
            p = p.row_parent
        return depth, top

    def _emit(self, entry, body, partial=False):
        kind, ordinal = entry.kind, entry.ordinal
        if ordinal <= self.skip[kind]:
            return
        parent = entry.row_parent.ordinal if entry.row_parent is not None and entry.row_parent.kind == kind else None
        a = body[1] or {}
        if kind == RECORD:
            depth, top = self._record_depth(entry)
            row = {"ordinal": ordinal, "parent_ordinal": parent, "top_ordinal": top, "depth": depth,
                   "model_type": a.get("type") or "", "source_model_id": a.get("id"),
                   "deleted_state": a.get("deleted_state"), "is_partial": partial, "body": body}
        elif kind == FILE:
            row = {"ordinal": ordinal, "parent_ordinal": parent, "is_partial": partial, "body": body}
            row.update(file_columns(body))
        else:
            row = {"ordinal": ordinal, "source_id": a.get("id"), "info_type": a.get("type"),
                   "is_partial": partial, "body": body}
        self.sink.row(kind, row)
        self.emitted[kind] += 1

    def _to_marker(self, entry, parent_entry):
        el = entry.el
        el.clear()
        if parent_entry is not None and (parent_entry.kind is not None or parent_entry.row_parent is not None):
            el.tag = MARK
            el.text = json.dumps([NESTED_MARK[entry.kind], entry.ordinal])
            return
        parent = parent_entry.el
        # the parser runs ahead of the events handled here, so later siblings may already be attached
        idx = _index(parent, el)
        prev = parent[idx - 1] if idx > 0 else None
        if prev is not None and prev.tag == MARK:
            span = json.loads(prev.text)
            if span[0] == SPAN_MARK[entry.kind] and len(span) == 3 and span[2] < entry.ordinal:
                span[2] = entry.ordinal
                prev.text = json.dumps(span)
                parent.remove(el)
                return
        el.tag = MARK
        el.text = json.dumps([SPAN_MARK[entry.kind], entry.ordinal, entry.ordinal])

    def _end(self, el):
        entry = self.stack.pop()
        if entry.kind is None:
            return
        self._emit(entry, encode(el))
        self._to_marker(entry, self.stack[-1] if self.stack else None)

    # -- flushing ------------------------------------------------------------------------------------
    def cursor(self):
        return {"record_ordinal": max(self.skip[RECORD], self._committed(RECORD)),
                "file_ordinal": max(self.skip[FILE], self._committed(FILE)),
                "extra_ordinal": max(self.skip[EXTRA], self._committed(EXTRA))}

    def _committed(self, kind):
        # every row up to the current ordinal of a closed element has been emitted, except rows still open
        open_ords = [e.ordinal for e in self.stack if e.kind == kind]
        return (min(open_ords) - 1) if open_ords else self.ordinal[kind]

    def _maybe_flush(self, force=False):
        if force or self.sink.flush_due():
            self.sink.flush(self.cursor())
            self.peak_rss = max(self.peak_rss, rss_bytes())
            if self.peak_rss > self.memory_budget:
                raise CaptureMemoryBudgetExceeded(CaptureMemoryBudgetExceeded.message)
            if self.on_flush is not None:
                self.on_flush(self)

    # -- the pass ------------------------------------------------------------------------------------
    def run(self, stream) -> dict:
        parser = ET.XMLPullParser(events=("start", "end"))
        error = None
        try:
            while True:
                b = stream.read(CHUNK)
                if not b:
                    break
                self.bytes_read += len(b)
                parser.feed(b)
                self._drain(parser)
                if self.on_progress is not None:
                    self.on_progress(self)
            parser.close()
            self._drain(parser)
        except ET.ParseError as e:
            try:
                self._drain(parser)
            except ET.ParseError:
                pass
            line, column = getattr(e, "position", (None, None))
            error = {"line": line, "column": column, "message": str(e), "bytes_read": self.bytes_read,
                     "open_path": self.open_path()}
        if self.root is None:
            skeleton = None
        elif error is None:
            skeleton = encode(self.root)
        else:
            skeleton = self._finish_partial()
        self._maybe_flush(force=True)
        return {"parse_state": "complete" if error is None else "truncated", "truncation": error,
                "skeleton": skeleton, "root_element": split_name(self.root.tag)[1] if self.root is not None else None,
                "counts": dict(self.ordinal), "emitted": dict(self.emitted), "bytes_read": self.bytes_read,
                "peak_rss": max(self.peak_rss, rss_bytes())}

    def _drain(self, parser):
        for ev, el in parser.read_events():
            if ev == "start":
                self._start(el)
            else:
                self._end(el)
                self._maybe_flush()

    def open_path(self):
        from app.phone.counts import qualified
        parts = []
        for e in self.stack:
            parts.append(qualified(e.local, {split_name(k)[1]: v for k, v in e.el.attrib.items()}))
        return "/".join(parts) or None

    def _finish_partial(self):
        """Truncated: store every open row as a partial row (innermost first) and the open skeleton."""
        open_ids = frozenset(id(e.el) for e in self.stack)
        while self.stack:
            entry = self.stack[-1]
            if entry.kind is not None:
                self._emit(entry, encode(entry.el, open_ids), partial=True)
                self.stack.pop()
                self._to_marker(entry, self.stack[-1] if self.stack else None)
            else:
                self.stack.pop()
        return encode(self.root, open_ids)


def capture_stream(stream, sink, cursor=None, **kw) -> dict:
    return Capture(sink, cursor=cursor, **kw).run(stream)
