"""Leads (lx-leads A): one type, one store, one list.

A lead is a ``corroborate_watches`` row grown up: the Corroborate question it answers, the level the engine's rules
gave it (``services.corroborate.levels``, never a model, never a person), where it came from, the state a person put
it in, the people, period, record kinds and records it rests on, and what raises and lowers it.

* ``origin``: ``found_by_loupe`` (the lead finder), ``asked`` (a person asked Corroborate) or ``agent``.
* A lead is a reading by Loupe (``read_by`` names the reader) until a person confirms it. Confirming adds it to a
  theory as a finding under that person's name, with the reader named as the finding's author
  (``workspace_entry_service.origin_label``: "Drafted by <reader>, accepted by <person>").
* ``state`` changes are appended to ``state_history`` with who and when; nothing is rewritten.
* A person's correction of a lead's words is appended to ``corrections``; Loupe's words stay as they were and stay
  visible, and the view shows the corrected words as current.
* Leads are listed on the Leads page only. ``count`` is the one sign of them anywhere else (the side menu).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select

ORIGINS = {"found_by_loupe": "Found by Loupe", "asked": "Asked", "agent": "Suggested by the agent"}
STATES = {"new": "New", "looking": "Looking into it", "in_theory": "In the theory", "not_relevant": "Not relevant"}
# Strongest first. "No link found" and "Set aside" are not likelihoods: they are listed in their own sections.
LEVEL_ORDER = ["strong", "probable", "possible", "cant_tell", "coincidence", "no_link_found", "set_aside"]
SET_ASIDE = {"key": "set_aside", "name": "Set aside"}
KIND_WORDS = {
    "contact": "Contact", "together": "Together", "money": "Money", "shared_content": "Words and files",
    "access": "Access logs", "absence": "Silence and deletion", "sequence": "Same order", "statement": "Statements",
    "activity": "Active at the same time", "same_person": "Same person", "documents": "Documents",
}
FINDER = "Loupe's lead finder"
CORROBORATE = "Corroborate"
MAX_REFS = 2000


class LeadError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(v) -> uuid.UUID:
    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError, AttributeError):
        raise LeadError("That lead is not in this case.", 404)


def _user_name(user) -> str:
    return str(getattr(user, "name", None) or getattr(user, "email", None) or "a person")


# ---- what a Corroborate result says, as a lead ---------------------------------------------------------------------

def level_of(result: dict) -> dict:
    lv = result.get("level") or {}
    return {k: lv.get(k) for k in ("key", "name", "sentence", "rule")}


def raises_of(result: dict) -> list[str]:
    """The rows that separate the instances asked about from ordinary ones, at full weight, in the engine's words."""
    rows = [g for g in result.get("grid") or [] if g.get("separates") and g.get("weight") == "full"
            and not g.get("picked_by") and not g.get("context") and (g.get("incident") or {}).get("present")]
    return [f"{g['label']}: {_counts(g, result)}" for g in rows][:12]


def lowers_of(result: dict) -> list[str]:
    """What weighs it down: rows weighed low with why, then the explained-away checks that weighed or ruled out."""
    out = [f"{g['label']}: weighed low ({g.get('why_low') or 'explained'})" for g in result.get("grid") or []
           if g.get("weight") != "full" and (g.get("incident") or {}).get("present")]
    out += [c.get("words") for c in result.get("checks") or [] if c.get("outcome") == "weighed_low" and c.get("words")]
    out += [c.get("words") for c in result.get("checks") or [] if c.get("open") and c.get("words")]
    return list(dict.fromkeys(x for x in out if x))[:12]


def _counts(g: dict, result: dict) -> str:
    comp = result.get("comparison") or {}
    inc, orda = g.get("incident") or {}, g.get("ordinary") or {}
    n_inc = len(comp.get("incident") or [])
    words = f"{inc.get('present', 0)} of {inc.get('of', 0)}"
    if orda.get("of"):
        words += f", against {orda.get('present', 0)} of {orda.get('of', 0)} ordinary"
    return words if n_inc else words


def kinds_of(result: dict) -> list[str]:
    lv = result.get("level") or {}
    kinds = list(lv.get("separating_kinds") or [])
    if not kinds:
        kinds = sorted({g["link_kind"] for g in result.get("grid") or [] if (g.get("incident") or {}).get("present")})
    return kinds


def people_of(result: dict) -> list[dict]:
    return [{"key": p.get("key"), "label": p.get("label")} for p in result.get("people") or [] if p.get("key")]


def period_of(result: dict) -> dict:
    inc = (result.get("comparison") or {}).get("incident") or []
    starts = sorted(i["start"][:10] for i in inc if i.get("start"))
    ends = sorted((i.get("money_until") or i.get("end") or "")[:10] for i in inc if i.get("end"))
    return {"from": starts[0], "to": ends[-1]} if starts and ends else {}


def refs_of(result: dict, members: Iterable[dict]) -> list[str]:
    """Every record the lead rests on: the members asked about, then the records of each row present on an incident
    instance. Kept whole up to MAX_REFS; the view says when more were left out (``refs_total``)."""
    refs: list[str] = [f"{m['type']}:{m['id']}" for m in members if m.get("type") and m.get("id")]
    incident_ids = {i.get("id") for i in (result.get("comparison") or {}).get("incident") or []} - {None}
    for g in result.get("grid") or []:
        if g.get("picked_by") is None and g.get("weight") != "full":
            continue
        for inst, rs in (g.get("records") or {}).items():
            if inst in incident_ids:
                refs.extend(str(r) for r in rs)
    return list(dict.fromkeys(refs))


# ---- saving --------------------------------------------------------------------------------------------------------

def save(db, case_id, *, origin: str, selection_id, result: dict | None, members: list[dict], title: str,
         summary: str = "", user=None, finder_key: str | None = None, read_by: str | None = None,
         detail: dict | None = None, kinds: list[str] | None = None, level: dict | None = None,
         lowers: list[str] | None = None, raises: list[str] | None = None, run_id=None, question: dict | None = None,
         commit: bool = True) -> dict:
    """Save a lead, or (same ``finder_key``) bring the finder's earlier lead up to date. An update keeps the lead's
    state, its history and every correction; a level change is appended to ``history`` with its reason."""
    from postgres.models.corroborate import CorroborateWatch
    from services.corroborate import facts
    if origin not in ORIGINS:
        raise LeadError(f"{origin} is not where a lead comes from")
    result = result or {}
    lv = level or level_of(result)
    if not lv.get("key"):
        raise LeadError("A lead needs the level Corroborate's rules gave it.")
    all_refs = refs_of(result, members)
    fields = dict(
        title=" ".join(str(title or "").split())[:500], summary=" ".join(str(summary or "").split())[:4000],
        people=people_of(result), period=period_of(result), kinds=kinds if kinds is not None else kinds_of(result),
        record_refs=all_refs[:MAX_REFS], raises=raises if raises is not None else raises_of(result),
        lowers=lowers if lowers is not None else lowers_of(result), searched=result.get("searched") or {},
        detail={**(detail or {}), "refs_total": len(all_refs)},
        read_by=read_by or (FINDER if origin == "found_by_loupe" else CORROBORATE),
    )
    q = question if question is not None else {
        "kind": (result.get("question") or {}).get("kind"), "text": (result.get("question") or {}).get("text"),
        "chips": {k: v for k, v in ((result.get("question") or {}).get("chips") or {}).items() if k != "when"}}
    now = _now()
    row = None
    if finder_key:
        row = db.scalars(select(CorroborateWatch).where(CorroborateWatch.case_id == _uuid(case_id),
                                                        CorroborateWatch.finder_key == finder_key)).first()
    if row is not None:
        old = row.level or {}
        if old.get("key") != lv.get("key"):
            row.history = list(row.history or []) + [{"at": now.isoformat(), "from": old, "to": lv,
                                                      "reason": f"Found again on new material: now {lv.get('name')}."}]
            row.unseen = True
        for k, v in fields.items():
            setattr(row, k, v)
        row.level, row.question, row.selection_id = lv, q, _uuid(selection_id)
        row.material, row.checked_at = facts.material(db, case_id), now
        if run_id:
            row.run_id = _uuid(run_id)
    else:
        row = CorroborateWatch(
            id=uuid.uuid4(), case_id=_uuid(case_id), selection_id=_uuid(selection_id), question=q, level=lv,
            # watched (re-checked on new material): the finder's own leads, by the finder; an asked lead only when
            # a person chooses Keep watching
            material=facts.material(db, case_id), active=origin == "found_by_loupe", unseen=True, origin=origin,
            state="new",
            state_history=[{"at": now.isoformat(), "from": None, "to": "new", "by": None,
                            "by_name": fields["read_by"], "why": f"{ORIGINS[origin]}."}],
            history=[{"at": now.isoformat(), "from": None, "to": lv, "reason": f"{ORIGINS[origin]}."}],
            created_by=getattr(user, "id", None), checked_at=now, finder_key=finder_key,
            run_id=_uuid(run_id) if run_id else None, **fields)
        db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
    return view(row, {})


def save_asked(db, case_id, *, selection_id, run_id, result: dict, members: list[dict], user=None) -> dict | None:
    """Each answer of an asked question saves to Leads as "Asked by <person>" (screen 7). One lead per run."""
    from postgres.models.corroborate import CorroborateWatch
    if not (result or {}).get("level"):
        return None
    if db.scalars(select(CorroborateWatch.id).where(CorroborateWatch.run_id == _uuid(run_id))).first():
        return None
    q = result.get("question") or {}
    title = q.get("text") or "Corroborate"
    summary = (result.get("level") or {}).get("sentence") or ""
    return save(db, case_id, origin="asked", selection_id=selection_id, result=result, members=members,
                title=title, summary=summary, user=user, run_id=run_id)


# ---- reading -------------------------------------------------------------------------------------------------------

def _names(db, ids: Iterable) -> dict[str, str]:
    from postgres.models.user import User
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {str(u.id): (u.name or u.email or "") for u in db.scalars(select(User).where(User.id.in_(ids)))}


def view(w, names: dict[str, str], me=None) -> dict:
    lv = w.level or {}
    by = names.get(str(w.created_by)) if w.created_by else None
    origin_words = ORIGINS.get(w.origin or "asked", "Asked")
    if w.origin == "asked":
        origin_words = "Asked by you" if (me is not None and w.created_by and str(w.created_by) == str(me)) else \
            (f"Asked by {by}" if by else "Asked")
    current = {"title": w.title, "summary": w.summary}
    for c in w.corrections or []:
        if c.get("field") in current:
            current[c["field"]] = c.get("value")
    return {
        "id": str(w.id), "origin": w.origin, "origin_words": origin_words, "state": w.state,
        "state_words": STATES.get(w.state, w.state), "state_history": w.state_history or [],
        "level": {k: lv.get(k) for k in ("key", "name", "sentence", "rule")},
        "title": current["title"], "summary": current["summary"],
        "read": {"title": w.title, "summary": w.summary, "by": w.read_by,
                 "words": f"Read by {w.read_by} · not confirmed" if not w.confirmed_at else
                 f"Read by {w.read_by} · confirmed by {w.confirmed_by_name}"},
        "corrections": w.corrections or [], "people": w.people or [], "period": w.period or {},
        "kinds": w.kinds or [], "kind_words": [KIND_WORDS.get(k, k) for k in (w.kinds or [])],
        "record_refs": w.record_refs or [], "raises": w.raises or [], "lowers": w.lowers or [],
        "searched": w.searched or {}, "detail": w.detail or {}, "question": w.question or {},
        "selection_id": str(w.selection_id), "run_id": str(w.run_id) if w.run_id else None,
        "history": w.history or [], "unseen": bool(w.unseen), "watching": bool(w.active),
        "finding_id": str(w.finding_id) if w.finding_id else None,
        "confirmed": ({"by": w.confirmed_by_name, "at": w.confirmed_at.isoformat()} if w.confirmed_at else None),
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "checked_at": w.checked_at.isoformat() if w.checked_at else None,
    }


def _rank(lead: dict) -> tuple:
    key = (lead["level"] or {}).get("key")
    return (LEVEL_ORDER.index(key) if key in LEVEL_ORDER else len(LEVEL_ORDER), lead.get("detail", {}).get("order", 0),
            lead["title"])


def _matches(lead: dict, records: set[str] | None, people: set[str] | None, period: tuple[str, str] | None,
             kinds: set[str] | None) -> bool:
    if kinds and not (set(lead["kinds"]) & kinds):
        return False
    hit = records is None and people is None and period is None
    if records and set(lead["record_refs"]) & records:
        hit = True
    if people and ({p.get("key") for p in lead["people"]} & people):
        hit = True
    if period and lead["period"].get("from") and lead["period"]["from"] <= period[1] and \
            lead["period"].get("to", lead["period"]["from"]) >= period[0]:
        hit = True
    return hit


def list_leads(db, case_id, *, records: Iterable[str] | None = None, people: Iterable[str] | None = None,
               period: tuple[str, str] | None = None, kinds: Iterable[str] | None = None, me=None) -> list[dict]:
    """The one list, strongest first. With ``records``, ``people`` or ``period`` it is the same list filtered to the
    leads that touch any of them ("Leads already here")."""
    from postgres.models.corroborate import CorroborateWatch
    rows = list(db.scalars(select(CorroborateWatch).where(CorroborateWatch.case_id == _uuid(case_id))
                           .order_by(CorroborateWatch.created_at)))
    names = _names(db, [r.created_by for r in rows])
    leads = [view(r, names, me) for r in rows]
    rec = {str(r) for r in records} if records is not None else None
    ppl = {str(p) for p in people} if people is not None else None
    knd = {str(k) for k in kinds} if kinds else None
    leads = [x for x in leads if _matches(x, rec, ppl, period, knd)]
    return sorted(leads, key=_rank)


def count(db, case_id) -> dict:
    """The side menu's count: leads that are likelihoods (not set aside, not "No link found") and not marked not
    relevant. ``new`` is how many no one has opened yet."""
    from postgres.models.corroborate import CorroborateWatch
    n = new = 0
    for level, state, unseen in db.execute(select(CorroborateWatch.level, CorroborateWatch.state,
                                                  CorroborateWatch.unseen)
                                           .where(CorroborateWatch.case_id == _uuid(case_id))):
        if (level or {}).get("key") in ("set_aside", "no_link_found") or state == "not_relevant":
            continue
        n += 1
        new += 1 if unseen else 0
    return {"count": n, "new": new}


def _row(db, case_id, lead_id):
    from postgres.models.corroborate import CorroborateWatch
    w = db.get(CorroborateWatch, _uuid(lead_id))
    if w is None or str(w.case_id) != str(case_id):
        raise LeadError("That lead is not in this case.", 404)
    return w


def get(db, case_id, lead_id, me=None) -> dict:
    w = _row(db, case_id, lead_id)
    return view(w, _names(db, [w.created_by]), me)


def set_state(db, case_id, lead_id, *, state: str, user, why: str | None = None) -> dict:
    """A person moves the lead: looking into it, not relevant, or back to new. Appended, never rewritten. "In the
    theory" is reached only by ``confirm``."""
    if state not in STATES or state == "in_theory":
        raise LeadError("A lead is put in the theory by confirming it.") if state == "in_theory" else \
            LeadError(f"{state} is not a state a lead can be in")
    w = _row(db, case_id, lead_id)
    if w.state != state:
        w.state_history = list(w.state_history or []) + [{
            "at": _now().isoformat(), "from": w.state, "to": state, "by": str(getattr(user, "id", "") or "") or None,
            "by_name": _user_name(user), "why": " ".join(str(why or "").split())[:500] or None}]
        w.state = state
    w.unseen = False
    db.commit()
    return view(w, _names(db, [w.created_by]), getattr(user, "id", None))


def mark_seen(db, case_id, lead_id, user=None) -> dict:
    w = _row(db, case_id, lead_id)
    w.unseen = False
    db.commit()
    return view(w, _names(db, [w.created_by]), getattr(user, "id", None))


def correct(db, case_id, lead_id, *, field: str, value: str, user) -> dict:
    """A person's correction of the lead's words. Loupe's words stay, visible, beside it."""
    if field not in ("title", "summary"):
        raise LeadError("Only a lead's title and summary can be corrected; its level comes from the rules.")
    value = " ".join(str(value or "").split())[:4000]
    if not value:
        raise LeadError("Write the corrected words.")
    w = _row(db, case_id, lead_id)
    w.corrections = list(w.corrections or []) + [{"field": field, "original": getattr(w, field), "value": value,
                                                  "by": str(getattr(user, "id", "") or "") or None,
                                                  "by_name": _user_name(user), "at": _now().isoformat()}]
    db.commit()
    return view(w, _names(db, [w.created_by]), getattr(user, "id", None))


def confirm(db, case_id, lead_id, *, theory_id, user, why: str | None = None) -> dict:
    """A person confirms the lead into a theory. It becomes a finding under that person's name, with the reader that
    found it named as the finding's author, holding the lead's records; the finding is added to the theory."""
    from services import theory_additions
    from services.workspace_entry_service import create_entry
    w = _row(db, case_id, lead_id)
    if w.finding_id:
        raise LeadError("This lead is already in the theory.", 409)
    current = view(w, {})
    body = "\n\n".join(x for x in [current["summary"], (w.level or {}).get("sentence"),
                                   *(f"Raises it: {r}" for r in w.raises or []),
                                   *(f"Lowers it: {r}" for r in w.lowers or [])] if x)
    origin = {"kind": "model", "model": w.read_by, "for": {"name": _user_name(user), "user_id": str(user.id)},
              "how": f"{ORIGINS.get(w.origin, '')}; level from Corroborate's rules: {(w.level or {}).get('name')}.",
              "citation": {"lead_id": str(w.id), "selection_id": str(w.selection_id)}}
    finding = create_entry(db, case_id=w.case_id, current_user=user, entry_type="finding",
                           title=current["title"][:300] or "Lead", body=body or current["title"],
                           actor_origin=origin, review_state="accepted",
                           links=[{"target_type": "relation_query", "target_id": str(w.selection_id),
                                   "relationship": "supports"}], commit=False)
    theory_additions.add(db, case_id=w.case_id, entry_id=theory_id, user=user, surface="relation",
                         why=why or f"Lead confirmed: {current['title']}"[:1000],
                         items=[{"target_type": "entry", "target_id": finding["id"],
                                 "target_label": current["title"][:300]}], commit=False)
    now = _now()
    w.finding_id = _uuid(finding["id"])
    w.confirmed_by, w.confirmed_by_name, w.confirmed_at = user.id, _user_name(user), now
    w.state_history = list(w.state_history or []) + [{"at": now.isoformat(), "from": w.state, "to": "in_theory",
                                                      "by": str(user.id), "by_name": _user_name(user),
                                                      "why": why, "theory_id": str(theory_id),
                                                      "finding_id": finding["id"]}]
    w.state, w.unseen = "in_theory", False
    db.commit()
    return view(w, _names(db, [w.created_by]), user.id)
