"""Element-level counter over a report XML document, on lxml (01 sections 8.1, 8.2; unit 0.2).

One streaming pass over the bytes computes the document's SHA-256 and MD5 and every 8.2 measure per
qualified path. The definitions are in `counts.py`. The independent cross-check is `counter_expat.py`
(01 decision D4); `counts.compare()` lists every difference between two outputs.

Memory stays flat: an element's text and attributes are dropped at its end, and the element is removed
from its parent when the next sibling starts or the parent ends (its tail is complete by then), so only
the open path and one finished child per level are held.

A document that fails to parse (for example a split section cut off mid-element, 01 section 5.6) gives
`parse_state = "truncated"` with the line, column, message and open path; the counts are those of
everything read before the error, and the digests still cover every byte.

CLI (prints totals only, never content): python3 -m app.phone.counter <xml> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import sys

from lxml import etree

from app.phone.counts import CountSink, local_name

CHUNK = 1 << 20

# XML ends every line with a single line feed, CDATA included (XML 1.0 section 2.11). libxml2 2.13 (bundled with
# lxml 5.x) leaves the carriage return of CRLF inside CDATA, so on a report written with CRLF line ends the counter
# reads two characters more than the capture for every such value and the report is wrongly called different
# (seen on a real report: 2 differences). libxml2 2.14 (lxml 6.0.2) is correct. The counter refuses to run on a
# library that gets this wrong rather than report a difference that is not in the report.
_LINE_END_PROBE = b"<a><![CDATA[x\r\ny\r]]></a>"


class ParserDefect(RuntimeError):
    """The installed XML library cannot be used for the reconciliation count."""


def _parser():
    return etree.XMLPullParser(events=("start", "end", "comment", "pi"), huge_tree=True,
                               resolve_entities=False, no_network=True)


def check_parser() -> None:
    """Probe the same push parser the count uses (the whole-document parser is not affected by the defect)."""
    parser = _parser()
    parser.feed(_LINE_END_PROBE)
    parser.close()
    got = next(el.text for ev, el in parser.read_events() if ev == "end")
    if got != "x\ny\n":
        raise ParserDefect(
            "lxml %s with libxml2 %s keeps carriage returns inside CDATA; the counter needs lxml 6.0.2 or later"
            % (".".join(map(str, etree.LXML_VERSION)), ".".join(map(str, etree.LIBXML_VERSION))))


def _attrs(el) -> dict:
    out = {}
    for k, v in el.attrib.items():
        out.setdefault(local_name(k), []).append(v)
    return out


class _Walker:
    def __init__(self, sink: CountSink):
        self.sink = sink
        # per open element: [path of its last closed, not yet flushed element child, had an element child]
        self.levels = []

    def _flush(self, node, level):
        """Count the tail of a finished node under the open element at `level`, then forget it."""
        if isinstance(node.tag, str):
            path = self.levels[level][0]
            self.levels[level][0] = None
            if path is not None:
                self.sink.tail(path, node.tail)
        else:  # a comment or processing instruction: its tail is mixed content of the parent
            self.sink.tail(self.sink.stack[level][0], node.tail)

    def start(self, el):
        if self.levels:
            level = len(self.levels) - 1
            parent = el.getparent()
            prev = el.getprevious()
            while prev is not None:
                before = prev.getprevious()
                self._flush(prev, level)
                parent.remove(prev)
                prev = before
            self.levels[level][1] = True
        self.sink.open(local_name(el.tag), _attrs(el))
        self.levels.append([None, False])

    def end(self, el):
        level = len(self.levels) - 1
        for child in list(el):
            self._flush(child, level)
            el.remove(child)
        had_child = self.levels[level][1]
        path = self.sink.stack[-1][0]
        self.sink.close(el.text, not had_child)
        self.levels.pop()
        if self.levels:
            self.levels[-1][0] = path
        el.text = None
        el.attrib.clear()


def count_stream(fh) -> dict:
    check_parser()
    sink = CountSink()
    walker = _Walker(sink)
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    nbytes = 0
    parser = _parser()

    def drain():
        for ev, el in parser.read_events():
            if ev == "start":
                walker.start(el)
            elif ev == "end":
                walker.end(el)
            elif ev == "comment":
                sink.comments += 1
            else:
                sink.pis += 1

    error = None
    try:
        while True:
            b = fh.read(CHUNK)
            if not b:
                break
            sha.update(b)
            md5.update(b)
            nbytes += len(b)
            parser.feed(b)
            drain()
        parser.close()
        drain()
    except etree.XMLSyntaxError as e:
        try:
            drain()
        except etree.XMLSyntaxError:
            pass
        pos = getattr(e, "position", None) or (None, None)
        error = {"line": pos[0], "column": pos[1], "message": e.msg if hasattr(e, "msg") else str(e),
                 "open_path": sink.open_path()}
        while True:  # the digests cover the whole document
            b = fh.read(CHUNK)
            if not b:
                break
            sha.update(b)
            md5.update(b)
            nbytes += len(b)
    document = {"sha256": sha.hexdigest(), "md5": md5.hexdigest(), "bytes": nbytes,
                "parser": "lxml " + ".".join(map(str, etree.LXML_VERSION)),
                "parse_state": "complete" if error is None else "truncated", "error": error}
    return sink.result(document)


def count_file(path: str) -> dict:
    with open(path, "rb") as fh:
        return count_stream(fh)


def main(argv):
    res = count_file(argv[0])
    with open(argv[1], "w", encoding="utf-8") as out:
        json.dump(res, out, sort_keys=True)
    print(json.dumps({"totals": res["totals"], "parse_state": res["document"]["parse_state"]}))


if __name__ == "__main__":
    main(sys.argv[1:])
