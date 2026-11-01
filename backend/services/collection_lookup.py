"""Where an item is used in a case: the reverse lookup over every case-building container (07 section 6.4 item 7).

For a batch of target ids of one registry type, this lists every finding, theory, note, dossier, dossier assessment,
interview and task that links to each target, and, for phone records, every `phone_selection` link whose frozen
record list holds it (through the per-record membership index). A selection is reported against the container
that holds it, marked `via: "selection"`. Deleted entries and tasks, and archived dossiers, are not reported.

Batches are bounded: more than LOOKUP_BATCH_LIMIT ids in one request is refused with a stated message, never cut.
"""
from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres import link_types
from postgres.models.case_profile import CaseProfile
from postgres.models.collection_membership import CollectionMembership
from postgres.models.dossier import (
    DossierAssessment, DossierAssessmentLink, DossierInterview, DossierInterviewEvidenceLink, DossierLink,
)
from postgres.models.work import CaseTask, CaseTaskLink
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink

LOOKUP_BATCH_LIMIT = 200
_PART = 500

# Singular and plural words for the summary line, e.g. "In 1 finding and 2 dossiers".
_WORDS = {
    "finding": ("finding", "findings"), "theory": ("theory", "theories"), "note": ("note", "notes"),
    "dossier": ("dossier", "dossiers"), "assessment": ("dossier assessment", "dossier assessments"),
    "interview": ("interview", "interviews"), "task": ("task", "tasks"),
}
_ORDER = tuple(_WORDS)


class LookupRefused(ValueError):
    pass


def summary_line(counts: dict[str, int]) -> str | None:
    parts = [f"{counts[kind]} {_WORDS[kind][0 if counts[kind] == 1 else 1]}" for kind in _ORDER if counts.get(kind)]
    if not parts:
        return None
    return "In " + (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1])


def lookup(db: Session, *, case_id: uuid.UUID, target_type: str, target_ids: list[str]) -> dict[str, Any]:
    if target_type not in link_types.ALL_TYPES:
        raise LookupRefused(f"Unknown link type: {target_type}")
    ids = list(dict.fromkeys(str(value).strip() for value in target_ids if str(value).strip()))
    if not ids:
        raise LookupRefused("At least one target id is required")
    if len(ids) > LOOKUP_BATCH_LIMIT:
        raise LookupRefused(
            f"{len(ids):,} ids were sent; one request takes at most {LOOKUP_BATCH_LIMIT}. Send them in parts."
        )
    found: dict[str, list[dict[str, Any]]] = {value: [] for value in ids}
    for start in range(0, len(ids), _PART):
        part = ids[start:start + _PART]
        _entries(db, case_id, target_type, part, found)
        _dossiers(db, case_id, target_type, part, found)
        _tasks(db, case_id, target_type, part, found)
        if target_type == "phone_record":
            _selections(db, case_id, part, found)
    results = []
    for value in ids:
        uses = found[value]
        # One container counts once even when it holds the record both directly and inside a selection.
        containers = {(use["kind"], use["container_id"]) for use in uses}
        counts = dict(Counter(kind for kind, _ in containers))
        results.append({"target_id": value, "uses": uses, "counts": counts, "summary": summary_line(counts)})
    return {"case_id": str(case_id), "target_type": target_type, "requested": len(ids),
            "limit": LOOKUP_BATCH_LIMIT, "results": results}


def _use(kind, container_id, label, link_id, via, relationship=None, extra=None):
    return {"kind": kind, "container_id": str(container_id), "container_label": label, "link_id": str(link_id),
            "via": via, "relationship": relationship, **(extra or {})}


def _entries(db, case_id, target_type, ids, found):
    rows = db.execute(
        select(WorkspaceEntryLink, WorkspaceEntry)
        .join(WorkspaceEntry, WorkspaceEntry.id == WorkspaceEntryLink.entry_id)
        .where(WorkspaceEntryLink.case_id == case_id, WorkspaceEntryLink.target_type == target_type,
               WorkspaceEntryLink.target_id.in_(ids), WorkspaceEntry.deleted_at.is_(None))
    ).all()
    for link, entry in rows:
        found[link.target_id].append(_use(entry.entry_type, entry.id, entry.title, link.id, "direct",
                                          link.relationship_type))


def _dossiers(db, case_id, target_type, ids, found):
    for link, dossier in db.execute(
        select(DossierLink, CaseProfile).join(CaseProfile, CaseProfile.id == DossierLink.dossier_id)
        .where(DossierLink.case_id == case_id, DossierLink.target_type == target_type,
               DossierLink.target_id.in_(ids), CaseProfile.archived_at.is_(None))
    ).all():
        found[link.target_id].append(_use("dossier", dossier.id, dossier.display_name, link.id, "direct",
                                          link.relationship_type))
    for link, assessment, dossier in db.execute(
        select(DossierAssessmentLink, DossierAssessment, CaseProfile)
        .join(DossierAssessment, DossierAssessment.id == DossierAssessmentLink.assessment_id)
        .join(CaseProfile, CaseProfile.id == DossierAssessment.dossier_id)
        .where(DossierAssessmentLink.case_id == case_id, DossierAssessmentLink.target_type == target_type,
               DossierAssessmentLink.target_id.in_(ids), CaseProfile.archived_at.is_(None))
    ).all():
        found[link.target_id].append(_use("assessment", assessment.id, assessment.category, link.id, "direct",
                                          extra={"dossier_id": str(dossier.id)}))
    if target_type in link_types.INTERVIEW_EVIDENCE_TYPES and target_type != "evidence":
        for link, interview, dossier in db.execute(
            select(DossierInterviewEvidenceLink, DossierInterview, CaseProfile)
            .join(DossierInterview, DossierInterview.id == DossierInterviewEvidenceLink.interview_id)
            .join(CaseProfile, CaseProfile.id == DossierInterview.dossier_id)
            .where(DossierInterviewEvidenceLink.case_id == case_id,
                   DossierInterviewEvidenceLink.target_type == target_type,
                   DossierInterviewEvidenceLink.target_id.in_(ids), CaseProfile.archived_at.is_(None))
        ).all():
            found[link.target_id].append(_use("interview", interview.id, interview.date_value, link.id, "direct",
                                              extra={"dossier_id": str(dossier.id)}))


def _tasks(db, case_id, target_type, ids, found):
    if target_type not in link_types.TASK_TYPES:
        return
    for link, task in db.execute(
        select(CaseTaskLink, CaseTask).join(CaseTask, CaseTask.id == CaseTaskLink.task_id)
        .where(CaseTaskLink.case_id == case_id, CaseTaskLink.target_type == target_type,
               CaseTaskLink.target_id.in_(ids), CaseTask.deleted_at.is_(None))
    ).all():
        found[link.target_id].append(_use("task", task.id, task.title, link.id, "direct"))


def _selections(db, case_id, ids, found):
    members = db.scalars(select(CollectionMembership).where(
        CollectionMembership.case_id == case_id, CollectionMembership.record_id.in_(ids))).all()
    by_kind: dict[str, list[CollectionMembership]] = {}
    for member in members:
        by_kind.setdefault(member.container_type, []).append(member)
    link_ids = {kind: list({member.link_id for member in rows}) for kind, rows in by_kind.items()}
    live: dict[uuid.UUID, tuple[str, str, Any, str | None]] = {}
    if link_ids.get("entry"):
        for link, entry in db.execute(
            select(WorkspaceEntryLink, WorkspaceEntry).join(WorkspaceEntry, WorkspaceEntry.id == WorkspaceEntryLink.entry_id)
            .where(WorkspaceEntryLink.id.in_(link_ids["entry"]), WorkspaceEntry.deleted_at.is_(None))
        ).all():
            live[link.id] = (entry.entry_type, str(entry.id), entry.title, link.relationship_type)
    if link_ids.get("dossier"):
        for link, dossier in db.execute(
            select(DossierLink, CaseProfile).join(CaseProfile, CaseProfile.id == DossierLink.dossier_id)
            .where(DossierLink.id.in_(link_ids["dossier"]), CaseProfile.archived_at.is_(None))
        ).all():
            live[link.id] = ("dossier", str(dossier.id), dossier.display_name, link.relationship_type)
    if link_ids.get("task"):
        for link, task in db.execute(
            select(CaseTaskLink, CaseTask).join(CaseTask, CaseTask.id == CaseTaskLink.task_id)
            .where(CaseTaskLink.id.in_(link_ids["task"]), CaseTask.deleted_at.is_(None))
        ).all():
            live[link.id] = ("task", str(task.id), task.title, None)
    for member in members:
        container = live.get(member.link_id)
        if container is None:
            continue  # the selection link was removed, or its container deleted: not a current use
        kind, container_id, label, relationship = container
        found[member.record_id].append(_use(kind, container_id, label, member.link_id, "selection", relationship))
