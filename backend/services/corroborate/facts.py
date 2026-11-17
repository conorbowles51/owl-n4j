"""Case facts and Keep watching (lx-corroengine H, brief item Z).

A case fact is what a person tells Loupe ("Doe and Roe live together", "this is a work group", "this phrase is
routine"). It is stored with who recorded it and when, used by every later weighing (``checks``), and sent to the
manual-change feed (``services.manual_changes``) so the lesson it carries is built into the rules' tests. A fact is
never rewritten; withdrawing it keeps it, marked withdrawn.

Keep watching saves a Corroborate result. Whenever the case's material changes (records added to or taken from the
phones, the ledger or the documents: ``material``), opening the case's watches re-runs the question and records any
level change with its reason ("New bank records raise this to Strong link"). Alerts show in Loupe only (Neil,
16 Nov). *Reverse if* re-checking on open is too late for users: run ``recheck`` from a timer instead.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text

KINDS = {"live_together": "live together", "work_group": "a work group", "routine_phrase": "a routine phrase",
         "routine_place": "a routine place", "same_person": "the same person", "not_same_person": "not the same person",
         "other": "other"}


class FactError(ValueError):
    """Refused, with a reason for the person."""


def _name(user) -> str:
    return (getattr(user, "full_name", None) or getattr(user, "name", None) or getattr(user, "email", None) or "a person")


def _view(f) -> dict:
    return {"id": str(f.id), "kind": f.kind, "kind_words": KINDS[f.kind], "text": f.text, "people": list(f.people or []),
            "phrase": f.phrase, "state": f.state, "by_name": f.created_by_name, "at": f.created_at.isoformat() if
            f.created_at else None, "withdrawn_by": f.withdrawn_by_name,
            "withdrawn_at": f.withdrawn_at.isoformat() if f.withdrawn_at else None}


def list_facts(db, case_id, *, include_withdrawn: bool = False) -> list[dict]:
    from postgres.models.corroborate import CorroborateFact
    try:
        q = select(CorroborateFact).where(CorroborateFact.case_id == uuid.UUID(str(case_id)))
        if not include_withdrawn:
            q = q.where(CorroborateFact.state == "active")
        return [_view(f) for f in db.scalars(q.order_by(CorroborateFact.created_at))]
    except Exception:  # noqa: BLE001 - before the migration runs there are no facts; weighing goes on without them
        db.rollback()
        return []


def add_fact(db, *, case_id, kind: str, text_: str, people: list[str], phrase: str | None, user, run_id=None) -> dict:
    from postgres.models.corroborate import CorroborateFact
    from services import manual_changes
    if kind not in KINDS:
        raise FactError("That kind of case fact is not known.")
    words = " ".join(str(text_ or "").split())[:500]
    if not words:
        raise FactError("Say the fact in a few words.")
    if kind in ("live_together", "work_group", "same_person", "not_same_person") and len(people or []) < 2:
        raise FactError("Name at least two people for this fact.")
    if kind == "routine_phrase" and not (phrase or "").strip():
        raise FactError("Give the phrase that is routine.")
    f = CorroborateFact(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), kind=kind, text=words,
                        people=list(dict.fromkeys(people or [])), phrase=(phrase or "").strip() or None, state="active",
                        source_run_id=uuid.UUID(str(run_id)) if run_id else None, created_by=getattr(user, "id", None),
                        created_by_name=_name(user)[:300], created_at=datetime.now(timezone.utc))
    db.add(f)
    manual_changes.record_change(db, "corroborate_case_fact", case_id, ("corroborate_case_fact", str(f.id)), None,
                                 {"kind": kind, "text": words, "people": f.people, "phrase": f.phrase}, user,
                                 reason=words, change_type="set_aside" if kind in ("routine_phrase", "routine_place")
                                 else "change", field=kind, producer="corroborate.levels")
    db.commit()
    return _view(f)


def withdraw_fact(db, *, case_id, fact_id, user) -> dict:
    from postgres.models.corroborate import CorroborateFact
    from services import manual_changes
    f = db.get(CorroborateFact, uuid.UUID(str(fact_id)))
    if f is None or str(f.case_id) != str(case_id):
        raise LookupError("That case fact is not in this case.")
    if f.state == "withdrawn":
        return _view(f)
    before = _view(f)
    f.state, f.withdrawn_by_name, f.withdrawn_at = "withdrawn", _name(user)[:300], datetime.now(timezone.utc)
    manual_changes.record_change(db, "corroborate_case_fact_withdrawn", case_id, ("corroborate_case_fact", str(f.id)),
                                 before, _view(f), user, reason="withdrawn", field=f.kind,
                                 producer="corroborate.levels")
    db.commit()
    return _view(f)


# ---- keep watching ---------------------------------------------------------------------------------------------

def material(db, case_id) -> dict:
    """A fingerprint of the case's material: counts and the newest row of each source Corroborate reads."""
    out = {}
    for key, sql in (
            ("phone_records", "SELECT count(*), max(created_at) FROM phone_extractions WHERE case_id = :c AND standing = 'active'"),
            ("ledger", "SELECT count(*), max(updated_at) FROM financial_transactions WHERE case_id = :c AND superseded_by_id IS NULL"),
            ("documents", "SELECT count(*), max(extracted_at) FROM evidence_document_texts t JOIN evidence_files f ON "
                          "f.id = t.evidence_file_id WHERE f.case_id = :c AND f.deleted_at IS NULL"),
            ("people", "SELECT count(*), max(updated_at) FROM case_profiles WHERE case_id = :c"),
            ("facts", "SELECT count(*), max(COALESCE(withdrawn_at, created_at)) FROM corroborate_case_facts WHERE case_id = :c")):
        try:
            n, last = db.execute(text(sql), {"c": str(case_id)}).first()
        except Exception:  # noqa: BLE001 - a missing table reads as no material of that kind
            db.rollback()
            n, last = 0, None
        out[key] = [int(n or 0), last.isoformat() if last else None]
    return out


def _change_reason(old: dict, new: dict) -> str:
    words = {"phone_records": "phone records", "ledger": "bank records", "documents": "documents",
             "people": "people's details", "facts": "case facts"}
    changed = [words[k] for k in words if old.get(k) != new.get(k)]
    if not changed:
        return "Re-checked."
    return "New or changed " + (" and ".join(changed) if len(changed) <= 2 else ", ".join(changed[:-1]) + " and " + changed[-1])


def watch(db, *, case_id, selection_id, question: dict, level: dict, user) -> dict:
    from postgres.models.corroborate import CorroborateWatch
    w = CorroborateWatch(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), selection_id=uuid.UUID(str(selection_id)),
                         question=question or {}, level=_level(level), material=material(db, case_id),
                         history=[{"at": datetime.now(timezone.utc).isoformat(), "from": None, "to": _level(level),
                                   "reason": "Started watching."}], created_by=getattr(user, "id", None),
                         checked_at=datetime.now(timezone.utc))
    db.add(w)
    db.commit()
    return watch_view(w)


def _level(level: dict | None) -> dict:
    level = level or {}
    return {k: level.get(k) for k in ("key", "name", "sentence")}


def watch_view(w) -> dict:
    return {"id": str(w.id), "selection_id": str(w.selection_id), "question": w.question, "level": w.level,
            "history": w.history, "unseen": w.unseen, "active": w.active,
            "checked_at": w.checked_at.isoformat() if w.checked_at else None}


def recheck(db, case_id, *, runner=None) -> list[dict]:
    """Re-run every active watch of the case whose material changed; record each level change with its reason."""
    from postgres.models.corroborate import CorroborateWatch
    from services import case_selections
    now_material = material(db, case_id)
    out = []
    for w in db.scalars(select(CorroborateWatch).where(CorroborateWatch.case_id == uuid.UUID(str(case_id)),
                                                      CorroborateWatch.active.is_(True))):
        if w.material == now_material:
            out.append(watch_view(w))
            continue
        sel = case_selections.describe(db, case_id, str(w.selection_id), member_limit=10 ** 9)
        if sel is None:
            w.active = False
            out.append(watch_view(w))
            continue
        members = [{k: v for k, v in m.items() if k in ("type", "id", "label", "quote")} for m in sel["members"]]
        if runner is None:
            from services.corroborate import engine
            from services.corroborate.store import CaseStore
            result = engine.run(CaseStore(db, case_id), members, w.question)
        else:
            result = runner(members, w.question)
        new = _level(result["level"])
        reason = _change_reason(w.material, now_material)
        if new.get("key") != (w.level or {}).get("key"):
            w.history = list(w.history or []) + [{"at": datetime.now(timezone.utc).isoformat(), "from": w.level,
                                                  "to": new, "reason": f"{reason}: now {new.get('name')}."}]
            w.unseen = True
        w.level, w.material, w.checked_at = new, now_material, datetime.now(timezone.utc)
        out.append(watch_view(w))
    db.commit()
    return out


def mark_seen(db, case_id, watch_id) -> dict:
    from postgres.models.corroborate import CorroborateWatch
    w = db.get(CorroborateWatch, uuid.UUID(str(watch_id)))
    if w is None or str(w.case_id) != str(case_id):
        raise LookupError("That watch is not in this case.")
    w.unseen = False
    db.commit()
    return watch_view(w)


def stop(db, case_id, watch_id) -> dict[str, Any]:
    from postgres.models.corroborate import CorroborateWatch
    w = db.get(CorroborateWatch, uuid.UUID(str(watch_id)))
    if w is None or str(w.case_id) != str(case_id):
        raise LookupError("That watch is not in this case.")
    w.active = False
    db.commit()
    return watch_view(w)
