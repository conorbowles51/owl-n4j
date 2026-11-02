"""Read a captured record body without depending on field order or unique field names (02 section 1.2).

A captured element is ``[tag, attrs, text, children]`` (01 section 5.3); a nested record inside a body is the
marker ``["@", ordinal]``, a file ``["@f", ordinal]`` and an extra info ``["@x", ordinal]``. A record body is its
``model`` element. ``fields(body)`` yields one ``FieldView`` per field element directly under the model, in
document order, for all six field kinds, with its values (``value`` children, and ``empty`` children as values
with ``is_empty``) and the ordinals of nested records. Nothing here knows a type or field name.

``body_path`` is the dotted child-index path from the model element, the same path 01 writes on
``phone_timestamps.body_path`` (``evidence-engine/app/phone/timestamps.py``), so a value and its parsed time
join on (record, ``body_path``).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Iterator

FIELD_KINDS = ("field", "multiField", "modelField", "multiModelField", "nodeField", "dataField")
MODEL_FIELD_KINDS = ("modelField", "multiModelField")
BASIC_TYPES = ("String", "TimeStamp", "TimeSpan", "Guid", "Boolean", "Int32", "Int64", "Double", "UInt32")
RECORD_MARK, FILE_MARK, EXTRA_MARK = "@", "@f", "@x"


@dataclass(frozen=True)
class ValueView:
    index: int            # position among this field's values and empties
    type: str | None      # the value's ``type`` attribute; None for ``<empty/>``
    text: str | None
    attrs: dict
    is_empty: bool
    body_path: str


@dataclass(frozen=True)
class FieldView:
    name: str | None
    kind: str
    position: int         # index of the field among the model's children
    body_path: str
    attrs: dict
    values: list = dc_field(default_factory=list)
    children: list = dc_field(default_factory=list)   # ordinals of nested records (``["@", n]``)
    files: list = dc_field(default_factory=list)      # ordinals of nested file rows (``["@f", n]``)
    other: list = dc_field(default_factory=list)      # any other child element, kept as captured

    @property
    def real_values(self):
        return [v for v in self.values if not v.is_empty]

    @property
    def value_types(self):
        return sorted({v.type or "(none)" for v in self.real_values})


def is_marker(node) -> bool:
    return (isinstance(node, list) and len(node) == 2 and isinstance(node[0], str) and node[0][:1] == "@"
            and isinstance(node[1], int))


def model_attrs(body) -> dict:
    return dict(body[1] or {}) if body else {}


def model_type(body) -> str | None:
    return model_attrs(body).get("type")


def _join(prefix: str, i: int) -> str:
    return "%s.%d" % (prefix, i) if prefix else str(i)


def fields(body) -> Iterator[FieldView]:
    """Every field element directly under the model, in order."""
    for i, el in enumerate(body[3] or ()):
        if is_marker(el) or not isinstance(el, list) or el[0] not in FIELD_KINDS:
            continue
        path = str(i)
        attrs = dict(el[1] or {})
        values, children, files, other = [], [], [], []
        vi = 0
        for j, c in enumerate(el[3] or ()):
            if is_marker(c):
                if c[0] == RECORD_MARK:
                    children.append(c[1])
                elif c[0] == FILE_MARK:
                    files.append(c[1])
                else:
                    other.append(c)
                continue
            if not isinstance(c, list):
                continue
            if c[0] == "value":
                a = dict(c[1] or {})
                values.append(ValueView(vi, a.get("type"), c[2], a, False, _join(path, j)))
                vi += 1
            elif c[0] == "empty":
                values.append(ValueView(vi, None, None, dict(c[1] or {}), True, _join(path, j)))
                vi += 1
            else:
                other.append(c)
        yield FieldView(attrs.get("name"), el[0], i, path, attrs, values, children, files, other)


def field_map(body) -> dict:
    """name -> list of FieldView (a name can repeat inside one record: C8 has 38 such records)."""
    out: dict = {}
    for f in fields(body):
        out.setdefault(f.name, []).append(f)
    return out


def first_value(body, name: str, kinds=("field", "multiField")) -> ValueView | None:
    for f in fields(body):
        if f.name == name and f.kind in kinds:
            for v in f.real_values:
                return v
    return None


def first_text(body, name: str) -> str | None:
    v = first_value(body, name)
    return v.text if v is not None else None


def count(body) -> dict:
    """Fields, values and empties of one body (02-U1's reconciliation measure)."""
    n_f = n_v = n_e = 0
    for f in fields(body):
        n_f += 1
        for v in f.values:
            if v.is_empty:
                n_e += 1
            else:
                n_v += 1
    return {"fields": n_f, "values": n_v, "empties": n_e}
