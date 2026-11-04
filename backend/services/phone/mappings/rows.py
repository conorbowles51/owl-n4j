"""Row-table mappings: match discipline and evaluation (02 section 6.5b; spec 04 section 3.4).

Rows of one kind match on (type, field) exactly, then every predicate and context item must hold; the most
specific row wins; two rows of equal specificity that could both match one input are refused at load time,
never discovered at run time. No match returns ``None`` (the caller applies 04's ``default_unknown``).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from itertools import product

from services.phone.mappings.loader import LoadError

NUMERIC_OPS = ("lt", "le", "gt", "ge")

# Fields a nested record is matched on from its top-level record when it does not carry them itself (04 decision 22,
# M9 on the 14 server reports): a sensor sample names no device; the sensor record above it does (DeviceName on
# 15,310 of 15,311 sensor records of one report, SourceDeviceType on all 13,125 of another; no Sample carries
# either). A row on the nested type may name these fields; the registry check reads them on the top-level type.
# Only these: a Party or a message never takes its chat's fields (that would move other rows' matches).
INHERITED_FROM_ROOT = {"ActivitySensorDataSample": {"DeviceName": "ActivitySensorData",
                                                    "SourceDeviceType": "ActivitySensorData"}}
NEG_INF, POS_INF = Decimal("-Infinity"), Decimal("Infinity")


def specificity(row) -> int:
    return len(row.get("predicates") or []) + len(row.get("context") or [])


def _key(p):
    return ("field", p["field"]) if p.get("field") is not None else ("context", p["name"])


def _num(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


# ---- static overlap -------------------------------------------------------------------------------------------

def _domain(p):
    """The set of inputs a predicate accepts: ('absent',), ('any',), ('set', frozenset), ('range', lo, lo_in, hi, hi_in)."""
    op, v = p["op"], p.get("value")
    if op == "absent":
        return ("absent",)
    if op == "present":
        return ("any",)
    if op == "contains_any":
        # a free-text field (a device name) holding any of the listed words, compared without case. Its domain is
        # not a finite set, so for the overlap check it counts as any present value (it can never meet `absent`)
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip() for x in v):
            raise LoadError("predicate contains_any needs a list of words, got %r" % (v,))
        return ("any",)
    if op == "eq":
        return ("set", frozenset([_canon(v)]))
    if op == "in":
        return ("set", frozenset(_canon(x) for x in (v or [])))
    n = _num(v)
    if n is None:
        raise LoadError("predicate %s needs a number, got %r" % (op, v))
    return {"lt": ("range", NEG_INF, False, n, False), "le": ("range", NEG_INF, False, n, True),
            "gt": ("range", n, False, POS_INF, False), "ge": ("range", n, True, POS_INF, False)}[op]


def _canon(v):
    if isinstance(v, bool) or v is None:
        return v
    n = _num(v) if isinstance(v, (int, float)) else None
    return n if n is not None else v


def _in_range(x, r):
    n = _num(x) if not isinstance(x, bool) else None
    if n is None:
        return False
    _, lo, lo_in, hi, hi_in = r
    return (n > lo or (lo_in and n == lo)) and (n < hi or (hi_in and n == hi))


def _overlap(a, b) -> bool:
    if a[0] == "absent" or b[0] == "absent":
        return a[0] == b[0]
    if a[0] == "any" or b[0] == "any":
        return True
    if a[0] == "set" and b[0] == "set":
        return bool(a[1] & b[1])
    if a[0] == "set":
        return any(_in_range(x, b) for x in a[1])
    if b[0] == "set":
        return any(_in_range(x, a) for x in b[1])
    lo = max((a[1], a[2]), (b[1], b[2]), key=lambda t: (t[0], not t[1]))
    hi = min((a[3], a[4]), (b[3], b[4]), key=lambda t: (t[0], t[1]))
    return lo[0] < hi[0] or (lo[0] == hi[0] and lo[1] and hi[1])


def could_both_match(r1, r2) -> bool:
    if (r1["type"], r1.get("field")) != (r2["type"], r2.get("field")):
        return False
    c1, c2 = {}, {}
    for p in (r1.get("predicates") or []) + (r1.get("context") or []):
        c1.setdefault(_key(p), []).append(_domain(p))
    for p in (r2.get("predicates") or []) + (r2.get("context") or []):
        c2.setdefault(_key(p), []).append(_domain(p))
    for k in set(c1) & set(c2):
        if not all(_overlap(a, b) for a, b in product(c1[k], c2[k])):
            return False
    return True


def check_static(mapping):
    rows = mapping.body["rows"]
    seen = set()
    for r in rows:
        if r["row_id"] in seen:
            raise LoadError("%s %s: row_id %s appears twice" % (mapping.kind, mapping.name, r["row_id"]))
        seen.add(r["row_id"])
        for p in (r.get("predicates") or []):
            if p.get("field") is None or p.get("name") is not None:
                raise LoadError("%s: a predicate names a field of the record" % r["row_id"])
            _domain(p)
        for p in (r.get("context") or []):
            if p.get("name") is None or p.get("field") is not None:
                raise LoadError("%s: a context item names a computed fact" % r["row_id"])
            if p["name"] not in CONTEXT_NAMES:
                raise LoadError("%s: unknown context name %s" % (r["row_id"], p["name"]))
            _domain(p)
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if specificity(a) == specificity(b) and could_both_match(a, b):
                raise LoadError("%s %s: rows %s and %s could both match one input at equal specificity"
                                % (mapping.kind, mapping.name, a["row_id"], b["row_id"]))


CONTEXT_NAMES = frozenset({"party_role", "party_is_owner", "direction", "container", "platform", "source",
                           "user_mapping", "affiliation", "deleted_state", "decoding_confidence", "offset_state",
                           "semantics"})


# ---- evaluation -----------------------------------------------------------------------------------------------

def _holds(p, facts):
    """``facts``: {"fields": {name: [value texts]}, "context": {name: value}}."""
    if p.get("field") is not None:
        vals = [v for v in (facts.get("fields") or {}).get(p["field"], []) if v is not None and v != ""]
    else:
        ctx = facts.get("context") or {}
        vals = [ctx[p["name"]]] if p["name"] in ctx and ctx[p["name"]] is not None else []
    op = p["op"]
    if op == "absent":
        return not vals
    if op == "present":
        return bool(vals)
    if op == "contains_any":
        words = [w.casefold() for w in p["value"]]
        return any(w in str(v).casefold() for v in vals for w in words)
    d = _domain(p)
    if d[0] == "set":
        return any(_canon(v) in d[1] or (isinstance(v, str) and _num(v) is not None and _num(v) in d[1])
                   for v in vals)
    return any(_in_range(v, d) for v in vals)


def match(rows, type_name, field_name, facts):
    """The winning row of ``rows`` (dicts in the 6.5b shape) or None."""
    best = None
    for r in rows:
        if r["type"] != type_name or r.get("field") != field_name:
            continue
        if all(_holds(p, facts) for p in (r.get("predicates") or []) + (r.get("context") or [])):
            if best is None or specificity(r) > specificity(best):
                best = r
    return best


def evaluate(kind, facts, mappings=None):
    """``facts`` carries ``type`` and ``field`` beside ``fields`` and ``context``. Returns
    ``{"row_id", "outputs", "basis", "reasoning", "would_change", "mapping_version_id"}`` or None."""
    from services.phone.mappings import loader
    ms = loader.loaded() if mappings is None else mappings
    for m in ms:
        if m.kind != kind:
            continue
        r = match(m.body["rows"], facts["type"], facts.get("field"), facts)
        if r is not None:
            outputs = dict(r["outputs"])
            if r["basis"] == "not_established" and kind == "activity_strength":
                outputs = {"class": "unknown", "actor": "unknown", "physical": outputs.get("physical")}
            return {"row_id": r["row_id"], "outputs": outputs, "basis": r["basis"], "reasoning": r["reasoning"],
                    "would_change": r["would_change"], "mapping_version_id": str(m.id), "name": m.name}
    return None
