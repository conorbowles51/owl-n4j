"""Trail (Corroborate X): the steps of a build-out, oldest first. Each step is a saved group that holds the group
before it plus what was added; its level is the level of its latest run. Opening an earlier step shows the result
without what later steps added, which is how a step is undone: nothing is rewritten."""
from __future__ import annotations

from typing import Any

from services import case_selections
from services.relations import runs

LEVEL_ORDER = ["cant_tell", "coincidence", "possible", "probable", "strong"]


def _key(m: dict) -> tuple:
    return (m.get("type"), str(m.get("id")))


def _level(db, case_id, selection_id) -> dict | None:
    run_id = runs.latest_for(db, case_id, selection_id)
    if not run_id:
        return None
    result = runs.full_result(db, case_id, run_id) or {}
    c = result.get("corroboration") or {}
    lvl = c.get("level") or {}
    return {"run_id": str(run_id), "key": lvl.get("key"), "name": lvl.get("name"), "sentence": lvl.get("sentence"),
            "grid_rows": len(c.get("grid") or [])} if lvl else {"run_id": str(run_id), "key": None, "name": None}


def build(db, case_id, selection_id: str, *, limit: int = 30) -> dict[str, Any]:
    chain: list[dict] = []
    seen: set[str] = set()
    cur: str | None = str(selection_id)
    while cur and cur not in seen and len(chain) < limit:
        seen.add(cur)
        g = case_selections.describe(db, case_id, cur, member_limit=10**9)
        if g is None or g["group_type"] != "relation_query":
            break
        chain.append(g)
        cur = (g.get("how") or {}).get("extends")
    chain.reverse()
    steps = []
    prev_members: set = set()
    prev_level = None
    for n, g in enumerate(chain, 1):
        members = {_key(m): m for m in g["members"]}
        added = [m for k, m in members.items() if k not in prev_members]
        lvl = _level(db, case_id, g["id"])
        moved = None
        if lvl and prev_level and lvl.get("key") in LEVEL_ORDER and prev_level.get("key") in LEVEL_ORDER:
            d = LEVEL_ORDER.index(lvl["key"]) - LEVEL_ORDER.index(prev_level["key"])
            moved = "raised" if d > 0 else "lowered" if d < 0 else "unchanged"
        steps.append({"n": n, "selection_id": g["id"], "created_at": g.get("created_at"), "members": len(members),
                      "added": [{"type": m["type"], "id": m["id"], "label": m.get("label")} for m in added[:50]],
                      "added_count": len(added), "level": lvl, "level_moved": moved,
                      "adds_nothing": n > 1 and not added})
        prev_members, prev_level = set(members), lvl or prev_level
    return {"steps": steps, "current": str(selection_id)}
