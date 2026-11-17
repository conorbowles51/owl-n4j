"""Saved subsets and set operations (lx-corroselect D, Q).

A saved subset is a ``case_selections`` group (kind ``relation_query``) saved under a name the person chose, in how it was
chosen (``how.subset``): the same store as every other group, never rewritten. ``combine`` takes two saved groups and
returns the members that are in both, in either, or in one but not the other; nothing is capped or dropped, and the
counts of each side are returned so the person sees what the operation did.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from postgres.models.case_selection import CaseSelection
from services import case_selections

OPS = {"both": "in both", "either": "in either", "a_not_b": "in the first but not the second", "b_not_a": "in the second but not the first"}


def save(db, *, case_id, name: str, members: list[dict[str, Any]], user=None, how: dict[str, Any] | None = None) -> dict[str, Any]:
    name = " ".join(str(name or "").split())[:120]
    if not name:
        raise case_selections.SelectionError("Name the subset so you can find it again.")
    return case_selections.freeze(db, case_id=case_id, group_type="relation_query", members=members,
                                  how={**(how or {}), "subset": name}, words=name, user=user)


def listing(db, case_id) -> list[dict[str, Any]]:
    rows = db.scalars(select(CaseSelection).where(CaseSelection.case_id == case_id, CaseSelection.group_type == "relation_query")
                      .order_by(CaseSelection.created_at.desc())).all()
    return [{"id": str(r.id), "name": (r.how or {}).get("subset"), "member_count": r.member_count,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows if (r.how or {}).get("subset")]


def _members(db, case_id, selection_id: str) -> list[dict[str, Any]]:
    got = case_selections.describe(db, case_id, selection_id, member_limit=10**9)
    if got is None or got["group_type"] != "relation_query":
        raise case_selections.SelectionError("That saved subset is not in this case.")
    return [{k: v for k, v in m.items() if k in ("type", "id", "label")} for m in got["members"]]


def combine(db, case_id, a_id: str, b_id: str, op: str) -> dict[str, Any]:
    if op not in OPS:
        raise case_selections.SelectionError("Choose both, either, or one but not the other.")
    a, b = _members(db, case_id, a_id), _members(db, case_id, b_id)
    ka, kb = {(m["type"], m["id"]) for m in a}, {(m["type"], m["id"]) for m in b}
    if op == "both":
        out = [m for m in a if (m["type"], m["id"]) in kb]
    elif op == "either":
        out = a + [m for m in b if (m["type"], m["id"]) not in ka]
    elif op == "a_not_b":
        out = [m for m in a if (m["type"], m["id"]) not in kb]
    else:
        out = [m for m in b if (m["type"], m["id"]) not in ka]
    return {"members": out, "count": len(out), "first": len(a), "second": len(b), "words": OPS[op]}
