"""Read-only migration preflight for the Workspace redesign."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import (
    CaseProfile,
    CaseProfileEvidenceLink,
    CaseProfileFindingLink,
    CaseProfileGraphNodeLink,
    CaseProfileNoteLink,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.workspace import (
    WorkspaceContext,
    WorkspaceDeadlineConfig,
    WorkspaceFinding,
    WorkspaceNote,
    WorkspacePinnedItem,
    WorkspaceTask,
    WorkspaceTheory,
    WorkspaceWitness,
)


PREFLIGHT_SCHEMA_VERSION = 1

LEGACY_RECORD_MODELS = (
    WorkspaceContext,
    WorkspaceWitness,
    WorkspaceTheory,
    WorkspaceTask,
    WorkspaceNote,
    WorkspaceFinding,
    WorkspacePinnedItem,
    WorkspaceDeadlineConfig,
    NotebookNote,
    NotebookNoteLink,
    CaseProfile,
    CaseProfileGraphNodeLink,
    CaseProfileEvidenceLink,
    CaseProfileNoteLink,
    CaseProfileFindingLink,
    CaseDeadline,
)

IDENTIFIER_FIELDS = {
    WorkspaceWitness: "witness_id",
    WorkspaceTheory: "theory_id",
    WorkspaceTask: "task_id",
    WorkspaceNote: "note_id",
    WorkspaceFinding: "finding_id",
    WorkspacePinnedItem: "pin_id",
    NotebookNoteLink: "target_id",
    CaseProfileGraphNodeLink: "node_key",
    CaseProfileNoteLink: "note_id",
    CaseProfileFindingLink: "finding_id",
}


def _case_key(value: Any) -> str:
    return str(value)


def _rows(db: Session, model: type, case_id: UUID | None) -> list[Any]:
    query = db.query(model)
    if case_id is not None:
        query = query.filter(model.case_id == case_id)
    return query.all()


def _count_rows(rows_by_model: dict[type, list[Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for model in LEGACY_RECORD_MODELS:
        rows = rows_by_model[model]
        by_case = Counter(_case_key(row.case_id) for row in rows)
        counts[model.__tablename__] = {
            "total": len(rows),
            "by_case": dict(sorted(by_case.items())),
        }
    return counts


def _malformed_identifiers(rows_by_model: dict[type, list[Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for model, field in IDENTIFIER_FIELDS.items():
        for row in rows_by_model[model]:
            value = getattr(row, field, None)
            if isinstance(value, str) and value.strip():
                continue
            findings.append(
                {
                    "table": model.__tablename__,
                    "row_id": str(row.id),
                    "case_id": _case_key(row.case_id),
                    "field": field,
                    "value": value,
                    "reason": "missing_or_blank",
                }
            )

    for theory in rows_by_model[WorkspaceTheory]:
        data = theory.data if isinstance(theory.data, dict) else {}
        for field in ("attached_evidence_ids", "attached_document_ids"):
            value = data.get(field)
            if value is None:
                continue
            if not isinstance(value, list):
                findings.append(
                    {
                        "table": WorkspaceTheory.__tablename__,
                        "row_id": str(theory.id),
                        "case_id": _case_key(theory.case_id),
                        "field": field,
                        "value": value,
                        "reason": "expected_list",
                    }
                )
                continue
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    findings.append(
                        {
                            "table": WorkspaceTheory.__tablename__,
                            "row_id": str(theory.id),
                            "case_id": _case_key(theory.case_id),
                            "field": field,
                            "value": item,
                            "reason": "invalid_list_identifier",
                        }
                    )

    return sorted(
        findings,
        key=lambda item: (
            item["case_id"],
            item["table"],
            item["row_id"],
            item["field"],
            str(item["value"]),
        ),
    )


def _orphaned_links(
    db: Session,
    rows_by_model: dict[type, list[Any]],
    case_id: UUID | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    evidence_rows = _rows(db, EvidenceFile, case_id)
    evidence_keys = {
        (str(row.case_id), value)
        for row in evidence_rows
        for value in (str(row.id), row.original_filename)
        if value
    }
    legacy_notes = {
        (str(row.case_id), row.note_id) for row in rows_by_model[WorkspaceNote]
    }
    notebook_notes = {
        (str(row.case_id), str(row.id)) for row in rows_by_model[NotebookNote]
    }
    findings_by_legacy_id = {
        (str(row.case_id), row.finding_id) for row in rows_by_model[WorkspaceFinding]
    }

    for link in rows_by_model[CaseProfileEvidenceLink]:
        key = (str(link.case_id), str(link.evidence_file_id))
        if key not in evidence_keys:
            findings.append(
                {
                    "table": link.__tablename__,
                    "row_id": str(link.id),
                    "case_id": str(link.case_id),
                    "target_type": "evidence",
                    "target_id": str(link.evidence_file_id),
                    "reason": "missing_evidence_file",
                }
            )

    for link in rows_by_model[CaseProfileNoteLink]:
        key = (str(link.case_id), link.note_id)
        if key not in legacy_notes and key not in notebook_notes:
            findings.append(
                {
                    "table": link.__tablename__,
                    "row_id": str(link.id),
                    "case_id": str(link.case_id),
                    "target_type": "note",
                    "target_id": link.note_id,
                    "reason": "missing_legacy_or_notebook_note",
                }
            )

    for link in rows_by_model[CaseProfileFindingLink]:
        key = (str(link.case_id), link.finding_id)
        if key not in findings_by_legacy_id:
            findings.append(
                {
                    "table": link.__tablename__,
                    "row_id": str(link.id),
                    "case_id": str(link.case_id),
                    "target_type": "finding",
                    "target_id": link.finding_id,
                    "reason": "missing_legacy_finding",
                }
            )

    for link in rows_by_model[NotebookNoteLink]:
        if link.target_type not in {"evidence", "document"}:
            continue
        key = (str(link.case_id), link.target_id)
        if key not in evidence_keys:
            findings.append(
                {
                    "table": link.__tablename__,
                    "row_id": str(link.id),
                    "case_id": str(link.case_id),
                    "target_type": link.target_type,
                    "target_id": link.target_id,
                    "reason": "missing_evidence_file",
                }
            )

    for theory in rows_by_model[WorkspaceTheory]:
        data = theory.data if isinstance(theory.data, dict) else {}
        for field in ("attached_evidence_ids", "attached_document_ids"):
            values = data.get(field)
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    continue
                key = (str(theory.case_id), value)
                if key not in evidence_keys:
                    findings.append(
                        {
                            "table": theory.__tablename__,
                            "row_id": str(theory.id),
                            "case_id": str(theory.case_id),
                            "target_type": "evidence",
                            "target_id": value,
                            "field": field,
                            "reason": "missing_evidence_file",
                        }
                    )

    return sorted(
        findings,
        key=lambda item: (
            item["case_id"],
            item["table"],
            item["row_id"],
            item["target_type"],
            item["target_id"],
        ),
    )


def _duplicate_pins(rows: list[WorkspacePinnedItem]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[WorkspacePinnedItem]] = defaultdict(list)
    for pin in rows:
        grouped[(str(pin.case_id), pin.item_type, pin.item_id)].append(pin)

    return [
        {
            "case_id": case_id,
            "item_type": item_type,
            "item_id": item_id,
            "count": len(group),
            "pin_ids": sorted(str(pin.id) for pin in group),
            "user_ids": sorted({pin.user_id for pin in group}),
        }
        for (case_id, item_type, item_id), group in sorted(grouped.items())
        if len(group) > 1
    ]


def _duplicate_profile_entities(
    rows: list[CaseProfileGraphNodeLink],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for link in rows:
        grouped[(str(link.case_id), link.node_key)].add(str(link.profile_id))

    return [
        {
            "case_id": case_id,
            "node_key": node_key,
            "profile_ids": sorted(profile_ids),
            "count": len(profile_ids),
        }
        for (case_id, node_key), profile_ids in sorted(grouped.items())
        if len(profile_ids) > 1
    ]


def _deadline_conflicts(rows_by_model: dict[type, list[Any]]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for deadline in rows_by_model[CaseDeadline]:
        sources[str(deadline.case_id)]["case_deadlines"].add(deadline.due_date.isoformat())

    for context in rows_by_model[WorkspaceContext]:
        data = context.data if isinstance(context.data, dict) else {}
        trial_date = data.get("trial_date")
        if isinstance(trial_date, str) and trial_date.strip():
            sources[str(context.case_id)]["workspace_context_trial_date"].add(trial_date.strip())

    for config in rows_by_model[WorkspaceDeadlineConfig]:
        data = config.data if isinstance(config.data, dict) else {}
        trial_date = data.get("trial_date")
        if isinstance(trial_date, str) and trial_date.strip():
            sources[str(config.case_id)]["workspace_deadline_trial_date"].add(trial_date.strip())
        deadlines = data.get("deadlines")
        if isinstance(deadlines, list):
            for item in deadlines:
                if not isinstance(item, dict):
                    continue
                due_date = item.get("due_date") or item.get("date")
                if isinstance(due_date, str) and due_date.strip():
                    sources[str(config.case_id)]["workspace_deadline_items"].add(due_date.strip())

    conflicts: list[dict[str, Any]] = []
    for case_key, by_source in sorted(sources.items()):
        all_dates = {date for dates in by_source.values() for date in dates}
        if len(by_source) < 2 or len(all_dates) < 2:
            continue
        conflicts.append(
            {
                "case_id": case_key,
                "sources": {
                    name: sorted(dates) for name, dates in sorted(by_source.items())
                },
            }
        )
    return conflicts


def build_workspace_preflight_report(
    db: Session,
    *,
    case_id: UUID | None = None,
) -> dict[str, Any]:
    """Return a deterministic report without flushing, committing, or mutating rows."""

    rows_by_model = {
        model: _rows(db, model, case_id) for model in LEGACY_RECORD_MODELS
    }
    report = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "scope": {"case_id": str(case_id) if case_id else None},
        "counts": _count_rows(rows_by_model),
        "malformed_identifiers": _malformed_identifiers(rows_by_model),
        "orphaned_links": _orphaned_links(db, rows_by_model, case_id),
        "duplicate_pins": _duplicate_pins(rows_by_model[WorkspacePinnedItem]),
        "duplicate_profile_entity_associations": _duplicate_profile_entities(
            rows_by_model[CaseProfileGraphNodeLink]
        ),
        "conflicting_deadline_sources": _deadline_conflicts(rows_by_model),
    }
    report["summary"] = {
        "legacy_records": sum(
            item["total"] for item in report["counts"].values()
        ),
        "malformed_identifiers": len(report["malformed_identifiers"]),
        "orphaned_links": len(report["orphaned_links"]),
        "duplicate_pins": len(report["duplicate_pins"]),
        "duplicate_profile_entity_associations": len(
            report["duplicate_profile_entity_associations"]
        ),
        "conflicting_deadline_sources": len(
            report["conflicting_deadline_sources"]
        ),
    }
    return report
