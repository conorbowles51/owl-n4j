"""Independent element-level counter on expat (01 decision D4: the counter uses lxml, the cross-check and
the capture use expat). Same measures and definitions as `counter.py` (see `counts.py`), computed from
expat's callbacks with no tree at all, so the two parsers check each other.

CLI (prints totals only, never content): python3 -m app.phone.counter_expat <xml> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import sys
from xml.parsers import expat

from app.phone.counts import CountSink

CHUNK = 1 << 20
SEP = "\x1f"  # namespace separator: names arrive as "uri<SEP>local"


def _local(name: str) -> str:
    return name.rsplit(SEP, 1)[-1]


def count_stream(fh) -> dict:
    sink = CountSink()
    # per open element: [text parts before the first child, had an element child, path of the last
    #                    closed child (None: the element itself), tail parts after it, text closed]
    levels = []

    def flush_tail(level):
        lv = levels[level]
        if lv[3]:
            target = lv[2] if lv[2] is not None else sink.stack[level][0]
            sink.tail(target, "".join(lv[3]))
        lv[2] = None
        lv[3] = []

    def start(name, attrs):
        if levels:
            flush_tail(len(levels) - 1)
            levels[-1][1] = True
            levels[-1][4] = True
        a = {}
        for k, v in attrs.items():
            a.setdefault(_local(k), []).append(v)
        sink.open(_local(name), a)
        levels.append([[], False, None, [], False])

    def end(name):
        flush_tail(len(levels) - 1)
        lv = levels.pop()
        path = sink.stack[-1][0]
        sink.close("".join(lv[0]) if lv[0] else None, not lv[1])
        if levels:
            levels[-1][2] = path
            levels[-1][3] = []

    def chars(data):
        if not levels:
            return
        lv = levels[-1]
        (lv[3] if lv[4] else lv[0]).append(data)

    def node(kind):
        # lxml's .text stops at a comment or processing instruction; what follows is that node's tail,
        # which counts as mixed content of the enclosing element
        if kind == "comment":
            sink.comments += 1
        else:
            sink.pis += 1
        if levels:
            flush_tail(len(levels) - 1)
            levels[-1][4] = True

    p = expat.ParserCreate(namespace_separator=SEP)
    p.buffer_text = True
    p.buffer_size = CHUNK
    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chars
    p.CommentHandler = lambda _d: node("comment")
    p.ProcessingInstructionHandler = lambda _t, _d: node("pi")
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    nbytes = 0
    error = None
    try:
        while True:
            b = fh.read(CHUNK)
            if not b:
                break
            sha.update(b)
            md5.update(b)
            nbytes += len(b)
            p.Parse(b, False)
        p.Parse(b"", True)
    except expat.ExpatError as e:
        error = {"line": e.lineno, "column": e.offset, "message": expat.ErrorString(e.code),
                 "open_path": sink.open_path()}
        while True:
            b = fh.read(CHUNK)
            if not b:
                break
            sha.update(b)
            md5.update(b)
            nbytes += len(b)
    document = {"sha256": sha.hexdigest(), "md5": md5.hexdigest(), "bytes": nbytes,
                "parser": "expat " + ".".join(map(str, expat.version_info)),
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
