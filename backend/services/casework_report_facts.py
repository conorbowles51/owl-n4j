"""What the casework report prints beside each entry, read from the case (the report itself only renders).

Per entry, under ``entry["_report"]``:

* ``additions``: each link's record as the theory reading shows it (services.theory_additions): its relationship, the
  person's reason, who added it and when, whether the model chose it (and who accepted it), and its current narrative
  with its words ("Written by ...", "Model reading · <model> · not confirmed");
* ``fit``: the theory's own "how it fits together" narrative, labelled the same way;
* ``counter_arguments``: for a theory, each accepted counter-argument: its title, strength, the model's text (a model
  reading, with the model's name), the person's edit when there is one, and who accepted it;
* ``timeline``: for a theory, every dated member of every addition, in date order;
* ``production``: per link id, the production (Bates) numbers of the cited file and page, each saying what kind it is.

Links saved without a label get the current name of what they point to (``link_names``). A record that cannot be read
is reported as unread in the entry (``missing``); nothing is dropped silently.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable

from postgres import link_types

TIMELINE_LIMIT = 500
NO_NAME = "no name on record"


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _entries(entries_by_section: dict[str, list[dict[str, Any]]]) -> Iterable[dict[str, Any]]:
    for entries in entries_by_section.values():
        for entry in entries:
            if not entry.get("deleted_at"):
                yield entry


# --- names for links saved without one --------------------------------------------------------------------------------

def link_names(db, case_id, target_type: str, ids: set[str]) -> dict[str, str]:
    """Current names, in this case, of linked items of one type. Ids that cannot be named are left out."""
    case_uuid = _uuid(case_id)
    wanted = sorted(ids)
    if target_type == "evidence":
        from postgres.models.evidence import EvidenceFile
        from postgres.soft_delete import showing_deleted
        with showing_deleted(db):  # a deleted file is still named; the link says what it pointed to
            rows = db.query(EvidenceFile.id, EvidenceFile.original_filename).filter(
                EvidenceFile.case_id == case_uuid,
                EvidenceFile.id.in_([u for u in (_uuid(i) for i in wanted) if u])).all()
        return {str(i): name for i, name in rows if name}
    if target_type in ("financial_transaction", "financial_account", "financial_party"):
        from services.financial_link_targets import financial_target_label
        out = {}
        for target_id in wanted:
            try:
                out[target_id] = financial_target_label(db, case_uuid, target_type, target_id)
            except Exception:  # noqa: BLE001 - not in this case: left unnamed, still printed
                continue
        return out
    if link_types.is_phone_type(target_type):
        out = {}
        for target_id in wanted:
            try:
                label = link_types.resolve_phone_target(db, case_uuid, target_type, target_id).label
            except Exception:  # noqa: BLE001 - no resolver, or not in this case: left unnamed
                continue
            if label:
                out[target_id] = label
        return out
    if link_types.is_group_type(target_type):
        from services import case_selections
        out = {}
        for target_id in wanted:
            group = case_selections.describe(db, case_uuid, target_id, member_limit=0)
            if group and group.get("label"):
                out[target_id] = group["label"]
        return out
    if target_type == "interview":
        from postgres.models.dossier import DossierInterview
        rows = db.query(DossierInterview.id, DossierInterview.date_value, DossierInterview.interview_date).filter(
            DossierInterview.case_id == case_uuid,
            DossierInterview.id.in_([u for u in (_uuid(i) for i in wanted) if u])).all()
        return {str(i): f"Interview on {value or (when.date().isoformat() if when else 'no date')}"
                for i, value, when in rows}
    return {}


# --- production numbers -----------------------------------------------------------------------------------------------

def _cited_page(link: dict[str, Any]) -> tuple[str, int | None] | None:
    anchor = link.get("source_anchor") or {}
    if link.get("target_type") == "evidence":
        page = anchor.get("page")
        return str(link.get("target_id")), int(page) if isinstance(page, int) or str(page or "").isdigit() else None
    if link.get("target_type") == "evidence_passage" and anchor.get("evidence_file_id"):
        page = anchor.get("page_number") or anchor.get("page")
        return str(anchor["evidence_file_id"]), int(page) if str(page or "").isdigit() else None
    return None


def _production(db, case_id, entries: list[dict[str, Any]]) -> None:
    from sqlalchemy import inspect

    from services.production_numbers import reference_words, references_for
    cited: dict[str, tuple[str, int | None]] = {}
    for entry in entries:
        for link in entry.get("links") or []:
            place = _cited_page(link)
            if place and _uuid(place[0]):
                cited[str(link.get("id"))] = place
    if not cited or not inspect(db.connection()).has_table("production_assignments"):
        return
    found = references_for(db, _uuid(case_id), list(cited.values()))
    for entry in entries:
        words = {}
        for link in entry.get("links") or []:
            place = cited.get(str(link.get("id")))
            if place and found.get(place):
                words[str(link["id"])] = reference_words(found[place])
        entry.setdefault("_report", {})["production"] = words


# --- counter-arguments -----------------------------------------------------------------------------------------------

def _counter_arguments(db, case_id, theory_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    from sqlalchemy import select

    from postgres.models.user import User
    from postgres.models.workspace_ai import WorkspaceAIOutput as W
    rows = db.scalars(select(W).where(W.case_id == _uuid(case_id), W.output_type == "counter_argument",
                                      W.review_status == "accepted").order_by(W.reviewed_at)).all()
    out: dict[str, list[dict[str, Any]]] = {}
    names: dict[Any, str | None] = {}
    for row in rows:
        content = row.content or {}
        theory = str(content.get("theory_id") or "")
        if theory not in theory_ids:
            continue
        meta = row.model_metadata or {}
        if row.reviewed_by_user_id and row.reviewed_by_user_id not in names:
            user = db.get(User, row.reviewed_by_user_id)
            names[row.reviewed_by_user_id] = user.name if user else None
        edits = meta.get("edits") or {}
        out.setdefault(theory, []).append({
            "id": str(row.id), "title": edits.get("title") or content.get("title"), "strength": content.get("strength"),
            "model": meta.get("model") or meta.get("model_id") or ((meta.get("origin") or {}).get("model")) or "the case agent",
            "model_text": content.get("body"), "person_text": edits.get("body"),
            "accepted_by": names.get(row.reviewed_by_user_id),
            "accepted_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        })
    return out


# --- the whole -------------------------------------------------------------------------------------------------------

def gather(db, case_id, entries_by_section: dict[str, list[dict[str, Any]]]) -> None:
    """Fill ``entry["_report"]`` for every live entry. Reads only."""
    from services import theory_additions as T
    entries = list(_entries(entries_by_section))
    for entry in entries:
        report = entry.setdefault("_report", {})
        try:
            read = T.reading(db, case_id=case_id, entry_id=entry["id"])
        except Exception:  # noqa: BLE001 - said in the entry, never dropped
            db.rollback()
            report["missing"] = "The record of how each item was added could not be read for this report."
            continue
        report["additions"] = {a["link_id"]: a for a in read["additions"]}
        report["fit"] = read["fit"]
        if entry.get("entry_type") == "theory" and entry.get("links"):
            try:
                whole = T.union(db, case_id=case_id, entry_id=entry["id"])
            except Exception:  # noqa: BLE001
                db.rollback()
                report["timeline_missing"] = "The theory's timeline could not be read for this report."
            else:
                dated = sorted((m for m in whole["members"] if m.get("date")), key=lambda m: (str(m["date"]), m["label"]))
                report["timeline"] = dated[:TIMELINE_LIMIT]
                report["timeline_total"] = len(dated)
                report["timeline_cut"] = whole["member_count"] > whole["members_shown"]
    theories = {str(e["id"]) for e in entries if e.get("entry_type") == "theory"}
    if theories:
        try:
            by_theory = _counter_arguments(db, case_id, theories)
        except Exception:  # noqa: BLE001
            db.rollback()
            for entry in entries:
                if str(entry["id"]) in theories:
                    entry["_report"]["counter_missing"] = "Accepted counter-arguments could not be read for this report."
        else:
            for entry in entries:
                if str(entry["id"]) in theories:
                    entry["_report"]["counter_arguments"] = by_theory.get(str(entry["id"]), [])
    try:
        _production(db, case_id, entries)
    except Exception:  # noqa: BLE001
        db.rollback()
        for entry in entries:
            if any(_cited_page(link) for link in entry.get("links") or []):
                entry["_report"]["production_missing"] = "Production numbers could not be read for this report."
