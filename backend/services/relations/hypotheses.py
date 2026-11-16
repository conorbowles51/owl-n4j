"""Hypotheses on how a group could be linked: a model reading until a person accepts it (lx-overlaps E).

The agent reads the engine's results (``get_relation_results``), names competing explanations, and records them with
``save``. Each hypothesis states what it predicts, cites records for and against, names the record that would tell
it apart from the others, and says what was searched for that record and what came back. Coincidence and routine are
always among them. Everything is stored under the model's name; nothing becomes part of a theory until a person
accepts it (``accept``), and then it is added as Supports or Contradicts with the model named as its author.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from postgres.models.relation_run import RelationRun

REQUIRED_KINDS = ("coincidence", "routine")
MAX_HYPOTHESES = 12


class HypothesisError(ValueError):
    status = 422


def _words(value: Any, limit: int = 1500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _cites(rows: Any, label: str) -> list[dict]:
    out = []
    for row in rows or []:
        cite = _words(row.get("cite") if isinstance(row, dict) else row, 300)
        text = _words(row.get("text") if isinstance(row, dict) else "", 600)
        if cite:
            out.append({"cite": cite, "text": text})
    return out


def validate(items: list[dict]) -> list[dict]:
    if not items or len(items) > MAX_HYPOTHESES:
        raise HypothesisError(f"Send between 1 and {MAX_HYPOTHESES} explanations.")
    clean = []
    for i, raw in enumerate(items):
        kind = _words(raw.get("kind"), 40).casefold()
        statement = _words(raw.get("statement"))
        if not kind or not statement:
            raise HypothesisError(f"Explanation {i + 1} needs a kind and a statement.")
        item = {"kind": kind, "statement": statement, "predicts": _words(raw.get("predicts")),
                "for": _cites(raw.get("for"), "for"), "against": _cites(raw.get("against"), "against"),
                "distinguishing_record": _words(raw.get("distinguishing_record")),
                "search": _words(raw.get("search")), "strength_words": _words(raw.get("strength_words"), 300)}
        if kind not in REQUIRED_KINDS and not (item["for"] or item["against"]):
            raise HypothesisError(f"Explanation {i + 1} ({kind}) cites no record for or against it.")
        if not item["distinguishing_record"]:
            raise HypothesisError(f"Explanation {i + 1} ({kind}) must name the record that would tell it apart from the others.")
        if not item["search"]:
            raise HypothesisError(f"Explanation {i + 1} ({kind}) must say what was searched for that record and what was found.")
        clean.append(item)
    missing = [k for k in REQUIRED_KINDS if k not in {c["kind"] for c in clean}]
    if missing:
        raise HypothesisError("Always include " + " and ".join(missing) + " among the explanations.")
    return clean


def save(db, *, case_id, selection_id, items: list[dict], origin: dict, no_link_words: str = "") -> dict:
    run = db.query(RelationRun).filter(RelationRun.case_id == uuid.UUID(str(case_id)),
                                       RelationRun.selection_id == uuid.UUID(str(selection_id)),
                                       RelationRun.status == "done").order_by(RelationRun.created_at.desc()).first()
    if run is None:
        raise HypothesisError("No finished analysis of this group exists. Run the analysis first.")
    clean = validate(items)
    run.hypotheses = {"reading_by": "model", "model": origin.get("model") or origin.get("actor_name"), "origin": origin,
                      "status": "A model reading. No person has confirmed it.", "saved_at": datetime.now(timezone.utc).isoformat(),
                      "no_links": _words(no_link_words, 3000),
                      "items": [{**c, "id": n, "accepted": None} for n, c in enumerate(clean)]}
    db.commit()
    return {"id": f"{run.id}", "run_id": str(run.id), "count": len(clean)}


def accept(db, *, case_id, run_id, number: int, entry_id, relationship: str, user) -> dict:
    from services import theory_additions
    if relationship not in ("supports", "contradicts"):
        raise HypothesisError("Accept it as supports or contradicts.")
    run = db.get(RelationRun, uuid.UUID(str(run_id)))
    if run is None or str(run.case_id) != str(case_id) or not run.hypotheses:
        raise LookupError("That reading is not in this case.")
    items = list(run.hypotheses["items"])
    if not 0 <= number < len(items):
        raise LookupError("That explanation is not in this reading.")
    item = items[number]
    added = theory_additions.add(db, case_id=case_id, entry_id=entry_id, user=user, surface="relation",
                                 why=item["statement"], relationship=relationship, commit=False,
                                 items=[{"target_type": "relation_query", "target_id": str(run.selection_id)}])
    theory_additions.mark_agent_addition(db, added["added_link_ids"], model=run.hypotheses.get("model") or "model",
                                         why=item["statement"], proposal_id=f"{run.id}:{number}", accepted_by=user)
    items[number] = {**item, "accepted": {"relationship": relationship, "entry_id": str(entry_id), "by": user.name,
                                          "at": datetime.now(timezone.utc).isoformat()}}
    run.hypotheses = {**run.hypotheses, "items": items}
    db.commit()
    return {"added_link_ids": added["added_link_ids"], "relationship": relationship}
