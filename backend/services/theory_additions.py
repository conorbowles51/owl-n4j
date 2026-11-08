"""Everything in a case can be added to a theory, and each addition explains itself (lx-theorybuild A, B, C, G, H).

An *addition* is one link row of a theory (or finding, or note): one item, or a group stored once in
``case_selections``. Each addition is a self-contained unit:

1. its members (the item, or every member of the group, each checked against the case);
2. why it was chosen: the surface it came from and the person's words (a group also keeps the filter, range or
   query it was chosen by). This is written once, by the server, into the link's ``metadata.addition`` and kept
   through every later save of the entry. An addition made by accepting an agent proposal says so (``origin
   'agent'``, the model, and the person who accepted it);
3. its narrative (``theory_narratives``): written by a person, or inferred by the model from the members with a
   citation to each member it relies on. An inferred narrative is a model reading: it carries the model's name and is
   shown as such until a person confirms it; it is never saved under a person's name. An edit is a new row that
   names the one it replaces, so the original stays visible;
4. its Loupe: ``loupe()`` returns the addition alone, with its members, its why and its narratives, for the view
   that suits it.

``reading()`` is the theory read as a whole: its additions in the order added, each with its narrative, and the
theory's own "how it fits together" narrative (``link_id`` null), which cites the additions.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy import select

from postgres import link_types
from postgres.models.theory_narrative import TheoryNarrative
from postgres.models.user import User
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services import case_selections
from services.workspace_entry_service import (
    WorkspaceEntryNotFound,
    WorkspaceEntryValidationError,
    batch_add_entry_links,
    create_entry,
)

SURFACES: dict[str, str] = {
    "graph": "the graph",
    "significant": "the Significant layer",
    "timeline": "the timeline",
    "financial": "the ledger",
    "evidence": "the evidence files",
    "passage": "a document's text",
    "interview": "an interview",
    "agent": "the case agent",
    "phone": "the phone viewer",
    "map": "the map",
    "search": "search",
    "workspace": "Workspace",
}
MAX_WHY = 1000
MAX_NARRATIVE = 8000
# A model reads at most this many members of one addition; the narrative says "read N of M" when there are more.
READ_LIMIT = 150
MAX_FACT = 700

Generator = Callable[[str], tuple[dict[str, Any], dict[str, Any]]]


class AdditionError(ValueError):
    """Refused; the message is written for the person."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _words(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _added_order(link: WorkspaceEntryLink):
    """The order additions were made: the row's time, then the add's own stamp (to the microsecond), then its id."""
    stamp = str(((link.link_metadata or {}).get("addition") or {}).get("at") or "")
    created = link.created_at.replace(tzinfo=None) if link.created_at else datetime.max
    return (created.replace(microsecond=0), stamp, str(link.id))


def _entry(db, case_id, entry_id) -> WorkspaceEntry:
    entry = db.get(WorkspaceEntry, _uuid(entry_id)) if _uuid(entry_id) else None
    if entry is None or entry.case_id != _uuid(case_id) or entry.deleted_at is not None:
        raise WorkspaceEntryNotFound(f"Workspace entry {entry_id} not found")
    return entry


def _link(db, entry: WorkspaceEntry, link_id) -> WorkspaceEntryLink:
    link = db.get(WorkspaceEntryLink, _uuid(link_id)) if _uuid(link_id) else None
    if link is None or link.entry_id != entry.id:
        raise WorkspaceEntryNotFound(f"That addition {link_id} is not on this entry")
    return link


# --- adding ---------------------------------------------------------------------------------------------------------

def add(db, *, case_id, entry_id, user: User, surface: str, why: str | None = None,
        items: Iterable[Mapping[str, Any]] | None = None, group: Mapping[str, Any] | None = None,
        narrative: str | None = None, relationship: str = "unclassified", commit: bool = True) -> dict[str, Any]:
    """Add one item, several items, or a group to an entry, each as a unit that knows why it was chosen.

    ``items`` are links ({target_type, target_id, target_label?, source_anchor?}); each becomes its own addition.
    ``group`` is {group_type, members, how, words}: stored once with every member, added as one addition.
    ``narrative``, when given, is the person's own account of what the addition shows (one per addition added)."""
    if surface not in SURFACES:
        raise AdditionError(f"{surface or 'That'} is not a place things are added from")
    items = list(items or [])
    if bool(items) == bool(group):
        raise AdditionError("Send either the items or the group, one of them")
    entry = _entry(db, case_id, entry_id)
    why = _words(why, MAX_WHY)
    selection = None
    if group:
        try:
            selection = case_selections.freeze(
                db, case_id=entry.case_id, group_type=str(group.get("group_type") or ""),
                members=group.get("members") or [], how=group.get("how"),
                words=group.get("words") or why, user=user, commit=False)
        except case_selections.SelectionError as exc:
            raise AdditionError(str(exc)) from exc
        why = why or selection["words"]
        items = [{"target_type": selection["group_type"], "target_id": selection["id"]}]
    links = [{
        "target_type": item.get("target_type"), "target_id": item.get("target_id"),
        "target_label": item.get("target_label"), "relationship": relationship,
        "source_anchor": item.get("source_anchor") or {}, "metadata": {},
    } for item in items]
    result = batch_add_entry_links(db, case_id=entry.case_id, entry_id=entry.id, current_user=user, links=links,
                                   rationale=f"Added from {SURFACES[surface]}" + (f": {why}" if why else ""),
                                   commit=False)
    record = {"surface": surface, "why": why or None, "origin": "person", "by_user_id": str(user.id),
              "by_name": user.name, "at": _now().isoformat()}
    text = _words(narrative, MAX_NARRATIVE) if narrative else ""
    for link_id in result["added_link_ids"]:
        row = db.get(WorkspaceEntryLink, uuid.UUID(link_id))
        row.link_metadata = {**(row.link_metadata or {}), "addition": record}
        if text:
            db.add(TheoryNarrative(id=uuid.uuid4(), case_id=entry.case_id, entry_id=entry.id, link_id=row.id,
                                   text=text, origin="person", user_id=user.id, citations=[], basis={}))
    if commit:
        db.commit()
    else:
        db.flush()
    return {**result, "group": selection}


def new_theory(db, *, case_id, user: User, title: str, statement: str | None = None, **addition) -> dict[str, Any]:
    """A new theory built from this: the theory, then the addition, in one change."""
    title = _words(title, 300)
    if not title:
        raise AdditionError("Name the theory")
    entry = create_entry(db, case_id=_uuid(case_id), current_user=user, entry_type="theory", title=title,
                         body=_words(statement, 20000) or title)
    result = add(db, case_id=case_id, entry_id=entry["id"], user=user, **addition)
    return {**result, "entry_id": entry["id"], "title": title}


def mark_agent_addition(db, link_ids: Iterable[str], *, model: str, why: str | None, proposal_id: str,
                        accepted_by: User) -> None:
    """An addition made by accepting an agent proposal: the model chose it, a person accepted it."""
    record = {"surface": "agent", "why": _words(why, MAX_WHY) or None, "origin": "agent", "model": model,
              "proposal_id": proposal_id, "by_user_id": str(accepted_by.id), "by_name": accepted_by.name,
              "accepted_by_name": accepted_by.name, "at": _now().isoformat()}
    for link_id in link_ids:
        row = db.get(WorkspaceEntryLink, _uuid(link_id))
        if row is not None:
            row.link_metadata = {**(row.link_metadata or {}), "addition": record}


# --- what an addition holds, as facts a reader (or the model) can cite ----------------------------------------------

def _money(minor: int, currency: str) -> str:
    from services.financial.money import Money
    try:
        return Money(minor, currency).format()
    except Exception:  # noqa: BLE001 - an unknown currency still shows its number
        return f"{minor / 100:,.2f} {currency}"


def _transaction_facts(db, case_id, ids: list[str]) -> dict[str, dict[str, Any]]:
    from postgres.models.financial import FinancialTransaction as T
    wanted = [u for u in (_uuid(i) for i in ids) if u]
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(wanted), 1000):
        for row in db.scalars(select(T).where(T.case_id == case_id, T.id.in_(wanted[start:start + 1000]))):
            day = row.transaction_date or row.posted_date or row.value_date or row.ordering_date
            way = "in" if row.direction == "credit" else "out"
            text = (f"{day.isoformat() if day else 'undated'} · {_money(row.amount_minor, row.currency)} {way} · "
                    f"{row.description or row.ref_id}" + (f" · {row.counterparty_raw}" if row.counterparty_raw else ""))
            state = "corrected" if row.superseded_by_id else ("rejected" if row.ledger_status == "rejected" else "present")
            if state == "corrected":
                text += " · corrected: this row was replaced; the correction is what counts"
            label = (f"{day.isoformat() if day else 'undated'} · {_money(row.amount_minor, row.currency)} {way} · "
                     f"{row.description or row.ref_id}")[:160]
            out[str(row.id)] = {"text": text, "label": label, "date": day.isoformat() if day else None, "state": state,
                                "amount_minor": row.amount_minor, "currency": row.currency, "direction": row.direction,
                                **({"corrected_by": str(row.superseded_by_id)} if row.superseded_by_id else {})}
    return out


def _evidence_facts(db, case_id, ids: list[str]) -> dict[str, dict[str, Any]]:
    from postgres.models.evidence import EvidenceFile
    from postgres.soft_delete import showing_deleted
    wanted = [u for u in (_uuid(i) for i in ids) if u]
    out: dict[str, dict[str, Any]] = {}
    if not wanted:
        return out
    with showing_deleted(db):
        rows = db.execute(select(EvidenceFile.id, EvidenceFile.original_filename, EvidenceFile.summary,
                                 EvidenceFile.deleted_at).where(EvidenceFile.case_id == case_id,
                                                                EvidenceFile.id.in_(wanted))).all()
    for fid, name, summary, deleted in rows:
        text = name + (f": {' '.join(summary.split())}" if summary else "")
        out[str(fid)] = {"text": text, "label": name, "state": "deleted" if deleted else "present"}
    return out


def member_facts(db, case_id, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each member as {ref, type, id, label, text, state, date?}: what a person sees and what the model may cite."""
    by_type: dict[str, list[str]] = {}
    for m in members:
        by_type.setdefault(m["type"], []).append(m["id"])
    known: dict[tuple[str, str], dict[str, Any]] = {}
    if by_type.get("financial_transaction"):
        known.update({("financial_transaction", k): v
                      for k, v in _transaction_facts(db, case_id, by_type["financial_transaction"]).items()})
    if by_type.get("evidence"):
        known.update({("evidence", k): v for k, v in _evidence_facts(db, case_id, by_type["evidence"]).items()})
    if by_type.get("graph_entity") or by_type.get("timeline_event"):
        # Dated graph nodes (events on the timeline) carry their date, so a theory can be read as a timeline.
        keys = by_type.get("graph_entity", []) + by_type.get("timeline_event", [])
        try:
            dates = case_selections.graph_event_dates(str(case_id), keys)
        except Exception:  # noqa: BLE001 - without the graph the members still show, undated
            dates = {}
        for kind in ("graph_entity", "timeline_event"):
            for key in by_type.get(kind, []):
                if key in dates:
                    known[(kind, key)] = {"date_shown": dates[key]["date"], "name": dates[key]["name"]}
    out = []
    for m in members:
        fact = known.get((m["type"], m["id"]), {})
        # A ledger row or file is named by what it is now; other members by the words they were chosen with.
        if m["type"] in ("financial_transaction", "evidence"):
            label = fact.get("label") or m.get("label") or m["id"]
        else:
            label = m.get("label") or fact.get("name") or fact.get("label") or m["id"]
        if "date_shown" in fact:
            fact = {**fact, "date": case_selections.iso_day(fact["date_shown"]) or fact["date_shown"]}
        state = m.get("state") if m.get("state") not in (None, "present") else fact.get("state", "present")
        if m["type"] in ("evidence", "financial_transaction") and (m["type"], m["id"]) not in known:
            state = "gone"
        text = fact.get("text") or f"{m['type'].replace('_', ' ')}: {label}"
        if state == "deleted":
            text += " · deleted, in Deleted items"
        elif state == "gone":
            text += " · no longer in the case"
        out.append({"ref": f"{m['type']}:{m['id']}", "type": m["type"], "id": m["id"], "label": label,
                    "text": text[:MAX_FACT], "state": state,
                    **{k: fact[k] for k in ("date", "date_shown", "amount_minor", "currency", "direction", "corrected_by") if k in fact}})
    return out


def _single_members(link: WorkspaceEntryLink) -> list[dict[str, Any]]:
    anchor = link.source_anchor or {}
    member = {"type": link.target_type, "id": link.target_id, "label": link.target_label or link.target_id}
    if link.target_type == "agent_answer":
        member["label"] = link.target_label or "Agent answer"
    return [member]


def _single_text(link: WorkspaceEntryLink, fact: dict[str, Any]) -> str:
    anchor = link.source_anchor or {}
    if link.target_type == "agent_answer":
        return (f"Agent answer ({anchor.get('model') or 'the case agent'}, a model reading): "
                f"{' '.join(str(anchor.get('excerpt') or '').split())}")[:MAX_FACT * 4]
    if link.target_type == "evidence_passage":
        return (f"Quote from {anchor.get('document_name') or 'a document'}"
                + (f", page {anchor.get('page_label') or anchor.get('page_number')}" if anchor.get('page_number') else "")
                + f": “{anchor.get('quote') or ''}”")[:MAX_FACT * 2]
    return fact["text"]


def addition_members(db, case_id, link: WorkspaceEntryLink, *, limit: int | None = None) -> dict[str, Any]:
    """The members of one addition with their facts: {members, member_count, members_shown, group?}."""
    if link_types.is_group_type(link.target_type):
        group = case_selections.describe(db, case_id, link.target_id, member_limit=limit if limit is not None else 10**9)
        if group is None:
            return {"members": [], "member_count": 0, "members_shown": 0, "group": None,
                    "missing": "This group is no longer held."}
        facts = member_facts(db, case_id, group["members"])
        return {"members": facts, "member_count": group["member_count"], "members_shown": len(facts),
                "group": {k: group[k] for k in ("id", "group_type", "surface", "label", "words", "how", "member_count",
                                                "left_out", "created_at")}}
    members = _single_members(link)
    facts = member_facts(db, case_id, members)
    for fact in facts:
        fact["text"] = _single_text(link, fact)
    return {"members": facts, "member_count": 1, "members_shown": 1, "group": None}


# --- narratives -------------------------------------------------------------------------------------------------------

def _names(db, ids: Iterable[Any]) -> dict[str, str]:
    wanted = [u for u in {_uuid(i) for i in ids if i} if u]
    if not wanted:
        return {}
    return {str(i): n for i, n in db.execute(select(User.id, User.name).where(User.id.in_(wanted)))}


def serialize_narrative(row: TheoryNarrative, names: Mapping[str, str]) -> dict[str, Any]:
    person = names.get(str(row.user_id)) if row.user_id else None
    confirmer = names.get(str(row.confirmed_by_user_id)) if row.confirmed_by_user_id else None
    if row.origin == "agent":
        words = f"Model reading · {row.model}"
        words += f" · confirmed by {confirmer}" if confirmer else " · not confirmed"
    else:
        words = f"Written by {person or 'a person'}"
    return {
        "id": str(row.id), "link_id": str(row.link_id) if row.link_id else None, "text": row.text,
        "origin": row.origin, "model": row.model, "words": words,
        "written_by": person if row.origin == "person" else None,
        "asked_by": person if row.origin == "agent" else None,
        "citations": list(row.citations or []), "basis": dict(row.basis or {}),
        "replaces_id": str(row.replaces_id) if row.replaces_id else None,
        "confirmed_by": confirmer, "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _narratives(db, entry_id) -> list[TheoryNarrative]:
    return list(db.scalars(select(TheoryNarrative).where(TheoryNarrative.entry_id == entry_id)
                           .order_by(TheoryNarrative.created_at, TheoryNarrative.id)))


def _current(rows: list[TheoryNarrative]) -> TheoryNarrative | None:
    replaced = {r.replaces_id for r in rows if r.replaces_id}
    live = [r for r in rows if r.id not in replaced]
    return live[-1] if live else None


def _versions(rows: list[TheoryNarrative], link_id) -> list[TheoryNarrative]:
    return [r for r in rows if r.link_id == link_id]


def write_narrative(db, *, case_id, entry_id, link_id=None, text: str, user: User) -> dict[str, Any]:
    """A person's own narrative for an addition (or for the theory when link_id is None). Replaces, never erases."""
    entry = _entry(db, case_id, entry_id)
    link = _link(db, entry, link_id) if link_id else None
    text = str(text or "").strip()[:MAX_NARRATIVE]
    if not text:
        raise AdditionError("Write what it shows")
    rows = _versions(_narratives(db, entry.id), link.id if link else None)
    before = _current(rows)
    row = TheoryNarrative(id=uuid.uuid4(), case_id=entry.case_id, entry_id=entry.id, link_id=link.id if link else None,
                          text=text, origin="person", user_id=user.id, citations=[], basis={},
                          replaces_id=before.id if before else None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_narrative(row, _names(db, [row.user_id]))


def confirm_narrative(db, *, case_id, entry_id, narrative_id, user: User) -> dict[str, Any]:
    """A person confirms a model reading as it stands. It stays the model's reading, now confirmed by them."""
    entry = _entry(db, case_id, entry_id)
    row = db.get(TheoryNarrative, _uuid(narrative_id)) if _uuid(narrative_id) else None
    if row is None or row.entry_id != entry.id:
        raise WorkspaceEntryNotFound("That narrative is not on this entry")
    if row.origin != "agent":
        raise AdditionError("A person's own narrative needs no confirming")
    if _current(_versions(_narratives(db, entry.id), row.link_id)) is not row:
        raise AdditionError("A later narrative replaced this one; confirm the current one")
    if row.confirmed_by_user_id is None:
        row.confirmed_by_user_id = user.id
        row.confirmed_at = _now()
        db.commit()
    return serialize_narrative(row, _names(db, [row.user_id, row.confirmed_by_user_id]))


_MARK = re.compile(r"\[(m\d+|a\d+)\]")


def _default_generator(db, case_id) -> Generator:
    def run(prompt: str):
        from postgres.models.cost_record import CostJobType
        from services.ai_costs_service import ai_cost_context
        from services.workspace_ai_service import WorkspaceAIError, _default_generator as generate
        with ai_cost_context(job_type=CostJobType.AI_ASSISTANT, case_id=_uuid(case_id), meter_calls=True,
                             description="Theory: narrative of an addition"):
            try:
                return generate(db, prompt=prompt)
            except WorkspaceAIError as exc:
                raise AdditionError(str(exc)) from exc
    return run


def _prompt(*, theory: WorkspaceEntry, subject: str, facts: list[tuple[str, str]], read: int, total: int,
            whole: bool) -> str:
    lines = "\n".join(f"[{mark}] {text}" for mark, text in facts)
    more = f"\nYou were given {read} of its {total} members; say so if it matters." if read < total else ""
    task = ("Write how these additions fit together as one account: what each contributes and how they connect. "
            if whole else "Write what this addition shows and what it finds. ")
    return (
        f"You are reading part of an investigator's theory titled \"{theory.title or 'Untitled'}\".\n"
        f"Theory statement: {' '.join((theory.body or '').split())[:1500]}\n\n{subject}{more}\n\n"
        f"Items (each with its mark):\n{lines}\n\n"
        f"{task}Use 2 to 6 plain sentences. State only what the items show; do not guess beyond them, and say plainly "
        "when something is not shown. Put the mark of every item you rely on in square brackets after the claim, "
        "e.g. [m3]. Return a JSON object: {\"narrative\": \"...\", \"citations\": [\"m3\", ...]}."
    )


def infer_narrative(db, *, case_id, entry_id, link_id=None, user: User,
                    generator: Generator | None = None) -> dict[str, Any]:
    """The model's reading of an addition (or of how the theory's additions fit together), from its members, with a
    citation to each member it relies on. Saved as a model reading under the model's name; the person who asked is
    recorded as asking, not as its author. Refused, with nothing saved, if it cites nothing it was given."""
    entry = _entry(db, case_id, entry_id)
    rows = _narratives(db, entry.id)
    if link_id:
        link = _link(db, entry, link_id)
        held = addition_members(db, entry.case_id, link, limit=READ_LIMIT)
        facts = held["members"]
        total = held["member_count"]
        why = (link.link_metadata or {}).get("addition", {}).get("why")
        group = held.get("group")
        subject = (f"This addition is: {link.target_label or link.target_type}."
                   + (f" It was chosen: {why}." if why else "")
                   + (f" How it was chosen: {json.dumps(group['how'])[:600]}." if group and group.get("how") else ""))
        marks = [(f"m{i + 1}", f) for i, f in enumerate(facts)]
        refs = {mark: {"mark": mark, "ref": f["ref"], "label": f["label"]} for mark, f in marks}
        prompt_facts = [(mark, f["text"]) for mark, f in marks]
        target_link = link.id
    else:
        if entry.entry_type != "theory":
            raise AdditionError("Only a theory has a whole to explain")
        links = sorted(entry.links, key=_added_order)
        if not links:
            raise AdditionError("This theory holds nothing yet")
        prompt_facts, refs = [], {}
        for i, l in enumerate(links[:READ_LIMIT]):
            mark = f"a{i + 1}"
            now = _current(_versions(rows, l.id))
            why = (l.link_metadata or {}).get("addition", {}).get("why")
            text = (f"{l.target_label or l.target_type}" + (f" — chosen: {why}" if why else "")
                    + (f" — its narrative ({'model reading' if now.origin == 'agent' and not now.confirmed_at else 'person'}): {now.text}"
                       if now else " — no narrative yet"))
            prompt_facts.append((mark, text[:MAX_FACT * 3]))
            refs[mark] = {"mark": mark, "ref": f"link:{l.id}", "label": l.target_label or l.target_type}
        total = len(links)
        subject = "Below are the theory's additions, in the order they were added."
        target_link = None
    if not prompt_facts:
        raise AdditionError("There is nothing in this addition to read")
    run = generator or _default_generator(db, entry.case_id)
    content, meta = run(_prompt(theory=entry, subject=subject, facts=prompt_facts, read=len(prompt_facts),
                                total=total, whole=target_link is None))
    text = str((content or {}).get("narrative") or "").strip()[:MAX_NARRATIVE]
    if not text:
        raise AdditionError("The model returned no narrative; nothing was saved")
    named = [str(c) for c in (content.get("citations") or []) if isinstance(c, (str, int))]
    named += _MARK.findall(text)
    marks = list(dict.fromkeys(m.strip("[]") for m in named))
    valid = [refs[m] for m in marks if m in refs]
    invalid = [m for m in marks if m not in refs]
    if not valid:
        raise AdditionError("The model's reading cited none of the items it was given, so it was not saved")
    model = str(meta.get("model_id") or meta.get("provider") or "the case model")[:128]
    before = _current(_versions(rows, target_link))
    row = TheoryNarrative(id=uuid.uuid4(), case_id=entry.case_id, entry_id=entry.id, link_id=target_link, text=text,
                          origin="agent", user_id=user.id, model=model, citations=valid,
                          basis={"read": len(prompt_facts), "of": total, "invalid_citations": len(invalid),
                                 **({"invalid_marks": invalid[:20]} if invalid else {})},
                          replaces_id=before.id if before else None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_narrative(row, _names(db, [row.user_id]))


# --- reading ----------------------------------------------------------------------------------------------------------

def _addition(link: WorkspaceEntryLink, rows: list[TheoryNarrative], names: Mapping[str, str]) -> dict[str, Any]:
    record = dict((link.link_metadata or {}).get("addition") or {})
    anchor = link.source_anchor or {}
    versions = _versions(rows, link.id)
    current = _current(versions)
    group = link_types.is_group_type(link.target_type)
    origin = record.get("origin") or ("agent" if link.target_type == "agent_answer" else "person")
    return {
        "link_id": str(link.id), "target_type": link.target_type, "target_id": link.target_id,
        "label": link.target_label or link.target_id, "relationship": link.relationship_type,
        "kind": "group" if group else "single",
        "surface": record.get("surface") or anchor.get("surface"),
        "why": record.get("why") or (anchor.get("words") if group else None),
        "how": anchor.get("how") if group else None,
        "member_count": anchor.get("member_count") if group else 1,
        "left_out": anchor.get("left_out") if group else 0,
        "origin": origin, "model": record.get("model") or (anchor.get("model") if link.target_type == "agent_answer" else None),
        "model_reading": link.target_type == "agent_answer",
        "added_by": record.get("by_name") or names.get(str(link.created_by_user_id)) or None,
        "accepted_by": record.get("accepted_by_name"),
        "added_at": link.created_at.isoformat() if link.created_at else None,
        "source_anchor": anchor,
        "narrative": serialize_narrative(current, names) if current else None,
        "narrative_versions": len(versions),
    }


def reading(db, *, case_id, entry_id) -> dict[str, Any]:
    """The theory read as a whole: each addition with its why and narrative, and how it all fits together."""
    entry = _entry(db, case_id, entry_id)
    rows = _narratives(db, entry.id)
    links = sorted(entry.links, key=_added_order)
    names = _names(db, [l.created_by_user_id for l in links] + [r.user_id for r in rows]
                   + [r.confirmed_by_user_id for r in rows])
    fit = _current(_versions(rows, None))
    return {
        "entry": {"id": str(entry.id), "entry_type": entry.entry_type, "title": entry.title, "body": entry.body,
                  "version": entry.version},
        "additions": [_addition(l, rows, names) for l in links],
        "fit": serialize_narrative(fit, names) if fit else None,
        "fit_versions": len(_versions(rows, None)),
    }


def loupe(db, *, case_id, entry_id, link_id, member_limit: int = 2000) -> dict[str, Any]:
    """One addition alone, viewed through its Loupe: its members (with their state now), why it was chosen, and
    every version of its narrative, newest first. ``members_shown`` of ``member_count`` says when the list is cut."""
    entry = _entry(db, case_id, entry_id)
    link = _link(db, entry, link_id)
    rows = _narratives(db, entry.id)
    versions = _versions(rows, link.id)
    names = _names(db, [link.created_by_user_id] + [r.user_id for r in versions]
                   + [r.confirmed_by_user_id for r in versions])
    held = addition_members(db, entry.case_id, link, limit=member_limit)
    return {
        "entry": {"id": str(entry.id), "title": entry.title, "entry_type": entry.entry_type},
        "addition": _addition(link, rows, names),
        **held,
        "history": [serialize_narrative(r, names) for r in reversed(versions)],
    }


UNION_LIMIT = 5000


def union(db, *, case_id, entry_id, limit: int = UNION_LIMIT) -> dict[str, Any]:
    """The theory's own timeline, graph and map: every member of every addition, once, with the additions it is in.
    ``members_shown`` of ``member_count`` says when the list is cut at ``limit``; nothing is cut silently."""
    entry = _entry(db, case_id, entry_id)
    links = sorted(entry.links, key=_added_order)
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for link in links:
        held = addition_members(db, entry.case_id, link, limit=limit)
        for member in held["members"]:
            ref = member["ref"]
            if ref not in seen:
                seen[ref] = {**member, "additions": []}
                order.append(ref)
            seen[ref]["additions"].append(str(link.id))
    members = [seen[ref] for ref in order]
    shown = members[:limit]
    return {"entry": {"id": str(entry.id), "title": entry.title}, "members": shown, "member_count": len(members),
            "members_shown": len(shown),
            "dated": sum(1 for m in shown if m.get("date")),
            "graph_keys": [m["id"] for m in shown if m["type"] == "graph_entity"]}
