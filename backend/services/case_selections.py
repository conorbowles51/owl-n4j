"""Groups added to a theory as one link: what was chosen and how (lx-theorybuild B).

``freeze`` stores a group: every member named that is in this case, in the order named, with the surface it was
chosen on and how (the filter, range, query or snapshot), and a sentence in the person's words. Each member is
checked against the case by its own type (graph entities in Neo4j by key *and* case, ledger rows, evidence files,
timeline events, phone records); a member that is not in the case is not kept and ``left_out`` says how many, so a
group is never cut silently. Nothing is capped: a group holds every member it was given, up to ``MAX_MEMBERS``,
and a larger group is refused with that number, never trimmed.

``resolve`` is the link check: a group of another case is not found. ``describe`` is what a group link opens on:
"N items from <surface>, chosen <how>", with each member's state now (deleted, corrected) so nothing a theory holds
drops silently.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy import select

from postgres import link_types
from postgres.models.case_selection import GROUP_SURFACES, CaseSelection

MAX_MEMBERS = 50_000
MAX_WORDS = 500

SURFACE_WORDS = {
    "graph": "the graph",
    "significant": "the Significant layer",
    "timeline": "the timeline",
    "financial": "the ledger",
    "evidence": "the evidence files",
    "map": "the map",
}

# Member types each group takes.
GROUP_MEMBER_TYPES: dict[str, tuple[str, ...]] = {
    "graph_selection": ("graph_entity",),
    "significant_set": ("graph_entity",),
    "timeline_range": ("timeline_event", "financial_transaction", "evidence", "phone_record", "graph_entity", "entry"),
    "financial_selection": ("financial_transaction", "financial_account", "financial_party"),
    "evidence_selection": ("evidence",),
    "map_selection": ("graph_entity", "phone_record"),
}


class SelectionError(ValueError):
    """A group was refused; the message is written for the person who made it."""


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


# --- members checked against the case, one query per type -------------------------------------------------------

def graph_keys_in_case(case_id: str, keys: list[str]) -> set[str]:
    """Entity keys that are active nodes of this case. The match is on key and case_id together, never key alone."""
    from services.neo4j_service import neo4j_service
    return set(neo4j_service.get_existing_node_keys(str(case_id), keys))


def _graph(db, case_id, ids):
    return graph_keys_in_case(str(case_id), ids)


def _transactions(db, case_id, ids):
    from postgres.models.financial import FinancialTransaction
    wanted = [u for u in (_uuid(i) for i in ids) if u]
    found: set[str] = set()
    for start in range(0, len(wanted), 1000):
        found.update(str(v) for v in db.scalars(select(FinancialTransaction.id).where(
            FinancialTransaction.case_id == case_id, FinancialTransaction.id.in_(wanted[start:start + 1000]))))
    return found


def _accounts(db, case_id, ids):
    from postgres.models.financial import FinancialAccount
    wanted = [u for u in (_uuid(i) for i in ids) if u]
    return {str(v) for v in db.scalars(select(FinancialAccount.id).where(
        FinancialAccount.case_id == case_id, FinancialAccount.id.in_(wanted)))} if wanted else set()


def _parties(db, case_id, ids):
    from services.financial.account_parties import account_parties
    known = {p["id"] for p in account_parties(db, case_id=case_id)["parties"]}
    return {str(_uuid(i)) for i in ids if _uuid(i) and str(_uuid(i)) in known}


def _evidence(db, case_id, ids):
    from postgres.models.evidence import EvidenceFile
    wanted = [u for u in (_uuid(i) for i in ids) if u]
    found: set[str] = set()
    for start in range(0, len(wanted), 1000):
        found.update(str(v) for v in db.scalars(select(EvidenceFile.id).where(
            EvidenceFile.case_id == case_id, EvidenceFile.deleted_at.is_(None),
            EvidenceFile.id.in_(wanted[start:start + 1000]))))
    return found


def _timeline_events(db, case_id, ids):
    """A timeline event of this case: one added to the timeline (``timeline-entry:<id>``), one kept in a saved view,
    or a dated node of the case's graph (matched by key and case together)."""
    from postgres.models.timeline_entry import TimelineEntry
    from postgres.models.timeline_view import TimelineViewEvent
    from services.timeline_entries import PREFIX
    found: set[str] = set()
    entry_ids = {key: _uuid(key[len(PREFIX):]) for key in ids if key.startswith(PREFIX)}
    wanted = [u for u in entry_ids.values() if u]
    if wanted:
        kept = {str(v) for v in db.scalars(select(TimelineEntry.id).where(
            TimelineEntry.case_id == case_id, TimelineEntry.id.in_(wanted)))}
        found.update(key for key, u in entry_ids.items() if u and str(u) in kept)
    rest = [key for key in ids if key not in entry_ids]
    for start in range(0, len(rest), 1000):
        found.update(db.scalars(select(TimelineViewEvent.event_key).where(
            TimelineViewEvent.case_id == case_id, TimelineViewEvent.event_key.in_(rest[start:start + 1000]))))
    unknown = [key for key in rest if key not in found]
    if unknown:
        found.update(graph_keys_in_case(str(case_id), unknown))
    return found


def _entries(db, case_id, ids):
    from postgres.models.workspace_entry import WorkspaceEntry
    wanted = [u for u in (_uuid(i) for i in ids) if u]
    return {str(v) for v in db.scalars(select(WorkspaceEntry.id).where(
        WorkspaceEntry.case_id == case_id, WorkspaceEntry.deleted_at.is_(None), WorkspaceEntry.id.in_(wanted)))} if wanted else set()


def _phone_records(db, case_id, ids):
    found: set[str] = set()
    for value in ids:
        try:
            link_types.resolve_phone_target(db, case_id, "phone_record", value)
        except link_types.LinkTargetError:
            continue
        found.add(value)
    return found


MEMBER_CHECKS: dict[str, Callable[[Any, uuid.UUID, list[str]], set[str]]] = {
    "graph_entity": _graph,
    "financial_transaction": _transactions,
    "financial_account": _accounts,
    "financial_party": _parties,
    "evidence": _evidence,
    "timeline_event": _timeline_events,
    "phone_record": _phone_records,
    "entry": _entries,
}


def _clean_members(group_type: str, members: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    allowed = GROUP_MEMBER_TYPES[group_type]
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in members:
        if not isinstance(raw, Mapping):
            raise SelectionError("Each member is {type, id}")
        kind = str(raw.get("type") or "").strip()
        ident = str(raw.get("id") or "").strip()[:512]
        if kind not in allowed:
            raise SelectionError(f"A group from {SURFACE_WORDS[GROUP_SURFACES[group_type]]} cannot hold {kind or 'that'}")
        if not ident or (kind, ident) in seen:
            continue
        seen.add((kind, ident))
        member = {"type": kind, "id": ident}
        label = raw.get("label")
        if isinstance(label, str) and label.strip():
            member["label"] = label.strip()[:300]
        out.append(member)
    return out


def freeze(db, *, case_id, group_type: str, members: Iterable[Mapping[str, Any]], how: Mapping[str, Any] | None,
           words: str, user=None, commit: bool = True) -> dict[str, Any]:
    """Store a group: every member of this case, in the order given. Returns its id, counts and what was left out."""
    if group_type not in GROUP_SURFACES:
        raise SelectionError(f"{group_type} is not a kind of group")
    case = _uuid(case_id)
    if case is None:
        raise SelectionError("Name the case")
    if how is not None and not isinstance(how, Mapping):
        raise SelectionError("How the group was chosen must be an object")
    words = " ".join(str(words or "").split())[:MAX_WORDS]
    if not words:
        raise SelectionError("Say in a few words how this group was chosen")
    named = _clean_members(group_type, members)
    if not named:
        raise SelectionError("Nothing is selected, so there is nothing to add.")
    if len(named) > MAX_MEMBERS:
        raise SelectionError(f"{len(named):,} items were chosen; a group holds at most {MAX_MEMBERS:,}. "
                             "Narrow the choice or add it in parts; nothing was added.")
    found: dict[str, set[str]] = {}
    for kind in dict.fromkeys(m["type"] for m in named):
        ids = [m["id"] for m in named if m["type"] == kind]
        found[kind] = MEMBER_CHECKS[kind](db, case, ids)
    kept = [m for m in named if m["id"] in found[m["type"]]]
    left = [m for m in named if m["id"] not in found[m["type"]]]
    if not kept:
        raise SelectionError("None of the chosen items is in this case, so nothing was added.")
    row = CaseSelection(id=uuid.uuid4(), case_id=case, group_type=group_type, words=words, how=dict(how or {}),
                        members=kept, member_count=len(kept), left_out=len(left),
                        created_by_user_id=getattr(user, "id", None))
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
    return {"id": str(row.id), "group_type": group_type, "member_count": len(kept), "left_out": len(left),
            "left_out_examples": [m["id"] for m in left[:20]], "words": words,
            "label": group_label(row)}


def _load(db, case_id, selection_id, group_type: str | None = None) -> CaseSelection | None:
    sid, case = _uuid(selection_id), _uuid(case_id)
    if sid is None or case is None:
        return None
    row = db.get(CaseSelection, sid)
    if row is None or row.case_id != case or (group_type is not None and row.group_type != group_type):
        return None
    return row


def group_label(row: CaseSelection) -> str:
    """'12 items from the graph, chosen: <words>'."""
    noun = "item" if row.member_count == 1 else "items"
    surface = SURFACE_WORDS[GROUP_SURFACES[row.group_type]]
    return f"{row.member_count:,} {noun} from {surface}, chosen: {row.words}"[:512]


def resolve(db, case_id, group_type: str, selection_id: str) -> dict[str, Any]:
    """The link check: the group must be of this case and of this type. Returns label, anchor and member refs."""
    row = _load(db, case_id, selection_id, group_type)
    if row is None:
        raise link_types.LinkTargetError(f"The group {selection_id} was not found in this case")
    anchor = {"surface": GROUP_SURFACES[row.group_type], "how": dict(row.how or {}), "words": row.words,
              "member_count": row.member_count, "left_out": row.left_out}
    return {"label": group_label(row), "anchor": anchor,
            "members": tuple(f"{m['type']}:{m['id']}" for m in row.members or [])}


def _member_states(db, case_id, members: list[dict]) -> dict[tuple[str, str], dict[str, Any]]:
    """Each member's state now, so a deleted or corrected source shows as such and is never dropped."""
    states: dict[tuple[str, str], dict[str, Any]] = {}
    ev = [_uuid(m["id"]) for m in members if m["type"] == "evidence" and _uuid(m["id"])]
    if ev:
        from postgres.models.evidence import EvidenceFile
        from postgres.soft_delete import showing_deleted
        for fid in ev:
            states[("evidence", str(fid))] = {"state": "gone"}
        # A file in Deleted items is read on purpose here, so it shows as deleted (and comes back on restore).
        with showing_deleted(db):
            rows = db.execute(select(EvidenceFile.id, EvidenceFile.original_filename, EvidenceFile.deleted_at).where(
                EvidenceFile.case_id == case_id, EvidenceFile.id.in_(ev))).all()
        for fid, name, deleted in rows:
            states[("evidence", str(fid))] = {"label": name, "state": "deleted" if deleted else "present"}
    tx = [_uuid(m["id"]) for m in members if m["type"] == "financial_transaction" and _uuid(m["id"])]
    if tx:
        from postgres.models.financial import FinancialTransaction as T
        for tid, status, replaced in db.execute(select(T.id, T.ledger_status, T.superseded_by_id).where(
                T.case_id == case_id, T.id.in_(tx))):
            if replaced is not None:
                states[("financial_transaction", str(tid))] = {"state": "corrected", "corrected_by": str(replaced)}
            else:
                states[("financial_transaction", str(tid))] = {"state": "present" if status != "rejected" else status}
    return states


def describe(db, case_id, selection_id, *, member_limit: int = 500) -> dict[str, Any] | None:
    """What a group link opens on: its sentence, surface, how it was chosen, counts and members with their state.

    Members are returned up to ``member_limit``; ``members_shown`` and ``member_count`` say how many of how many."""
    row = _load(db, case_id, selection_id)
    if row is None:
        return None
    members = list(row.members or [])
    shown = members[:max(0, member_limit)]
    states = _member_states(db, row.case_id, shown)
    out_members = []
    for m in shown:
        state = states.get((m["type"], m["id"]), {})
        out_members.append({**m, "state": state.get("state", "present"),
                            **({"corrected_by": state["corrected_by"]} if "corrected_by" in state else {}),
                            **({"label": m.get("label") or state.get("label")} if (m.get("label") or state.get("label")) else {})})
    return {"id": str(row.id), "group_type": row.group_type, "surface": GROUP_SURFACES[row.group_type],
            "label": group_label(row), "words": row.words, "how": dict(row.how or {}),
            "member_count": row.member_count, "left_out": row.left_out, "members": out_members,
            "members_shown": len(out_members),
            "created_by_user_id": str(row.created_by_user_id) if row.created_by_user_id else None,
            "created_at": row.created_at.isoformat() if row.created_at else None}
