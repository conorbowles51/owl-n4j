"""Shared definitions for the element-level counters (01 section 8).

Both counters (`counter.py` on lxml, `counter_expat.py` on expat) and the later recount from Postgres
(`recount.py`, 01 section 8.2) produce the same structure through `CountSink`, so their outputs can be
compared with `compare()`. Nothing here reads XML.

Definitions, fixed so every implementation computes the same numbers:

- Qualified name (8.1): the local name (namespace removed), plus `[<type>]` for `model` and `modelType`,
  `[<name>]` for `field`, `multiField`, `modelField`, `multiModelField`, `nodeField`, `dataField`, `item`,
  `timestamp`, `jumptargets`, and `[<section>]` for `metadata`. When the naming attribute is absent the
  qualified name is the local name alone. A path is the `/`-joined qualified names from the root down.
- Whitespace is XML whitespace only (space, tab, carriage return, line feed). Text of any other kind,
  including a no-break space, is content.
- An element's text is the character data before its first child (lxml's `.text`). `texts` counts an
  element whose text is non-whitespace, or a leaf (no child element) whose text is non-empty.
- A tail is the character data after an element's end tag and before the next sibling or the parent's end
  tag. `bad_tails` counts tails that are non-whitespace (mixed content; must be 0).
- `attr_hash` and `text_hash` add, modulo 2^64, the first 8 bytes of the BLAKE2b digest (default 64-byte
  digest) of the UTF-8 value, read as a big-endian unsigned integer. Sums are order-independent. They are
  written as 16-digit lowercase hex.
"""
from __future__ import annotations

import hashlib

NAME_ATTR = {
    "model": "type",
    "modelType": "type",
    "field": "name",
    "multiField": "name",
    "modelField": "name",
    "multiModelField": "name",
    "nodeField": "name",
    "dataField": "name",
    "item": "name",
    "timestamp": "name",
    "jumptargets": "name",
    "metadata": "section",
}
FIELD_KINDS = ("field", "multiField", "modelField", "multiModelField", "nodeField", "dataField")
XML_WS = " \t\r\n"
MASK = (1 << 64) - 1
MEASURES = ("elements", "attributes", "attr_hash", "texts", "text_chars", "text_hash", "bad_tails")


def local_name(name: str) -> str:
    """Strip a `{uri}` (ElementTree/lxml) or `uri<sep>` (expat with a separator) namespace prefix."""
    if name.startswith("{"):
        return name.rsplit("}", 1)[-1]
    return name


def qualified(local: str, attrs_by_local: dict) -> str:
    key = NAME_ATTR.get(local)
    if key is None:
        return local
    v = attrs_by_local.get(key)
    if v is None:
        return local
    return "%s[%s]" % (local, v)


def h64(value: str) -> int:
    return int.from_bytes(hashlib.blake2b(value.encode("utf-8", "surrogatepass")).digest()[:8], "big")


def is_ws(text: str) -> bool:
    return not text.strip(XML_WS)


class _PathCounts:
    __slots__ = ("elements", "attributes", "attr_hash", "texts", "text_chars", "text_hash", "bad_tails")

    def __init__(self):
        self.elements = 0
        self.attributes = {}
        self.attr_hash = {}
        self.texts = 0
        self.text_chars = 0
        self.text_hash = 0
        self.bad_tails = 0


class CountSink:
    """Accumulates the 8.2 measures. Callers report elements as they open and close."""

    def __init__(self):
        self.paths = {}
        self.stack = []  # (path, local name, parent local name)
        self.elements = 0
        self.attributes = 0
        self.texts = 0
        self.nonws_texts = 0
        self.ws_only_texts = 0
        self.text_chars = 0
        self.text_bytes = 0
        self.longest_text = 0
        self.bad_tails = 0
        self.comments = 0
        self.pis = 0
        self.max_depth = 0
        self.models_top = 0
        self.models_nested = 0
        self.values = 0
        self.tagged_files = 0
        self.root_attrs = {}

    def open(self, local: str, attrs: dict) -> None:
        """`attrs`: local attribute name -> list of values (a name may occur twice under two namespaces)."""
        first = {k: v[0] for k, v in attrs.items()}
        q = qualified(local, first)
        parent = self.stack[-1] if self.stack else None
        path = parent[0] + "/" + q if parent else q
        parent_local = parent[1] if parent else None
        if not self.stack:
            self.root_attrs = {k: v[0] for k, v in attrs.items()
                               if k in ("reportVersion", "extractionType", "NodeCount", "ModelCount")}
        self.stack.append((path, local, parent_local))
        if len(self.stack) > self.max_depth:
            self.max_depth = len(self.stack)
        pc = self.paths.get(path)
        if pc is None:
            pc = self.paths[path] = _PathCounts()
        pc.elements += 1
        self.elements += 1
        for name, values in attrs.items():
            for v in values:
                pc.attributes[name] = pc.attributes.get(name, 0) + 1
                pc.attr_hash[name] = (pc.attr_hash.get(name, 0) + h64(v)) & MASK
                self.attributes += 1
        if local == "model":
            if parent_local == "modelType":
                self.models_top += 1
            elif parent_local in FIELD_KINDS:
                self.models_nested += 1
        elif local == "value":
            self.values += 1
        elif local == "file" and parent_local == "taggedFiles":
            self.tagged_files += 1

    def close(self, text, is_leaf: bool) -> None:
        path = self.stack.pop()[0]
        if not text:
            return
        ws = is_ws(text)
        if ws:
            self.ws_only_texts += 1
        else:
            self.nonws_texts += 1
        if ws and not is_leaf:
            return
        pc = self.paths[path]
        n = len(text)
        pc.texts += 1
        pc.text_chars += n
        pc.text_hash = (pc.text_hash + h64(text)) & MASK
        self.texts += 1
        self.text_chars += n
        self.text_bytes += len(text.encode("utf-8", "surrogatepass"))
        if n > self.longest_text:
            self.longest_text = n

    def tail(self, path: str, text) -> None:
        """A tail of an element at `path`; counted only when non-whitespace."""
        if text and not is_ws(text):
            self.paths[path].bad_tails += 1
            self.bad_tails += 1

    def open_path(self):
        return self.stack[-1][0] if self.stack else None

    def result(self, document: dict) -> dict:
        paths = {}
        for p in sorted(self.paths):
            c = self.paths[p]
            paths[p] = {
                "elements": c.elements,
                "attributes": dict(sorted(c.attributes.items())),
                "attr_hash": {k: "%016x" % v for k, v in sorted(c.attr_hash.items())},
                "texts": c.texts,
                "text_chars": c.text_chars,
                "text_hash": "%016x" % c.text_hash,
                "bad_tails": c.bad_tails,
            }
        return {
            "counter_version": "phone-counter-1",
            "document": document,
            "totals": {
                "elements": self.elements,
                "attributes": self.attributes,
                "texts": self.texts,
                "nonws_texts": self.nonws_texts,
                "ws_only_texts": self.ws_only_texts,
                "text_chars": self.text_chars,
                "text_bytes": self.text_bytes,
                "longest_text_chars": self.longest_text,
                "bad_tails": self.bad_tails,
                "comments": self.comments,
                "processing_instructions": self.pis,
                "max_depth": self.max_depth,
                "distinct_paths": len(self.paths),
                "distinct_path_attributes": sum(len(c.attributes) for c in self.paths.values()),
                "models_top": self.models_top,
                "models_nested": self.models_nested,
                "values": self.values,
                "tagged_files": self.tagged_files,
            },
            "root_attributes": self.root_attrs,
            "paths": paths,
        }


def compare(source: dict, captured: dict) -> list:
    """Every difference between two counter outputs, in 01 section 8.4's shape, sorted by path.

    A path present on one side only gives one difference per measure that is non-zero on the other side.
    """
    out = []
    a = source["paths"]
    b = captured["paths"]
    for path in sorted(set(a) | set(b)):
        pa = a.get(path)
        pb = b.get(path)
        for m in ("elements", "texts", "text_chars", "text_hash", "bad_tails"):
            va = pa[m] if pa else None
            vb = pb[m] if pb else None
            if va != vb:
                out.append({"path": path, "measure": m, "attribute": None, "source": va, "captured": vb})
        for m in ("attributes", "attr_hash"):
            da = pa[m] if pa else {}
            db = pb[m] if pb else {}
            for name in sorted(set(da) | set(db)):
                if da.get(name) != db.get(name):
                    out.append({"path": path, "measure": m, "attribute": name,
                                "source": da.get(name), "captured": db.get(name)})
    return out


def bad_tail_paths(result: dict) -> list:
    """Paths with non-whitespace tails. Any entry makes reconciliation `differs` (01 section 8.3)."""
    return [p for p, c in result["paths"].items() if c["bad_tails"]]
