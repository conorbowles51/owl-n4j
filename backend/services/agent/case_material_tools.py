"""The agent reads the case material it had no tool for (lx-agentlive G/H, Neil 8 Nov: "I don't know that the agent is
actually working with financials and phones etc and graph and every other type").

- ``evidence_files``: the case's files and their processing state, as the Evidence page lists them, with counts by
  state, failures in the Evidence page's words (``services.evidence_failure_words``) and files held from reading;
- ``interviews``: interviews recorded on the case's dossiers (``dossier_service._serialize_interview``'s fields) and
  the recordings that have a transcript, with the transcript's review state;
- ``transcript``: one recording's transcript: the working text, and whether a person reviewed or published it;
- ``list_dossiers``: every dossier with how much each holds (links, assessments, interviews);
- ``theory``: one theory with every addition (``theory_additions.reading``), each addition's members and the
  narratives, a model's narrative labelled as a model reading until a person confirms it;
- ``significant_layer``: the items marked significant (``significant_service``), with their names from the graph;
- ``reports``: saved financial reports (casework tagged ``financial-report``, as the Reports page lists them) and what
  the casework report (``casework_report``) would hold if it were exported now.

Every function reads only; the case id is the run's (the runner checked access), and a reference to something of
another case is "Not in this case." in the same words whether or not it exists elsewhere. Lists are paged with
``total_matching``, ``returned``, ``has_more`` and ``next_offset``; text cut for length says so.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import func, or_, select

NOT_IN_CASE = "Not in this case."
MAX_LIMIT = 50
NOTES_LIMIT = 2000
TRANSCRIPT_LIMIT = 12000
MEMBERS_SHOWN = 25
FILE_STATES = ("unprocessed", "processing", "processed", "failed")
STATE_WORDS = {"unprocessed": "waiting to be processed", "processing": "being processed", "processed": "processed",
               "failed": "failed"}


def _schema(name: str) -> str:
    return "loupe.agent.%s/1" % name


def _page(offset, limit, default=20) -> tuple[int, int]:
    return max(0, int(offset or 0)), max(1, min(int(limit or default), MAX_LIMIT))


def _clip(value: str | None, limit: int) -> tuple[str | None, str | None]:
    if value is None or len(value) <= limit:
        return value, None
    return value[:limit], "Cut at %d of %d characters here." % (limit, len(value))


def _paged(name, case_id, items, total, offset, **extra) -> dict[str, Any]:
    nxt = offset + len(items) if offset + len(items) < total else None
    out = {"schema": _schema(name), "case_id": str(case_id), "available": True, "total_matching": total,
           "returned": len(items), "offset": offset, "has_more": nxt is not None, "next_offset": nxt, "items": items}
    out.update(extra)
    if nxt is not None and not out.get("limitation"):
        out["limitation"] = "Only %d of %d are in this result; read on with offset %d." % (len(items), total, nxt)
    return out


def _unavailable(name, case_id, reason) -> dict[str, Any]:
    return {"schema": _schema(name), "case_id": str(case_id), "available": False, "not_in_case": True,
            "total_matching": 0, "returned": 0, "has_more": False, "next_offset": None, "items": [], "reason": reason}


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def entry_href(case_id, entry) -> str:
    return "/cases/%s/workspace?view=casework&kind=%s&entry=%s" % (case_id, entry.entry_type, entry.id)


def dossier_href(case_id, dossier_id) -> str:
    return "/cases/%s/dossiers?dossier=%s" % (case_id, dossier_id)


# ---- evidence files ------------------------------------------------------------------------------------------------

def _visible_files(case_id):
    """The Evidence page's files: not deleted (the session's soft-delete filter), not a phone conversation document
    and not a proven internal copy (``source_lineage.visible_evidence_condition``)."""
    from postgres.models.evidence import EvidenceFile
    from services.financial.source_lineage import visible_evidence_condition
    return [EvidenceFile.case_id == case_id, visible_evidence_condition()]


def evidence_files(db, case_id, *, state=None, name=None, offset=0, limit=20) -> dict[str, Any]:
    """The case's files with their processing state: counts by state, then a page of files (failed first, then the
    newest), each with its failure in words."""
    from postgres.models.evidence import EvidenceFile
    from services.evidence_failure_words import plain_failure
    if state not in (None, "", *FILE_STATES):
        raise ValueError("State is one of: %s." % ", ".join(FILE_STATES))
    offset, limit = _page(offset, limit)
    base = _visible_files(case_id)
    by_state = {s: 0 for s in FILE_STATES}
    for s, n in db.execute(select(EvidenceFile.status, func.count()).where(*base).group_by(EvidenceFile.status)):
        by_state[s] = int(n)
    shown_total = sum(by_state.values())
    everything = int(db.scalar(select(func.count()).select_from(EvidenceFile).where(EvidenceFile.case_id == case_id))
                     or 0)
    duplicates = int(db.scalar(select(func.count()).select_from(EvidenceFile).where(
        *base, EvidenceFile.is_duplicate.is_(True))) or 0)
    held = int(db.scalar(select(func.count()).select_from(EvidenceFile).where(
        *base, EvidenceFile.reading_hold.isnot(None))) or 0)
    cond = list(base)
    if state:
        cond.append(EvidenceFile.status == state)
    if name and name.strip():
        cond.append(EvidenceFile.original_filename.ilike("%%%s%%" % name.strip()))
    total = int(db.scalar(select(func.count()).select_from(EvidenceFile).where(*cond)) or 0)
    failed_first = (EvidenceFile.status != "failed")
    rows = db.scalars(select(EvidenceFile).where(*cond).order_by(failed_first, EvidenceFile.created_at.desc(),
                                                                 EvidenceFile.id).offset(offset).limit(limit)).all()
    items = []
    for f in rows:
        item = {"evidence_file_id": str(f.id), "filename": f.original_filename, "state": f.status,
                "state_words": STATE_WORDS.get(f.status, f.status), "doc": "doc://%s" % f.id,
                "added_at": _iso(f.created_at), "processed_at": _iso(f.processed_at), "size_bytes": f.size,
                "copy_of_another_file": bool(f.is_duplicate)}
        if f.status == "failed":
            item["failure"] = plain_failure(f.last_error) if f.last_error else "No reason was recorded."
        if f.reading_hold:
            item["held_from_reading"] = f.reading_hold_reason or f.reading_hold
        if f.processing_stale:
            item["needs_processing_again"] = "Its processing settings changed since it was processed."
        items.append(item)
    hidden = everything - shown_total
    coverage = ("%d file%s on the Evidence page: %d processed, %d waiting, %d being processed, %d failed."
                % (shown_total, "" if shown_total == 1 else "s", by_state["processed"], by_state["unprocessed"], by_state["processing"],
                   by_state["failed"]))
    if hidden:
        coverage += (" A further %d are documents written from phone conversations or internal copies, which the "
                     "Evidence page does not list (%d in all)." % (hidden, everything))
    filters = ", ".join(x for x in (("state %s" % state) if state else None,
                                    ("name containing '%s'" % name.strip()) if name and name.strip() else None) if x)
    return _paged("evidence_files", case_id, items, total, offset, counts_by_state=by_state,
                  files_on_evidence_page=shown_total, files_in_all=everything, copies_of_another_file=duplicates,
                  held_from_reading=held,
                  coverage=coverage + (" %d match %s." % (total, filters) if filters else ""),
                  cite="Cite a file by its doc link.")


# ---- interviews and transcripts --------------------------------------------------------------------------------------

def _transcript_state(db, file) -> dict[str, Any]:
    from postgres.models.transcript import TranscriptState
    state = db.get(TranscriptState, file.id)
    if state is not None:
        if state.published_revision_id:
            words = "published by a person"
        elif state.reviewed_revision_id:
            words = "reviewed by a person"
        else:
            words = "machine transcript, not yet reviewed by a person"
        return {"review": words, "review_required": bool(state.review_required)}
    return {"review": "machine transcript, not yet reviewed by a person", "review_required": None}


def _transcribed_files(case_id):
    from postgres.models.evidence import EvidenceFile
    from postgres.models.transcript import TranscriptSource
    return or_(EvidenceFile.id.in_(select(TranscriptSource.evidence_file_id).where(TranscriptSource.case_id == case_id)),
               (EvidenceFile.transcription.isnot(None)) & (EvidenceFile.transcription != ""))


def interviews(db, case_id, *, dossier=None, offset=0, limit=20) -> dict[str, Any]:
    """Interviews on the case's dossiers, newest first, with participants, state, notes and attached files cited;
    and the count and first page of recordings with a transcript."""
    from postgres.models.case_profile import CaseProfile
    from postgres.models.dossier import DossierInterview, DossierInterviewEvidenceLink
    from postgres.models.evidence import EvidenceFile
    offset, limit = _page(offset, limit)
    cond = [DossierInterview.case_id == case_id]
    if dossier and str(dossier).strip():
        did = _uuid(dossier)
        dcond = [CaseProfile.case_id == case_id]
        dcond.append(CaseProfile.id == did if did else CaseProfile.display_name.ilike("%%%s%%" % str(dossier).strip()))
        ids = list(db.scalars(select(CaseProfile.id).where(*dcond)))
        if not ids:
            return _unavailable("interviews", case_id, "%s No dossier matches %s." % (NOT_IN_CASE, dossier))
        cond.append(DossierInterview.dossier_id.in_(ids))
    total = int(db.scalar(select(func.count()).select_from(DossierInterview).where(*cond)) or 0)
    rows = db.scalars(select(DossierInterview).where(*cond).order_by(
        DossierInterview.interview_date.desc().nullslast(), DossierInterview.created_at.desc(),
        DossierInterview.id).offset(offset).limit(limit)).all()
    names = {d.id: d.display_name for d in db.scalars(select(CaseProfile).where(
        CaseProfile.id.in_([r.dossier_id for r in rows])))} if rows else {}
    items = []
    for r in rows:
        notes, cut = _clip(r.working_notes, NOTES_LIMIT)
        files = []
        for link in db.scalars(select(DossierInterviewEvidenceLink).where(
                DossierInterviewEvidenceLink.interview_id == r.id).order_by(DossierInterviewEvidenceLink.created_at)):
            fid = link.evidence_file_id or _uuid(link.target_id)
            f = db.get(EvidenceFile, fid) if fid else None
            if f is None or f.case_id != case_id:
                files.append({"state": "not_in_case", "reason": "%s The attached file is no longer in the case."
                              % NOT_IN_CASE})
                continue
            files.append({"evidence_file_id": str(f.id), "filename": f.original_filename, "doc": "doc://%s" % f.id,
                          "file_state": f.status})
        item = {"id": str(r.id), "dossier_id": str(r.dossier_id), "dossier": names.get(r.dossier_id),
                "dossier_href": dossier_href(case_id, r.dossier_id),
                "date": r.date_value or _iso(r.interview_date), "participants": list(r.participants or []),
                "status": r.status, "notes": notes, "attached_files": files}
        if cut:
            item["notes_clipped"] = cut
        items.append(item)
    tcond = [EvidenceFile.case_id == case_id, _transcribed_files(case_id)]
    t_total = int(db.scalar(select(func.count()).select_from(EvidenceFile).where(*tcond)) or 0)
    recordings = [{"evidence_file_id": str(f.id), "filename": f.original_filename, "doc": "doc://%s" % f.id,
                   **_transcript_state(db, f)}
                  for f in db.scalars(select(EvidenceFile).where(*tcond).order_by(EvidenceFile.original_filename)
                                      .limit(MAX_LIMIT))]
    coverage = "%d interviews recorded on dossiers%s; %d recordings in the case have a transcript." % (
        total, " (dossier %s)" % dossier if dossier else "", t_total)
    out = _paged("interviews", case_id, items, total, offset, coverage=coverage,
                 transcripts={"total": t_total, "listed": len(recordings), "items": recordings,
                              "read_with": "get_transcript with the evidence_file_id"})
    if t_total > len(recordings):
        out["transcripts"]["limitation"] = "%d of %d recordings with a transcript are listed here." % (
            len(recordings), t_total)
    return out


def transcript(db, case_id, *, evidence, offset=0) -> dict[str, Any]:
    """One recording's transcript: the working text (the last saved revision, else the machine text), paged by
    characters, with its review state."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.transcript import TranscriptRevision, TranscriptSource, TranscriptState
    fid = _uuid(evidence)
    f = db.get(EvidenceFile, fid) if fid else None
    if f is None:
        f = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
                                                  EvidenceFile.original_filename == str(evidence or "").strip())
                       .limit(2)).all()
        if len(f) > 1:
            return _unavailable("transcript", case_id, "Several files are named %s; give the file's id." % evidence)
        f = f[0] if f else None
    if f is None or f.case_id != case_id:
        return _unavailable("transcript", case_id, "%s No such file." % NOT_IN_CASE)
    state = db.get(TranscriptState, f.id)
    text, basis = None, None
    if state is not None:
        rev = db.get(TranscriptRevision, state.working_revision_id)
        src = db.get(TranscriptSource, state.source_id)
        text = (rev.payload or {}).get("body_text") if rev is not None else None
        text = text if text is not None else (src.text if src is not None else None)
        basis = "the transcript as last saved"
    elif f.transcription:
        text, basis = f.transcription, "the machine transcript"
    base = {"schema": _schema("transcript"), "case_id": str(case_id), "evidence_file_id": str(f.id),
            "filename": f.original_filename, "doc": "doc://%s" % f.id}
    if not text:
        return {**base, "available": False, "total_matching": 0, "returned": 0, "has_more": False,
                "next_offset": None, "items": [], "reason": "This file has no transcript."}
    offset = max(0, int(offset or 0))
    part = text[offset:offset + TRANSCRIPT_LIMIT]
    nxt = offset + len(part) if offset + len(part) < len(text) else None
    return {**base, "available": True, "basis": basis, **_transcript_state(db, f), "characters": len(text),
            "offset": offset, "text": part, "has_more": nxt is not None, "next_offset": nxt,
            "total_matching": 1, "returned": 1,
            "limitation": ("Characters %d to %d of %d; read on with offset %d." % (offset, offset + len(part),
                                                                                   len(text), nxt))
            if nxt is not None else None}


# ---- dossiers ----------------------------------------------------------------------------------------------------------

def list_dossiers(db, case_id, *, search=None, include_archived=False, offset=0, limit=20) -> dict[str, Any]:
    from postgres.models.case_profile import CaseProfile
    from postgres.models.dossier import DossierAssessment, DossierInterview, DossierLink
    offset, limit = _page(offset, limit)
    cond = [CaseProfile.case_id == case_id]
    if not include_archived:
        cond.append(CaseProfile.archived_at.is_(None))
    if search and search.strip():
        pattern = "%%%s%%" % search.strip()
        cond.append(or_(CaseProfile.display_name.ilike(pattern), CaseProfile.summary.ilike(pattern)))
    total = int(db.scalar(select(func.count()).select_from(CaseProfile).where(*cond)) or 0)
    archived = int(db.scalar(select(func.count()).select_from(CaseProfile).where(
        CaseProfile.case_id == case_id, CaseProfile.archived_at.isnot(None))) or 0)
    rows = db.scalars(select(CaseProfile).where(*cond).order_by(CaseProfile.display_name, CaseProfile.id)
                      .offset(offset).limit(limit)).all()

    def count(model, did):
        return int(db.scalar(select(func.count()).select_from(model).where(model.dossier_id == did)) or 0)
    items = [{"id": str(d.id), "name": d.display_name, "type": d.profile_type, "status": d.status,
              "importance": d.importance, "summary": _clip(d.summary, 400)[0], "graph_entity": d.canonical_entity_key,
              "archived": d.archived_at is not None, "links": count(DossierLink, d.id),
              "assessments": count(DossierAssessment, d.id), "interviews": count(DossierInterview, d.id),
              "href": dossier_href(case_id, d.id), "read_with": "get_dossier with this id"} for d in rows]
    return _paged("dossiers", case_id, items, total, offset,
                  coverage="%d dossiers%s%s." % (total, "" if include_archived else " (not archived)",
                                                 "; %d archived" % archived if archived and not include_archived else ""))


# ---- theories ----------------------------------------------------------------------------------------------------------

def _find_entry(db, case_id, ref, kind="theory"):
    from postgres.models.workspace_entry import WorkspaceEntry
    eid = _uuid(ref)
    if eid is not None:
        e = db.get(WorkspaceEntry, eid)
        return [e] if e is not None and e.case_id == case_id and e.deleted_at is None and e.entry_type == kind else []
    return db.scalars(select(WorkspaceEntry).where(
        WorkspaceEntry.case_id == case_id, WorkspaceEntry.entry_type == kind, WorkspaceEntry.deleted_at.is_(None),
        WorkspaceEntry.title.ilike("%%%s%%" % str(ref or "").strip())).order_by(
        WorkspaceEntry.updated_at.desc()).limit(21)).all()


def theory(db, case_id, *, theory) -> dict[str, Any]:
    """One theory read whole: its statement, every addition oldest first (what it is, who added it and why, a model's
    addition marked as one, its members up to 25 with their facts) and the narratives on it."""
    from services import theory_additions as T
    found = _find_entry(db, case_id, theory)
    if not found:
        return _unavailable("theory", case_id, "%s No theory matches %s." % (NOT_IN_CASE, theory))
    if len(found) > 1:
        out = _unavailable("theory", case_id, "%s%d theories match %s; ask which one, or give its id." % (
            "More than 20; the first 20 are listed. " if len(found) > 20 else "", min(len(found), 20), theory))
        out.update(not_in_case=False, ambiguous=True,
                   candidates=[{"id": str(e.id), "title": e.title} for e in found[:20]])
        return out
    entry = found[0]
    reading = T.reading(db, case_id=case_id, entry_id=entry.id)
    links = {str(l.id): l for l in entry.links}
    additions = []
    for a in reading["additions"]:
        a = dict(a)
        anchor = a.pop("source_anchor", None) or {}
        link = links.get(a["link_id"])
        if link is not None:
            members = T.addition_members(db, case_id, link, limit=MEMBERS_SHOWN)
            a["members"] = members["members"]
            a["members_shown"] = members["members_shown"]
            a["member_count"] = members["member_count"]
            if members["member_count"] > members["members_shown"]:
                a["members_clipped"] = "%d of %d members are listed here." % (members["members_shown"],
                                                                               members["member_count"])
            if members.get("missing"):
                a["missing"] = members["missing"]
        if a.get("model_reading") or a.get("origin") == "agent":
            a["provenance"] = "Added from a model's answer (%s); a model reading, not a person's finding." % (
                a.get("model") or "the case agent")
        if anchor.get("quote"):
            a["quote"] = anchor.get("quote")
        additions.append(a)
    narratives = [a["narrative"] for a in additions if a.get("narrative")]
    item = {"id": str(entry.id), "title": entry.title, "statement": entry.body, "state": entry.lifecycle_state,
            "confidence": entry.confidence, "significance": entry.significance,
            "author": entry.author_name or entry.author_email, "href": entry_href(case_id, entry),
            "additions": additions, "fit": reading.get("fit"), "fit_versions": reading.get("fit_versions")}
    by_rel: dict[str, int] = {}
    for a in additions:
        by_rel[a.get("relationship") or "unclassified"] = by_rel.get(a.get("relationship") or "unclassified", 0) + 1
    model_narr = sum(1 for n in narratives + ([reading["fit"]] if reading.get("fit") else []) if n["origin"] == "agent")
    return {"schema": _schema("theory"), "case_id": str(case_id), "available": True, "total_matching": 1,
            "returned": 1, "has_more": False, "next_offset": None, "items": [item],
            "coverage": "The whole theory: %d additions (%s), %d narratives on additions%s." % (
                len(additions), ", ".join("%d %s" % (n, k) for k, n in sorted(by_rel.items())) or "none",
                len(narratives), ", and one on how it fits together" if reading.get("fit") else ""),
            "provenance": ("%d narratives were written by a model; each says whether a person confirmed it." % model_narr)
            if model_narr else None}


# ---- significant layer -------------------------------------------------------------------------------------------------

SOURCE_WORDS = {"manual": "added by a person", "merge": "carried over when two entities were merged",
                "agent": "added from the agent's work", "bulk": "added in a group"}


def significant_layer(db, case_id, *, names: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
                      search=None, offset=0, limit=50) -> dict[str, Any]:
    """The items marked significant: each with its name and kind from the graph, how and when it was added and by
    whom. ``names`` reads the graph (key -> {name, type}); without it the keys are given and that is said."""
    from postgres.models.significant import SignificantEntity, SignificantRelationship
    from postgres.models.user import User
    offset, limit = _page(offset, limit, default=50)
    rows = db.scalars(select(SignificantEntity).where(SignificantEntity.case_id == case_id,
                                                      SignificantEntity.removed_at.is_(None))
                      .order_by(SignificantEntity.created_at, SignificantEntity.id)).all()
    # Relationships marked significant (GR-01): read beside the entities, named from the graph by their two ends.
    rel_rows = db.scalars(select(SignificantRelationship).where(SignificantRelationship.case_id == case_id,
                                                                SignificantRelationship.removed_at.is_(None))
                          .order_by(SignificantRelationship.created_at, SignificantRelationship.id)).all()
    graph: dict[str, dict[str, Any]] = {}
    graph_note = None
    wanted = list(dict.fromkeys([r.entity_key for r in rows] + [k for r in rel_rows for k in (r.source_key, r.target_key)]))
    if names is not None and wanted:
        try:
            graph = names(wanted) or {}
        except Exception:  # the graph could not be read: keys are still given, and the result says so
            graph_note = "The graph could not be read just now, so names are missing; the keys are given."
    elif wanted:
        graph_note = "Names were not read from the graph; the keys are given."
    adders = {r.added_by_user_id for r in list(rows) + list(rel_rows) if r.added_by_user_id}
    people = {str(i): n for i, n in db.execute(select(User.id, User.name).where(User.id.in_(adders)))} if adders else {}
    items = []
    for r in rows:
        g = graph.get(r.entity_key) or {}
        items.append({"entity_key": r.entity_key, "name": g.get("name"), "kind": g.get("type"),
                      "in_graph": bool(g) if graph else None,
                      "how_added": SOURCE_WORDS.get(r.addition_source, r.addition_source),
                      "added_by": people.get(str(r.added_by_user_id)), "added_at": _iso(r.created_at)})
    if search and search.strip():
        s = search.strip().lower()
        items = [i for i in items if s in (i["name"] or "").lower() or s in i["entity_key"].lower()]
    total = len(items)
    kinds: dict[str, int] = {}
    for i in items:
        kinds[i["kind"] or "unknown"] = kinds.get(i["kind"] or "unknown", 0) + 1
    missing = sum(1 for i in items if i["in_graph"] is False)
    out = _paged("significant_layer", case_id, items[offset:offset + limit], total, offset,
                 counts_by_kind=kinds,
                 coverage="%d items are in the Significant layer%s." % (
                     len(rows), (" (%d match '%s')" % (total, search.strip())) if search and search.strip() else ""),
                 not_in_graph=("%d of them are no longer in the graph." % missing) if missing else None)
    rels = [{"from_key": r.source_key, "from": (graph.get(r.source_key) or {}).get("name"), "type": r.rel_type,
             "to_key": r.target_key, "to": (graph.get(r.target_key) or {}).get("name"),
             "how_added": SOURCE_WORDS.get(r.addition_source, r.addition_source),
             "added_by": people.get(str(r.added_by_user_id)), "added_at": _iso(r.created_at)} for r in rel_rows]
    if search and search.strip():
        s_ = search.strip().lower()
        rels = [r for r in rels if any(s_ in (r[k] or "").lower() for k in ("from", "to", "type", "from_key", "to_key"))]
    out["relationships"] = rels[:limit]
    out["relationship_coverage"] = "%d relationships are in the Significant layer%s." % (
        len(rel_rows), (" (%d match)" % len(rels)) if search and search.strip() else "") + (
        " The first %d are listed." % limit if len(rels) > limit else "")
    if graph_note:
        out["names_note"] = graph_note
    return out


# ---- reports -----------------------------------------------------------------------------------------------------------

REPORT_TAG = "financial-report"


def reports(db, case_id, *, offset=0, limit=20) -> dict[str, Any]:
    """Saved financial reports (newest first) and what the casework report would hold if exported now."""
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
    from services.casework_report import DEFAULT_ORDER, SECTIONS, SECTION_TITLES
    offset, limit = _page(offset, limit)
    live = [WorkspaceEntry.case_id == case_id, WorkspaceEntry.deleted_at.is_(None)]
    tagged = WorkspaceEntry.tags.contains([REPORT_TAG]) if db.get_bind().dialect.name == "postgresql" else \
        WorkspaceEntry.tags.like('%%"%s"%%' % REPORT_TAG)
    cond = live + [tagged]
    total = int(db.scalar(select(func.count()).select_from(WorkspaceEntry).where(*cond)) or 0)
    rows = db.scalars(select(WorkspaceEntry).where(*cond).order_by(WorkspaceEntry.updated_at.desc(),
                                                                  WorkspaceEntry.id).offset(offset).limit(limit)).all()
    items = []
    for e in rows:
        body, cut = _clip(e.body, 4000)
        links = int(db.scalar(select(func.count()).select_from(WorkspaceEntryLink).where(
            WorkspaceEntryLink.entry_id == e.id)) or 0)
        item = {"id": str(e.id), "title": e.title, "kind": e.entry_type, "text": body, "linked_items": links,
                "author": e.author_name or e.author_email, "updated_at": _iso(e.updated_at),
                "href": entry_href(case_id, e)}
        if cut:
            item["text_clipped"] = cut + " Read it in full with get_casework."
        items.append(item)
    sections = []
    for key in DEFAULT_ORDER:
        n = int(db.scalar(select(func.count()).select_from(WorkspaceEntry).where(
            *live, WorkspaceEntry.entry_type == SECTIONS[key])) or 0)
        sections.append({"section": SECTION_TITLES[key], "entries": n})
    words = ", ".join("%s %d" % (s["section"], s["entries"]) for s in sections)
    return _paged("reports", case_id, items, total, offset, casework_report={
        "sections": sections,
        "words": ("The casework report is produced when it is exported (Reports page); exported now it would hold: "
                  "%s. Deleted entries never print." % words)},
        coverage="%d saved financial reports in this case. Casework report if exported now: %s." % (total, words))
