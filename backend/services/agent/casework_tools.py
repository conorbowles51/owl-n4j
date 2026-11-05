"""The agent reads the case's casework and dossiers, with their phone links cited (docs/cellebrite/07 section 6.4
item 15, test CO-11).

Schemas ``loupe.agent.casework/1`` and ``loupe.agent.dossier/1``. Every link comes back with a ``citation``: a phone
record as ``rec://<record id>`` with the record read in full (Neil, 2026-11-01: "the agent should have full
visibility of the phones"; sensitive values stay masked as on screen), a phone thread, file, identity, phone,
analysis or selection by its own key with what it holds, and evidence as ``doc://<file name>``. A link whose target
is no longer in the case is returned with ``state`` and never dropped. A phone link whose record was corrected, read
differently or set aside since it was collected carries ``link_state`` in words (07 section 6.3), so an answer that
cites it can say so.

Case scope: the case id is the run's; a dossier or entry of another case is "Not in this case.", the same words
whether or not it exists elsewhere.
"""
from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

from sqlalchemy import or_, select, text

NOT_IN_CASE = "Not in this case."
LINK_STATE_NOTE = ("Links with link_state here: %d. What they collected changed after they were made. Say so whenever "
                   "you cite one, in the words of link_state.")
RECORD_TEXT_LIMIT = 4000
SELECTION_RECS = 25


def _schema(tool: str) -> str:
    return "loupe.agent.%s/1" % tool


def _clip(value: str | None, limit: int) -> tuple[str | None, bool]:
    if value is None or len(value) <= limit:
        return value, False
    return value[:limit], True


def _record_citation(conn, case_id, record_uid: str) -> dict[str, Any]:
    from services.agent import phone_tools
    out = phone_tools.record(conn, case_id, record_uid)
    if not out.get("available"):
        return {"rec": "rec://%s" % record_uid, "state": "not_in_case", "reason": out.get("reason")}
    item = out["items"][0]
    body, clipped = _clip(item.get("text"), RECORD_TEXT_LIMIT)
    cite = {"rec": item["rec"], "phone": item.get("phone"), "model_type": item.get("model_type"), "text": body,
            "corrections": item.get("corrections") or []}
    if clipped:
        cite["clipped"] = ("The record's text is cut at %d characters here; read it in full with phone_record %s."
                           % (RECORD_TEXT_LIMIT, item["rec"]))
    return cite


def _thread_citation(conn, case_id, thread_key: str) -> dict[str, Any]:
    rows = conn.execute(text(
        "SELECT title_in_record, coalesce(event_count, 0) AS n FROM pv_thread WHERE case_id = :c AND thread_key = :k"),
        {"c": str(case_id), "k": thread_key}).fetchall()
    if not rows:
        return {"thread": thread_key, "state": "not_in_case", "reason": "%s No such conversation." % NOT_IN_CASE}
    return {"thread": thread_key, "title": next((r.title_in_record for r in rows if r.title_in_record), None),
            "records": sum(int(r.n) for r in rows),
            "read_with": "phone_messages (the conversation's people) or phone_record per rec:// link"}


def _selection_citation(link_anchor: dict, target) -> dict[str, Any]:
    members = list(getattr(target, "members", None) or (link_anchor or {}).get("record_ids") or [])
    shown = ["rec://%s" % m for m in members[:SELECTION_RECS]]
    cite = {"selection_size": len(members), "recs": shown}
    if len(members) > len(shown):
        cite["clipped"] = "%d of %d records are listed here; the selection holds all %d." % (
            len(shown), len(members), len(members))
    return cite


def cite_link(db, conn, case_id, target_type: str, target_id: str, anchor: dict | None) -> dict[str, Any]:
    """One link's citation. Phone targets are checked against the case through the registry's resolver."""
    from postgres import link_types
    anchor = dict(anchor or {})
    if link_types.is_phone_type(target_type):
        if target_type == "phone_record":
            return _record_citation(conn, case_id, target_id)
        if target_type == "phone_thread":
            return _thread_citation(conn, case_id, target_id)
        try:
            target = link_types.resolve_phone_target(db, case_id, target_type, target_id)
        except link_types.LinkTargetError as exc:
            return {"state": "not_in_case", "reason": "%s %s" % (NOT_IN_CASE, exc)}
        cite: dict[str, Any] = {"label": target.label}
        if target_type == "phone_selection":
            cite.update(_selection_citation(anchor, target))
        elif target_type in ("phone_analysis", "statement_check") and target.snapshot is not None:
            snap = dict(target.snapshot)
            cite.update({"kind": snap.get("kind"), "window": snap.get("window"),
                         "summary_counts": snap.get("summary_counts"),
                         "recs": ["rec://%s" % r for r in (snap.get("record_ids") or [])[:SELECTION_RECS]]})
        elif target_type == "phone_file":
            cite["file"] = target_id
        elif target_type == "phone_identity":
            cite["identity_key"] = target_id
        elif target_type == "phone_extraction":
            cite["phone"] = target.label
        return cite
    if target_type == "evidence":
        name = conn.execute(text("SELECT original_filename FROM evidence_files WHERE id::text = :i AND case_id = :c "
                                 "AND deleted_at IS NULL"),
                            {"i": target_id, "c": str(case_id)}).scalar()
        if name is None:
            return {"state": "not_in_case", "reason": "%s No such evidence file." % NOT_IN_CASE}
        page = anchor.get("page")
        return {"doc": "doc://%s%s" % (quote(name, safe=""), "/%s" % page if page else ""), "file": name}
    return {"target": "%s:%s" % (target_type, target_id)}


def _link_out(db, conn, case_id, link, *, label_attr: str) -> dict[str, Any]:
    return {"id": str(link.id), "target_type": link.target_type, "target_id": link.target_id,
            "label": getattr(link, label_attr, None),
            "relationship": getattr(link, "relationship_type", None),
            "citation": cite_link(db, conn, case_id, link.target_type, link.target_id, link.source_anchor)}


def _with_link_states(links: list[dict], found: dict) -> int:
    """Put each link's state on it; returns how many have one."""
    marked = 0
    for link in links:
        state = found.get(str(link.get("id")))
        if state:
            link["link_state"] = state
            marked += 1
    return marked


def _link_state_note(marked: int) -> str | None:
    return LINK_STATE_NOTE % marked if marked else None


def _phone_link_count(links: list[dict]) -> int:
    return sum(1 for l in links if str(l["target_type"]).startswith("phone_") or l["target_type"] == "statement_check")


def casework(db, case_id, *, kinds=(), search=None, offset=0, limit=20) -> dict[str, Any]:
    """Notes, findings and theories, newest first, each with its links cited."""
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
    from services.phone import link_states
    conn = db.connection()
    cond = [WorkspaceEntry.case_id == case_id, WorkspaceEntry.deleted_at.is_(None)]
    if kinds:
        cond.append(WorkspaceEntry.entry_type.in_(list(kinds)))
    if search and search.strip():
        pattern = "%%%s%%" % search.strip()
        cond.append(or_(WorkspaceEntry.title.ilike(pattern), WorkspaceEntry.body.ilike(pattern)))
    from sqlalchemy import func
    total = int(db.scalar(select(func.count()).select_from(WorkspaceEntry).where(*cond)) or 0)
    offset, limit = max(0, int(offset or 0)), max(1, min(int(limit or 20), 50))
    entries = db.scalars(select(WorkspaceEntry).where(*cond).order_by(WorkspaceEntry.updated_at.desc(),
                                                                       WorkspaceEntry.id).offset(offset).limit(limit)).all()
    items = []
    for e in entries:
        links = db.scalars(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id == e.id,
                                                            WorkspaceEntryLink.case_id == case_id)
                           .order_by(WorkspaceEntryLink.created_at, WorkspaceEntryLink.id)).all()
        out_links = [_link_out(db, conn, case_id, l, label_attr="target_label") for l in links]
        items.append({"id": str(e.id), "kind": e.entry_type, "title": e.title, "body": e.body, "tags": e.tags,
                      "significance": e.significance, "confidence": e.confidence, "state": e.lifecycle_state,
                      "review_state": e.review_state, "author": e.author_name or e.author_email,
                      "updated_at": e.updated_at.isoformat() if e.updated_at else None,
                      "links": out_links, "phone_links": _phone_link_count(out_links)})
    collecting = [l for e in entries for l in link_states.entry_links(conn, case_id, e.id)]
    found = link_states.for_readers(conn, case_id, collecting)
    marked = sum(_with_link_states(i["links"], found) for i in items)
    nxt = offset + len(items) if offset + len(items) < total else None
    return {"schema": _schema("casework"), "case_id": str(case_id), "available": True, "total_matching": total,
            "returned": len(items), "has_more": nxt is not None, "next_offset": nxt, "items": items,
            "coverage": "Read %d of %d casework entries%s." % (
                len(items), total, " (%s)" % ", ".join(kinds) if kinds else ""),
            "limitation": ("Only %d of %d are in this result; read on with offset %d." % (len(items), total, nxt))
            if nxt is not None else None, "link_states": _link_state_note(marked)}


def _find_dossier(db, case_id, ref: str):
    from postgres.models.case_profile import CaseProfile
    ref = (ref or "").strip()
    try:
        did = uuid.UUID(ref)
    except ValueError:
        did = None
    if did is not None:
        row = db.get(CaseProfile, did)
        return ([row] if row is not None and row.case_id == case_id else [])
    return db.scalars(select(CaseProfile).where(CaseProfile.case_id == case_id, CaseProfile.archived_at.is_(None),
                                                CaseProfile.display_name.ilike("%%%s%%" % ref))
                      .order_by(CaseProfile.display_name).limit(21)).all()


def dossier(db, case_id, dossier: str) -> dict[str, Any]:
    """One dossier with its links, assessments (with how each was made) and interviews' evidence, links cited."""
    from services import dossier_service as D
    from services.phone import link_states
    conn = db.connection()
    ref = dossier
    found = _find_dossier(db, case_id, ref)
    base = {"schema": _schema("dossier"), "case_id": str(case_id)}
    if not found:
        return {**base, "available": False, "not_in_case": True, "total_matching": 0, "returned": 0,
                "has_more": False, "items": [], "reason": "%s No dossier matches %s." % (NOT_IN_CASE, ref)}
    if len(found) > 1:
        return {**base, "available": False, "ambiguous": True, "total_matching": len(found), "returned": 0,
                "has_more": False, "items": [],
                "candidates": [{"id": str(d.id), "name": d.display_name, "type": d.profile_type} for d in found[:20]],
                "reason": "%s%d dossiers match %s; ask which one, by id." % (
                    "More than 20; the first 20 are listed. " if len(found) > 20 else "", min(len(found), 20), ref)}
    d = found[0]
    try:
        data = D.serialize_dossier(db, d)
    except Exception:
        # the graph identity could not be read; the dossier itself still can
        data = D.serialize_dossier(db, d, detail=False)
        data.update({"links": [D._serialize_link(l) for l in db.scalars(select(D.DossierLink).where(
            D.DossierLink.dossier_id == d.id).order_by(D.DossierLink.created_at)).all()],
            "assessments": [D._serialize_assessment(db, a) for a in db.scalars(select(D.DossierAssessment).where(
                D.DossierAssessment.dossier_id == d.id).order_by(D.DossierAssessment.created_at.desc())).all()],
            "interviews": [], "identity_note": "The graph identity could not be read just now."})

    def cite_all(links):
        return [{**l, "citation": cite_link(db, conn, case_id, l["target_type"], l["target_id"], l.get("source_anchor"))}
                for l in links]
    links = cite_all(data.get("links") or [])
    for l in links:
        l.pop("source_anchor", None)
    assessments = []
    for a in data.get("assessments") or []:
        sup = cite_all(a.get("supporting_links") or [])
        for l in sup:
            l.pop("source_anchor", None)
        assessments.append({"id": a["id"], "category": a["category"], "content": a["content"],
                            "date": a.get("assessment_date"), "provenance": a.get("provenance_type"),
                            "read_by": a.get("read_by"), "supporting_links": sup})
    interviews = []
    for i in data.get("interviews") or []:
        ev = []
        for e in i.get("evidence_links") or []:
            tt, tid = e.get("target_type") or ("evidence" if e.get("evidence_file_id") else None), \
                e.get("target_id") or e.get("evidence_file_id")
            if tt and tid:
                ev.append({"id": e.get("id"), "target_type": tt, "target_id": tid,
                           "citation": cite_link(db, conn, case_id, tt, str(tid), e.get("source_anchor"))})
        interviews.append({"id": i.get("id"), "date": i.get("date_value"), "participants": i.get("participants"),
                           "status": i.get("status"), "evidence": ev})
    found = link_states.for_readers(conn, case_id, link_states.dossier_links(conn, case_id, d.id))
    marked = (_with_link_states(links, found) + sum(_with_link_states(a["supporting_links"], found) for a in assessments)
              + sum(_with_link_states(i["evidence"], found) for i in interviews))
    item = {"id": data["id"], "name": data["display_name"], "type": data["dossier_type"], "summary": data["summary"],
            "status": data["status"], "importance": data["importance"], "contacts": data["contacts"],
            "graph_entity": data["canonical_entity_key"], "links": links, "assessments": assessments,
            "interviews": interviews, "phone_links": _phone_link_count(links)}
    if data.get("identity_note"):
        item["identity_note"] = data["identity_note"]
    return {**base, "available": True, "total_matching": 1, "returned": 1, "has_more": False, "next_offset": None,
            "items": [item],
            "coverage": "The whole dossier: %d links (%d to phone material), %d assessments, %d interviews." % (
                len(links), item["phone_links"], len(assessments), len(interviews)),
            "limitation": None, "link_states": _link_state_note(marked)}
