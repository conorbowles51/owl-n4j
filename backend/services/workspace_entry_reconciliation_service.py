"""Deterministic source-to-canonical reconciliation for Phase 1 casework."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from postgres.models.case_profile import CaseProfileFindingLink, CaseProfileNoteLink
from postgres.models.notebook import NotebookNote
from postgres.models.workspace import WorkspaceFinding, WorkspaceNote, WorkspaceTheory
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryLink,
    WorkspaceLegacyMapping,
)


SOURCE_MODELS = {
    "notebook_note": (NotebookNote, "id", "note"),
    "workspace_note": (WorkspaceNote, "note_id", "note"),
    "workspace_finding": (WorkspaceFinding, "finding_id", "finding"),
    "workspace_theory": (WorkspaceTheory, "theory_id", "theory"),
}


def _case(value: Any) -> str:
    return str(value)


def build_workspace_entry_reconciliation_report(
    db: Session,
    *,
    case_id: UUID | None = None,
) -> dict[str, Any]:
    """Compare immutable legacy sources, mappings, and canonical targets."""

    source_keys: set[tuple[str, str, str]] = set()
    duplicate_sources: list[dict[str, Any]] = []
    source_counts: dict[str, Counter[str]] = {}
    for source_type, (model, id_field, _entry_type) in SOURCE_MODELS.items():
        query = db.query(model)
        if case_id is not None:
            query = query.filter(model.case_id == case_id)
        counts: Counter[tuple[str, str]] = Counter()
        by_case: Counter[str] = Counter()
        for row in query.all():
            case_key = _case(row.case_id)
            source_id = str(getattr(row, id_field))
            counts[(case_key, source_id)] += 1
            by_case[case_key] += 1
            source_keys.add((case_key, source_type, source_id))
        source_counts[source_type] = by_case
        duplicate_sources.extend(
            {
                "case_id": case_key,
                "source_type": source_type,
                "source_id": source_id,
                "count": count,
            }
            for (case_key, source_id), count in counts.items()
            if count > 1
        )

    mapping_query = db.query(WorkspaceLegacyMapping).filter(
        WorkspaceLegacyMapping.target_type == "entry",
        WorkspaceLegacyMapping.source_type.in_(SOURCE_MODELS),
    )
    entry_query = db.query(WorkspaceEntry).filter(
        WorkspaceEntry.legacy_source.in_(SOURCE_MODELS)
    )
    link_query = db.query(WorkspaceEntryLink)
    note_link_query = db.query(CaseProfileNoteLink)
    finding_link_query = db.query(CaseProfileFindingLink)
    if case_id is not None:
        mapping_query = mapping_query.filter(WorkspaceLegacyMapping.case_id == case_id)
        entry_query = entry_query.filter(WorkspaceEntry.case_id == case_id)
        link_query = link_query.filter(WorkspaceEntryLink.case_id == case_id)
        note_link_query = note_link_query.filter(CaseProfileNoteLink.case_id == case_id)
        finding_link_query = finding_link_query.filter(CaseProfileFindingLink.case_id == case_id)

    mappings = mapping_query.all()
    entries = entry_query.all()
    entry_by_id = {str(entry.id): entry for entry in entries}
    mapping_by_source = {
        (_case(mapping.case_id), mapping.source_type, mapping.source_id): mapping
        for mapping in mappings
    }
    entry_by_source = {
        (_case(entry.case_id), entry.legacy_source, entry.legacy_id): entry
        for entry in entries
        if entry.legacy_source and entry.legacy_id
    }

    missing_mappings: list[dict[str, str]] = []
    missing_targets: list[dict[str, str]] = []
    inconsistent_targets: list[dict[str, str]] = []
    for source_key in sorted(source_keys):
        case_key, source_type, source_id = source_key
        mapping = mapping_by_source.get(source_key)
        if not mapping:
            missing_mappings.append(
                {
                    "case_id": case_key,
                    "source_type": source_type,
                    "source_id": source_id,
                }
            )
            continue
        target = entry_by_id.get(mapping.target_id)
        if not target:
            missing_targets.append(
                {
                    "case_id": case_key,
                    "source_type": source_type,
                    "source_id": source_id,
                    "target_id": mapping.target_id,
                }
            )
            continue
        expected_type = SOURCE_MODELS[source_type][2]
        if (
            _case(target.case_id) != case_key
            or target.entry_type != expected_type
            or target.legacy_source != source_type
            or target.legacy_id != source_id
        ):
            inconsistent_targets.append(
                {
                    "case_id": case_key,
                    "source_type": source_type,
                    "source_id": source_id,
                    "target_id": str(target.id),
                    "target_case_id": _case(target.case_id),
                    "target_entry_type": target.entry_type,
                    "target_legacy_source": target.legacy_source or "",
                    "target_legacy_id": target.legacy_id or "",
                }
            )

    compatibility_only = [
        {
            "case_id": case_key,
            "source_type": source_type,
            "source_id": source_id,
            "target_id": str(entry.id),
        }
        for (case_key, source_type, source_id), entry in sorted(entry_by_source.items())
        if (case_key, source_type, source_id) not in source_keys
    ]
    mappings_without_target_identity = [
        {
            "case_id": _case(mapping.case_id),
            "source_type": mapping.source_type,
            "source_id": mapping.source_id,
            "target_id": mapping.target_id,
        }
        for mapping in sorted(
            mappings,
            key=lambda item: (_case(item.case_id), item.source_type, item.source_id),
        )
        if (_case(mapping.case_id), mapping.source_type, mapping.source_id)
        not in entry_by_source
    ]
    unresolved_links = [
        {
            "case_id": _case(link.case_id),
            "entry_id": str(link.entry_id),
            "link_id": str(link.id),
            "target_type": link.target_type,
            "target_id": link.target_id,
        }
        for link in link_query.all()
        if bool((link.link_metadata or {}).get("migration_unresolved"))
    ]
    unresolved_links.sort(
        key=lambda item: (
            item["case_id"],
            item["entry_id"],
            item["target_type"],
            item["target_id"],
        )
    )
    unrepointed_profile_links = [
        {
            "case_id": _case(link.case_id),
            "table": link.__tablename__,
            "link_id": str(link.id),
            "legacy_id": link.note_id,
        }
        for link in note_link_query.all()
        if link.workspace_entry_id is None
    ] + [
        {
            "case_id": _case(link.case_id),
            "table": link.__tablename__,
            "link_id": str(link.id),
            "legacy_id": link.finding_id,
        }
        for link in finding_link_query.all()
        if link.workspace_entry_id is None
    ]
    unrepointed_profile_links.sort(
        key=lambda item: (item["case_id"], item["table"], item["legacy_id"])
    )
    needs_review = [
        {
            "case_id": _case(entry.case_id),
            "entry_id": str(entry.id),
            "entry_type": entry.entry_type,
            "legacy_source": entry.legacy_source,
            "legacy_id": entry.legacy_id,
        }
        for entry in entries
        if entry.needs_migration_review
    ]
    needs_review.sort(
        key=lambda item: (
            item["case_id"],
            item["legacy_source"] or "",
            item["legacy_id"] or "",
        )
    )

    counts: dict[str, Any] = {}
    for source_type in SOURCE_MODELS:
        source_by_case = source_counts[source_type]
        target_by_case = Counter(
            _case(entry.case_id)
            for entry in entries
            if entry.legacy_source == source_type
        )
        mapped_by_case = Counter(
            _case(mapping.case_id)
            for mapping in mappings
            if mapping.source_type == source_type
        )
        counts[source_type] = {
            "source": sum(source_by_case.values()),
            "mapped": sum(mapped_by_case.values()),
            "target": sum(target_by_case.values()),
            "source_by_case": dict(sorted(source_by_case.items())),
            "mapped_by_case": dict(sorted(mapped_by_case.items())),
            "target_by_case": dict(sorted(target_by_case.items())),
        }

    report = {
        "schema_version": 1,
        "scope": {"case_id": str(case_id) if case_id else None},
        "counts": counts,
        "duplicate_sources": sorted(
            duplicate_sources,
            key=lambda item: (
                item["case_id"], item["source_type"], item["source_id"]
            ),
        ),
        "missing_mappings": missing_mappings,
        "missing_targets": missing_targets,
        "inconsistent_targets": inconsistent_targets,
        "mappings_without_target_identity": mappings_without_target_identity,
        "compatibility_only_entries": compatibility_only,
        "unresolved_links": unresolved_links,
        "unrepointed_profile_links": unrepointed_profile_links,
        "needs_migration_review": needs_review,
    }
    report["summary"] = {
        "source_records": len(source_keys),
        "canonical_entries": len(entries),
        "mappings": len(mappings),
        "compatibility_only_entries": len(compatibility_only),
        "duplicate_sources": len(report["duplicate_sources"]),
        "missing_mappings": len(missing_mappings),
        "missing_targets": len(missing_targets),
        "inconsistent_targets": len(inconsistent_targets),
        "mappings_without_target_identity": len(mappings_without_target_identity),
        "unresolved_links": len(unresolved_links),
        "unrepointed_profile_links": len(unrepointed_profile_links),
        "needs_migration_review": len(needs_review),
    }
    return report
