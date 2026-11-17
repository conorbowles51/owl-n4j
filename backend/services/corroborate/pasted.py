"""A pasted list of numbers, accounts, plates or e-mails matched to what the case holds (lx-corroselect C).

Every token in the paste gets an answer: matched (with the case items it matched, and how many) or unmatched (with
the reason). Nothing is dropped. Finders are one per kind of identity; tests give the matcher fakes with the same
call shape. A phone number matches the phone records it takes part in, so a long list can hold many records: the
count is stated, and a selection larger than the group limit is refused with that number, never trimmed.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from sqlalchemy import text

from services.relations import rules

MAX_TOKENS = 2000
_SPLIT = re.compile(r"[\n\r;,\t]+")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PLATE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9 -]{4,10}$")

Finder = Callable[[Any, str, str, str], list[dict[str, Any]]]


def tokens(raw: str) -> list[str]:
    out: list[str] = []
    for chunk in _SPLIT.split(raw or ""):
        chunk = chunk.strip()
        if chunk and chunk not in out:
            out.append(chunk)
    return out


def classify(token: str) -> str:
    if _EMAIL.match(token):
        return "email"
    if re.fullmatch(r"[+()\d\s.-]+", token):
        return "number" if rules.norm_number(token) else "short_number"
    if _PLATE.match(token):
        return "plate"
    return "name"


def _accounts(db, case_id: str, kind: str, value: str) -> list[dict[str, Any]]:
    if kind != "number":
        return []
    norm = rules.norm_number(value)
    rows = db.execute(text(
        "SELECT id, COALESCE(institution_name, ''), identifier_as_printed FROM financial_accounts WHERE case_id = :c "
        "AND (identifier_normalised = :n OR regexp_replace(COALESCE(identifier_normalised, ''), '\\D', '', 'g') = :n)"),
        {"c": str(case_id), "n": norm}).fetchall()
    return [{"type": "financial_account", "id": str(r[0]), "label": f"{r[1]} account {r[2]}".strip(), "via": "an account number"}
            for r in rows]


def _phone_records(db, case_id: str, kind: str, value: str) -> list[dict[str, Any]]:
    if kind != "number":
        return []
    norm = rules.norm_number(value)
    rows = db.execute(text(
        "SELECT DISTINCT record_uid FROM phone_participations WHERE case_id = :c AND "
        "regexp_replace(COALESCE(identifier_raw, ''), '\\D', '', 'g') LIKE :n"),
        {"c": str(case_id), "n": "%" + norm[-9:]}).fetchall()
    return [{"type": "phone_record", "id": str(r[0]), "label": f"Phone record with {value}", "via": "a number on the phones"}
            for r in rows]


def _graph(db, case_id: str, kind: str, value: str) -> list[dict[str, Any]]:
    from services.neo4j.driver import active_node_predicate, driver
    wanted = re.sub(r"[\s-]", "", value).casefold()
    with driver.session() as session:
        rows = session.run(
            f"MATCH (n) WHERE {active_node_predicate('n')} AND replace(replace(toLower(coalesce(n.name, '')), ' ', ''), '-', '') = $v "
            "RETURN n.key AS key, n.name AS name LIMIT 50", case_id=str(case_id), v=wanted)
        return [{"type": "graph_entity", "id": r["key"], "label": r["name"], "via": "a name in the graph"} for r in rows]


DEFAULT_FINDERS: tuple[Finder, ...] = (_accounts, _phone_records, _graph)


def match(db, case_id, raw: str, *, finders: tuple[Finder, ...] = DEFAULT_FINDERS) -> dict[str, Any]:
    """Every token with what it matched. ``members`` is the union, in paste order, without repeats."""
    listed = tokens(raw)
    if len(listed) > MAX_TOKENS:
        raise ValueError(f"{len(listed):,} entries were pasted; at most {MAX_TOKENS:,} can be matched at once. Nothing was matched.")
    results, members, seen = [], [], set()
    for tok in listed:
        kind = classify(tok)
        found: list[dict[str, Any]] = []
        errors: list[str] = []
        if kind == "short_number":
            reason = "Too short to be a phone or account number (under 7 digits)."
        else:
            for finder in finders:
                try:
                    found += finder(db, str(case_id), kind, tok)
                except Exception as exc:  # noqa: BLE001 - one source failing is said, never read as "no match"
                    errors.append(f"{finder.__name__.strip('_')} could not be searched: {exc}")
            reason = "Nothing in this case carries it." if not errors else " ".join(errors)
        results.append({"token": tok, "kind": kind, "matched": len(found), "items": len(found),
                        "unmatched_reason": None if found else reason,
                        "via": sorted({f["via"] for f in found})})
        for f in found:
            key = (f["type"], f["id"])
            if key not in seen:
                seen.add(key)
                members.append({k: f[k] for k in ("type", "id", "label")})
    return {"tokens": results, "members": members,
            "matched": sum(1 for r in results if r["matched"]), "unmatched": [r for r in results if not r["matched"]]}
