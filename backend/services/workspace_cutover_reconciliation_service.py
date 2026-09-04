"""Final, read-only reconciliation for the Workspace Phase 8 cutover."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres.models.agent import AgentArtifactRecord, AgentThread
from postgres.models.case import Case
from postgres.models.case_context import (
    CaseContext,
    CaseContextLegacyMapping,
    CaseMandateVersion,
)
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import (
    DossierAssessment,
    DossierAssessmentLink,
    DossierGeneratedOutput,
    DossierInterview,
    DossierInterviewEvidenceLink,
    DossierLegacyMapping,
    DossierLink,
    DossierMedia,
    DossierRole,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.timeline_view import TimelineViewEvent
from postgres.models.work import (
    CaseTask,
    CaseTaskLink,
    SharedEvidencePin,
    WorkLegacyMapping,
)
from postgres.models.workspace import (
    WorkspaceContext,
    WorkspaceDeadlineConfig,
    WorkspacePinnedItem,
    WorkspaceTask,
)
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
)
from services.dossier_reconciliation_service import (
    build_dossier_reconciliation_report,
)
from services.workspace_entry_reconciliation_service import (
    build_workspace_entry_reconciliation_report,
)
from services.workspace_preflight_service import build_workspace_preflight_report


RECONCILIATION_SCHEMA_VERSION = 1


def _count(db: Session, model: type, case_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(model).where(model.case_id == case_id)
        )
        or 0
    )


def _payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _review_key(category: str, identity: str) -> str:
    return f"{category}:{identity}"


def _hashed_review_key(category: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return _review_key(category, hashlib.sha256(encoded).hexdigest()[:20])


def _review_item(
    category: str,
    identity: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    return {
        "key": _review_key(category, identity),
        "category": category,
        "detail": detail,
    }


def _legacy_task_id(row: WorkspaceTask) -> str:
    data = _payload(row.data)
    return str(data.get("task_id") or row.task_id or row.id)


def _legacy_pin_id(row: WorkspacePinnedItem) -> str:
    data = _payload(row.data)
    return str(data.get("pin_id") or row.pin_id or row.id)


def _deadline_source_ids(row: WorkspaceDeadlineConfig) -> list[str]:
    data = _payload(row.data)
    source_ids: list[str] = []
    if data.get("trial_date"):
        source_ids.append("trial")
    deadlines = data.get("deadlines")
    if isinstance(deadlines, list):
        for index, item in enumerate(deadlines):
            if isinstance(item, dict):
                source_ids.append(str(item.get("deadline_id") or f"deadline_{index}"))
    return source_ids


def _work_reconciliation(
    db: Session,
    case_id: UUID,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    legacy_tasks = db.scalars(
        select(WorkspaceTask).where(WorkspaceTask.case_id == case_id)
    ).all()
    legacy_pins = db.scalars(
        select(WorkspacePinnedItem).where(WorkspacePinnedItem.case_id == case_id)
    ).all()
    legacy_deadline_configs = db.scalars(
        select(WorkspaceDeadlineConfig).where(
            WorkspaceDeadlineConfig.case_id == case_id
        )
    ).all()
    mappings = db.scalars(
        select(WorkLegacyMapping).where(WorkLegacyMapping.case_id == case_id)
    ).all()
    mapping_by_source = {
        (row.source_type, row.source_id): row for row in mappings
    }

    source_keys = [
        *(('workspace_task', _legacy_task_id(row)) for row in legacy_tasks),
        *(('workspace_pin', _legacy_pin_id(row)) for row in legacy_pins),
        *(
            ('workspace_deadline', source_id)
            for row in legacy_deadline_configs
            for source_id in _deadline_source_ids(row)
        ),
    ]
    unexpected: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []

    for source_type, source_id in source_keys:
        mapping = mapping_by_source.get((source_type, source_id))
        if mapping is None:
            unexpected.append(
                {
                    "kind": "missing_work_mapping",
                    "source_type": source_type,
                    "source_id": source_id,
                }
            )
            continue
        if mapping.canonical_id is None:
            if mapping.status in {"unresolved", "needs_review"}:
                review_items.append(
                    _review_item(
                        "work-mapping",
                        str(mapping.id),
                        {
                            "source_type": source_type,
                            "source_id": source_id,
                            "status": mapping.status,
                            "metadata": mapping.migration_metadata or {},
                        },
                    )
                )
            else:
                unexpected.append(
                    {
                        "kind": "work_mapping_without_target",
                        "mapping_id": str(mapping.id),
                        "source_type": source_type,
                        "source_id": source_id,
                        "status": mapping.status,
                    }
                )
            continue
        try:
            canonical_id = UUID(mapping.canonical_id)
        except (TypeError, ValueError):
            unexpected.append(
                {
                    "kind": "invalid_work_target_id",
                    "mapping_id": str(mapping.id),
                    "canonical_id": mapping.canonical_id,
                }
            )
            continue
        target: Any
        if mapping.canonical_type == "task":
            target = db.get(CaseTask, canonical_id)
        elif mapping.canonical_type == "deadline":
            target = db.get(CaseDeadline, canonical_id)
        elif mapping.canonical_type == "evidence_pin":
            target = db.get(SharedEvidencePin, canonical_id)
        else:
            target = None
        if target is None or target.case_id != case_id:
            unexpected.append(
                {
                    "kind": "missing_or_cross_case_work_target",
                    "mapping_id": str(mapping.id),
                    "canonical_type": mapping.canonical_type,
                    "canonical_id": mapping.canonical_id,
                }
            )
        if mapping.status != "migrated":
            review_items.append(
                _review_item(
                    "work-mapping",
                    str(mapping.id),
                    {
                        "source_type": source_type,
                        "source_id": source_id,
                        "status": mapping.status,
                        "metadata": mapping.migration_metadata or {},
                    },
                )
            )

    tasks = db.scalars(select(CaseTask).where(CaseTask.case_id == case_id)).all()
    for task in tasks:
        if task.needs_migration_review:
            review_items.append(
                _review_item(
                    "task",
                    str(task.id),
                    {"legacy_id": task.legacy_id, "metadata": task.migration_metadata or {}},
                )
            )

    summary = {
        "legacy_tasks": len(legacy_tasks),
        "legacy_deadline_candidates": sum(
            len(_deadline_source_ids(row)) for row in legacy_deadline_configs
        ),
        "legacy_pins": len(legacy_pins),
        "mappings": len(mappings),
        "tasks": len(tasks),
        "task_links": _count(db, CaseTaskLink, case_id),
        "deadlines": _count(db, CaseDeadline, case_id),
        "pins": _count(db, SharedEvidencePin, case_id),
        "unexpected_differences": len(unexpected),
        "review_items": len(review_items),
    }
    return summary, unexpected, review_items


def _context_reconciliation(
    db: Session,
    case_id: UUID,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    legacy = db.scalar(
        select(WorkspaceContext).where(WorkspaceContext.case_id == case_id)
    )
    canonical = db.scalar(select(CaseContext).where(CaseContext.case_id == case_id))
    mapping = db.scalar(
        select(CaseContextLegacyMapping).where(
            CaseContextLegacyMapping.case_id == case_id
        )
    )
    unexpected: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    if legacy is not None:
        if mapping is None:
            unexpected.append(
                {"kind": "missing_context_mapping", "source_id": str(legacy.id)}
            )
        elif mapping.workspace_context_id != legacy.id:
            unexpected.append(
                {
                    "kind": "inconsistent_context_mapping",
                    "mapping_id": str(mapping.id),
                    "source_id": str(legacy.id),
                    "mapped_source_id": str(mapping.workspace_context_id),
                }
            )
        if canonical is None:
            unexpected.append({"kind": "missing_canonical_context"})
    if mapping is not None:
        for index, warning in enumerate(mapping.warnings or []):
            review_items.append(
                _review_item(
                    "context-warning",
                    f"{mapping.id}:{index}",
                    {"warning": warning},
                )
            )
    summary = {
        "legacy_contexts": int(legacy is not None),
        "canonical_contexts": int(canonical is not None),
        "mandate_versions": _count(db, CaseMandateVersion, case_id),
        "mappings": int(mapping is not None),
        "unexpected_differences": len(unexpected),
        "review_items": len(review_items),
    }
    return summary, unexpected, review_items


def _canonical_counts(db: Session, case_id: UUID) -> dict[str, int]:
    models = {
        "entries": WorkspaceEntry,
        "entry_links": WorkspaceEntryLink,
        "entry_revisions": WorkspaceEntryRevision,
        "entry_events": WorkspaceEntryEvent,
        "dossiers": CaseProfile,
        "dossier_roles": DossierRole,
        "dossier_links": DossierLink,
        "dossier_assessments": DossierAssessment,
        "dossier_assessment_links": DossierAssessmentLink,
        "dossier_media": DossierMedia,
        "dossier_interviews": DossierInterview,
        "dossier_interview_evidence_links": DossierInterviewEvidenceLink,
        "dossier_generated_outputs": DossierGeneratedOutput,
        "dossier_legacy_mappings": DossierLegacyMapping,
        "tasks": CaseTask,
        "task_links": CaseTaskLink,
        "deadlines": CaseDeadline,
        "shared_evidence_pins": SharedEvidencePin,
        "work_legacy_mappings": WorkLegacyMapping,
        "contexts": CaseContext,
        "mandate_versions": CaseMandateVersion,
    }
    return {name: _count(db, model, case_id) for name, model in models.items()}


def _relational_target_is_in_case(
    db: Session,
    *,
    case_id: UUID,
    target_type: str,
    target_id: str,
) -> bool:
    """Validate relational link targets without pretending graph keys are UUIDs."""
    if target_type == "graph_entity":
        return bool(target_id.strip())
    if target_type == "timeline_event":
        return bool(
            db.scalar(
                select(TimelineViewEvent.id).where(
                    TimelineViewEvent.case_id == case_id,
                    TimelineViewEvent.event_key == target_id,
                )
            )
        )
    try:
        target_uuid = UUID(target_id)
    except (TypeError, ValueError):
        return False
    if target_type == "agent_artifact":
        return bool(
            db.scalar(
                select(AgentArtifactRecord.id)
                .join(AgentThread, AgentThread.id == AgentArtifactRecord.thread_id)
                .where(
                    AgentArtifactRecord.id == target_uuid,
                    AgentThread.case_id == case_id,
                )
            )
        )
    model_by_type = {
        "entry": WorkspaceEntry,
        "dossier": CaseProfile,
        "task": CaseTask,
        "deadline": CaseDeadline,
        "evidence": EvidenceFile,
    }
    model = model_by_type.get(target_type)
    if model is None:
        return False
    return bool(
        db.scalar(
            select(model.id).where(model.id == target_uuid, model.case_id == case_id)
        )
    )


def _canonical_integrity_errors(db: Session, case_id: UUID) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    entries = db.scalars(
        select(WorkspaceEntry).where(WorkspaceEntry.case_id == case_id)
    ).all()
    revisions = db.scalars(
        select(WorkspaceEntryRevision).where(WorkspaceEntryRevision.case_id == case_id)
    ).all()
    events = db.scalars(
        select(WorkspaceEntryEvent).where(WorkspaceEntryEvent.case_id == case_id)
    ).all()
    revision_entry_ids = {row.entry_id for row in revisions}
    event_entry_ids = {row.entry_id for row in events}
    for entry in entries:
        if entry.id not in revision_entry_ids:
            errors.append({"kind": "entry_without_revision", "entry_id": str(entry.id)})
        if entry.id not in event_entry_ids:
            errors.append({"kind": "entry_without_event", "entry_id": str(entry.id)})

    entry_ids = {row.id for row in entries}
    for revision in revisions:
        if revision.entry_id not in entry_ids:
            errors.append(
                {"kind": "entry_revision_parent_mismatch", "id": str(revision.id)}
            )
    for event in events:
        if event.entry_id not in entry_ids:
            errors.append({"kind": "entry_event_parent_mismatch", "id": str(event.id)})
    for link in db.scalars(
        select(WorkspaceEntryLink).where(WorkspaceEntryLink.case_id == case_id)
    ):
        if link.entry_id not in entry_ids:
            errors.append({"kind": "entry_link_parent_mismatch", "link_id": str(link.id)})
        if not _relational_target_is_in_case(
            db,
            case_id=case_id,
            target_type=link.target_type,
            target_id=link.target_id,
        ):
            errors.append(
                {"kind": "entry_link_target_mismatch", "link_id": str(link.id)}
            )

    dossiers = {
        row.id: row
        for row in db.scalars(
            select(CaseProfile).where(CaseProfile.case_id == case_id)
        ).all()
    }
    dossier_children: Iterable[tuple[str, Any]] = (
        (name, row)
        for name, model in (
            ("role", DossierRole),
            ("link", DossierLink),
            ("assessment", DossierAssessment),
            ("media", DossierMedia),
            ("interview", DossierInterview),
            ("generated_output", DossierGeneratedOutput),
        )
        for row in db.scalars(select(model).where(model.case_id == case_id)).all()
    )
    for name, row in dossier_children:
        parent = dossiers.get(row.dossier_id)
        if parent is None or parent.case_id != row.case_id:
            errors.append(
                {"kind": f"dossier_{name}_parent_mismatch", "id": str(row.id)}
            )

    dossier_links = db.scalars(
        select(DossierLink).where(DossierLink.case_id == case_id)
    ).all()
    for link in dossier_links:
        if not _relational_target_is_in_case(
            db,
            case_id=case_id,
            target_type=link.target_type,
            target_id=link.target_id,
        ):
            errors.append(
                {"kind": "dossier_link_target_mismatch", "link_id": str(link.id)}
            )

    assessments = {
        row.id: row
        for row in db.scalars(
            select(DossierAssessment).where(DossierAssessment.case_id == case_id)
        ).all()
    }
    for link in db.scalars(
        select(DossierAssessmentLink).where(DossierAssessmentLink.case_id == case_id)
    ):
        if link.assessment_id not in assessments:
            errors.append(
                {
                    "kind": "dossier_assessment_link_parent_mismatch",
                    "link_id": str(link.id),
                }
            )
        if not _relational_target_is_in_case(
            db,
            case_id=case_id,
            target_type=link.target_type,
            target_id=link.target_id,
        ):
            errors.append(
                {
                    "kind": "dossier_assessment_link_target_mismatch",
                    "link_id": str(link.id),
                }
            )

    for media in db.scalars(select(DossierMedia).where(DossierMedia.case_id == case_id)):
        evidence = db.get(EvidenceFile, media.evidence_file_id)
        if evidence is None or evidence.case_id != case_id:
            errors.append({"kind": "dossier_media_evidence_mismatch", "id": str(media.id)})
    for link in db.scalars(
        select(DossierInterviewEvidenceLink).where(
            DossierInterviewEvidenceLink.case_id == case_id
        )
    ):
        interview = db.get(DossierInterview, link.interview_id)
        evidence = db.get(EvidenceFile, link.evidence_file_id)
        if (
            interview is None
            or evidence is None
            or interview.case_id != case_id
            or evidence.case_id != case_id
        ):
            errors.append(
                {"kind": "interview_evidence_case_mismatch", "id": str(link.id)}
            )

    tasks = {
        row.id: row
        for row in db.scalars(select(CaseTask).where(CaseTask.case_id == case_id)).all()
    }
    for task in tasks.values():
        if task.parent_task_id and task.parent_task_id not in tasks:
            errors.append({"kind": "task_parent_case_mismatch", "task_id": str(task.id)})
        if task.deadline_id:
            deadline = db.get(CaseDeadline, task.deadline_id)
            if deadline is None or deadline.case_id != case_id:
                errors.append({"kind": "task_deadline_case_mismatch", "task_id": str(task.id)})
    for link in db.scalars(select(CaseTaskLink).where(CaseTaskLink.case_id == case_id)):
        if link.task_id not in tasks:
            errors.append({"kind": "task_link_parent_mismatch", "link_id": str(link.id)})
        if not _relational_target_is_in_case(
            db,
            case_id=case_id,
            target_type=link.target_type,
            target_id=link.target_id,
        ):
            errors.append({"kind": "task_link_target_mismatch", "link_id": str(link.id)})
    for pin in db.scalars(
        select(SharedEvidencePin).where(SharedEvidencePin.case_id == case_id)
    ):
        evidence = db.get(EvidenceFile, pin.evidence_file_id)
        if evidence is None or evidence.case_id != case_id:
            errors.append({"kind": "pin_evidence_case_mismatch", "pin_id": str(pin.id)})
    return errors


def _preflight_review_items(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for category in (
        "malformed_identifiers",
        "orphaned_links",
        "duplicate_pins",
        "duplicate_profile_entity_associations",
        "conflicting_deadline_sources",
    ):
        for detail in preflight[category]:
            items.append(
                {
                    "key": _hashed_review_key(f"preflight-{category}", detail),
                    "category": f"preflight-{category}",
                    "detail": detail,
                }
            )
    return items


def _entry_review_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        _review_item("entry-link", row["link_id"], row)
        for row in report["unresolved_links"]
    ]
    items.extend(
        _review_item("entry", row["entry_id"], row)
        for row in report["needs_migration_review"]
    )
    return items


def _dossier_review_items(
    db: Session,
    case_id: UUID,
) -> list[dict[str, Any]]:
    return [
        _review_item(
            "dossier-linkage",
            str(row.id),
            {
                "display_name": row.display_name,
                "linkage_state": row.linkage_state,
                "legacy_source": row.legacy_source,
                "legacy_id": row.legacy_id,
            },
        )
        for row in db.scalars(
            select(CaseProfile).where(
                CaseProfile.case_id == case_id,
                CaseProfile.needs_link_review.is_(True),
            )
        )
    ]


def _legacy_evidence_dossier_reconciliation(
    db: Session,
    case_id: UUID,
) -> tuple[dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
    """Account for every historical EvidenceFile profile association."""
    canonical_pairs = {
        (row.dossier_id, row.target_id)
        for row in db.scalars(
            select(DossierLink).where(
                DossierLink.case_id == case_id,
                DossierLink.target_type == "evidence",
            )
        )
    }
    dossier_cases = {
        row.id: row.case_id for row in db.scalars(select(CaseProfile)).all()
    }
    source_links = resolved_links = 0
    unexpected: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    for evidence in db.scalars(
        select(EvidenceFile).where(EvidenceFile.case_id == case_id)
    ):
        seen: set[str] = set()
        for raw_dossier_id in evidence.linked_entity_ids or []:
            source_id = str(raw_dossier_id).strip()
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            source_links += 1
            detail = {
                "evidence_file_id": str(evidence.id),
                "legacy_dossier_id": source_id,
            }
            try:
                dossier_id = UUID(source_id)
            except (TypeError, ValueError):
                review_items.append(
                    _review_item(
                        "legacy-evidence-dossier-link",
                        f"{evidence.id}:{source_id}",
                        {**detail, "reason": "malformed_dossier_id"},
                    )
                )
                continue
            dossier_case_id = dossier_cases.get(dossier_id)
            if dossier_case_id != case_id:
                review_items.append(
                    _review_item(
                        "legacy-evidence-dossier-link",
                        f"{evidence.id}:{dossier_id}",
                        {
                            **detail,
                            "reason": (
                                "missing_dossier"
                                if dossier_case_id is None
                                else "cross_case_dossier"
                            ),
                        },
                    )
                )
                continue
            if (dossier_id, str(evidence.id)) not in canonical_pairs:
                unexpected.append(
                    {
                        "kind": "missing_canonical_evidence_dossier_link",
                        **detail,
                    }
                )
                continue
            resolved_links += 1
    return (
        {
            "source_links": source_links,
            "resolved_links": resolved_links,
            "unexpected_differences": len(unexpected),
            "review_items": len(review_items),
        },
        unexpected,
        review_items,
    )


def _entry_unexpected(report: dict[str, Any]) -> list[dict[str, Any]]:
    categories = (
        "duplicate_sources",
        "missing_mappings",
        "missing_targets",
        "inconsistent_targets",
        "mappings_without_target_identity",
        "unrepointed_profile_links",
    )
    return [
        {"kind": f"entry_{category}", **row}
        for category in categories
        for row in report[category]
    ]


def _dossier_unexpected(report: dict[str, Any]) -> list[dict[str, Any]]:
    categories = (
        "invalid_profile_mappings",
        "missing_witness_mappings",
        "duplicate_active_entity_claims",
        "integrity_errors",
        "multiple_cover_errors",
    )
    items = [
        {"kind": f"dossier_{category}", **(row if isinstance(row, dict) else {"id": row})}
        for category in categories
        for row in report[category]
    ]
    if report["summary"]["unrepointed_witness_links"]:
        items.append(
            {
                "kind": "dossier_unrepointed_witness_links",
                "count": report["summary"]["unrepointed_witness_links"],
            }
        )
    return items


def build_workspace_cutover_reconciliation_report(
    db: Session,
    *,
    case_id: UUID | None = None,
    accepted_review_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Account for every legacy source and canonical Workspace record per case."""
    accepted_review_keys = accepted_review_keys or set()
    case_query = select(Case.id).order_by(Case.id)
    if case_id is not None:
        case_query = case_query.where(Case.id == case_id)
    case_ids = list(db.scalars(case_query).all())

    case_reports: list[dict[str, Any]] = []
    all_unexpected: list[dict[str, Any]] = []
    all_review_items: list[dict[str, Any]] = []
    for current_case_id in case_ids:
        entry_report = build_workspace_entry_reconciliation_report(
            db, case_id=current_case_id
        )
        dossier_report = build_dossier_reconciliation_report(
            db, case_id=current_case_id
        )
        preflight = build_workspace_preflight_report(db, case_id=current_case_id)
        work_summary, work_unexpected, work_reviews = _work_reconciliation(
            db, current_case_id
        )
        context_summary, context_unexpected, context_reviews = (
            _context_reconciliation(db, current_case_id)
        )
        (
            evidence_dossier_summary,
            evidence_dossier_unexpected,
            evidence_dossier_reviews,
        ) = _legacy_evidence_dossier_reconciliation(db, current_case_id)
        unexpected = [
            *_entry_unexpected(entry_report),
            *_dossier_unexpected(dossier_report),
            *work_unexpected,
            *context_unexpected,
            *evidence_dossier_unexpected,
            *_canonical_integrity_errors(db, current_case_id),
        ]
        review_items = [
            *_entry_review_items(entry_report),
            *_dossier_review_items(db, current_case_id),
            *work_reviews,
            *context_reviews,
            *evidence_dossier_reviews,
            *_preflight_review_items(preflight),
        ]
        deduplicated_reviews = {
            item["key"]: item for item in review_items
        }
        review_items = [deduplicated_reviews[key] for key in sorted(deduplicated_reviews)]
        for item in review_items:
            item["accepted"] = item["key"] in accepted_review_keys
        unaccepted = [item for item in review_items if not item["accepted"]]
        case_report = {
            "case_id": str(current_case_id),
            "canonical_counts": _canonical_counts(db, current_case_id),
            "legacy_counts": {
                name: values["total"] for name, values in preflight["counts"].items()
            },
            "entries": entry_report["summary"],
            "dossiers": dossier_report["summary"],
            "work": work_summary,
            "context": context_summary,
            "evidence_dossier_links": evidence_dossier_summary,
            "unexpected_differences": unexpected,
            "review_items": review_items,
            "unaccepted_review_items": len(unaccepted),
            "passed": not unexpected and not unaccepted,
        }
        case_reports.append(case_report)
        all_unexpected.extend(
            {"case_id": str(current_case_id), **item} for item in unexpected
        )
        all_review_items.extend(
            {"case_id": str(current_case_id), **item} for item in review_items
        )

    unknown_acceptances = sorted(
        accepted_review_keys - {item["key"] for item in all_review_items}
    )
    unaccepted_count = sum(not item["accepted"] for item in all_review_items)
    report = {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "scope": {"case_id": str(case_id) if case_id else None},
        "cases": case_reports,
        "unexpected_differences": all_unexpected,
        "review_items": all_review_items,
        "unknown_acceptance_keys": unknown_acceptances,
        "summary": {
            "cases": len(case_reports),
            "unexpected_differences": len(all_unexpected),
            "review_items": len(all_review_items),
            "accepted_review_items": len(all_review_items) - unaccepted_count,
            "unaccepted_review_items": unaccepted_count,
            "unknown_acceptance_keys": len(unknown_acceptances),
        },
    }
    report["passed"] = (
        not all_unexpected
        and unaccepted_count == 0
        and not unknown_acceptances
        and bool(case_reports)
    )
    return report
