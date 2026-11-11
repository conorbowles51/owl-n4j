"""A failed tool call answered in words that say how to make the call work (lx-agentfit R2, item T).

Measured 11 Nov 2026 over 81 recorded runs: 25 of 134 hand-written graph queries were refused, 13 of them for a list
or map expression, while the agent's system prompt said WITH and UNWIND were allowed (the validator refuses both);
argument errors reached the model as pydantic dumps ("1 validation error for StreamFilter ... input_value={...}").
Each message here keeps the original reason first, then adds the fix and one working example.
"""
from __future__ import annotations

import re

CYPHER_EXAMPLE = ("MATCH (a:Person {case_id: $case_id})-[r {case_id: $case_id}]-(b {case_id: $case_id}) "
                  "WHERE toLower(a.name) CONTAINS 'smith' RETURN a.name AS person, type(r) AS link, b.name AS other, "
                  "labels(b) AS kind LIMIT 50")

_CYPHER_FIXES = (
    (re.compile(r"Nested graph patterns|list expressions|map projections|Return scalar expressions", re.I),
     "After RETURN and in WHERE use only properties, functions and aggregates of names already matched: no "
     "(a)-[]-(b) pattern there, no map {...}, and a list only as literal values, e.g. n.key IN ['k1', 'k2']. "
     "Return labels(n) rather than an item of it, and fields as columns rather than a map. Put each extra hop in "
     "its own MATCH."),
    (re.compile(r"must be case-scoped", re.I),
     "Write the scope in the pattern itself: (x:Label {case_id: $case_id}) for each node and "
     "[r:TYPE {case_id: $case_id}] for each relationship, including unnamed ones: -[{case_id: $case_id}]-."),
    (re.compile(r"WITH, UNWIND|subqueries|variable-length|path expressions", re.I),
     "Write one MATCH ... RETURN, with any count(), collect() or sum() in RETURN: no WITH, UNWIND, UNION, EXISTS "
     "or [*] paths. For how two entities connect use find_paths_between_entities; for an entity's connections "
     "use get_entity_neighborhood."),
    (re.compile(r"custom query functions|built-in scalar", re.I),
     "Use only built-in functions such as coalesce, toLower, toString, count, collect, sum, min, max, size, "
     "labels, type, keys, date, substring."),
)


def cypher_fix(message: str) -> str:
    """The original refusal, how to fix the query, and an example that runs."""
    for pattern, fix in _CYPHER_FIXES:
        if pattern.search(message or ""):
            return "%s. How to fix: %s Example: %s" % (message.rstrip(". "), fix, CYPHER_EXAMPLE)
    return message


def _schema_hint(tool, field: str) -> str:
    schema = getattr(tool, "args_schema", None)
    fields = getattr(schema, "model_fields", None) or {}
    info = fields.get(field)
    if info is None:
        names = ", ".join(sorted(fields)) if fields else ""
        return (" The tool takes: %s." % names) if names else ""
    parts = []
    if info.description:
        parts.append(info.description)
    annotation = getattr(info, "annotation", None)
    if annotation is not None:
        parts.append("type %s" % getattr(annotation, "__name__", str(annotation)).replace("typing.", ""))
    return (" %s: %s." % (field, "; ".join(parts))) if parts else ""


def validation_text(exc: Exception, tool=None) -> str | None:
    """A pydantic validation error as one line per field (no input dump), with what the field takes, or None
    when ``exc`` is not one."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return None
    try:
        items = errors()
    except Exception:  # noqa: BLE001 - not a pydantic error after all
        return None
    lines = []
    for item in items[:6]:
        location = ".".join(str(x) for x in item.get("loc") or ()) or "the arguments"
        message = str(item.get("msg") or "is not accepted").replace("Value error, ", "")
        hint = _schema_hint(tool, str((item.get("loc") or ("",))[0])) if tool is not None else ""
        lines.append("%s: %s.%s" % (location, message.rstrip("."), hint))
    if not lines:
        return None
    return "The call's arguments were not accepted. " + " ".join(lines) + " Call again with these fixed."


def model_error(name: str, exc: Exception, tool=None, known: list[str] | None = None) -> str:
    """What the model is told when a tool call fails: the reason, and how to make the call work."""
    from services.agent.cypher_safety import UnsafeCypherError
    if isinstance(exc, UnsafeCypherError):
        return cypher_fix(str(exc))
    text = validation_text(exc, tool)
    if text:
        return text
    message = str(exc) or type(exc).__name__
    if message.startswith("Unknown tool") and known:
        import difflib
        close = difflib.get_close_matches(name or "", known, n=3, cutoff=0.5)
        if close:
            return "%s. Tools with a close name: %s." % (message, ", ".join(close))
    return message
